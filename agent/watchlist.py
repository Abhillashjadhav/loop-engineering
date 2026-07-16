"""Watchlist — companies whose roles get guaranteed brief visibility.

Used by run_daily.py to tag candidates from priority companies so the user
never misses a posting from their target list, even at borderline scores.

Match is case-insensitive substring on the candidate's company field — same
rule as decline_list_companies. Sister entities collapse onto the parent
(e.g. "Salesforce.com Inc" matches "Salesforce"; "JPMorganChase Services
India" matches "JPMorganChase").
"""

from __future__ import annotations

from pathlib import Path

_WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "profile" / "watchlist_companies.txt"


def load_watchlist(path: Path | None = None) -> list[str]:
    """Return the watchlist preserving original casing. Empty list on missing file."""
    p = path or _WATCHLIST_FILE
    if not p.exists():
        return []
    entries: list[str] = []
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def is_watchlist_match(company: str, watchlist: list[str] | None = None) -> str | None:
    """Return the matching watchlist entry (as written in the file) if any, else None.

    >>> is_watchlist_match("Salesforce.com Inc", ["Salesforce"])
    'Salesforce'
    >>> is_watchlist_match("JPMorganChase Services India", ["JPMorganChase"])
    'JPMorganChase'
    """
    if not company:
        return None
    wl = watchlist if watchlist is not None else load_watchlist()
    if not wl:
        return None
    c = company.lower()
    for needle in wl:
        if needle.lower() in c:
            return needle
    return None
