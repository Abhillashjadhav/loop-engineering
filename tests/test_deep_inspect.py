"""Deterministic deep-inspection selection (cohort audit method step 4-5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loop_engineering.use_cases.github_authority_audit.deep_inspect import (
    select_deep_inspection,
    selection_score,
)

AS_OF = datetime(2026, 7, 17, tzinfo=UTC)


def rec(name: str, **overrides: object) -> dict:
    base: dict = {
        "name": name,
        "fork": False,
        "archived": False,
        "mirror": False,
        "stargazers_count": 0,
        "forks_count": 0,
        "language": "Python",
        "size": 120,
        "commit_count": 40,
        "created_at": "2025-01-01T00:00:00Z",
        "pushed_at": "2026-07-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_selection_is_deterministic_and_labels_everything() -> None:
    records = [rec(f"repo-{i}", stargazers_count=i * 10) for i in range(15)]
    first = select_deep_inspection(records, AS_OF, limit=10)
    second = select_deep_inspection(list(reversed(records)), AS_OF, limit=10)
    assert [e.to_dict() for e in first] == [e.to_dict() for e in second]
    assert len(first) == 15  # unselected repos are labeled, never dropped
    assert sum(e.selected for e in first) == 10
    assert all("not deep-inspected" in e.reason for e in first if not e.selected)


def test_forks_mirrors_and_empty_repos_ineligible() -> None:
    records = [
        rec("real"),
        rec("a-fork", fork=True),
        rec("a-mirror", mirror_url="https://example.com/m.git"),
        rec("empty", size=0, commit_count=0),
        rec("archived-own-work", archived=True),
    ]
    entries = select_deep_inspection(records, AS_OF)
    names = {e.name for e in entries}
    assert names == {"real", "archived-own-work"}


def test_flagships_always_selected_and_labeled() -> None:
    strong = [rec(f"strong-{i}", stargazers_count=5000, commit_count=500) for i in range(10)]
    weak_flagship = rec("pm-evals", stargazers_count=0, commit_count=3, size=15)
    entries = select_deep_inspection([*strong, weak_flagship], AS_OF, flagships=("pm-evals",))
    flag = next(e for e in entries if e.name == "pm-evals")
    assert flag.selected
    assert "flagship" in flag.reason
    assert sum(e.selected for e in entries) == 11  # 10 formula slots + 1 flagship


def test_missing_flagship_fails_loudly() -> None:
    with pytest.raises(ValueError, match="flagship repositories not present"):
        select_deep_inspection([rec("other")], AS_OF, flagships=("loop-engineering",))


def test_popularity_is_selection_visibility_capped() -> None:
    # Prominence is bounded (25 of 100): stars alone cannot dominate an
    # active, relevant, code-bearing repository.
    popular_dormant = rec(
        "old-viral-gist",
        stargazers_count=20000,
        commit_count=2,
        size=5,
        language=None,
        pushed_at="2020-01-01T00:00:00Z",
    )
    active_relevant = rec(
        "rag-eval-harness",
        description="RAG evals for product managers",
        topics=["ai", "evals"],
        stargazers_count=4,
        commit_count=60,
    )
    s_pop, _ = selection_score(popular_dormant, AS_OF)
    s_act, _ = selection_score(active_relevant, AS_OF)
    assert s_act > s_pop


def test_relevance_matches_whole_tokens_only() -> None:
    _, comps = selection_score(rec("maintain-stuff", language=None, description=None), AS_OF)
    assert comps["relevance"] == 0.0  # "ai" must not match inside "maintain"
    _, comps2 = selection_score(rec("ai-agent-evals"), AS_OF)
    assert comps2["relevance"] == 12.0  # ai + agent + evals (plural-tolerant)


def test_absent_description_and_topics_are_tolerated() -> None:
    legacy = rec("legacy-snapshot-record")
    legacy.pop("size")
    legacy["size_kb"] = 120
    entries = select_deep_inspection([legacy], AS_OF)
    assert entries[0].name == "legacy-snapshot-record"


def test_tie_break_by_stars_then_name() -> None:
    a = rec("bbb", stargazers_count=100)
    b = rec("aaa", stargazers_count=100)
    c = rec("ccc", stargazers_count=300)
    entries = select_deep_inspection([a, b, c], AS_OF, limit=2)
    assert [e.name for e in entries] == ["ccc", "aaa", "bbb"]
    assert [e.selected for e in entries] == [True, True, False]
