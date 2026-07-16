"""The AI-slop mechanism: 10 observable quality dimensions (spec §10).

Division of labour: observation vs judgment. An inspector (human, agent, or
fixture) records *observable signals* per repository; this module converts
signals into dimension scores and derived scores with documented, deterministic
formulas, each carrying an evidence line. AI assistance, simple code, curation,
tutorials, and popularity are never equated with slop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loop_engineering.use_cases.github_authority_audit.inventory import RepoRecord

#: Signal keys an inspection is expected to record; confidence scales with coverage.
EXPECTED_SIGNALS = (
    "readme_claims_total",
    "readme_claims_code_backed",
    "original_logic_notes",
    "template_similarity_pct",
    "boilerplate_share_pct",
    "error_handling_present",
    "edge_case_handling_present",
    "security_practices_present",
    "test_files",
    "ci_runs",
    "failure_handling_tested",
    "setup_reproducible",
    "deps_valid",
    "secrets_policy_ok",
    "apis_current",
    "distinct_commit_days",
    "refactor_commits",
    "issue_responses",
    "dependency_updates",
    "abstraction_layers",
    "complexity_justified",
    "explanation_quality",
    "tradeoffs_discussed",
    "limitations_disclosed",
    "one_shot_dump",
    "commit_msg_uniformity_pct",
    "mass_generated_siblings",
    "ai_tool_attribution",
)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


@dataclass
class DimensionScore:
    key: str
    score: float
    polarity: str  # "quality" (higher is better) or "risk" (higher is worse)
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "score": round(self.score, 1),
            "polarity": self.polarity,
            "evidence": self.evidence,
        }


def score_dimensions(repo: RepoRecord) -> list[DimensionScore]:
    s = repo.signals
    dims: list[DimensionScore] = []

    total = int(s.get("readme_claims_total", 0))
    backed = int(s.get("readme_claims_code_backed", 0))
    claim_integrity = 100.0 * backed / total if total else 50.0
    dims.append(
        DimensionScore(
            "claim_functionality_integrity",
            _clamp(claim_integrity),
            "quality",
            f"{backed}/{total} README claims backed by executable code/tests"
            if total
            else "no explicit README claims found; neutral 50",
        )
    )

    notes = int(s.get("original_logic_notes", 0))
    original = 20.0 * notes + (20.0 if s.get("meaningful_adaptation") else 0.0)
    dims.append(
        DimensionScore(
            "original_problem_decision_content",
            _clamp(original),
            "quality",
            f"{notes} instance(s) of original logic/product reasoning/architecture rationale; "
            f"meaningful adaptation: {bool(s.get('meaningful_adaptation'))}",
        )
    )

    template_risk = 0.6 * float(s.get("template_similarity_pct", 0)) + 0.4 * float(
        s.get("boilerplate_share_pct", 0)
    )
    dims.append(
        DimensionScore(
            "template_duplication_risk",
            _clamp(template_risk),
            "risk",
            f"template similarity {s.get('template_similarity_pct', 0)}%, "
            f"boilerplate share {s.get('boilerplate_share_pct', 0)}%",
        )
    )

    depth_marks = [
        bool(s.get("error_handling_present")),
        bool(s.get("input_validation_present")),
        bool(s.get("state_management_present")),
        bool(s.get("security_practices_present")),
        bool(s.get("edge_case_handling_present")),
    ]
    integration = min(3, int(s.get("integration_complexity", 0)))
    depth = 16.0 * sum(depth_marks) + integration / 3.0 * 20.0
    dims.append(
        DimensionScore(
            "engineering_depth",
            _clamp(depth),
            "quality",
            f"{sum(depth_marks)}/5 depth markers present; integration complexity {integration}/3",
        )
    )

    verification = (
        min(40.0, 8.0 * int(s.get("test_files", 0)))
        + (20.0 if s.get("ci_runs") else 0.0)
        + (15.0 if s.get("eval_fixtures") else 0.0)
        + (10.0 if s.get("golden_cases") else 0.0)
        + (15.0 if s.get("failure_handling_tested") else 0.0)
    )
    dims.append(
        DimensionScore(
            "verification_depth",
            _clamp(verification),
            "quality",
            f"{s.get('test_files', 0)} test file(s), CI={bool(s.get('ci_runs'))}, "
            f"failure handling tested={bool(s.get('failure_handling_tested'))}",
        )
    )

    runnable_marks = [
        bool(s.get("setup_reproducible")),
        bool(s.get("deps_valid")),
        bool(s.get("secrets_policy_ok")),
        bool(s.get("apis_current")),
        bool(s.get("smoke_path_documented")),
    ]
    dims.append(
        DimensionScore(
            "runnable_integrity",
            _clamp(20.0 * sum(runnable_marks)),
            "quality",
            f"{sum(runnable_marks)}/5 runnable-integrity markers "
            "(reproducible setup, valid deps, secrets policy, current APIs, smoke path)",
        )
    )

    evolution = (
        min(40.0, 2.0 * int(s.get("distinct_commit_days", 0)))
        + min(30.0, 6.0 * int(s.get("refactor_commits", 0)))
        + min(15.0, 3.0 * int(s.get("issue_responses", 0)))
        + min(15.0, 5.0 * repo.releases)
    )
    if s.get("one_shot_dump"):
        evolution = min(evolution, 15.0)
    dims.append(
        DimensionScore(
            "development_evolution",
            _clamp(evolution),
            "quality",
            f"{s.get('distinct_commit_days', 0)} distinct commit day(s), "
            f"{s.get('refactor_commits', 0)} refactor commit(s), {repo.releases} release(s), "
            f"one-shot dump={bool(s.get('one_shot_dump'))}",
        )
    )

    stewardship = (
        min(40.0, 10.0 * int(s.get("dependency_updates", 0)))
        + min(30.0, 6.0 * int(s.get("issue_responses", 0)))
        + min(15.0, 5.0 * int(s.get("docs_corrections", 0)))
        + (15.0 if s.get("deprecations_handled") else 0.0)
    )
    dims.append(
        DimensionScore(
            "maintenance_stewardship",
            _clamp(stewardship),
            "quality",
            f"{s.get('dependency_updates', 0)} dependency update(s), "
            f"{s.get('issue_responses', 0)} issue response(s), "
            f"{s.get('docs_corrections', 0)} docs correction(s)",
        )
    )

    layers = int(s.get("abstraction_layers", 1))
    justified = bool(s.get("complexity_justified", True))
    proportionality = 100.0 - max(0, layers - 2) * 20.0
    if not justified:
        proportionality -= 30.0
    dims.append(
        DimensionScore(
            "architecture_proportionality",
            _clamp(proportionality),
            "quality",
            f"{layers} abstraction layer(s); complexity justified={justified} "
            "(decorative agents/frameworks penalised)",
        )
    )

    education = (
        min(40.0, float(s.get("explanation_quality", 0)) / 3.0 * 40.0)
        + (20.0 if s.get("tradeoffs_discussed") else 0.0)
        + (20.0 if s.get("limitations_disclosed") else 0.0)
        + (20.0 if s.get("runnable_learning") else 0.0)
    )
    dims.append(
        DimensionScore(
            "educational_value",
            _clamp(education),
            "quality",
            f"explanation quality {s.get('explanation_quality', 0)}/3, "
            f"trade-offs={bool(s.get('tradeoffs_discussed'))}, "
            f"limitations={bool(s.get('limitations_disclosed'))}, "
            f"runnable learning={bool(s.get('runnable_learning'))}",
        )
    )

    return dims


@dataclass
class RepoScores:
    """Derived scores (spec §10). ai_assistance_likelihood and ai_slop_risk are
    distinct on purpose: AI-assisted work may be technically strong and useful."""

    human_reasoning_evidence: float
    technical_proficiency: float
    ai_assistance_likelihood: float
    ai_assistance_confidence: float
    ai_slop_risk: float
    educational_value: float
    distribution_strength: float
    claim_evidence_integrity: float
    confidence: float

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 1) for k, v in vars(self).items()}


def _dim(dims: list[DimensionScore], key: str) -> float:
    for d in dims:
        if d.key == key:
            return d.score
    raise KeyError(key)


def derive_scores(repo: RepoRecord, dims: list[DimensionScore]) -> RepoScores:
    s = repo.signals

    human_reasoning = (
        0.40 * _dim(dims, "original_problem_decision_content")
        + 0.25 * _dim(dims, "engineering_depth")
        + 0.20 * _dim(dims, "development_evolution")
        + 0.15 * _dim(dims, "architecture_proportionality")
    )
    technical = (
        0.35 * _dim(dims, "engineering_depth")
        + 0.25 * _dim(dims, "verification_depth")
        + 0.25 * _dim(dims, "runnable_integrity")
        + 0.15 * _dim(dims, "architecture_proportionality")
    )

    ai_likelihood = (
        (30.0 if s.get("one_shot_dump") else 0.0)
        + 0.25 * float(s.get("commit_msg_uniformity_pct", 0))
        + min(25.0, 8.0 * int(s.get("mass_generated_siblings", 0)))
        + (20.0 if s.get("ai_tool_attribution") else 0.0)
    )
    ai_signal_keys = (
        "one_shot_dump",
        "commit_msg_uniformity_pct",
        "mass_generated_siblings",
        "ai_tool_attribution",
    )
    ai_signals_present = sum(1 for k in ai_signal_keys if k in s)
    ai_confidence = 100.0 * ai_signals_present / len(ai_signal_keys)
    # The AI-share band may never be stated with more confidence than the
    # overall evidence coverage supports: a near-empty repo can have all four
    # AI-axis signals recorded (e.g. a single-commit LICENSE-only repo) while
    # there is no code for a "share" to describe. Capping at overall coverage
    # sends such repos to INSUFFICIENT_EVIDENCE via band_ai_share's floor.

    slop_risk = (
        0.30 * (100.0 - _dim(dims, "claim_functionality_integrity"))
        + 0.15 * _dim(dims, "template_duplication_risk")
        + 0.15 * (100.0 - _dim(dims, "original_problem_decision_content"))
        + 0.10 * (100.0 - _dim(dims, "engineering_depth"))
        + 0.10 * (100.0 - _dim(dims, "verification_depth"))
        + 0.10 * (100.0 - _dim(dims, "runnable_integrity"))
        + 0.10 * (100.0 - _dim(dims, "development_evolution"))
    )

    # Distribution is a signal, never quality: log-ish bands over stars+forks.
    reach = repo.stars + 2 * repo.forks
    if reach >= 5000:
        distribution = 95.0
    elif reach >= 1000:
        distribution = 80.0
    elif reach >= 200:
        distribution = 60.0
    elif reach >= 50:
        distribution = 40.0
    elif reach >= 10:
        distribution = 20.0
    else:
        distribution = 5.0

    coverage = sum(1 for k in EXPECTED_SIGNALS if k in s) / len(EXPECTED_SIGNALS)
    confidence = 100.0 * coverage
    if repo.inaccessible:
        confidence = min(confidence, 20.0)
    ai_confidence = min(ai_confidence, confidence)

    return RepoScores(
        human_reasoning_evidence=_clamp(human_reasoning),
        technical_proficiency=_clamp(technical),
        ai_assistance_likelihood=_clamp(ai_likelihood),
        ai_assistance_confidence=_clamp(ai_confidence),
        ai_slop_risk=_clamp(slop_risk),
        educational_value=_dim(dims, "educational_value"),
        distribution_strength=distribution,
        claim_evidence_integrity=_dim(dims, "claim_functionality_integrity"),
        confidence=_clamp(confidence),
    )
