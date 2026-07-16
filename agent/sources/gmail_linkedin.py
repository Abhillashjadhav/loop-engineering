"""Gmail job-alert source — LinkedIn + Naukri (Hirist not present in user's inbox).

LinkedIn doesn't expose a public jobs API and direct scraping is blocked from
the Routine datacenter IP, but the user's Gmail receives daily LinkedIn alert
digests at `jobalerts-noreply@linkedin.com` (and occasionally
`jobs-listings@linkedin.com`). Naukri alerts arrive at
`naukrialerts@naukri.com`. Both are quality-filtered (the user configured the
alerts in-product), so this is a clean candidate signal — same priority as a
direct Indeed query.

Architecture: Gmail MCP is an agent-side tool, not callable from Python. The
agent fetches threads via `Gmail.search_threads` / `get_thread` and dumps the
raw response JSON to `outputs/{date}/_gmail_threads/{linkedin,naukri}.json`
before invoking `fetch_all.py`. This module is parser-only — it reads those
JSON files and emits Job dicts matching `agent/sources/greenhouse.py:Job`.

Output sources (per CLAUDE.md Step 1e):
  - `gmail_linkedin` — alerts from LinkedIn
  - `gmail_naukri`   — alerts from Naukri

Usage (programmatic):
    from agent.sources.gmail_linkedin import fetch_jobs
    jobs = fetch_jobs(date="2026-05-03", root=".")
"""
from __future__ import annotations

import html.parser
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


LINKEDIN_SENDERS = (
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
)
NAUKRI_SENDERS = (
    "naukrialerts@naukri.com",
)

# Recommended Gmail MCP queries the agent should use in Step 1e. Both filter
# variants are listed: the label-based one (preferred, set up via Gmail
# filter rules) and the raw `from:` fallback for runs before the user has
# applied filters yet.
LINKEDIN_QUERY_LABEL = "label:JobAlerts/LinkedIn newer_than:2d"
LINKEDIN_QUERY_FROM = (
    "from:jobalerts-noreply@linkedin.com OR "
    "from:jobs-listings@linkedin.com newer_than:2d"
)
NAUKRI_QUERY_LABEL = "label:JobAlerts/Naukri newer_than:2d"
NAUKRI_QUERY_FROM = "from:naukrialerts@naukri.com newer_than:2d"

# Lines in digest bodies that are navigation / footer noise — skip them.
# Checked before the " · " company-location split so they don't become
# false positives.
_DIGEST_JUNK_FRAGMENTS = (
    "©",
    "linkedin corporation",
    "manage alerts",
    "unsubscribe",
    "see all jobs",
    "edit alert",
    "install linkedin",
    "add widget",
    "easy apply",
    "actively recruiting",
    "connections",
    "fast growing",
    "new jobs from",
)

# Max roles extracted from a single digest email body.
_DIGEST_MAX_ROLES = 20


@dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: str | None
    raw_id: str | None
    department: str | None = None
    description_excerpt: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---- Subject-line parsers --------------------------------------------------

# LinkedIn alerts use two recurring subject formats:
#   1. "{Title} at {Company}"
#      e.g. "Principal Group Product Manager at Microsoft"
#   2. "\"{search_query}\": {Company} - {Title} ( {Location} ) posted on {date}"
#      e.g. '"product management": Smartsheet - Principal Product Manager,
#             Data & AI Platforms ( Hybrid in Bangalore ) posted on 4/30/26'
LINKEDIN_QUOTED_RE = re.compile(
    r'^\s*[“”"]?[^“”"\']*[“”"]?\s*:\s*'  # "search":
    r'(?P<company>[^\-]+?)\s+-\s+'                                       # Company -
    r'(?P<title>.+?)'                                                    # Title
    r'(?:\s*\(\s*(?P<location>[^)]+?)\s*\))?'                           # ( Location )
    r'(?:\s*posted\s+on\s+(?P<posted_at>[\d/.\-]+))?'                   # posted on date
    r'\s*$',
    re.IGNORECASE,
)
LINKEDIN_AT_RE = re.compile(
    r"^(?P<title>.+?)\s+at\s+(?P<company>[^|]+?)\s*$",
    re.IGNORECASE,
)

# Naukri alert subject:
#   "New job - {Title} | More jobs matching your Custom Job Alert - {alert_name}"
NAUKRI_SUBJECT_RE = re.compile(
    r"^new\s+job\s*[-:]\s*(?P<title>.+?)\s*(?:\||$)",
    re.IGNORECASE,
)

# Naukri snippets pack the title twice in a row before the company:
#   `... matching your job alert {AlertName} {Title} {Title} {Company}
#    (Hybrid|Remote|On-site|Work from Home) - {Location}, ...`
# We use the title from the subject to anchor the rfind, then take the
# words between the last title occurrence and the work-mode keyword as
# the company. NAUKRI_WORKMODE_RE is the right boundary marker.
NAUKRI_WORKMODE_RE = re.compile(
    r"\b(?:Hybrid|Remote|On[-\s]?site|Work\s+from\s+Home)\s*[-–:]\s*"
    r"(?P<location>[A-Za-z][A-Za-z, ]+)",
    re.IGNORECASE,
)

# Digest subject patterns — any of these signals a multi-role digest body
# that needs `parse_linkedin_body()` instead of subject-line extraction.
_DIGEST_SUBJECT_RE = re.compile(
    r"view jobs|new jobs?(?!\s+at\b)|jobs? match your alert|\d+\s+new jobs?",
    re.IGNORECASE,
)


def _job_id_from_url(url: str) -> str | None:
    m = re.search(r"/jobs/view/[^/?#]*?(\d{6,})", url)
    if m:
        return m.group(1)
    m = re.search(r"jobId=(\d+)", url)
    if m:
        return m.group(1)
    return None


def _first_url(text: str) -> str:
    m = re.search(r"https?://[^\s<>\"']+", text or "")
    return m.group(0) if m else ""


def parse_linkedin_subject(subject: str) -> dict | None:
    """Extract title/company/location/posted_at from a LinkedIn alert subject.

    Returns None if neither subject template matches — the caller should
    treat this as a digest email and call parse_linkedin_body() on the
    message HTML body instead.
    """
    if not subject:
        return None
    s = subject.strip()
    # Strip leading "Re:"/"Fwd:" if present
    s = re.sub(r"^(re|fwd|fw):\s*", "", s, flags=re.IGNORECASE)
    m = LINKEDIN_QUOTED_RE.match(s)
    if m:
        return {
            "title": m.group("title").strip(),
            "company": m.group("company").strip(),
            "location": (m.group("location") or "").strip(),
            "posted_at": (m.group("posted_at") or "").strip() or None,
        }
    m = LINKEDIN_AT_RE.match(s)
    if m:
        return {
            "title": m.group("title").strip(),
            "company": m.group("company").strip(),
            "location": "",
            "posted_at": None,
        }
    return None


def parse_digest_subject(subject: str) -> bool:
    """Return True if the subject looks like a LinkedIn digest (multi-role) email.

    Digest subjects include phrases like:
      "View jobs in Mumbai — 5 new jobs match your alert"
      "5 new jobs match your alert"
      "New jobs for you"
    Single-role alerts always include " at " (e.g. "Director PM at Google")
    and are handled by parse_linkedin_subject() instead.
    """
    if not subject:
        return False
    s = subject.strip()
    s = re.sub(r"^(re|fwd|fw):\s*", "", s, flags=re.IGNORECASE)
    return bool(_DIGEST_SUBJECT_RE.search(s))


# ---- HTML-to-text helper ---------------------------------------------------

class _TextExtractor(html.parser.HTMLParser):
    """Minimal HTML-to-text: skips style/script blocks, collapses whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth: int = 0
        self._skip_tags = {"style", "script", "head"}

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        # Block-level tags → newline separator
        if tag.lower() in {"p", "div", "br", "li", "tr", "td", "th"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Normalise whitespace within each line; keep line breaks
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(lines)


def _html_to_text(html_body: str) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(html_body)
    except Exception:
        # Malformed HTML — fall back to stripping tags with a regex
        return re.sub(r"<[^>]+>", " ", html_body)
    return extractor.get_text()


def _is_junk_line(line: str) -> bool:
    """Return True if a digest body line is navigation / footer noise."""
    if len(line) < 5:
        return True
    low = line.lower()
    return any(frag in low for frag in _DIGEST_JUNK_FRAGMENTS)


def parse_linkedin_body(html_body: str) -> list[dict]:
    """Extract job listings from a LinkedIn digest email HTML body.

    The digest body (after HTML-to-text extraction) contains blocks like:

        Senior Vice President, POM Product Management
        BNY · Pune/Pimpri-Chinchwad Area
        Actively recruiting
        Custody Product Development Manager...
        State Street · Mumbai

    The pattern: a line containing " · " (Unicode middle dot U+00B7 or
    standard ASCII centered dot) identifies "Company · Location". The line
    IMMEDIATELY before it is the job title.

    Returns a list of {title, company, location} dicts, capped at
    _DIGEST_MAX_ROLES to avoid noise from very long digests.
    """
    text = _html_to_text(html_body)
    lines = [ln.strip() for ln in text.splitlines()]
    # Remove blank lines and junk
    clean: list[str] = [ln for ln in lines if ln and not _is_junk_line(ln)]

    roles: list[dict] = []
    i = 0
    while i < len(clean) and len(roles) < _DIGEST_MAX_ROLES:
        line = clean[i]
        # Look for the "Company · Location" pattern.
        # LinkedIn uses U+00B7 (·) as the separator.
        if " · " in line or " · " in line:
            sep = " · " if " · " in line else " · "
            parts = line.split(sep, 1)
            company = parts[0].strip()
            location = parts[1].strip() if len(parts) > 1 else ""
            # The title is on the line before this one (if it exists and
            # doesn't itself contain " · ").
            if i > 0:
                candidate_title = clean[i - 1]
                if " · " not in candidate_title and " · " not in candidate_title:
                    # Skip if the prior line was already used as a title
                    # (i.e., the role immediately above this one already
                    # consumed clean[i-1]).
                    title = candidate_title
                    if company and title:
                        roles.append({
                            "title": title,
                            "company": company,
                            "location": location,
                        })
        i += 1

    return roles


def parse_naukri_subject_and_snippet(subject: str, snippet: str) -> dict | None:
    """Extract title from Naukri subject + company/location from the snippet."""
    if not subject:
        return None
    title_m = NAUKRI_SUBJECT_RE.match(subject.strip())
    if not title_m:
        return None
    title = title_m.group("title").strip().rstrip(",")

    company = ""
    location = ""
    if snippet:
        # Anchor on the last occurrence of the (clean) subject-title in the
        # snippet — that's the title repetition that immediately precedes
        # the company. Everything between that and the work-mode keyword
        # is the company name.
        idx = snippet.rfind(title)
        after = snippet[idx + len(title):] if idx >= 0 else snippet
        loc_m = NAUKRI_WORKMODE_RE.search(after)
        if loc_m:
            company = after[:loc_m.start()].strip(" -:|")
            location = loc_m.group("location").strip().split(",")[0].strip()

    return {
        "title": title,
        "company": company,
        "location": location,
        "posted_at": None,
    }


# ---- Thread → Job conversion ----------------------------------------------

def parse_linkedin_threads(threads: list[dict]) -> list[Job]:
    """Convert a list of Gmail thread dicts (LinkedIn alerts) to Job entries.

    Expected thread shape mirrors the Gmail MCP `search_threads` /
    `get_thread` response: each thread has a `messages` list, each message
    has `sender`, `subject`, `snippet`, optionally `htmlBody` / `body`.

    Two email types are handled:
      1. Single-role alerts — subject like "{Title} at {Company}".
         Parsed via parse_linkedin_subject(); URL extracted from body.
      2. Digest emails — subject like "View jobs in Mumbai — 5 new jobs
         match your alert". These are the majority of LinkedIn alert emails.
         parse_linkedin_body() is called on the HTML body to extract
         multiple {title, company, location} triples.
    """
    jobs: list[Job] = []
    for thread in threads or []:
        for msg in thread.get("messages", []):
            sender = (msg.get("sender") or "").lower()
            if not any(s in sender for s in LINKEDIN_SENDERS):
                continue

            subject = msg.get("subject", "")
            parsed = parse_linkedin_subject(subject)

            if parsed:
                # Single-role alert — fast path
                body = msg.get("htmlBody") or msg.get("body") or msg.get("snippet") or ""
                url = _first_url(body) if body else ""
                jobs.append(Job(
                    source="gmail_linkedin",
                    company=parsed["company"],
                    title=parsed["title"],
                    location=parsed["location"],
                    url=url,
                    posted_at=parsed["posted_at"],
                    raw_id=_job_id_from_url(url) or msg.get("id"),
                    description_excerpt=(msg.get("snippet") or "")[:500] or None,
                ))
            else:
                # Digest email — parse body for multiple roles.
                # We proceed whether or not parse_digest_subject() confirms
                # it's a digest; if parse_linkedin_subject returned None
                # and there's HTML body content, try body parsing anyway.
                html_body = msg.get("htmlBody") or msg.get("body") or ""
                if not html_body:
                    continue
                digest_roles = parse_linkedin_body(html_body)
                msg_id = msg.get("id")
                for role in digest_roles:
                    if not role.get("title") or not role.get("company"):
                        continue
                    jobs.append(Job(
                        source="gmail_linkedin",
                        company=role["company"],
                        title=role["title"],
                        location=role.get("location", ""),
                        url="",  # digest bodies don't embed per-role URLs
                        posted_at=None,
                        raw_id=msg_id,
                        description_excerpt=None,
                    ))

    return jobs


def parse_naukri_threads(threads: list[dict]) -> list[Job]:
    jobs: list[Job] = []
    for thread in threads or []:
        for msg in thread.get("messages", []):
            sender = (msg.get("sender") or "").lower()
            if not any(s in sender for s in NAUKRI_SENDERS):
                continue
            parsed = parse_naukri_subject_and_snippet(
                msg.get("subject", ""), msg.get("snippet", ""),
            )
            if not parsed:
                continue
            body = msg.get("htmlBody") or msg.get("body") or msg.get("snippet") or ""
            url = _first_url(body) if body else ""
            jobs.append(Job(
                source="gmail_naukri",
                company=parsed["company"],
                title=parsed["title"],
                location=parsed["location"],
                url=url,
                posted_at=parsed["posted_at"],
                raw_id=msg.get("id"),
                description_excerpt=(msg.get("snippet") or "")[:500] or None,
            ))
    return jobs


# ---- Driver ----------------------------------------------------------------

def fetch_jobs(date: str, root: str | Path = ".") -> list[dict]:
    """Read pre-saved Gmail thread JSON for `date` and return Job dicts.

    Looks for `outputs/{date}/_gmail_threads/linkedin.json` and
    `outputs/{date}/_gmail_threads/naukri.json`. The agent populates these
    files in Step 1e by calling Gmail MCP `search_threads` and dumping the
    raw response. Missing files are non-fatal — return [] for that source
    and continue.

    Each input file should be either:
      - the raw `search_threads` response: `{"threads": [...]}`, OR
      - a bare list of thread dicts.
    """
    root = Path(root)
    base = root / "outputs" / date / "_gmail_threads"
    out: list[dict] = []
    for sender_tag, filename, parser in (
        ("linkedin", "linkedin.json", parse_linkedin_threads),
        ("naukri",   "naukri.json",   parse_naukri_threads),
    ):
        path = base / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        threads = payload.get("threads", payload) if isinstance(payload, dict) else payload
        if not isinstance(threads, list):
            continue
        out.extend(j.to_dict() for j in parser(threads))
    return out


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    jobs = fetch_jobs(args.date, args.root)
    json.dump(jobs, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    print(f"# {len(jobs)} jobs from Gmail labels", file=sys.stderr)
