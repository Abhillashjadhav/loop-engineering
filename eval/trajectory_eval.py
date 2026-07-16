"""P1 — Weekly trajectory eval (LLM-as-judge).

Reads every `outputs/{date}/trajectory.jsonl` from the past 7 days, sends each
day's trajectory to Claude (Opus 4.7 via Max OAuth) with the rubric from
`eval/judge_prompt.md`, and emits `eval/eval_results/{ISO-week}/trajectory_scores.json`.

Five axes scored 1–5 per CLAUDE.md / eval/README.md spec:
    Coverage / Efficiency / Rule compliance / Recovery / Honesty

Honesty=1 if any fabricated bullet detected (no exceptions). Drift signals
bubble up to the weekly digest.

Run:
    python eval/trajectory_eval.py --week 2026-W20 --end 2026-05-17
    # or with explicit date range:
    python eval/trajectory_eval.py --start 2026-05-11 --end 2026-05-17

Cost: 0 (Max OAuth). 7 Opus calls × ~5K tokens each = ~35K tokens/week,
well inside the daily Opus quota window.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
JUDGE_PROMPT_PATH = ROOT / "eval" / "judge_prompt.md"
TRAJECTORY_AXES = ("coverage", "efficiency", "rule_compliance", "recovery", "honesty")


def _has_cli() -> bool:
    """Check claude CLI is available. Token is optional — the CLI may
    authenticate via local config (~/.claude/) or env. If auth fails at
    call time, we surface the failure honestly via `cli-rc-N` skipped."""
    return shutil.which("claude") is not None


def _date_range(start_d: date, end_d: date) -> list[str]:
    out = []
    d = start_d
    while d <= end_d:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _load_trajectory(date_str: str) -> str | None:
    p = ROOT / "outputs" / date_str / "trajectory.jsonl"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")[:80000]  # cap input


def _load_judge_prompt() -> str:
    if not JUDGE_PROMPT_PATH.exists():
        return ""
    return JUDGE_PROMPT_PATH.read_text(encoding="utf-8")


def score_day(date_str: str, judge_prompt: str) -> dict:
    """Send one day's trajectory to Claude. Return scores dict or skipped flag."""
    trajectory = _load_trajectory(date_str)
    if trajectory is None:
        return {"date": date_str, "skipped": True, "reason": "no-trajectory"}
    if not _has_cli():
        return {"date": date_str, "skipped": True, "reason": "no-claude-cli"}

    prompt = (
        f"{judge_prompt}\n\n"
        f"## Trajectory for {date_str}\n"
        f"```jsonl\n{trajectory}\n```\n\n"
        f"Return ONLY the JSON object for Task A (trajectory scoring), no prose.\n"
        f"Required shape:\n"
        '{"date":"YYYY-MM-DD","coverage":{"score":1-5,"evidence":"..."},'
        '"efficiency":{"score":1-5,"evidence":"..."},'
        '"rule_compliance":{"score":1-5,"evidence":"..."},'
        '"recovery":{"score":1-5,"evidence":"..."},'
        '"honesty":{"score":1-5,"evidence":"..."},"notes":"..."}'
    )

    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--model", "claude-opus-4-7",
             "--output-format", "json",
             "--max-turns", "20",
             "--disallowed-tools", "Bash,Edit,Write,WebFetch,WebSearch,Read"],
            capture_output=True, text=True, timeout=180,
            env={**os.environ},
        )
        if proc.returncode != 0:
            return {"date": date_str, "skipped": True,
                    "reason": f"cli-rc-{proc.returncode}",
                    "stderr": proc.stderr[-300:]}
        envelope = json.loads(proc.stdout)
        result_text = envelope.get("result", "")
        m = re.search(r"\{[\s\S]*\}", result_text)
        if not m:
            return {"date": date_str, "skipped": True,
                    "reason": "no-json-in-response",
                    "raw": result_text[:500]}
        return json.loads(m.group())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        return {"date": date_str, "skipped": True,
                "reason": f"{type(e).__name__}: {str(e)[:200]}"}


def aggregate_week(daily_scores: list[dict]) -> dict:
    """Compute weekly means + drift signals from per-day scores."""
    scored = [s for s in daily_scores if not s.get("skipped")]
    if not scored:
        return {"scored_days": 0, "drift_signals": ["no-scored-days"]}

    means = {}
    mins = {}
    for axis in TRAJECTORY_AXES:
        values = [s[axis]["score"] for s in scored if axis in s and "score" in s[axis]]
        if values:
            means[axis] = round(sum(values) / len(values), 2)
            mins[axis] = min(values)

    drift = []
    if mins.get("honesty", 5) < 4:
        drift.append("honesty<4 — block daily send")
    if mins.get("rule_compliance", 5) < 3:
        drift.append("rule_compliance<3 — resume-rule violations")
    if means.get("coverage", 5) < 3:
        drift.append("coverage<3 — sources skipped")

    return {
        "scored_days": len(scored),
        "axis_means": means,
        "axis_mins": mins,
        "drift_signals": drift,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--week", help="ISO week label like 2026-W20")
    p.add_argument("--start", help="YYYY-MM-DD inclusive")
    p.add_argument("--end", help="YYYY-MM-DD inclusive")
    args = p.parse_args()

    if args.start and args.end:
        start_d = datetime.strptime(args.start, "%Y-%m-%d").date()
        end_d = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:
        end_d = datetime.utcnow().date()
        start_d = end_d - timedelta(days=6)

    week_label = args.week or f"{start_d.isocalendar()[0]}-W{start_d.isocalendar()[1]:02d}"
    out_dir = ROOT / "eval" / "eval_results" / week_label
    out_dir.mkdir(parents=True, exist_ok=True)

    judge_prompt = _load_judge_prompt()
    daily_scores = []
    for d_str in _date_range(start_d, end_d):
        print(f"[trajectory_eval] scoring {d_str}", file=sys.stderr)
        daily_scores.append(score_day(d_str, judge_prompt))

    summary = aggregate_week(daily_scores)
    out_path = out_dir / "trajectory_scores.json"
    out_path.write_text(json.dumps({
        "week": week_label,
        "range": [start_d.isoformat(), end_d.isoformat()],
        "daily_scores": daily_scores,
        "summary": summary,
    }, indent=2, ensure_ascii=False))
    print(f"[trajectory_eval] wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
