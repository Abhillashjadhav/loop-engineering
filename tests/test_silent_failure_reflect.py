"""Test the ReAct Reflect substep — the post-Apify halt on raw collapse.

GOAL coverage: simulate skip_apify=True with 30 Gmail URLs and assert the
agent halts at the post-Apify Reflect step instead of silently continuing
with a collapsed candidate pool.

The Reflect substep is `agent.anomaly.reflect()` — invoked by
run_daily right after the post-Apify fetch observation. These tests drive
it directly with a seeded baseline so no network / OAuth is needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent import anomaly  # noqa: E402


def _seed_healthy_baseline(metrics_path: Path, runs: int = 7) -> None:
    """Seed `runs` healthy runs: ~4000 raw candidates each."""
    for i in range(runs):
        anomaly.append_metrics(
            {
                "gmail_urls": 100,
                "raw_candidates": 4000,
                "filtered": 60,
                "scored": 60,
                "fits": 12,
                "resumes": 12,
            },
            date=f"2026-05-{i + 1:02d}",
            path=metrics_path,
        )


def test_skip_apify_30_urls_halts_at_post_apify_reflect(tmp_path: Path) -> None:
    """skip_apify scenario: 30 Gmail URLs, raw pool collapses post-Apify.

    With a healthy ~4000-raw baseline, a post-Apify observation of 200 raw
    candidates is < 30% of the median. The Reflect substep must return
    'halt' and write RUN_ANOMALY.md.
    """
    metrics_path = tmp_path / "run_metrics.jsonl"
    _seed_healthy_baseline(metrics_path)

    date_dir = tmp_path / "outputs" / "2026-05-20"

    # Simulate skip_apify=True: 30 Gmail URLs were extracted, but with Apify
    # skipped the raw candidate pool collapsed to 200.
    collapsed_raw = 200
    decision, detail = anomaly.reflect(
        date_dir, stage="raw_candidates", observed_value=collapsed_raw,
        date="2026-05-20", path=metrics_path,
    )

    assert decision == "halt", f"expected halt, got {decision}: {detail}"
    assert (date_dir / "RUN_ANOMALY.md").exists(), "RUN_ANOMALY.md not written"
    anomaly_text = (date_dir / "RUN_ANOMALY.md").read_text()
    assert "raw_candidates" in anomaly_text
    assert "200" in anomaly_text
    assert detail["flagged"][0]["stage"] == "raw_candidates"


def test_healthy_run_passes_reflect(tmp_path: Path) -> None:
    """A healthy post-Apify observation (~4000 raw) must proceed, not halt."""
    metrics_path = tmp_path / "run_metrics.jsonl"
    _seed_healthy_baseline(metrics_path)

    date_dir = tmp_path / "outputs" / "2026-05-20"
    decision, detail = anomaly.reflect(
        date_dir, stage="raw_candidates", observed_value=3900,
        date="2026-05-20", path=metrics_path,
    )

    assert decision == "proceed", f"expected proceed, got {decision}: {detail}"
    assert not (date_dir / "RUN_ANOMALY.md").exists()


def test_reflect_proceeds_when_history_insufficient(tmp_path: Path) -> None:
    """With < MIN_HISTORY prior runs the baseline is unknown — proceed.

    A brand-new pipeline must not halt on its first runs just because there
    is no baseline yet.
    """
    metrics_path = tmp_path / "run_metrics.jsonl"
    anomaly.append_metrics(
        {"gmail_urls": 100, "raw_candidates": 4000, "filtered": 60,
         "scored": 60, "fits": 12, "resumes": 12},
        date="2026-05-01", path=metrics_path,
    )  # only 1 prior run — below MIN_HISTORY

    date_dir = tmp_path / "outputs" / "2026-05-20"
    decision, detail = anomaly.reflect(
        date_dir, stage="raw_candidates", observed_value=10,
        date="2026-05-20", path=metrics_path,
    )

    assert decision == "proceed"
    assert detail["reason"] == "insufficient-history"
