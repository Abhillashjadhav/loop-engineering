"""Accuracy Evidence Pack + Learning Receipt (spec §9, PD-05).

Every successful run produces outputs/<goal-id>/ with the full pack. The pack
explains plainly why the output is considered reliable — and what it cannot
prove.
"""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loop_engineering.domain.models import (
    Claim,
    GoalMatchVerdict,
    RunState,
    Task,
    VerificationResult,
    utc_now,
)
from loop_engineering.planning.planner import CoverageReport
from loop_engineering.reporting.metrics import NorthStar
from loop_engineering.verification.e2e_reviewer import GateAResult, GateBResult
from loop_engineering.verification.loop3_evidence import EvidenceCoverage, is_supported
from loop_engineering.verification.loop4_stability import StabilityReport


@dataclass
class LearningReceipt:
    """PD-05: what the user should understand before using the conclusion."""

    important_decisions: list[str] = field(default_factory=list)
    alternatives_rejected: list[str] = field(default_factory=list)
    failures_and_repairs: list[str] = field(default_factory=list)
    surprising_evidence: list[str] = field(default_factory=list)
    before_you_use_this: list[str] = field(default_factory=list)

    def render(self) -> str:
        def section(title: str, items: list[str]) -> str:
            body = "\n".join(f"- {i}" for i in items) if items else "- (none recorded)"
            return f"## {title}\n\n{body}\n"

        return (
            "# Learning Receipt\n\n"
            + section("Important decisions", self.important_decisions)
            + "\n"
            + section("Alternatives rejected", self.alternatives_rejected)
            + "\n"
            + section("Key failures and repairs", self.failures_and_repairs)
            + "\n"
            + section("Surprising evidence", self.surprising_evidence)
            + "\n"
            + section(
                "What you should understand before using this conclusion",
                self.before_you_use_this,
            )
        )


@dataclass
class PackInputs:
    contract: dict[str, Any]
    state: RunState
    tasks: list[Task]
    verifications: list[VerificationResult]
    claims: list[Claim]
    evidence_coverage: EvidenceCoverage
    coverage: CoverageReport
    gate_a: GateAResult
    gate_b: GateBResult
    north_star: NorthStar
    leading: dict[str, Any]
    final_output_markdown: str
    learning_receipt: LearningReceipt
    stability: StabilityReport | None = None
    scorecards: dict[str, dict[str, Any]] = field(default_factory=dict)
    unresolved_uncertainties: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    run_directory: Path | None = None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _accuracy_markdown(p: PackInputs) -> str:
    contract = p.contract
    lines = [
        "# Accuracy Evidence",
        "",
        f"Generated: {utc_now()}",
        "",
        "## Original goal and expected output",
        "",
        f"**Goal ({contract['goal_id']} v{contract['version']}):** {contract['goal_statement']}",
        "",
        "**Expected deliverables:** " + ", ".join(contract["expected_output"]["deliverables"]),
        "",
        f"**Contract digest:** `{contract['canonical_digest']}`",
        "",
        "## Process completeness (Gate A)",
        "",
        f"Verdict: **{p.gate_a.verdict.value}**",
        "",
    ]
    lines += [
        f"- {'PASS' if c.passed else 'FAIL'} — {c.name}" + (f" ({c.detail})" if c.detail else "")
        for c in p.gate_a.checks
    ]
    lines += [
        "",
        "## Autonomous task completion",
        "",
        f"- Planned tasks completed autonomously: "
        f"{p.leading['planned_tasks_completed_autonomously_pct']}%",
        f"- Human interventions: {p.leading['human_interventions']}",
        "",
        "## First-pass verification",
        "",
        f"- First-pass task verification rate: "
        f"{p.leading['first_pass_task_verification_rate_pct']}%",
        f"- Average repair attempts per task: {p.leading['avg_repair_attempts_per_task']}",
        "",
        "## Claim evidence coverage",
        "",
        f"- Material claims: {p.evidence_coverage.total_claims}",
        f"- Independently supported: {p.evidence_coverage.supported_claims} "
        f"({p.evidence_coverage.supported_pct}%)",
        f"- Unsupported (excluded from all percentages): "
        f"{p.evidence_coverage.unsupported_claim_ids or 'none'}",
        f"- Claims with visible source conflict: "
        f"{p.evidence_coverage.conflicted_claim_ids or 'none'}",
        "",
        "## Four-loop results",
        "",
    ]
    by_loop: dict[str, list[VerificationResult]] = {}
    for v in p.verifications:
        by_loop.setdefault(v.loop, []).append(v)
    for loop_name in ("loop1_task", "loop2_drift", "loop3_evidence", "loop4_stability"):
        results = by_loop.get(loop_name, [])
        passed = sum(1 for v in results if v.passed)
        lines.append(f"- {loop_name}: {passed}/{len(results)} passed")
    lines += ["", "## Six-run agreement / disagreement", ""]
    if p.stability is not None:
        lines += [
            f"- Variants compared: {p.stability.variant_count}",
            f"- Stable findings: {len(p.stability.stable)}",
            f"- Unstable findings (disagreement preserved): {len(p.stability.unstable)}",
            f"- Unresolved: {len(p.stability.unresolved)}",
        ]
    else:
        lines.append("- Six-run stability was not required for this goal.")
    lines += [
        "",
        "## Goal drift",
        "",
        f"- Drift: {p.coverage.drift_pct}% (guardrail < 5%)",
        f"- Orphan tasks: {p.coverage.orphan_task_ids or 'none'}",
        f"- Uncovered requirements: {p.coverage.uncovered_requirements or 'none'}",
        "",
        "## End-to-end goal-match score",
        "",
        f"- Score: **{p.gate_b.score}/100** → **{p.gate_b.verdict.value}**",
    ]
    lines += [f"  - {k}: {v}" for k, v in p.gate_b.dimension_scores.items()]
    if p.gate_b.caveats:
        lines += ["", "**Caveats:**"] + [f"- {c}" for c in p.gate_b.caveats]
    lines += [
        "",
        "## North Star outcome",
        "",
        f"- Baseline manual minutes: {p.north_star.baseline_manual_minutes}",
        f"- Human active minutes: {p.north_star.human_active_minutes}",
        f"- Goal successfully verified: {p.north_star.goal_successfully_verified}",
        f"- Estimated minutes saved: {p.north_star.estimated_minutes_saved}",
        "",
        "## Exclusions and limitations",
        "",
    ]
    exclusions = [str(e) for e in p.contract.get("exclusions", [])]
    lines += [f"- (contract exclusion) {e}" for e in exclusions]
    lines += [f"- {limit}" for limit in p.limitations] or ["- none recorded"]
    return "\n".join(lines) + "\n"


def _claim_matrix_rows(claims: list[Claim]) -> list[list[str]]:
    rows: list[list[str]] = [
        [
            "claim_id",
            "claim",
            "impact",
            "kind",
            "epistemics",
            "supported",
            "reason",
            "evidence_origins",
            "evidence_urls",
            "conflicts",
        ]
    ]
    for c in claims:
        supported, reason = is_supported(c)
        rows.append(
            [
                c.claim_id,
                c.text,
                c.impact.value,
                c.kind.value,
                c.epistemics.value,
                "yes" if supported else "no",
                reason,
                ";".join(sorted({e.origin for e in c.evidence})),
                ";".join(e.source_url for e in c.evidence),
                ";".join(c.conflicts),
            ]
        )
    return rows


def build_pack(p: PackInputs, outputs_root: str | Path) -> Path:
    """Write the full Accuracy Evidence Pack to outputs/<goal-id>/."""
    out = Path(outputs_root) / str(p.contract["goal_id"])
    out.mkdir(parents=True, exist_ok=True)

    _write(out / "final-output.md", p.final_output_markdown)
    _write(out / "accuracy-evidence.md", _accuracy_markdown(p))

    accuracy_json = {
        "goal_id": p.contract["goal_id"],
        "contract_digest": p.contract["canonical_digest"],
        "gate_a": p.gate_a.to_dict(),
        "gate_b": p.gate_b.to_dict(),
        "north_star": p.north_star.to_dict(),
        "leading_metrics": p.leading,
        "evidence_coverage": p.evidence_coverage.to_dict(),
        "goal_drift": p.coverage.to_dict(),
        "stability": p.stability.to_dict() if p.stability else None,
        "generated_at": utc_now(),
    }
    _write(out / "accuracy-evidence.json", json.dumps(accuracy_json, indent=2))

    _write(out / "learning-receipt.md", p.learning_receipt.render())

    with (out / "claim-evidence-matrix.csv").open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(_claim_matrix_rows(p.claims))

    scorecard_dir = out / "repository-scorecards"
    scorecard_dir.mkdir(exist_ok=True)
    for name, card in p.scorecards.items():
        _write(scorecard_dir / f"{name}.json", json.dumps(card, indent=2))

    if p.run_directory is not None:
        src_ledger = p.run_directory / "task-ledger.jsonl"
        if src_ledger.exists():
            shutil.copyfile(src_ledger, out / "task-ledger.jsonl")
    with (out / "verification-results.jsonl").open("w", encoding="utf-8") as fh:
        for v in p.verifications:
            fh.write(json.dumps(v.to_dict()) + "\n")

    if p.stability is not None:
        stab = p.stability
        lines = ["# Six-run comparison", ""]
        lines += [f"Variants compared: {stab.variant_count}", "", "## Stable findings", ""]
        lines += [f"- **{k}**: {v}" for k, v in stab.stable.items()] or ["- none"]
        lines += ["", "## Unstable findings (per-variant values preserved)", ""]
        for k, per_variant in stab.unstable.items():
            lines.append(f"- **{k}**:")
            lines += [f"  - {variant}: {value}" for variant, value in per_variant.items()]
        if not stab.unstable:
            lines.append("- none")
        lines += ["", "## Unresolved", ""]
        lines += [f"- {u}" for u in stab.unresolved] or ["- none"]
        lines += [
            "",
            "_Consistency alone does not prove accuracy; source triangulation and",
            "independent evidence verification (Loop 3) remain mandatory._",
        ]
        _write(out / "six-run-comparison.md", "\n".join(lines) + "\n")

    review_lines = [
        "# End-to-end goal review",
        "",
        f"- Gate A (process completeness): **{p.gate_a.verdict.value}**",
        f"- Gate B (goal/output match): **{p.gate_b.score}/100 → {p.gate_b.verdict.value}**",
        "",
        "## Gate A checks",
        "",
    ]
    review_lines += [
        f"- {'PASS' if c.passed else 'FAIL'} — {c.name}" + (f" ({c.detail})" if c.detail else "")
        for c in p.gate_a.checks
    ]
    review_lines += ["", "## Gate B dimensions", ""]
    review_lines += [f"- {k}: {v}" for k, v in p.gate_b.dimension_scores.items()]
    _write(out / "end-to-end-goal-review.md", "\n".join(review_lines) + "\n")

    unresolved = p.unresolved_uncertainties or ["none recorded"]
    _write(
        out / "unresolved-uncertainties.md",
        "# Unresolved uncertainties\n\n" + "\n".join(f"- {u}" for u in unresolved) + "\n",
    )
    return out


def deliverable(verdict: GoalMatchVerdict) -> bool:
    """Whether this verdict may be delivered as success (PD-06)."""
    return verdict in (GoalMatchVerdict.GOAL_MATCH, GoalMatchVerdict.GOAL_MATCH_WITH_CAVEATS)
