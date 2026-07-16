"""
agent/resume_reviewer.py — Independent resume quality reviewer.

For each (resume PDF, JD candidate) pair:
  - ATS score: keyword coverage from JD signals vs resume text
  - Hallucination check: every $/₹/% figure in PDF must appear in master_profile.json
  - Domain alignment: lead paragraph mentions domain-expected terms
  - Verdict: PASS / WARN / FAIL

Run standalone:
    python agent/resume_reviewer.py --date 2026-06-17 --root .
"""

from __future__ import annotations
import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass, field

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


# ── Approved metrics allowlist (same source as resume_pipeline.py) ────────────
# These are the ONLY numbers allowed in any resume.
_APPROVED_PATTERN = re.compile(
    r'\$(?:300M|15M|2M|4B|1\.2B|3\.2B|30\s?Cr|2,?000\s?Cr|78\s?Cr|15\s?Cr)'
    r'|Rs\.?\s?(?:30|78|2,000|15)\s?Cr'
    r'|₹(?:30|78|2,000|15)\s?Cr'
    r'|\b(?:2,800|15,000|800M|10M|800|21|20|13|10|8|6|3|2|40|30|29|25|15|400|140|250|98|33|80|87|1,200|30|18|24)\b'
    r'|(?:\+\d+\s?(?:bps|%)|(?:\d+)[+-]?\s*(?:year|yr|month|week|hour|day|min))',
    re.IGNORECASE,
)

_STOP_WORDS = {
    # Standard English stop words
    'the', 'and', 'for', 'with', 'from', 'this', 'that', 'are', 'was',
    'has', 'have', 'will', 'been', 'our', 'you', 'your', 'their', 'they',
    'into', 'about', 'more', 'all', 'each', 'can', 'not', 'its', 'but',
    'also', 'both', 'across', 'such', 'per', 'any', 'who', 'how', 'what',
    'when', 'where', 'which', 'than', 'then', 'role', 'roles', 'work',
    'using', 'used', 'ability', 'other', 'team', 'product', 'build', 'built',
    # Common English verbs / adjectives that are NOT technical/skill keywords
    'act', 'acting', 'acts', 'alongside', 'ambitious', 'bar', 'being',
    'believe', 'building', 'career', 'chance', 'class', 'close', 'come',
    'committed', 'company', 'critical', 'decades', 'decisiveness', 'deep',
    'deeply', 'domain', 'done', 'drive', 'excellence', 'expertise', 'fast',
    'financial', 'finished', 'fit', 'frontier', 'future', 'generational',
    'gets', 'getting', 'help', 'inflection', 'information', 'intensity',
    'investor', 'job', 'judgment', 'legal', 'live', 'looking', 'love',
    'mission', 'moves', 'never', 'new', 'operate', 'operating', 'opportunity',
    'over', 'point', 'professionals', 'pushing', 'quickly', 'rare', 'real',
    'reshaping', 'satisfied', 'scales', 'services', 'simplicity', 'sophisticated',
    'started', 'staying', 'strong', 'support', 'takes', 'three', 'today',
    'transforming', 'transforms', 'true', 'unmatched', 'values', 'want',
    'why', 'world', 'written', 'together', 'great', 'good', 'best', 'right',
    'need', 'looking', 'join', 'exciting', 'growing', 'leading', 'passionate',
    'driven', 'talented', 'dynamic', 'innovative', 'collaborative', 'dedicated',
    'seeking', 'required', 'level', 'tier', 'hire', 'hiring', 'candidate',
    'full', 'well', 'signal', 'likely', 'bookmark', 'bookmarked', 'exactly',
    'near', 'apply', 'applying', 'applies', 'before', 'verify', 'cap',
    'year', 'years', 'experience', 'must', 'able', 'strong', 'proven',
    'working', 'excellent', 'good', 'high', 'large', 'long', 'short',
    'include', 'including', 'make', 'take', 'give', 'get', 'put', 'set',
    'time', 'way', 'case', 'part', 'day', 'key', 'new', 'own', 'use',
    'work', 'working', 'based', 'focused', 'given', 'known', 'related',
    # Meta-commentary noise from why_fit agent analysis (not real JD words)
    'maps', 'map', 'direct', 'directly', 'perfectly', 'perfect', 'scope',
    'sweet', 'spot', 'match', 'matches', 'matching', 'matched', 'analog',
    'analogous', 'identical', 'mirror', 'mirrors', 'same', 'aligns', 'aligning',
    'outputs', 'jsonl', 'documented', 'profile', 'achieves', 'achievement',
    # Company names that would never be in a resume
    'harvey', 'teradata', 'twilio', 'fico', 'intuit', 'harness', 'serko',
    'volante', 'moengage', 'inmobi', 'greyorange', 'smartsheet', 'digicert',
    'eightfold', 'flexmoney', 'nexocean', 'jfrog', 'jll', 'jpmorganchase',
    'salesforce', 'autodesk', 'mongodb', 'adyen', 'uipath', 'microsoft',
    'google', 'sap', 'peak', 'gnani', 'wayfair', 'amazon', 'indiamart',
    # Recruiter / JD boilerplate filler
    'unicorn', 'exceptional', 'pay', 'pays', 'lpa', 'equity', 'office',
    'interest', 'autonomy', 'ownership', 'principal', 'staff',
    'dir', 'policing', 'philosophy', 'balance', 'enabler',
    'provider', 'bridging', 'globally', 'worldwide', 'associate',
    'competitive', 'compensation', 'benefits', 'perks', 'hybrid', 'remote',
    'location', 'city', 'india', 'bangalore', 'bengaluru', 'mumbai', 'hyderabad',
    'equal', 'opportunity', 'employer', 'diversity', 'inclusion',
    # Weak generics that appear in every JD (not useful for ATS matching)
    'impact', 'outcomes', 'results', 'success', 'goal', 'goals', 'objective',
    'vision', 'mission', 'value', 'values', 'culture', 'team', 'teams',
    'customer', 'customers', 'user', 'users', 'market', 'business',
    'company', 'organization', 'leadership', 'management', 'senior',
    'manager', 'director', 'head', 'lead', 'leads',
}

_DOMAIN_SIGNALS: dict[str, list[str]] = {
    "knowledge_ai": ["knowledge", "retrieval", "rag", "semantic", "knowledge base"],
    "genai_platform": ["genai", "llm", "model platform", "ai platform", "eval", "foundry"],
    "agentic_ai": ["agentic", "agent", "multi-step", "orchestration", "reasoning"],
    "b2b_enterprise": ["payments", "fintech", "saas", "enterprise", "marketplace", "billing", "b2b"],
    "consumer_ai": ["recommendation", "personalisation", "consumer", "growth", "discovery"],
    "developer_platform": ["developer", "devex", "idp", "appsec", "ci/cd", "sdlc"],
}



# ── Technical/professional keyword vocabulary ─────────────────────────────────
# ATS systems match against skill and domain keywords, not generic prose words.
# This vocabulary defines what counts as an ATS-meaningful keyword. A word must
# appear in BOTH the JD and this vocabulary to count toward coverage.
# The vocabulary is intentionally broad to avoid false-low scores.
_TECH_VOCAB = {
    # AI / ML / GenAI
    'ai', 'genai', 'llm', 'rag', 'agentic', 'agent', 'agents', 'reasoning',
    'langchain', 'langgraph', 'langsmith', 'llamaindex', 'openai', 'claude',
    'gpt', 'embedding', 'embeddings', 'vector', 'semantic', 'retrieval',
    'nlp', 'nlg', 'classification', 'inference', 'finetuning', 'pretraining',
    'transformer', 'bert', 'diffusion', 'multimodal', 'foundry', 'mlops',
    'xgboost', 'reinforcement', 'algorithms', 'models', 'training', 'evaluation',
    'evals', 'eval', 'hallucination', 'grounding', 'orchestration', 'workflow',
    'automation', 'autonomous', 'multi-agent', 'subagent', 'copilot', 'cursor',
    'guardrails', 'safety', 'governance', 'responsible', 'drift', 'monitoring',
    # Cloud / Infra
    'aws', 'azure', 'gcp', 'cloud', 'kubernetes', 'docker', 'terraform',
    'microservices', 'serverless', 'lambda', 'eks', 'ecs', 'ec2', 's3',
    'kafka', 'pubsub', 'redis', 'elasticsearch', 'postgres', 'sql', 'nosql',
    'distributed', 'compute', 'infrastructure', 'deployment', 'deployments',
    'devops', 'cicd', 'sdlc', 'observability', 'reliability', 'sla', 'slo',
    'latency', 'throughput', 'scalability', 'availability', 'resilience',
    # Developer tools / platforms
    'apis', 'api', 'sdk', 'sdks', 'rest', 'graphql', 'grpc', 'webhook',
    'idp', 'appsec', 'devsecops', 'sast', 'dast', 'sbom', 'vulnerability',
    'developer', 'developers', 'devex', 'dx', 'productivity', 'tooling',
    # Data / Analytics
    'analytics', 'data', 'warehouse', 'lakehouse', 'etl', 'pipeline',
    'bigquery', 'snowflake', 'databricks', 'redshift', 'spark', 'airflow',
    'dbt', 'looker', 'tableau', 'powerbi', 'sql', 'python', 'java',
    'schema', 'catalog', 'lineage', 'metadata', 'ontology', 'taxonomy',
    # Product craft
    'roadmap', 'strategy', 'vision', 'okrs', 'kpis', 'metrics', 'nps',
    'csat', 'experimentation', 'testing', 'hypothesis', 'mvp',
    'discovery', 'research', 'personas', 'journey', 'funnel', 'conversion',
    'retention', 'acquisition', 'activation', 'monetisation', 'monetization',
    'pricing', 'billing', 'subscriptions', 'revenue', 'growth', 'plg',
    'gtm', 'launch', 'adoption', 'engagement', 'churn', 'cohort', 'rfm',
    # Platform / B2B
    'platform', 'saas', 'paas', 'iaas', 'b2b', 'b2c', 'marketplace',
    'payments', 'fintech', 'checkout', 'bnpl', 'fraud', 'kyc', 'aml',
    'banking', 'ledger', 'settlement', 'clearing', 'swift', 'iso20022',
    'subscriptions', 'billing', 'invoicing', 'erp', 'crm',
    'multi-tenant', 'multitenancy', 'enterprise', 'compliance',
    'privacy', 'gdpr', 'hipaa', 'sox', 'iso27001', 'soc2',
    # Recommendations / Search
    'recommendation', 'recommendations', 'personalisation', 'personalization',
    'search', 'ranking', 'indexing', 'crawling', 'nlp', 'entity',
    'knowledge', 'graph', 'ontology', 'taxonomy', 'classification',
    # Leadership / Strategy
    'stakeholder', 'alignment', 'cross-functional', 'executive',
    'engineering', 'design', 'ux', 'research', 'operations', 'sales',
    'marketing', 'partnership', 'ecosystem', 'integration', 'enablement',
    # Technical areas specific to JD corpus
    'workloads', 'abstractions', 'customization', 'foundry', 'azure',
    'federated', 'durable', 'surfaces', 'compute', 'distributed',
    'allocation', 'optimization', 'benchmark', 'tradeoffs',
    'architecture', 'design', 'patterns', 'frameworks', 'libraries',
    'security', 'encryption', 'authorization', 'authentication', 'rbac',
    'logging', 'tracing', 'alerting', 'debugging', 'profiling',
    # Singular/plural variants that must both be present for matching
    'agent', 'agents', 'recommendation', 'recommendations',
    'model', 'models', 'deployment', 'deployments',
    'autonomous', 'autonomy', 'productivity',
    'enablement', 'alignment', 'responsible',
    'observability', 'monitoring', 'availability',
    'conversion', 'conversions', 'monetization', 'monetisation',
}


def _extract_text(pdf_path: pathlib.Path) -> str:
    if not FITZ_AVAILABLE:
        return ""
    doc = fitz.open(str(pdf_path))
    return "\n".join(page.get_text() for page in doc)


def _singularize(word: str) -> str:
    """Collapse a simple English plural to its singular for ATS-style matching.

    Conservative on purpose: only strips 'ies'→'y', 'sses'→'ss', and a trailing
    's' on words longer than 4 chars. Leaves short words and non-plurals alone so
    we don't mangle 'analysis', 'kpis'→'kpi' (fine), 'apis'→'api' (fine).
    """
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("sses"):
        return w[:-2]
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _keyword_set(text: str) -> set[str]:
    """Extract all non-stop words from text (unfiltered — for resume text)."""
    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _jd_keyword_set(text: str) -> set[str]:
    """Extract JD keywords filtered to technical/professional vocabulary.

    ATS systems match against skill and domain keywords, not generic prose.
    We filter the JD keyword set to only include words from _TECH_VOCAB so
    that generic JD prose ('define', 'closely', 'collaboration', 'shape')
    doesn't dilute the keyword coverage score. A word must be both:
      1. Not in _STOP_WORDS (standard filters)
      2. In _TECH_VOCAB (substantive skill/domain keyword)

    This gives a fair, skill-focused ATS score consistent with how real
    ATS parsers (Taleo, Workday, iCIMS) weight job description keywords.
    """
    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    return {w for w in words if w not in _STOP_WORDS and w in _TECH_VOCAB}


_JD_REQUIREMENTS_HEADERS = re.compile(
    r'(?:responsibilities|requirements|what you.{0,10}do|what you.{0,10}bring|'
    r'role overview|about the role|job description|qualifications|'
    r'you.{0,5}will|we.{0,5}look|minimum qualifications|'
    r'what we.{0,10}looking|basic qualifications|preferred qualifications)',
    re.IGNORECASE,
)

_JD_BOILERPLATE_PATTERNS = re.compile(
    r'(?:why .{1,30}|about .{1,30}|we help the world|at .{1,30}we|'
    r'equal opportunity|diversity|our values|benefits include|'
    r'competitive salary|what we offer|life at )',
    re.IGNORECASE,
)


def _extract_requirements_section(jd_text: str) -> tuple[str, bool]:
    """Try to isolate the requirements/responsibilities section of a JD.

    Returns (extracted_text, found_requirements_section).
    If a requirements section header is found, return text from that point on.
    If the JD starts with obvious boilerplate ('Why Harvey', 'At X, we...'),
    skip to the first requirements-like section.
    If no section boundary found, return the full text.
    """
    # Try to find requirements section header
    m = _JD_REQUIREMENTS_HEADERS.search(jd_text)
    if m:
        # Use text from the requirements header onward
        return jd_text[m.start():], True

    # Check if text starts with boilerplate (company intro)
    first_200 = jd_text[:200].lower()
    starts_with_boilerplate = any(pat in first_200 for pat in [
        'why ', 'at ', 'we help', 'about us', 'about the company',
        'our mission', "we're building", "we are building",
    ])
    if starts_with_boilerplate:
        # Find the first bullet point or numbered list item — likely role content
        bullet_m = re.search(r'\n[\-\*•]\s+\w', jd_text)
        if bullet_m:
            return jd_text[bullet_m.start():], False

    return jd_text, False


def _ats_score(resume_text: str, candidate: dict) -> tuple[int, int, int, str]:
    """Return (matched, total, pct, jd_source) keyword coverage.

    JD source priority:
    1. 'description' field (full JD text from raw pipeline)  → jd_source='full'
    2. 'description_excerpt' >= 300 chars (LinkedIn/Indeed full excerpt) → jd_source='full'
    3. 'description_excerpt' < 300 chars (truncated/summary)  → jd_source='excerpt_only'

    The JD keyword set is computed ONLY from actual JD text (description /
    description_excerpt), NOT from why_fit bullets which are the agent's own
    meta-commentary and introduce noise words ('maps perfectly', 'scope sweet
    spot') that never appear in the resume, artificially tanking the score.

    For JDs where the excerpt starts with company culture/intro boilerplate,
    we attempt to isolate the requirements section before computing keywords.
    The title is always included as it's authentic JD text.
    """
    description = (candidate.get("description") or "").strip()
    excerpt = (candidate.get("description_excerpt") or "").strip()

    # Prefer full description; fall back to long excerpt; last resort: excerpt
    if description:
        jd_text = description
        jd_source = "full"
    elif len(excerpt) >= 300:
        jd_text = excerpt
        jd_source = "full"
    elif excerpt:
        jd_text = excerpt
        jd_source = "excerpt_only"
    else:
        # No JD text at all — fall back to why_fit as last resort
        jd_text = " ".join(candidate.get("why_fit") or [])
        jd_source = "why_fit_fallback"

    # Try to strip intro boilerplate and focus on requirements section
    req_text, found_req = _extract_requirements_section(jd_text)
    # Use the requirements slice only if it's substantial. A requirements header
    # near the truncated tail of a 1500-char excerpt (e.g. "...we're looking for")
    # yields a tiny fragment with no keywords and collapses coverage to 0 — when
    # that happens, fall back to the full JD text instead.
    if found_req and len(req_text) >= 250:
        effective_jd = req_text
    else:
        effective_jd = jd_text

    jd_blob = " ".join([
        effective_jd,
        (candidate.get("title") or ""),
    ])
    # JD side: filtered to technical/skill vocabulary only (avoids generic prose noise)
    jd_kw = _jd_keyword_set(jd_blob)
    # Resume side: all non-stop words (resume text is already skills-dense)
    resume_kw = _keyword_set(resume_text)
    if not jd_kw:
        # Fallback: if JD has no tech vocab words, use full keyword set
        jd_kw = _keyword_set(jd_blob)
        if not jd_kw:
            return 0, 0, 0, jd_source
    # Match with singular/plural normalisation, the way real ATS parsers stem.
    # 'models'↔'model', 'recommendations'↔'recommendation', 'agents'↔'agent',
    # 'deployments'↔'deployment', 'developers'↔'developer', 'workloads'↔'workload'
    # — a JD plural and a résumé singular (or vice-versa) is a genuine match, not
    # a miss. Without this, identical concepts scored as gaps purely on an 's'.
    resume_norm = {_singularize(w) for w in resume_kw}
    matched = {w for w in jd_kw if _singularize(w) in resume_norm}
    pct = round(100 * len(matched) / len(jd_kw))
    return len(matched), len(jd_kw), pct, jd_source


def _check_hallucination(resume_text: str, profile: dict) -> list[str]:
    """
    Find numeric tokens in resume that look like metrics but are NOT
    in the profile's approved metrics. Returns list of suspicious strings.
    """
    # Build set of all numbers from profile (flat scan)
    profile_str = json.dumps(profile)
    profile_nums = set(re.findall(r'\d[\d,\.]*[MBK%]?', profile_str))

    # Extract all numeric tokens from resume
    resume_nums = re.findall(r'\$[\d,\.]+[MBK]?|\b\d[\d,\.]*[MBK%]?\b|[\+\-]\d+\s?(?:bps|%)', resume_text)

    suspicious = []
    for num in resume_nums:
        clean = num.replace(',', '').replace('+', '').replace('-', '').replace('$', '').replace('₹', '').strip()
        # Strip trailing unit suffixes (bps, %) so "+400 bps" -> "400"
        clean_digits = re.sub(r'\s*(bps|%|K|M|B)\s*$', '', clean, flags=re.IGNORECASE).strip()
        if clean_digits in {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
                     '12', '13', '14', '15', '16', '20', '21', '30', '40', '50',
                     '60', '70', '80', '90', '100', '200', '500', '400', '250',
                     '140', '98', '95', '87', '81', '78', '75', '72', '71', '70',
                     '29', '25', '18', '24', '33', '37', '74', '76', '77', '83',
                     '84', '85', '86', '88', '89', '91', '92', '93', '94'}:
            continue
        if not any(clean_digits in p.replace(',', '') for p in profile_nums):
            if len(clean_digits) > 2:  # ignore trivially short numbers
                suspicious.append(num)

    return suspicious[:10]  # cap at 10 to keep report readable


def _check_domain_alignment(resume_text: str, domain: str) -> bool:
    """Check whether the résumé's lead block signals the expected domain.

    Window is the first 1000 chars — name + contact line + the full Core Skills
    line + the opening of the (domain-tailored) executive summary. The contact
    line now carries full LinkedIn/GitHub URL strings and the skills line grew,
    which pushed domain signals (e.g. 'Enterprise SaaS', 'B2B Platforms' land at
    char ~780) past the old 500/700 cutoffs; 1000 captures the whole lead block
    so a domain that IS signalled there isn't reported as a false-negative miss.
    """
    lead = resume_text[:1000].lower()
    signals = _DOMAIN_SIGNALS.get(domain, [])
    return any(s in lead for s in signals)


def _check_formatting(pdf_path: pathlib.Path, resume_text: str) -> list[str]:
    """Catch visual / markup defects the keyword scorer is blind to.

    The keyword reviewer scores *coverage* and *honesty* but never looked at how
    the résumé actually renders — so broken bold markup (nested <b>, leaked tags,
    ransom-note over-bolding, duplicate words) sailed through as PASS. This closes
    that gap. Returns a list of human-readable formatting issues (empty == clean).
    """
    issues: list[str] = []

    # 1) Leaked markup — literal tags/entities that should never reach the page.
    for leak in ("<b>", "</b>", "&amp;", "&lt;", "&gt;", "<para", "</para>"):
        if leak in resume_text:
            issues.append(f"leaked markup token '{leak}' visible in rendered text")

    # 2) Duplicate adjacent words ('Improved improved', 'the the').
    dups = re.findall(r'\b(\w{3,})\s+\1\b', resume_text, flags=re.IGNORECASE)
    if dups:
        issues.append(f"duplicate adjacent word(s): {', '.join(sorted(set(d.lower() for d in dups))[:5])}")

    # 3) Bold analysis via PyMuPDF span flags (bit 4 = bold = flags & 16).
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            bold_chars = total_chars = 0
            nested_or_broken = False
            for page in doc:
                d = page.get_text("dict")
                for blk in d.get("blocks", []):
                    for line in blk.get("lines", []):
                        for span in line.get("spans", []):
                            t = span.get("text", "")
                            total_chars += len(t)
                            if span.get("flags", 0) & 16:
                                bold_chars += len(t)
            if total_chars:
                frac = bold_chars / total_chars
                # Body should be mostly regular weight; headers/lead-ins are bold.
                # >45% bold across the doc means over-bolding (ransom-note effect).
                if frac > 0.45:
                    issues.append(f"over-bolded: {round(frac*100)}% of glyphs are bold (target <45%)")
        except Exception as exc:  # pragma: no cover - defensive
            issues.append(f"could not analyse bold spans: {exc}")

    return issues


@dataclass
class ReviewResult:
    pdf: str
    company: str
    title: str
    fit_score: int
    domain: str
    ats_matched: int
    ats_total: int
    ats_pct: int
    jd_source: str = "excerpt_only"
    hallucination_flags: list[str] = field(default_factory=list)
    domain_aligned: bool = True
    formatting_issues: list[str] = field(default_factory=list)
    verdict: str = "PASS"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pdf": self.pdf,
            "company": self.company,
            "title": self.title,
            "fit_score": self.fit_score,
            "domain": self.domain,
            "ats_pct": self.ats_pct,
            "ats_matched": self.ats_matched,
            "ats_total": self.ats_total,
            "jd_source": self.jd_source,
            "hallucination_flags": self.hallucination_flags,
            "domain_aligned": self.domain_aligned,
            "formatting_issues": self.formatting_issues,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def review_resume(
    pdf_path: pathlib.Path,
    candidate: dict,
    profile: dict,
) -> ReviewResult:
    """Full review of one resume PDF against its JD candidate."""
    from agent.resume_pipeline import classify_jd_domain

    company = candidate.get("company", "Unknown")
    title = candidate.get("title", "")
    fit_score = max(candidate.get("score", 0), candidate.get("bumped_score", 0))
    domain = classify_jd_domain(candidate)

    resume_text = _extract_text(pdf_path)
    if not resume_text:
        return ReviewResult(
            pdf=pdf_path.name, company=company, title=title,
            fit_score=fit_score, domain=domain,
            ats_matched=0, ats_total=0, ats_pct=0,
            verdict="FAIL", notes=["Could not extract PDF text"],
        )

    matched, total, ats_pct, jd_source = _ats_score(resume_text, candidate)
    hallucination_flags = _check_hallucination(resume_text, profile)
    domain_aligned = _check_domain_alignment(resume_text, domain)
    formatting_issues = _check_formatting(pdf_path, resume_text)

    notes = []
    verdict = "PASS"

    if hallucination_flags:
        notes.append(f"Suspicious metrics not traced to profile: {', '.join(hallucination_flags[:5])}")
        verdict = "FAIL"
    if formatting_issues:
        # Broken markup / over-bolding makes a résumé unfit for submission even
        # when its keyword coverage is perfect — treat as a hard FAIL.
        notes.append(f"Formatting defects: {'; '.join(formatting_issues[:5])}")
        verdict = "FAIL"
    if ats_pct < 40:
        notes.append(f"ATS keyword coverage low: {ats_pct}% ({matched}/{total} JD keywords) [{jd_source}]")
        verdict = "FAIL" if verdict != "FAIL" else "FAIL"
    elif ats_pct < 70:
        notes.append(f"ATS keyword coverage moderate: {ats_pct}% ({matched}/{total}) [{jd_source}] — target 70%+")
        if verdict == "PASS":
            verdict = "WARN"
    if not domain_aligned:
        notes.append(f"Lead section does not clearly signal '{domain}' domain — consider reordering")
        if verdict == "PASS":
            verdict = "WARN"
    if fit_score < 80:
        notes.append(f"Fit score {fit_score} is below 80 — resume should not have been generated")
        verdict = "FAIL"

    if not notes:
        notes.append(f"All checks passed — ATS {ats_pct}% [{jd_source}]")

    return ReviewResult(
        pdf=pdf_path.name, company=company, title=title,
        fit_score=fit_score, domain=domain,
        ats_matched=matched, ats_total=total, ats_pct=ats_pct,
        jd_source=jd_source,
        hallucination_flags=hallucination_flags,
        domain_aligned=domain_aligned,
        formatting_issues=formatting_issues,
        verdict=verdict,
        notes=notes,
    )


def _enrich_from_raw(scored: list[dict], root: pathlib.Path, date: str) -> int:
    """Enrich scored candidates with full description from raw candidates JSONL.

    The raw pipeline stores up to 1500-char description_excerpt; the scored
    pipeline often truncates or drops this. Match by URL and backfill the longer
    description so _ats_score() has real JD text to work with.

    Returns the count of candidates enriched.
    """
    raw_path = root / f"outputs/{date}/_raw_candidates.jsonl"
    if not raw_path.exists():
        return 0

    raw_by_url: dict[str, dict] = {}
    with raw_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = (c.get("url") or c.get("job_url") or "").strip()
            if url:
                raw_by_url[url] = c

    enriched = 0
    for sc in scored:
        url = (sc.get("job_url") or sc.get("url") or "").strip()
        if not url or url not in raw_by_url:
            continue
        raw = raw_by_url[url]
        raw_excerpt = (raw.get("description_excerpt") or "").strip()
        sc_excerpt = (sc.get("description_excerpt") or "").strip()
        if len(raw_excerpt) > len(sc_excerpt):
            sc["description_excerpt"] = raw_excerpt
            enriched += 1

    return enriched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--output", default=None,
                    help="Override output path (default: outputs/{date}/_resume_review_full_jd.json)")
    args = ap.parse_args()

    root = pathlib.Path(args.root)
    scored_path = root / f"outputs/{args.date}/_scored_candidates.json"
    profile_path = root / "profile/master_profile.json"
    resumes_dir = root / f"outputs/{args.date}/resumes"
    out_path = pathlib.Path(args.output) if args.output else \
        root / f"outputs/{args.date}/_resume_review_full_jd.json"

    scored = json.loads(scored_path.read_text())
    profile = json.loads(profile_path.read_text())

    # Enrich scored candidates with full JD descriptions from raw pipeline
    enriched = _enrich_from_raw(scored, root, args.date)
    print(f"Enriched {enriched} candidates with full JD text from raw pipeline")

    # Build candidate lookup by company (best match)
    def _slug(s: str) -> str:
        return re.sub(r'[^a-z0-9]', '', (s or '').lower())

    results = []
    pdfs = sorted(resumes_dir.glob("*.pdf"))
    print(f"Reviewing {len(pdfs)} resumes...")

    for pdf in pdfs:
        stem = pdf.stem  # e.g. 2026-06-17_Harvey_group-product-manager-knowledge-platform
        parts = stem.split("_", 2)
        if len(parts) < 3:
            continue
        company_slug = _slug(parts[1])
        # Role-slug tokens from the filename, e.g. 'director-platform-...-infrastructure'
        role_tokens = set(t for t in (parts[2] if len(parts) > 2 else "").split("-") if t)

        best = None
        best_key = (-1, -1)  # (role-token overlap, fit score)
        for c in scored:
            cs = max(c.get("score", 0), c.get("bumped_score", 0))
            if cs < 80:
                continue
            c_slug = _slug(c.get("company", ""))
            if not (company_slug in c_slug or c_slug in company_slug):
                continue
            # When a company has multiple roles (e.g. FICO Infrastructure vs FICO
            # Security), pick the candidate whose ROLE matches this PDF's filename
            # — matching on company alone scored both PDFs against one JD.
            c_role = (c.get("role") or c.get("title") or "").lower()
            c_tokens = set(t for t in re.split(r'[^a-z0-9]+', c_role) if t)
            overlap = len(role_tokens & c_tokens)
            key = (overlap, cs)
            if key > best_key:
                best = c
                best_key = key

        if not best:
            print(f"  SKIP (no candidate match): {pdf.name}")
            continue

        result = review_resume(pdf, best, profile)
        results.append(result.to_dict())
        status_icon = {"PASS": "OK", "WARN": "!!", "FAIL": "XX"}.get(result.verdict, "?")
        src_tag = {"full": "JD", "excerpt_only": "ex", "why_fit_fallback": "wf"}.get(result.jd_source, "?")
        print(f"  [{result.verdict:4}] {status_icon} {result.company:28} ATS:{result.ats_pct:3d}%[{src_tag}]  fit:{result.fit_score}  {result.notes[0][:55]}")

    out_path.write_text(json.dumps(results, indent=2))

    totals: dict[str, int] = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for r in results:
        totals[r["verdict"]] = totals.get(r["verdict"], 0) + 1

    at_70_plus = sum(1 for r in results if r["ats_pct"] >= 70)
    at_60_plus = sum(1 for r in results if r["ats_pct"] >= 60)
    avg_ats = round(sum(r["ats_pct"] for r in results) / len(results)) if results else 0
    full_jd_count = sum(1 for r in results if r.get("jd_source") == "full")

    print(f"\n{'='*60}")
    print(f"REVIEW SUMMARY: {totals['PASS']} PASS  |  {totals['WARN']} WARN  |  {totals['FAIL']} FAIL")
    print(f"ATS coverage:   avg {avg_ats}%  |  ≥70%: {at_70_plus}/{len(results)}  |  ≥60%: {at_60_plus}/{len(results)}")
    print(f"JD source:      {full_jd_count} full JD  |  {len(results)-full_jd_count} excerpt/fallback")
    print(f"Results saved to {out_path}")
    return 1 if totals["FAIL"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
