"""Objective deep-inspection selection for large-portfolio audits.

Selects the top-N authored repositories per subject for judgment-signal deep
inspection, from recorded snapshot fields only. The four criteria are the
goal contract's, weighted and banded deterministically:

- current activity (0-25): recency of ``pushed_at`` relative to ``as_of``;
- public prominence (0-25): a *visibility* signal for selection only —
  popularity never feeds a technical-quality score (locked rule);
- substantive code surface (0-30): language, size, and commit-count bands;
- relevance (0-20): AI/ML/evals/agents/product-tooling terms in the name,
  description, and topics (fields may be absent in older snapshots — absent
  fields simply contribute nothing).

Flagship repositories named by the audit config are always selected, even
when the formula alone would not pick them; they are labeled as such.
Repositories not selected are explicitly labeled ``deep_inspected: false`` —
never silently skipped. Same inputs => same selection; ties break by
(score desc, stars desc, name asc).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from loop_engineering.use_cases.github_authority_audit.inventory import classify_kind

#: Distinct-term matches count 4 points each, capped at 20.
RELEVANCE_TERMS = (
    "ai",
    "ml",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "agent",
    "eval",
    "rag",
    "retrieval",
    "prompt",
    "mcp",
    "recsys",
    "recommend",
    "data",
    "pm",
    "product",
    "tool",
)

RELEVANCE_POINTS_PER_TERM = 4.0
RELEVANCE_CAP = 20.0
DEFAULT_LIMIT = 10


@dataclass
class SelectionEntry:
    name: str
    score: float
    components: dict[str, float]
    selected: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "selected": self.selected,
            "reason": self.reason,
        }


def _days_since(iso_ts: str, as_of: datetime) -> float | None:
    try:
        then = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return (as_of - then).total_seconds() / 86400.0


def _activity(record: dict[str, Any], as_of: datetime) -> float:
    days = _days_since(str(record.get("pushed_at", "")), as_of)
    if days is None:
        return 0.0
    if days <= 90:
        return 25.0
    if days <= 365:
        return 18.0
    if days <= 730:
        return 10.0
    return 0.0


def _prominence(record: dict[str, Any]) -> float:
    reach = int(record.get("stargazers_count", record.get("stars", 0))) + 2 * int(
        record.get("forks_count", record.get("forks", 0))
    )
    if reach >= 5000:
        return 25.0
    if reach >= 1000:
        return 20.0
    if reach >= 200:
        return 15.0
    if reach >= 50:
        return 10.0
    if reach >= 10:
        return 5.0
    return 0.0


def _code_surface(record: dict[str, Any]) -> float:
    score = 8.0 if record.get("language") else 0.0
    size = int(record.get("size", record.get("size_kb", 0)))
    if size >= 1000:
        score += 10.0
    elif size >= 100:
        score += 7.0
    elif size >= 10:
        score += 4.0
    commits = int(record.get("commit_count", 0))
    if commits >= 100:
        score += 12.0
    elif commits >= 30:
        score += 8.0
    elif commits >= 10:
        score += 5.0
    elif commits >= 3:
        score += 2.0
    return score


def _relevance(record: dict[str, Any]) -> float:
    haystack = " ".join(
        [
            str(record.get("name", "")),
            str(record.get("description") or ""),
            " ".join(str(t) for t in record.get("topics") or []),
        ]
    ).lower()
    # Whole-token matching (plural-tolerant): "ai" must not match "maintain",
    # while "evals" still counts for "eval".
    padded = "".join(c if c.isalnum() else " " for c in haystack)
    tokens = set(padded.split())
    hits = sum(1 for term in RELEVANCE_TERMS if term in tokens or f"{term}s" in tokens)
    return min(RELEVANCE_CAP, RELEVANCE_POINTS_PER_TERM * hits)


def selection_score(record: dict[str, Any], as_of: datetime) -> tuple[float, dict[str, float]]:
    components = {
        "current_activity": _activity(record, as_of),
        "public_prominence": _prominence(record),
        "code_surface": _code_surface(record),
        "relevance": _relevance(record),
    }
    return sum(components.values()), components


def select_deep_inspection(
    records: list[dict[str, Any]],
    as_of: datetime,
    flagships: tuple[str, ...] = (),
    limit: int = DEFAULT_LIMIT,
) -> list[SelectionEntry]:
    """Rank authored repositories and mark the deep-inspection set.

    Only authored repositories (original or archived own work, per
    ``classify_kind``) are eligible; forks, mirrors, and empty repos are out.
    Returns one entry per eligible repository — unselected repositories are
    labeled, never dropped.
    """
    eligible = [r for r in records if classify_kind(r) in ("original", "archived")]
    scored = sorted(
        ((record, *selection_score(record, as_of)) for record in eligible),
        key=lambda item: (
            -item[1],
            -int(item[0].get("stargazers_count", item[0].get("stars", 0))),
            str(item[0].get("name", "")),
        ),
    )
    flagship_set = {f for f in flagships}
    missing = flagship_set - {str(r.get("name", "")) for r in eligible}
    if missing:
        raise ValueError(
            f"flagship repositories not present among authored records: {sorted(missing)} "
            "(private, renamed, or not yet harvested — resolve before selection)"
        )

    entries: list[SelectionEntry] = []
    for rank, (record, score, components) in enumerate(scored):
        name = str(record.get("name", ""))
        in_top = rank < limit
        is_flagship = name in flagship_set
        if in_top and is_flagship:
            reason = "top-N by selection formula; also config-designated flagship"
        elif in_top:
            reason = "top-N by selection formula"
        elif is_flagship:
            reason = "flagship (config-designated, outside formula top-N)"
        else:
            reason = "not deep-inspected (below selection cut)"
        entries.append(SelectionEntry(name, score, components, in_top or is_flagship, reason))
    return entries
