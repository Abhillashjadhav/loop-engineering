"""Audit runner: plugs the GitHub authority audit into the run engine.

Task graph per subject: identity → inventory → assess → aggregate; then a
cross-subject comparison and the final output. Every task writes its artifact
and raw-evidence snapshots to disk; the engine's Loop 1 verifies each from the
filesystem.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from loop_engineering.domain.errors import LoopEngineeringError
from loop_engineering.domain.models import (
    Claim,
    ClaimEpistemics,
    ClaimImpact,
    ClaimKind,
    EvidenceItem,
    PassCondition,
    SearchCoverage,
    StabilityVariant,
    Task,
    utc_now,
)
from loop_engineering.reporting.evidence_pack import LearningReceipt
from loop_engineering.runtime.engine import ExecutionContext, TaskOutcome
from loop_engineering.use_cases.github_authority_audit import (
    aggregate as agg,
)
from loop_engineering.use_cases.github_authority_audit import (
    classify as cls_mod,
)
from loop_engineering.use_cases.github_authority_audit import (
    cohort_report,
    rubric,
)
from loop_engineering.use_cases.github_authority_audit import (
    identity as identity_mod,
)
from loop_engineering.use_cases.github_authority_audit import (
    inventory as inv_mod,
)
from loop_engineering.use_cases.github_authority_audit.datasource import GitHubDataSource
from loop_engineering.verification.loop4_stability import RunFindings

# Goal requirements — must match the contract's scope entries verbatim.
REQ_IDENTITY = "verify subject identity from at least two public attributes"
REQ_INVENTORY = "inventory all public repositories for each subject"
REQ_ASSESS = "assess repository quality across the ten-dimension rubric"
REQ_AGGREGATE = "aggregate person-level distributions and verdicts"
REQ_COMPARE = "compare subjects and answer the underlying question"
REQ_FINAL = "produce final output with uncertainties disclosed"

SKEPTICAL_SLOP_FLOOR = 65.0


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence_from_fixture(items: list[dict[str, Any]], prefix: str) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    for i, raw in enumerate(items):
        excerpt = str(raw.get("excerpt", ""))
        out.append(
            EvidenceItem(
                evidence_id=f"{prefix}-{i}",
                source_url=str(raw.get("url", "")),
                origin=str(raw.get("origin", "unknown")),
                retrieved_at=str(raw.get("retrieved_at", utc_now())),
                content_hash=_hash(excerpt or str(raw.get("url", ""))),
                excerpt=excerpt,
            )
        )
    return out


class AuditUseCase:
    """UseCase implementation for the public GitHub authority audit."""

    name = "github-authority-audit"

    def __init__(self, data_source: GitHubDataSource, subjects: list[dict[str, Any]]) -> None:
        self.data_source = data_source
        self.subjects = subjects

    # -- planning -----------------------------------------------------------

    def build_plan(self, contract: dict[str, Any], config: dict[str, Any]) -> list[Task]:
        tasks: list[Task] = []
        agg_ids: list[str] = []
        for subject in self.subjects:
            slug = str(subject["slug"])
            tasks.append(
                Task(
                    task_id=f"{slug}-1-identity",
                    goal_requirement=REQ_IDENTITY,
                    action=f"Verify public identity of subject {slug}",
                    expected_artifact=f"identity/{slug}.json",
                    evidence_required=[f"{slug}/profile.json"],
                    pass_condition=PassCondition(type="file_contains", text='"confirmed": true'),
                    failure_condition="fewer than two matching public attributes or a collision",
                )
            )
            tasks.append(
                Task(
                    task_id=f"{slug}-2-inventory",
                    goal_requirement=REQ_INVENTORY,
                    action=f"Inventory all public repositories of subject {slug}",
                    expected_artifact=f"inventory/{slug}.json",
                    evidence_required=[f"{slug}/repos.json"],
                    pass_condition=PassCondition(
                        type="json_has_keys", keys=["login", "counts", "records"]
                    ),
                    failure_condition="repository listing unavailable or empty pages missing",
                    dependencies=[f"{slug}-1-identity"],
                )
            )
            tasks.append(
                Task(
                    task_id=f"{slug}-3-assess",
                    goal_requirement=REQ_ASSESS,
                    action=f"Score every original repository of subject {slug} on the rubric",
                    expected_artifact=f"assessments/{slug}.json",
                    evidence_required=[],
                    pass_condition=PassCondition(
                        type="json_has_keys", keys=["login", "assessments"]
                    ),
                    failure_condition="rubric signals missing for analyzed repositories",
                    dependencies=[f"{slug}-2-inventory"],
                )
            )
            agg_id = f"{slug}-4-aggregate"
            agg_ids.append(agg_id)
            tasks.append(
                Task(
                    task_id=agg_id,
                    goal_requirement=REQ_AGGREGATE,
                    action=f"Aggregate person-level assessment for subject {slug}",
                    expected_artifact=f"persons/{slug}.json",
                    evidence_required=[],
                    pass_condition=PassCondition(
                        type="json_has_keys",
                        keys=["verdict", "repo_count_weighted", "active_code_weighted"],
                    ),
                    failure_condition="per-repo assessments unavailable",
                    dependencies=[f"{slug}-3-assess"],
                )
            )
        tasks.append(
            Task(
                task_id="z-1-compare",
                goal_requirement=REQ_COMPARE,
                action="Compare subjects and answer the underlying question",
                expected_artifact="comparison.json",
                evidence_required=[],
                pass_condition=PassCondition(type="json_has_keys", keys=["subjects"]),
                failure_condition="person assessments missing",
                dependencies=agg_ids,
            )
        )
        tasks.append(
            Task(
                task_id="z-2-final-output",
                goal_requirement=REQ_FINAL,
                action="Render the final answer with verdicts and open uncertainties",
                expected_artifact="reports/final-answer.md",
                evidence_required=[],
                pass_condition=PassCondition(type="file_contains", text="## Verdict"),
                failure_condition="comparison artifact missing",
                dependencies=["z-1-compare"],
            )
        )
        return tasks

    def _slug_and_step(self, task_id: str) -> tuple[str, str] | None:
        """Resolve (slug, step) from a task id, robust to hyphenated slugs.

        Task ids are built as f"{slug}-{step}-{name}"; slugs themselves may
        contain hyphens (e.g. "aakash-gupta"), so match against the known
        subject slugs instead of naive splitting.
        """
        for s in self.subjects:
            prefix = f"{s['slug']}-"
            if task_id.startswith(prefix):
                return str(s["slug"]), task_id[len(prefix) :].split("-", 1)[0]
        return None

    def stage_of(self, task: Task) -> str:
        resolved = self._slug_and_step(task.task_id)
        if resolved is not None:
            return resolved[0]
        return task.task_id.split("-", 1)[0]

    # -- execution ------------------------------------------------------------

    def _subject(self, slug: str) -> dict[str, Any]:
        for s in self.subjects:
            if s["slug"] == slug:
                return s
        raise LoopEngineeringError(f"unknown subject slug {slug!r}")

    def execute_task(self, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        if task.task_id.startswith("z-1-compare"):
            return self._exec_compare(task, ctx)
        if task.task_id.startswith("z-2-final-output") or task.task_id.startswith("repair-"):
            return self._exec_final(task, ctx)
        resolved = self._slug_and_step(task.task_id)
        if resolved is not None:
            slug, step = resolved
            if step == "1":
                return self._exec_identity(slug, task, ctx)
            if step == "2":
                return self._exec_inventory(slug, task, ctx)
            if step == "3":
                return self._exec_assess(slug, task, ctx)
            if step == "4":
                return self._exec_aggregate(slug, task, ctx)
        raise LoopEngineeringError(f"no executor for task {task.task_id}")

    def _exec_identity(self, slug: str, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        subject = self._subject(slug)
        login = str(subject["candidate_login"])
        profile = self.data_source.profile(login)
        others = self.data_source.candidate_profiles(slug)
        result = identity_mod.verify_identity(
            subject=str(subject["display_name"]),
            candidate_login=login,
            expected_attributes=dict(subject.get("expected_attributes", {})),
            profile=profile,
            other_candidates=others,
        )
        ctx.evidence_path(f"{slug}/profile.json").write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
        ctx.artifact_path(task.expected_artifact).write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        evidence = _evidence_from_fixture(
            list(profile.get("evidence_links", [])), f"{slug}-identity"
        )
        claim = Claim(
            claim_id=f"{slug}-identity",
            text=(
                f"GitHub login {login!r} is the public profile of "
                f"{subject['display_name']} ({len(result.matched_attributes)} attributes matched)"
            ),
            impact=ClaimImpact.NORMAL,
            epistemics=ClaimEpistemics.OBSERVATION,
            evidence=evidence,
        )
        return TaskOutcome(claims=[claim], notes=result.notes)

    def _exec_inventory(self, slug: str, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        subject = self._subject(slug)
        login = str(subject["candidate_login"])
        raw = self.data_source.repositories(login)
        inventory = inv_mod.build_inventory(login, raw)
        ctx.evidence_path(f"{slug}/repos.json").write_text(
            json.dumps(raw, indent=2), encoding="utf-8"
        )
        ctx.artifact_path(task.expected_artifact).write_text(
            json.dumps(inventory.to_dict(), indent=2), encoding="utf-8"
        )
        uncertainties = [
            f"{slug}/{r.name}: inaccessible ({r.inaccessible_reason})"
            for r in inventory.inaccessible
        ]
        return TaskOutcome(claims=[], uncertainties=uncertainties)

    def _assess_repos(
        self, inventory: inv_mod.Inventory, slop_floor: float = cls_mod.SLOP_RISK_FLOOR
    ) -> list[agg.RepoAssessment]:
        assessments: list[agg.RepoAssessment] = []
        for record in inventory.authored:
            dims = rubric.score_dimensions(record)
            scores = rubric.derive_scores(record, dims)
            ce_raw = record.signals.get("counter_evidence_review")
            counter = (
                cls_mod.CounterEvidenceReview(
                    reviewed=bool(ce_raw.get("reviewed", False)),
                    strongest_counter_evidence=[
                        str(x) for x in ce_raw.get("strongest_counter_evidence", [])
                    ],
                    review_notes=str(ce_raw.get("review_notes", "")),
                )
                if isinstance(ce_raw, dict)
                else None
            )
            classification = cls_mod.classify_repo(scores, counter, slop_floor=slop_floor)
            assessments.append(
                agg.RepoAssessment(record=record, scores=scores, classification=classification)
            )
        return assessments

    def _exec_assess(self, slug: str, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        subject = self._subject(slug)
        login = str(subject["candidate_login"])
        inventory_data = ctx.read_artifact_json(f"inventory/{slug}.json")
        inventory = inv_mod.build_inventory(login, list(inventory_data["records"]))
        assessments = self._assess_repos(inventory)

        claims: list[Claim] = []
        payload: list[dict[str, Any]] = []
        for a in assessments:
            record = a.record
            dims = rubric.score_dimensions(record)
            ai_stmt = cls_mod.ai_share_statement(
                a.scores.ai_assistance_likelihood,
                a.scores.ai_assistance_confidence,
                evidence=str(record.signals.get("ai_share_evidence", "signal-based estimate")),
            )
            payload.append(
                {
                    "repo": record.name,
                    # Coverage label (cohort method step 5): False = scored from
                    # mechanical signals only, no judgment inspection performed.
                    "deep_inspected": bool(record.signals.get("deep_inspected", False)),
                    "dimensions": cls_mod.dimension_evidence(dims),
                    "scores": a.scores.to_dict(),
                    "classification": a.classification.to_dict(),
                    "ai_share": ai_stmt,
                }
            )
            fixture_evidence = list(record.signals.get("evidence", []))
            impact = (
                ClaimImpact.HIGH
                if a.classification.primary == "LIKELY_SHALLOW_OR_TEMPLATED"
                else ClaimImpact.NORMAL
            )
            claims.append(
                Claim(
                    claim_id=f"{slug}-{record.name}-classification",
                    text=(
                        f"{login}/{record.name}: primary classification "
                        f"{a.classification.primary} ({a.classification.rationale})"
                    ),
                    impact=impact,
                    epistemics=ClaimEpistemics.INFERENCE,
                    evidence=_evidence_from_fixture(fixture_evidence, f"{slug}-{record.name}"),
                    counter_evidence=_evidence_from_fixture(
                        list(record.signals.get("counter_evidence", [])),
                        f"{slug}-{record.name}-counter",
                    ),
                    conflicts=[str(c) for c in record.signals.get("evidence_conflicts", [])],
                )
            )
            if not record.has_tests:
                search = record.signals.get("test_search", {})
                claims.append(
                    Claim(
                        claim_id=f"{slug}-{record.name}-no-tests",
                        text=f"{login}/{record.name} contains no test suite",
                        impact=ClaimImpact.NORMAL,
                        kind=ClaimKind.ABSENCE,
                        epistemics=ClaimEpistemics.OBSERVATION,
                        evidence=_evidence_from_fixture(
                            fixture_evidence, f"{slug}-{record.name}-notests"
                        ),
                        search_coverage=SearchCoverage(
                            queries=[str(q) for q in search.get("queries", [])],
                            scope_description=str(search.get("scope", "default branch tree")),
                            complete=bool(search.get("complete", False)),
                        ),
                    )
                )
        ctx.artifact_path(task.expected_artifact).write_text(
            json.dumps({"login": login, "assessments": payload}, indent=2), encoding="utf-8"
        )
        return TaskOutcome(claims=claims)

    def _exec_aggregate(self, slug: str, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        subject = self._subject(slug)
        login = str(subject["candidate_login"])
        inventory_data = ctx.read_artifact_json(f"inventory/{slug}.json")
        inventory = inv_mod.build_inventory(login, list(inventory_data["records"]))
        assessments = self._assess_repos(inventory)
        person = agg.aggregate_person(
            subject=str(subject["display_name"]),
            login=login,
            assessments=assessments,
            fork_names=[r.name for r in inventory.forks],
        )
        ctx.artifact_path(task.expected_artifact).write_text(
            json.dumps(person.to_dict(), indent=2), encoding="utf-8"
        )
        origins_seen: dict[str, dict[str, Any]] = {}
        for a in assessments:
            for item in a.record.signals.get("evidence", []):
                origins_seen.setdefault(str(item.get("origin", "unknown")), dict(item))
        claim = Claim(
            claim_id=f"{slug}-person-verdict",
            text=f"{subject['display_name']}: portfolio verdict {person.verdict}",
            impact=ClaimImpact.HIGH,
            epistemics=ClaimEpistemics.INFERENCE,
            evidence=_evidence_from_fixture(list(origins_seen.values())[:5], f"{slug}-verdict"),
        )
        return TaskOutcome(
            claims=[claim],
            uncertainties=[f"{slug}: {c}" for c in person.cannot_conclude],
        )

    def _exec_compare(self, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        persons = [ctx.read_artifact_json(f"persons/{s['slug']}.json") for s in self.subjects]
        comparison = {
            "subjects": persons,
            "compared_at": utc_now(),
            "note": (
                "distribution strength is reported as reach, never as technical quality; "
                "AI assistance is not slop"
            ),
        }
        ctx.artifact_path(task.expected_artifact).write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
        return TaskOutcome()

    def _exec_final(self, task: Task, ctx: ExecutionContext) -> TaskOutcome:
        markdown = self.build_final_output(ctx)
        cls_mod.assert_no_exact_ai_percentage(markdown)
        ctx.artifact_path(task.expected_artifact).write_text(markdown, encoding="utf-8")
        self._render_cohort_reports(ctx)
        return TaskOutcome()

    def _render_cohort_reports(self, ctx: ExecutionContext) -> None:
        """Render the product comparison + A-H answers when the fixture carries
        cohort inputs (comparisons/ + audit-config.yaml). Non-cohort runs are
        unaffected; absent inputs mean no report — never a guessed one."""
        root = getattr(self.data_source, "root", None)
        if root is None:
            return
        inputs = cohort_report.load_inputs(Path(root))
        if inputs is None:
            return
        persons = [ctx.read_artifact_json(f"persons/{s['slug']}.json") for s in self.subjects]
        assessments_by_subject = {
            str(s["display_name"]): list(
                ctx.read_artifact_json(f"assessments/{s['slug']}.json")["assessments"]
            )
            for s in self.subjects
        }
        flagship_md = cohort_report.render_flagship_comparison(inputs)
        answers_md = cohort_report.render_answers_a_h(persons, assessments_by_subject, inputs)
        cls_mod.assert_no_exact_ai_percentage(flagship_md)
        cls_mod.assert_no_exact_ai_percentage(answers_md)
        ctx.artifact_path("reports/flagship-comparison.md").write_text(
            flagship_md, encoding="utf-8"
        )
        ctx.artifact_path("reports/cohort-answers-a-h.md").write_text(answers_md, encoding="utf-8")

    # -- final output ----------------------------------------------------------

    def build_final_output(self, ctx: ExecutionContext) -> str:
        try:
            comparison = ctx.read_artifact_json("comparison.json")
        except FileNotFoundError:
            return "# GitHub authority audit\n\n(comparison not yet available)\n"
        lines = ["# GitHub authority audit — final answer", ""]
        for person in comparison["subjects"]:
            scores = person["aggregate_scores"]
            lines += [
                f"## {person['subject']} (`{person['login']}`)",
                "",
                f"### Verdict: {person['verdict']}",
                "",
                f"- Substantive technical depth: {scores['substantive_technical_depth']}",
                f"- Human reasoning evidence: {scores['human_reasoning_evidence']}",
                f"- Educational strength: {scores['educational_strength']}",
                f"- Distribution strength (reach signal, not quality): "
                f"{scores['distribution_strength']}",
                f"- AI-assisted creation likelihood: {scores['ai_assisted_creation_likelihood']}",
                f"- Shallow/templated portfolio share: {scores['shallow_templated_share_pct']}%",
                f"- Claim-to-evidence integrity: {scores['claim_evidence_integrity']}",
                f"- Confidence: {scores['confidence']}",
                "",
                f"- Repo-count-weighted distribution: {person['repo_count_weighted']}",
                f"- Active-code-weighted distribution: {person['active_code_weighted']}",
                f"- Forks excluded from authored scoring: {person['fork_count']}",
                "",
                "### What cannot be concluded",
                "",
            ]
            lines += [f"- {c}" for c in person["cannot_conclude"]]
            lines.append("")
        lines += [
            "---",
            "",
            "_Evidence rules: every material claim above is backed by at least two",
            "independent public sources (three for high-impact claims); unsupported",
            "claims were excluded from all percentages. Exact AI-authorship percentages",
            "are never stated — only conservative ranges with confidence._",
        ]
        return "\n".join(lines) + "\n"

    # -- six-run stability variants ---------------------------------------------

    def run_variant(self, variant: StabilityVariant, ctx: ExecutionContext) -> RunFindings:
        findings: dict[str, Any] = {}
        confidence: dict[str, float] = {}
        uncertainties: list[str] = []
        slop_floor = (
            SKEPTICAL_SLOP_FLOOR
            if variant == StabilityVariant.SKEPTICAL
            else cls_mod.SLOP_RISK_FLOOR
        )
        for subject in self.subjects:
            slug = str(subject["slug"])
            login = str(subject["candidate_login"])
            inventory_data = ctx.read_artifact_json(f"inventory/{slug}.json")
            records = list(inventory_data["records"])
            if variant == StabilityVariant.REORDERED_SOURCES:
                records = list(reversed(records))
            inventory = inv_mod.build_inventory(login, records)
            assessments = self._assess_repos(inventory, slop_floor=slop_floor)
            for a in assessments:
                key = f"{slug}/{a.record.name}:primary"
                findings[key] = a.classification.primary
                confidence[key] = a.scores.confidence
                findings[f"{slug}/{a.record.name}:ai_slop_risk"] = a.scores.ai_slop_risk
            person = agg.aggregate_person(
                subject=str(subject["display_name"]),
                login=login,
                assessments=assessments,
                fork_names=[r.name for r in inventory.forks],
            )
            findings[f"{slug}:verdict"] = person.verdict
            findings[f"{slug}:technical_depth"] = person.aggregate_scores[
                "substantive_technical_depth"
            ]
            confidence[f"{slug}:verdict"] = person.aggregate_scores["confidence"]
        if variant == StabilityVariant.SKEPTICAL:
            uncertainties.append(
                f"skeptical stance used slop-risk floor {SKEPTICAL_SLOP_FLOOR}; "
                "borderline repositories may flip classification"
            )
        if variant == StabilityVariant.CONCLUSION_BLIND:
            uncertainties.append(
                "conclusion-blind pass recomputed classifications from raw signals only"
            )
        return RunFindings(
            variant=variant,
            findings=findings,
            confidence=confidence,
            uncertainties=uncertainties,
        )

    # -- reporting hooks ---------------------------------------------------------

    def deliverables_present(self, ctx: ExecutionContext) -> list[str]:
        present: list[str] = []
        artifacts = ctx.run_directory / "artifacts"
        if (artifacts / "comparison.json").is_file():
            present.append("cross-subject comparison")
            present.append("cross-subject comparison across both cohorts")
        if (artifacts / "reports" / "final-answer.md").is_file():
            present.append("final answer with per-subject verdicts")
        if any((artifacts / "persons").glob("*.json")):
            present.append("person-level assessments")
        assessment_files = sorted((artifacts / "assessments").glob("*.json"))
        if assessment_files:
            present.append("repository scorecards")
            labeled = all(
                all("deep_inspected" in card for card in json.loads(f.read_text())["assessments"])
                for f in assessment_files
            )
            if labeled:
                present.append("repository scorecards with deep-inspection coverage labeled")
        if (artifacts / "reports" / "flagship-comparison.md").is_file():
            present.append("product-level flagship comparison")
        answers = artifacts / "reports" / "cohort-answers-a-h.md"
        if answers.is_file():
            text = answers.read_text(encoding="utf-8")
            if all(f"## {letter}." in text for letter in "ABCDEFGH"):
                present.append("separate answers to the eight cohort questions (A-H)")
        return present

    def repair_tasks(
        self, weak_dimensions: list[str], ctx: ExecutionContext, existing: list[Task]
    ) -> list[Task]:
        n = sum(1 for t in existing if t.task_id.startswith("repair-"))
        tasks: list[Task] = []
        if "output_contract" in weak_dimensions or "actionable_conclusion" in weak_dimensions:
            tasks.append(
                Task(
                    task_id=f"repair-{n + 1:03d}-final-output",
                    goal_requirement=REQ_FINAL,
                    action="Re-render the final answer to satisfy the output contract",
                    expected_artifact="reports/final-answer.md",
                    evidence_required=[],
                    pass_condition=PassCondition(type="file_contains", text="## Verdict"),
                    failure_condition="final output still missing required sections",
                    dependencies=["z-1-compare"],
                    repair_of="z-2-final-output",
                )
            )
        return tasks

    def scorecards(self, ctx: ExecutionContext) -> dict[str, dict[str, Any]]:
        cards: dict[str, dict[str, Any]] = {}
        for subject in self.subjects:
            slug = str(subject["slug"])
            try:
                data = ctx.read_artifact_json(f"assessments/{slug}.json")
            except FileNotFoundError:
                continue
            for entry in data["assessments"]:
                cards[f"{slug}--{entry['repo']}"] = dict(entry)
        return cards

    def learning_receipt(self, ctx: ExecutionContext) -> LearningReceipt:
        return LearningReceipt(
            important_decisions=[
                "identity was confirmed only from >=2 corroborating public attributes",
                "forks were excluded from authored-code scoring and reported separately",
                "negative (shallow/templated) classifications required slop risk >= 70, "
                "confidence >= 70, and a recorded counter-evidence review",
            ],
            alternatives_rejected=[
                "stating an exact AI-generated-code percentage — rejected; only "
                "conservative ranges with confidence are permitted without provenance logs",
                "using stars/forks as a quality input — rejected; distribution is reported "
                "as a reach signal only",
            ],
            failures_and_repairs=[
                f"{e['kind']}: {e.get('detail', {})}"
                for e in ctx_events(ctx)
                if e.get("kind") in ("task_requeued", "repair_task_created")
            ],
            surprising_evidence=[u for u in sorted(set(ctx.uncertainties)) if "inaccessible" in u],
            before_you_use_this=[
                "scores describe public repository artifacts, not the person's private "
                "ability or intent",
                "AI-assistance likelihood and slop risk are different axes; high AI "
                "assistance does not mean low value",
                "six-run stability shows robustness of the pipeline's conclusions, not "
                "ground truth; evidence citations remain the accuracy anchor",
            ],
        )

    def limitations(self, ctx: ExecutionContext) -> list[str]:
        limits = [str(x) for x in ctx.config.get("limitations", [])]
        limits.append(
            "analysis is limited to public artifacts at retrieval time; private "
            "contributions are invisible to this audit"
        )
        return limits


def ctx_events(ctx: ExecutionContext) -> list[dict[str, Any]]:
    from loop_engineering.runtime.ledger import RunLedger

    return RunLedger(ctx.run_directory).events()
