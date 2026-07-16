"""Referral lookup — match fit companies against the user's LinkedIn
connections CSV.

The user exports their LinkedIn connections via:
  LinkedIn → Settings → Data Privacy → Get a copy of your data → Connections
and commits the resulting CSV to `data/linkedin_connections.csv`. The file
is a normal LinkedIn export with a 2–3 line preamble, then a header row
with columns roughly:

    First Name,Last Name,URL,Email Address,Company,Position,Connected On

(Header row may be `URL` or `Profile URL` depending on export vintage.)

This module reads the CSV (skipping the preamble), then for each fit
company does a case-insensitive substring match on the `Company` column
and returns the matches the brief renders as the referral path.

Honesty rule: if the file doesn't exist, return [] — the brief shows
"no LinkedIn connections export in repo" rather than fabricating names.
If the file exists but no match for a company, the brief shows
"no 1st-degree connections at {Company}".

Usage:
    from agent.referral_lookup import find_referrals_for_company
    refs = find_referrals_for_company("Harvey")
    # -> [{"name": "...", "title": "...", "url": "...", "company": "..."}]
"""
from __future__ import annotations

import csv
import io
from pathlib import Path


CONNECTIONS_PATH_DEFAULT = Path("data/linkedin_connections.csv")


def _open_skipping_preamble(path: Path) -> tuple[list[str], list[dict]]:
    """Return (header_columns, rows_as_dicts) tolerant of LinkedIn's preamble.

    LinkedIn's connections export has 2–3 explanatory lines before the
    actual CSV header. We scan for the first line that contains
    "First Name" and treat that as the header row.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    header_idx = 0
    for i, line in enumerate(lines):
        if "First Name" in line and ("Company" in line or "Position" in line):
            header_idx = i
            break
    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text))
    header = reader.fieldnames or []
    rows = list(reader)
    return header, rows


def load_connections(path: Path | str = CONNECTIONS_PATH_DEFAULT) -> list[dict]:
    """Load all connections from the CSV. Returns [] if the file is absent.

    Each returned dict has stable keys: name, title, company, url. Empty
    fields are normalised to "".
    """
    path = Path(path)
    if not path.exists():
        return []
    try:
        _header, rows = _open_skipping_preamble(path)
    except Exception:
        return []

    out: list[dict] = []
    for row in rows:
        first = (row.get("First Name") or "").strip()
        last = (row.get("Last Name") or "").strip()
        if not first and not last:
            continue
        out.append({
            "name": f"{first} {last}".strip(),
            "title": (row.get("Position") or "").strip(),
            "company": (row.get("Company") or "").strip(),
            "url": (row.get("URL") or row.get("Profile URL") or "").strip(),
        })
    return out


def find_referrals_for_company(company: str,
                               connections: list[dict] | None = None,
                               path: Path | str = CONNECTIONS_PATH_DEFAULT,
                               max_matches: int = 5) -> list[dict]:
    """Return connections whose `company` field substring-matches `company`.

    Match is case-insensitive substring on company name only — the same
    rule `rule_filter.py` uses for the decline list, so sister entities
    (e.g. "Experian Services", "Sabre GLBL Services") all hit when the
    canonical company name is "Experian" / "Sabre".

    `max_matches` caps the returned list to keep the brief readable when
    the user has many ex-colleagues at a megacorp.
    """
    if connections is None:
        connections = load_connections(path)
    if not connections:
        return []
    needle = (company or "").strip().lower()
    if not needle:
        return []
    matches: list[dict] = []
    for c in connections:
        haystack = c.get("company", "").lower()
        if needle in haystack:
            matches.append(c)
            if len(matches) >= max_matches:
                break
    return matches


def format_referral_block(company: str,
                          matches: list[dict],
                          connections_loaded: bool) -> str:
    """Render the referral path for the brief.

    Three states:
      1. Connections file missing → "no referral path identified (no LinkedIn connections export in repo)"
      2. File present, no matches → "no 1st-degree connections at {Company}"
      3. Matches → "[Name] ({Title}) — [LinkedIn URL]" repeated.
    """
    if not connections_loaded:
        return ("**Referral path:** no referral path identified "
                "*(no LinkedIn connections export in repo)*")
    if not matches:
        return f"**Referral path:** no 1st-degree connections at {company}"
    bits = []
    for m in matches:
        title = m.get("title") or "—"
        url = m.get("url") or ""
        url_part = f" — [{url}]({url})" if url else ""
        bits.append(f"{m['name']} ({title}){url_part}")
    return "**Referral path:** " + "; ".join(bits)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--connections", default=str(CONNECTIONS_PATH_DEFAULT))
    args = ap.parse_args()
    conns = load_connections(args.connections)
    matches = find_referrals_for_company(args.company, conns)
    json.dump(matches, sys.stdout, indent=2)
    sys.stdout.write("\n")
    print(f"# {len(matches)} match(es) for '{args.company}' "
          f"(connections file loaded: {bool(conns)})", file=sys.stderr)
