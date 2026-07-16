"""ATS readiness report — honest parseability + keyword coverage analysis.

This is NOT a fake "ATS pass score." It produces two honest signals:
  1. Parseability: deterministic checks the PDF can pass cleanly through
     Greenhouse/Lever/Workday parsers.
  2. Keyword coverage: ratio of JD-extracted keywords found in the resume.

Together these give a realistic pass-likelihood estimate per ATS family.

Filenames are date-stamped (run date as prefix) so artifacts remain
identifiable outside the parent folder. See CLAUDE.md Step 5d "Output filename".

Usage:
    python agent/ats_report.py \
        --resume outputs/2026-05-02/resumes/2026-05-02_Airbnb_principal-pm-ai.pdf \
        --jd /tmp/jd_airbnb_principal-pm-ai.txt \
        --output outputs/2026-05-02/ats_reports/2026-05-02_Airbnb_principal-pm-ai_ats.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# pypdf is the standard text extractor; pip install pypdf in Routine env.
try:
    from pypdf import PdfReader
except ImportError:
    sys.stderr.write("ERROR: pypdf not installed. Run: pip install pypdf\n")
    sys.exit(2)


# ---------- Parseability checks ----------

STANDARD_HEADERS = [
    "experience", "work experience", "professional experience",
    "education", "skills", "summary",
]

DATE_PATTERNS = [
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}\b",
    r"\b\d{1,2}/\d{4}\b",
    r"\b\d{4}\s*[-–]\s*(present|\d{4})\b",
]


def check_parseability(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    full_text = "\n".join((p.extract_text() or "") for p in reader.pages)

    checks = {}

    # 1. Text actually extracts (i.e. not a scanned image)
    checks["text_extractable"] = bool(full_text.strip())
    checks["text_length_chars"] = len(full_text)

    # 2. Standard headers present
    text_lower = full_text.lower()
    found_headers = [h for h in STANDARD_HEADERS if h in text_lower]
    checks["standard_headers_found"] = found_headers
    checks["standard_headers_pass"] = len(found_headers) >= 3

    # 3. Machine-readable dates
    date_hits = sum(len(re.findall(p, text_lower)) for p in DATE_PATTERNS)
    checks["date_pattern_count"] = date_hits
    checks["dates_pass"] = date_hits >= 4  # at least 4 role-date markers

    # 4. Embedded fonts (heuristic via metadata)
    has_metadata = bool(reader.metadata)
    checks["has_metadata"] = has_metadata

    # 5. Page count reasonable
    checks["pages"] = n_pages
    checks["pages_pass"] = 1 <= n_pages <= 3

    # 6. File size signal (embedded fonts ~ 40KB+, unembedded ~ 8-12KB)
    size_kb = pdf_path.stat().st_size / 1024
    checks["size_kb"] = round(size_kb, 1)
    checks["size_indicates_embedded_fonts"] = size_kb >= 30

    # Score
    pass_count = sum(1 for k, v in checks.items()
                     if k.endswith("_pass") and v)
    total_pass = sum(1 for k in checks if k.endswith("_pass"))
    score = round(pass_count / max(total_pass, 1) * 100)

    return {
        "score": score,
        "checks": checks,
        "extracted_text_for_kw_check": full_text,
    }


# ---------- Keyword coverage ----------

# Filler words to exclude from JD keyword extraction
STOPWORDS = set("""
a an and as at be by for from has have he her him his how i in into is it its
just may might must of on or our she so such than that the their them these
they this those to was we were what when where which who whom why will with
would you your yours yourself ourselves over under more less than then etc
about above after again all am any been before being below between both but
can did do does doing during each few further had having here if no nor not
now once only other own same should shouldn some still through very were
will would year years experience role responsibilities requirements role
position senior manager director principal product team work working ability
strong excellent proven track record drive deliver own lead build develop
collaborate cross functional stakeholders ideal candidate bachelor degree
masters mba degree opportunity company we re looking seeking growth scale
""".split())

CRITICAL_TERMS = {
    "ai/ml", "ml", "ai", "llm", "rag", "genai", "agentic", "agents",
    "platform", "saas", "b2b", "fintech", "marketplace", "personalization",
    "recommendation", "recommendations", "search", "ranking",
    "aws", "gcp", "kubernetes", "microservices", "kafka", "rest",
    "metrics", "kpis", "dora", "ab testing", "experimentation",
    "leadership", "people management", "mentorship", "coaching",
    "roadmap", "strategy", "vision", "okr", "okrs",
    "developer productivity", "developer experience", "internal tools",
}


def extract_keywords(text: str, top_n: int = 40) -> list[str]:
    """Naive keyword extraction — bigrams and unigrams by frequency."""
    text = text.lower()
    # Tokenize on word boundaries
    tokens = re.findall(r"[a-z][a-z0-9+/.\-]{1,}", text)
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]

    # Count unigrams + bigrams
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    for a, b in zip(tokens, tokens[1:]):
        bg = f"{a} {b}"
        if a in STOPWORDS or b in STOPWORDS:
            continue
        counts[bg] = counts.get(bg, 0) + 1

    # Boost critical terms
    for ct in CRITICAL_TERMS:
        if ct in counts:
            counts[ct] *= 3

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [k for k, _ in ranked[:top_n]]


def keyword_coverage(jd_text: str, resume_text: str) -> dict:
    jd_keywords = extract_keywords(jd_text, top_n=30)
    resume_lower = resume_text.lower()

    matched: list[str] = []
    missing: list[str] = []
    for kw in jd_keywords:
        if kw in resume_lower:
            matched.append(kw)
        else:
            missing.append(kw)

    # Critical missing — these are high-priority gaps
    missing_critical = [m for m in missing if m in CRITICAL_TERMS or
                        any(t in m for t in CRITICAL_TERMS)]

    score = round(len(matched) / max(len(jd_keywords), 1) * 100)
    return {
        "score": score,
        "jd_keywords_total": len(jd_keywords),
        "matched_count": len(matched),
        "matched": matched,
        "missing": missing,
        "missing_critical": missing_critical[:10],
        "missing_nice_to_have": [m for m in missing
                                 if m not in missing_critical][:10],
    }


# ---------- Pass-likelihood estimate ----------

def estimate_pass_likelihood(parseability_score: int,
                             keyword_score: int) -> dict:
    """Rough heuristic per ATS family. Conservative — undersell rather than oversell."""
    # Parseability dominates — if text doesn't extract, ATS can't read it
    base = parseability_score * 0.6 + keyword_score * 0.4
    return {
        "greenhouse": _bucket(base + 5),  # Greenhouse is forgiving
        "lever": _bucket(base + 3),
        "ashby": _bucket(base + 5),
        "workday": _bucket(base - 5),     # Workday is strictest
    }


def _bucket(score: float) -> str:
    if score >= 90: return f"Very High ({round(score)})"
    if score >= 75: return f"High ({round(score)})"
    if score >= 60: return f"Medium ({round(score)})"
    return f"Low ({round(score)})"


# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", required=True, type=Path)
    ap.add_argument("--jd", required=True, type=Path,
                    help="Plain text JD file")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    if not args.resume.exists():
        print(f"ERROR: resume not found: {args.resume}", file=sys.stderr)
        return 1
    if not args.jd.exists():
        print(f"ERROR: JD not found: {args.jd}", file=sys.stderr)
        return 1

    parse_result = check_parseability(args.resume)
    resume_text = parse_result.pop("extracted_text_for_kw_check")
    jd_text = args.jd.read_text(encoding="utf-8")
    kw_result = keyword_coverage(jd_text, resume_text)
    likelihood = estimate_pass_likelihood(parse_result["score"],
                                           kw_result["score"])

    report = {
        "resume": str(args.resume),
        "jd": str(args.jd),
        "parseability": parse_result,
        "keyword_coverage": kw_result,
        "pass_likelihood_by_ats": likelihood,
        "summary": (
            f"Parseability {parse_result['score']}/100 + "
            f"Keyword coverage {kw_result['score']}/100. "
            f"Top missing critical: "
            f"{', '.join(kw_result['missing_critical'][:3]) or 'none'}"
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(report["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
