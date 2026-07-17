"""Deterministic cohort-report renderers (product comparison + questions A-H).

Division of labour, unchanged: inspectors record observable judgments as
DATA (the 12-dimension comparison JSON, per-repo signals); the engine
verifies scores; this module only RENDERS deterministic markdown from those
verified inputs. Every ranking states its formula inline; popularity feeds
only the distribution question (C) and the distribution_mechanics dimension;
AI-share is never an exact percentage.

Inputs come from the fixture directory (``comparisons/*.json``,
``audit-config.yaml``) and the run's verified artifacts (``persons/*.json``,
``assessments/*.json``). Absent inputs mean the reports are simply not
rendered — never guessed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: G/H bucket map over the locked 12 comparison dimensions. Dimensions not
#: listed (success_attribution, ai_assistance_transparency) are descriptive
#: and belong to neither gap bucket.
SUBSTANCE_DIMENSIONS = (
    "product_scope",
    "technical_depth",
    "verification_quality",
    "tests_and_ci",
    "originality_of_frameworks",
)
PACKAGING_DIMENSIONS = (
    "installation_and_activation",
    "user_experience",
    "ecosystem_compatibility",
    "community_contribution_design",
)
DISTRIBUTION_DIMENSIONS = ("distribution_mechanics",)

USABLE_PRODUCT_WEIGHTS = (
    ("technical_proficiency", 0.4),
    ("claim_evidence_integrity", 0.3),
    ("educational_value", 0.3),
)


def load_inputs(fixture_root: Path) -> dict[str, Any] | None:
    """Comparison JSON + audit config, or None when this isn't a cohort run."""
    comp_dir = fixture_root / "comparisons"
    cfg_path = fixture_root / "audit-config.yaml"
    comparisons = sorted(comp_dir.glob("*.json")) if comp_dir.is_dir() else []
    if not comparisons or not cfg_path.is_file():
        return None
    import yaml

    return {
        "comparison": json.loads(comparisons[0].read_text(encoding="utf-8")),
        "config": yaml.safe_load(cfg_path.read_text(encoding="utf-8")),
    }


def _fmt_evidence(items: list[dict[str, Any]], limit: int = 2) -> list[str]:
    out = []
    for e in items[:limit]:
        out.append(f"  - `{e.get('origin', '?')}` {e.get('url', '')} — “{e.get('excerpt', '')}”")
    return out


def render_flagship_comparison(inputs: dict[str, Any]) -> str:
    comp = inputs["comparison"]
    dims: dict[str, Any] = comp["dimensions"]
    lines = [
        f"# Product-level flagship comparison — {comp.get('comparison', '?')}",
        "",
        "Observable public artifacts only; recorded by an independent inspector",
        "from harvested snapshots, verified evidence excerpts inline. Popularity",
        "appears ONLY under distribution_mechanics, as reach — never as quality.",
        "",
    ]
    for key, d in dims.items():
        lines += [
            f"## {key}",
            "",
            f"- **favors (artifacts):** {d.get('favors', 'not recorded')}"
            f" (confidence: {d.get('confidence', '?')})",
            f"- **pm-skills:** {d.get('pm_skills', '')}",
            f"- **PM-agent-OS:** {d.get('pm_agent_os', '')}",
            f"- **assessment:** {d.get('assessment', '')}",
            "- evidence:",
            *_fmt_evidence(list(d.get("evidence", []))),
            "",
        ]
    sa = comp.get("success_attribution", {})
    if sa:
        lines += [
            "## Success attribution (descriptive, no winner)",
            "",
            f"- pm-skills: {sa.get('pm_skills', '')}",
            f"- PM-agent-OS: {sa.get('pm_agent_os', '')}",
            f"- note: {sa.get('note', '')}",
            "",
        ]
    caveats = comp.get("caveats", [])
    if caveats:
        lines += ["## Caveats (snapshot-depth limits)", ""]
        lines += [f"- {c}" for c in caveats]
        lines.append("")
    return "\n".join(lines) + "\n"


def _rank(persons: list[dict[str, Any]], score_key: str) -> list[tuple[str, float]]:
    pairs = [(str(p["subject"]), float(p["aggregate_scores"][score_key])) for p in persons]
    return sorted(pairs, key=lambda x: (-x[1], x[0]))


def _best_products(
    assessments_by_subject: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str, float]]:
    """Per subject: best deep-inspected repo by the documented usable-product
    composite. Subjects with no deep-inspected repo are listed last with n/a."""
    rows: list[tuple[str, str, float]] = []
    for subject, cards in assessments_by_subject.items():
        best_name, best_score = "", -1.0
        for card in cards:
            if not card.get("deep_inspected"):
                continue
            s = card["scores"]
            composite = sum(float(s[k]) * w for k, w in USABLE_PRODUCT_WEIGHTS)
            if composite > best_score:
                best_name, best_score = str(card["repo"]), composite
        rows.append((subject, best_name or "(no deep-inspected repo)", round(best_score, 1)))
    return sorted(rows, key=lambda r: (-r[2], r[0]))


def render_answers_a_h(
    persons: list[dict[str, Any]],
    assessments_by_subject: dict[str, list[dict[str, Any]]],
    inputs: dict[str, Any],
    focus_subject: str = "Abhillash Jadhav",
) -> str:
    comp_dims: dict[str, Any] = inputs["comparison"]["dimensions"]
    tech = _rank(persons, "substantive_technical_depth")
    dist = _rank(persons, "distribution_strength")
    products = _best_products(assessments_by_subject)
    tech_rank = {s: i for i, (s, _) in enumerate(tech)}
    dist_rank = {s: i for i, (s, _) in enumerate(dist)}
    conversion = sorted(
        ((s, tech_rank[s] - dist_rank[s]) for s, _ in tech),
        key=lambda x: (-x[1], x[0]),
    )
    focus = next(p for p in persons if p["subject"] == focus_subject)
    others = [p for p in persons if p["subject"] != focus_subject]

    def median(vals: list[float]) -> float:
        v = sorted(vals)
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    score_keys = [
        "substantive_technical_depth",
        "human_reasoning_evidence",
        "educational_strength",
        "distribution_strength",
        "claim_evidence_integrity",
    ]
    ahead: list[tuple[str, float, float]] = []
    behind: list[tuple[str, float, float]] = []
    for k in score_keys:
        mine = float(focus["aggregate_scores"][k])
        med = median([float(p["aggregate_scores"][k]) for p in others])
        (ahead if mine > med else behind).append((k, mine, med))

    def favored(side: str, bucket: tuple[str, ...]) -> list[str]:
        return [k for k in bucket if comp_dims.get(k, {}).get("favors") == side]

    product_gaps = favored("pm_skills", SUBSTANCE_DIMENSIONS)
    packaging_gaps = favored("pm_skills", PACKAGING_DIMENSIONS) + favored(
        "pm_skills", DISTRIBUTION_DIMENSIONS
    )
    leverage = (packaging_gaps + product_gaps)[:3]

    lines = [
        "# Cohort questions A-H — separate answers",
        "",
        "Each answer states its metric. Scores are the engine-verified",
        "aggregates; flagship-dimension verdicts are the inspector's recorded",
        "artifact-level judgments. Popularity appears only in C and D's",
        "distribution side. No private competence or intent is inferred;",
        "answers describe public artifacts only.",
        "",
        "## A. Strongest technical depth",
        "",
        "Metric: aggregate substantive_technical_depth.",
        "",
        *[f"{i + 1}. {s} — {v}" for i, (s, v) in enumerate(tech)],
        "",
        "## B. Best usable products",
        "",
        "Metric: best deep-inspected repository per subject by composite "
        "0.4*technical_proficiency + 0.3*claim_evidence_integrity + "
        "0.3*educational_value.",
        "",
        *[f"{i + 1}. {s} — {r} ({v})" for i, (s, r, v) in enumerate(products)],
        "",
        "## C. Strongest distribution",
        "",
        "Metric: aggregate distribution_strength (reach signal, never quality).",
        "",
        *[f"{i + 1}. {s} — {v}" for i, (s, v) in enumerate(dist)],
        "",
        "## D. Converts technical work into public authority most effectively",
        "",
        "Metric: distribution rank minus technical rank (positive = reach",
        "exceeds what technical rank alone would predict — a packaging/",
        "distribution effect; negative = technical work under-distributed).",
        "",
        *[f"- {s}: {'+' if d > 0 else ''}{d}" for s, d in conversion],
        "",
        f"## E. Where {focus_subject} is genuinely ahead",
        "",
        "Metric: aggregate score above the cohort median (his value vs median);",
        "plus flagship dimensions the artifacts favor his side.",
        "",
        *[f"- {k}: {m} vs median {md}" for k, m, md in ahead],
        *[
            f"- flagship dimension favoring PM-agent-OS: {k}"
            for k in [k for k, d in comp_dims.items() if d.get("favors") == "pm_agent_os"]
        ],
        "",
        f"## F. Where {focus_subject} is behind",
        "",
        *[f"- {k}: {m} vs median {md}" for k, m, md in behind],
        *[
            f"- flagship dimension favoring pm-skills: {k}"
            for k in [k for k, d in comp_dims.items() if d.get("favors") == "pm_skills"]
        ],
        "",
        "## G. Product gaps versus packaging/distribution gaps",
        "",
        "Bucketed from the flagship dimensions the artifacts favor pm-skills:",
        "",
        f"- product/substance gaps: {', '.join(product_gaps) or '(none recorded)'}",
        f"- packaging/distribution gaps: {', '.join(packaging_gaps) or '(none recorded)'}",
        "",
        f"## H. Three highest-leverage actions for {focus_subject}",
        "",
        "Derived deterministically: the top gap dimensions recorded above,",
        "packaging/distribution first (largest observed deltas at equal",
        "product substance), each grounded in the flagship comparison.",
        "",
        *[
            f"{i + 1}. Close the {k} gap (see flagship comparison, `{k}`)."
            for i, k in enumerate(leverage)
        ],
        "",
        "---",
        "",
        "_What cannot be concluded (all subjects): private intent, private or",
        "unpublished work, exact human/AI authorship of any file, or what any",
        "person privately understands._",
    ]
    return "\n".join(lines) + "\n"
