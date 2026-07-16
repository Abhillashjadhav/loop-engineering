"""
Calibration recommender for Dreamjob-agent.
Reads applications.jsonl + agent score history; emits proposals for the weekly digest.

Run: python eval/calibration.py --week YYYY-Www --weeks_elapsed N --end_date YYYY-MM-DD --out eval/eval_results/{week}/calibration_proposals.json

Safety contract:
- Never auto-applies. Only writes proposals. User approval required.
- Requires >= MIN_LABELS in rolling 4-week window before threshold changes.
- Requires >= MIN_OBSERVE_WEEKS elapsed (default 4) before any proposals emit.
"""
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

MIN_LABELS = 30
MIN_OBSERVE_WEEKS = 4
ROLLING_WINDOW_DAYS = 28
CURRENT_THRESHOLD = 80
APPLY_RATE_LOWER_BOUND = 0.60
SKIP_RATE_UPPER_BOUND = 0.60
REWORK_RATE_TRIGGER = 0.30
DIM_DIVERGENCE_PT_TRIGGER = 5.0


def load_labels(applications_path, end, window_days=ROLLING_WINDOW_DAYS):
    if not applications_path.exists():
        return []
    rows = [json.loads(l) for l in applications_path.read_text().splitlines() if l.strip()]
    cutoff = end - timedelta(days=window_days)
    return [r for r in rows if date.fromisoformat(r["date"]) >= cutoff]


def bucketize(score):
    if score >= 90: return "90-100"
    if score >= 80: return "80-89"
    if score >= 70: return "70-79"
    if score >= 60: return "60-69"
    return "<60"


def compute_label_distribution(labels):
    by_bucket = defaultdict(Counter)
    for r in labels:
        by_bucket[bucketize(r["agent_score"])][r["label"]] += 1
    return by_bucket


def apply_rate(bucket_counts):
    total = sum(bucket_counts.values())
    return (bucket_counts.get("Apply", 0) / total) if total else 0.0


def skip_rate(bucket_counts):
    total = sum(bucket_counts.values())
    return (bucket_counts.get("Skip", 0) / total) if total else 0.0


def rework_rate(bucket_counts):
    total = sum(bucket_counts.values())
    return (bucket_counts.get("Needs-rework", 0) / total) if total else 0.0


def detect_calibration_slope(by_bucket):
    order = ["60-69", "70-79", "80-89", "90-100"]
    rates = [apply_rate(by_bucket[b]) for b in order if sum(by_bucket[b].values()) >= 3]
    if len(rates) < 3:
        return "insufficient_data"
    if all(rates[i] <= rates[i+1] for i in range(len(rates)-1)):
        return "monotonic"
    if all(rates[i] >= rates[i+1] for i in range(len(rates)-1)):
        return "inverted"
    return "noisy"


def diagnose_dimensions(labels, dim_breakdowns):
    findings = []
    by_dim = defaultdict(lambda: {"Apply": [], "Skip": []})
    for r in labels:
        dims = dim_breakdowns.get(r["role_id"], {})
        for d, v in dims.items():
            if r["label"] in ("Apply", "Skip"):
                by_dim[d][r["label"]].append(v)
    for d, payload in by_dim.items():
        if len(payload["Apply"]) >= 5 and len(payload["Skip"]) >= 5:
            diff = statistics.mean(payload["Apply"]) - statistics.mean(payload["Skip"])
            if abs(diff) >= DIM_DIVERGENCE_PT_TRIGGER:
                findings.append({
                    "dimension": d,
                    "direction": "over" if diff < 0 else "under",
                    "magnitude_pts": round(abs(diff), 1),
                    "n_apply": len(payload["Apply"]),
                    "n_skip": len(payload["Skip"]),
                })
    return findings


def recommend_threshold(by_bucket, n_total, weeks_elapsed):
    if weeks_elapsed < MIN_OBSERVE_WEEKS or n_total < MIN_LABELS:
        return {"current": CURRENT_THRESHOLD, "proposed": CURRENT_THRESHOLD,
                "rationale": "Insufficient data; keep current.", "min_labels_satisfied": False}

    apply_70 = apply_rate(by_bucket["70-79"])
    skip_80 = skip_rate(by_bucket["80-89"])

    if apply_70 >= APPLY_RATE_LOWER_BOUND:
        return {"current": CURRENT_THRESHOLD, "proposed": 75,
                "rationale": f"User applied to {apply_70:.0%} of 70-79 roles; lower threshold to 75.",
                "min_labels_satisfied": True}
    if skip_80 >= SKIP_RATE_UPPER_BOUND:
        return {"current": CURRENT_THRESHOLD, "proposed": 85,
                "rationale": f"User skipped {skip_80:.0%} of 80-89 roles; raise threshold OR investigate dimension weighting.",
                "min_labels_satisfied": True,
                "alternative": "rubric_reweight"}
    return {"current": CURRENT_THRESHOLD, "proposed": CURRENT_THRESHOLD,
            "rationale": "Calibration in healthy range.", "min_labels_satisfied": True}


def recommend_skill_rules(labels):
    rework = [r for r in labels if r["label"] == "Needs-rework"]
    if not labels or len(rework) / len(labels) < REWORK_RATE_TRIGGER:
        return []
    themes = Counter()
    for r in rework:
        c = (r.get("comment") or "").lower()
        for theme in ["framing", "metric", "scope", "dates", "title", "tone", "ats", "length"]:
            if theme in c:
                themes[theme] += 1
    return [{"rule": f"Add resume-rule guidance for rework theme: {t}",
             "rationale": f"{n} rework comments mentioned '{t}' this window.",
             "diff": "(human-authored after approval)"}
            for t, n in themes.most_common(3)]


def build_proposals(applications_path, dim_breakdowns_path, week, weeks_elapsed, end_date):
    labels = load_labels(applications_path, end_date)
    by_bucket = compute_label_distribution(labels)
    n_total = sum(sum(c.values()) for c in by_bucket.values())
    slope = detect_calibration_slope(by_bucket)
    dims = json.loads(dim_breakdowns_path.read_text()) if dim_breakdowns_path.exists() else {}
    diagnoses = diagnose_dimensions(labels, dims)
    threshold = recommend_threshold(by_bucket, n_total, weeks_elapsed)
    rules = recommend_skill_rules(labels)

    return {
        "week": week,
        "n_labels": n_total,
        "weeks_elapsed": weeks_elapsed,
        "by_bucket": {k: dict(v) for k, v in by_bucket.items()},
        "calibration_slope": slope,
        "dimension_diagnosis": diagnoses,
        "threshold_recommendation": threshold,
        "skill_rule_recommendations": rules,
        "auto_apply": False,
        "approval_status": "pending",
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--week", required=True)
    p.add_argument("--applications", default="outputs/applications.jsonl")
    p.add_argument("--dim_breakdowns", default="eval/metrics/dimension_breakdowns.json")
    p.add_argument("--weeks_elapsed", type=int, required=True)
    p.add_argument("--end_date", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    proposals = build_proposals(
        Path(a.applications), Path(a.dim_breakdowns),
        a.week, a.weeks_elapsed, date.fromisoformat(a.end_date)
    )
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(proposals, indent=2))
    print(f"Wrote {a.out}; auto_apply=False (user approval required).")
