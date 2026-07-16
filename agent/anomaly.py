"""Rolling-baseline anomaly detection for the daily pipeline.

Invariants (agent/invariants.py) catch *absolute* failures — a stage that
produced zero / collapsed output. This module catches *relative* failures:
a stage whose output is implausibly small compared to its own recent
history, even if non-zero.

Example: Gmail normally yields ~100 URLs/day. A run that yields 12 passes
the `> 0` invariant but is clearly anomalous. `check_anomaly` flags any
stage where today is < 30% of the trailing 7-run median.

History lives in `data/run_metrics.jsonl` (one JSON object per run). The
file is created on first use and appended to every run regardless of
whether an anomaly fired — so the baseline keeps growing.

On a flagged anomaly: `write_run_anomaly` drops a `RUN_ANOMALY.md`
comparison table into the date folder; `run_daily` halts before the Gmail
draft and exits non-zero.

Adaptation note: spec path was `pipeline/anomaly.py`; placed at
`agent/anomaly.py` for import consistency with the rest of the package.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUN_METRICS_PATH = ROOT / "data" / "run_metrics.jsonl"

# Stages tracked for anomaly detection, in pipeline order. Each maps to an
# integer count emitted by the corresponding stage.
TRACKED_STAGES = (
    "gmail_urls",
    "raw_candidates",
    "filtered",
    "scored",
    "fits",
    "resumes",
)

ANOMALY_FRACTION = 0.30   # today < 30% of trailing median => anomaly
BASELINE_WINDOW = 7       # trailing runs used for the baseline
MIN_HISTORY = 3           # need at least this many prior runs to judge


class RunAnomalyError(Exception):
    """Raised when one or more stages are anomalously low vs the baseline."""

    def __init__(self, flagged: list[dict]):
        self.flagged = flagged  # list of {stage, today, median, p25, p75}
        summary = ", ".join(
            f"{f['stage']} {f['today']} vs median {f['median']}" for f in flagged
        )
        super().__init__(f"Anomalous stages: {summary}")


def _load_history(path: Path = RUN_METRICS_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def append_metrics(metrics: dict, date: str,
                   path: Path = RUN_METRICS_PATH) -> None:
    """Append today's stage counts to data/run_metrics.jsonl.

    Called unconditionally at the end of every run (even anomalous ones) so
    the rolling baseline always reflects reality.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "date": date,
        "ts": datetime.now(timezone.utc).isoformat(),
        **{k: int(metrics.get(k, 0)) for k in TRACKED_STAGES},
    }
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _baseline(history: list[dict], stage: str) -> dict | None:
    """Median / p25 / p75 of `stage` over the trailing BASELINE_WINDOW runs."""
    values = [int(h.get(stage, 0)) for h in history[-BASELINE_WINDOW:]]
    values = [v for v in values if v >= 0]
    if len(values) < MIN_HISTORY:
        return None
    s = sorted(values)
    return {
        "median": statistics.median(s),
        "p25": s[len(s) // 4],
        "p75": s[(len(s) * 3) // 4],
        "n": len(s),
    }


def check_anomaly(today_metrics: dict,
                  path: Path = RUN_METRICS_PATH) -> list[dict]:
    """Compare today's stage counts to the trailing-7-run baseline.

    Returns a list of flagged stages (empty if all clear). Does NOT raise —
    the caller decides whether to halt. Does NOT append today's metrics;
    call `append_metrics` separately so history grows even on a clean run.
    """
    history = _load_history(path)
    flagged: list[dict] = []
    for stage in TRACKED_STAGES:
        if stage not in today_metrics:
            continue  # partial metrics dict — only judge stages present
        base = _baseline(history, stage)
        if base is None:
            continue  # not enough history to judge this stage yet
        today = int(today_metrics.get(stage, 0))
        threshold = base["median"] * ANOMALY_FRACTION
        # Only flag when the baseline itself is non-trivial — a median of 0
        # or 1 makes the 30% rule meaningless.
        if base["median"] >= 5 and today < threshold:
            flagged.append({
                "stage": stage,
                "today": today,
                "median": base["median"],
                "p25": base["p25"],
                "p75": base["p75"],
                "threshold": round(threshold, 1),
                "baseline_runs": base["n"],
            })
    return flagged


def reflect(date_dir: Path, stage: str, observed_value: int, date: str,
            path: Path = RUN_METRICS_PATH) -> tuple[str, dict]:
    """ReAct 'Reflect' substep for a single stage.

    After a stage's Observation, reflect: is the observed value consistent
    with the trailing baseline? Returns ('halt', detail) or
    ('proceed', detail). On 'halt' a RUN_ANOMALY.md is written immediately
    so the run stops at THIS stage rather than continuing to a later
    checkpoint.

    Used by run_daily right after the post-Apify fetch observation, and is
    independently unit-testable (see tests/test_silent_failure_reflect.py).
    """
    history = _load_history(path)
    base = _baseline(history, stage)
    if base is None:
        return "proceed", {"stage": stage, "reason": "insufficient-history",
                            "observed": observed_value}
    threshold = base["median"] * ANOMALY_FRACTION
    if base["median"] >= 5 and observed_value < threshold:
        flagged = [{
            "stage": stage,
            "today": observed_value,
            "median": base["median"],
            "p25": base["p25"],
            "p75": base["p75"],
            "threshold": round(threshold, 1),
            "baseline_runs": base["n"],
        }]
        write_run_anomaly(date_dir, flagged, date)
        return "halt", {"stage": stage, "flagged": flagged,
                         "reflection": (
                             f"observed {observed_value} is below "
                             f"{int(ANOMALY_FRACTION*100)}% of the "
                             f"{base['n']}-run median ({base['median']}) — "
                             f"inconsistent with baseline, likely an upstream "
                             f"source collapse; halting.")}
    return "proceed", {"stage": stage, "observed": observed_value,
                        "median": base["median"],
                        "reflection": "consistent with baseline"}


def write_run_anomaly(date_dir: Path, flagged: list[dict], date: str) -> None:
    """Write a RUN_ANOMALY.md comparison table into the date folder."""
    date_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RUN ANOMALY — stage output far below baseline",
        "",
        f"- **Date:** {date}",
        f"- **Timestamp (UTC):** {datetime.now(timezone.utc).isoformat()}",
        f"- **Rule:** a stage is flagged when today < {int(ANOMALY_FRACTION*100)}% "
        f"of the trailing {BASELINE_WINDOW}-run median.",
        "",
        "## Flagged stages",
        "",
        "| Stage | Today | 7-run median | p25 | p75 | Threshold |",
        "|---|---|---|---|---|---|",
    ]
    for f in flagged:
        lines.append(
            f"| {f['stage']} | **{f['today']}** | {f['median']} | "
            f"{f['p25']} | {f['p75']} | {f['threshold']} |"
        )
    lines += [
        "",
        "The run was halted before the Gmail draft. The brief (if any) is still",
        "committed to the daily-runs branch for forensics, but no draft was sent.",
        "",
        "## Likely causes",
        "",
        "- An upstream source silently degraded (Apify / Greenhouse / Gmail).",
        "- A filter or scoring threshold changed and over-pruned.",
        "- A genuine quiet day — if so, re-trigger to confirm and the baseline",
        "  will absorb it.",
        "",
        "## What to do",
        "",
        "1. Compare the flagged counts above against `trajectory.jsonl`.",
        "2. If a source degraded, fix it and re-trigger this date.",
        "3. If it is a genuine low-volume day, re-trigger — a second similar",
        "   run shifts the baseline and stops the flag.",
    ]
    (date_dir / "RUN_ANOMALY.md").write_text("\n".join(lines) + "\n")
