"""The run engine: drives one goal from locked contract to evidence pack.

Deterministic control flow only — planning content and task execution live in
use-case modules behind the UseCase protocol. The engine enforces:
one task at a time, independent verification after every task, loop2 at stage
boundaries, loop3 over claims, loop4 six-variant stability when required,
the E2E review gates, automatic repair below 70, budgets, duplicate detection,
circuit breakers, checkpoints, and crash-safe resume.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from loop_engineering.contracts import goal_contract
from loop_engineering.domain.errors import (
    BudgetExhausted,
    CircuitOpen,
    LoopEngineeringError,
)
from loop_engineering.domain.models import (
    Claim,
    RunState,
    RunStatus,
    StabilityVariant,
    Task,
    TaskStatus,
    VerificationResult,
    utc_now,
)
from loop_engineering.planning import planner
from loop_engineering.recovery.controller import RecoveryController
from loop_engineering.reporting import metrics as metrics_mod
from loop_engineering.reporting.evidence_pack import LearningReceipt, PackInputs, build_pack
from loop_engineering.runtime.budget import Budget
from loop_engineering.runtime.checkpoint import (
    latest_checkpoint,
    load_tasks_from_checkpoint,
    normalize_for_resume,
    write_checkpoint,
)
from loop_engineering.runtime.circuit_breaker import CircuitBreaker, write_blocking_report
from loop_engineering.runtime.ledger import RunLedger, append_jsonl, read_jsonl
from loop_engineering.runtime.state import atomic_write_json, load_state, run_dir, save_state
from loop_engineering.runtime.task_queue import TaskQueue
from loop_engineering.verification import (
    e2e_reviewer,
    loop1_task,
    loop2_drift,
    loop3_evidence,
    loop4_stability,
)


class SimulatedInterruption(LoopEngineeringError):
    """Raised by the interruption demo to model a hard crash mid-run."""


@dataclass
class TaskOutcome:
    """What a use case reports back after executing one task.

    Artifacts and evidence are written to disk by the use case; the outcome
    only carries claims and notes. The executor's notes are never proof.
    """

    claims: list[Claim] = field(default_factory=list)
    notes: str = ""
    uncertainties: list[str] = field(default_factory=list)


@dataclass
class ExecutionContext:
    contract: dict[str, Any]
    run_directory: Path
    config: dict[str, Any] = field(default_factory=dict)
    claims: list[Claim] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    def artifact_path(self, relative: str) -> Path:
        path = self.run_directory / "artifacts" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def evidence_path(self, relative: str) -> Path:
        path = self.run_directory / "evidence" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def read_artifact_json(self, relative: str) -> Any:
        with (self.run_directory / "artifacts" / relative).open(encoding="utf-8") as fh:
            return json.load(fh)


class UseCase(Protocol):
    """What a use case must provide. New use cases plug in here — the runtime
    is never rewritten."""

    name: str

    def build_plan(self, contract: dict[str, Any], config: dict[str, Any]) -> list[Task]: ...

    def execute_task(self, task: Task, ctx: ExecutionContext) -> TaskOutcome: ...

    def stage_of(self, task: Task) -> str: ...

    def build_final_output(self, ctx: ExecutionContext) -> str: ...

    def run_variant(
        self, variant: StabilityVariant, ctx: ExecutionContext
    ) -> loop4_stability.RunFindings: ...

    def deliverables_present(self, ctx: ExecutionContext) -> list[str]: ...

    def repair_tasks(
        self, weak_dimensions: list[str], ctx: ExecutionContext, existing: list[Task]
    ) -> list[Task]: ...

    def scorecards(self, ctx: ExecutionContext) -> dict[str, dict[str, Any]]: ...

    def learning_receipt(self, ctx: ExecutionContext) -> LearningReceipt: ...

    def limitations(self, ctx: ExecutionContext) -> list[str]: ...


@dataclass
class RunResult:
    state: RunState
    gate_a: e2e_reviewer.GateAResult | None
    gate_b: e2e_reviewer.GateBResult | None
    pack_dir: Path | None
    verifications: list[VerificationResult]

    @property
    def delivered(self) -> bool:
        return self.pack_dir is not None


MAX_REPAIR_ROUNDS = 3


class Engine:
    def __init__(
        self,
        contract: dict[str, Any],
        use_case: UseCase,
        runs_root: str | Path,
        config: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        goal_contract.verify_integrity(contract)
        self.contract = contract
        self.use_case = use_case
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
        self.run_directory = run_dir(runs_root, str(contract["goal_id"]), self.run_id)
        self.ledger = RunLedger(self.run_directory)
        self.breaker = CircuitBreaker(self.run_directory)
        self.budget = Budget.from_contract(contract)
        self.ctx = ExecutionContext(
            contract=contract, run_directory=self.run_directory, config=dict(config or {})
        )
        self.verifications: list[VerificationResult] = []
        self.queue: TaskQueue | None = None
        self.state = RunState(
            goal_id=str(contract["goal_id"]),
            run_id=self.run_id,
            contract_digest=str(contract["canonical_digest"]),
            status=RunStatus.CREATED,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        goal_contract.save(contract, self.run_directory / "contract.yaml")
        save_state(self.run_directory, self.state)

    # -- construction from disk (resume) ------------------------------------

    @classmethod
    def resume(
        cls, run_directory: str | Path, use_case: UseCase, config: dict[str, Any] | None = None
    ) -> Engine:
        run_path = Path(run_directory)
        contract = goal_contract.load(run_path / "contract.yaml")
        engine = cls.__new__(cls)
        engine.contract = contract
        engine.use_case = use_case
        engine.run_id = run_path.name
        engine.run_directory = run_path
        engine.ledger = RunLedger(run_path)
        engine.breaker = CircuitBreaker(run_path)
        engine.budget = Budget.from_contract(contract)
        engine.ctx = ExecutionContext(
            contract=contract, run_directory=run_path, config=dict(config or {})
        )
        engine.verifications = engine._load_verifications()
        engine.state = load_state(run_path)

        checkpoint = latest_checkpoint(run_path)
        if checkpoint is None:
            raise LoopEngineeringError(f"no checkpoint to resume from in {run_path}")
        tasks = load_tasks_from_checkpoint(checkpoint)
        reset = normalize_for_resume(tasks)
        engine.queue = TaskQueue(tasks, engine.ledger)
        engine.ctx.claims = engine._load_claims()
        engine.state.status = RunStatus.RUNNING
        engine.state.flags.append(f"resumed:{utc_now()}")
        save_state(run_path, engine.state)
        engine.ledger.record_event("resumed", {"reset_tasks": reset})
        return engine

    # -- persistence helpers -------------------------------------------------

    def _persist_claims(self, claims: list[Claim], task_id: str) -> None:
        for claim in claims:
            record = claim.to_dict()
            record["_produced_by_task"] = task_id
            append_jsonl(self.run_directory / "evidence" / "claims.jsonl", record)

    def _load_claims(self) -> list[Claim]:
        records = read_jsonl(self.run_directory / "evidence" / "claims.jsonl")
        return [Claim.from_dict(r) for r in records]

    def _persist_verification(self, result: VerificationResult) -> None:
        self.verifications.append(result)
        append_jsonl(self.run_directory / "verifications" / "results.jsonl", result.to_dict())

    def _load_verifications(self) -> list[VerificationResult]:
        out: list[VerificationResult] = []
        for r in read_jsonl(self.run_directory / "verifications" / "results.jsonl"):
            out.append(
                VerificationResult(
                    verification_id=str(r["verification_id"]),
                    loop=str(r["loop"]),
                    subject_id=str(r["subject_id"]),
                    verifier_role=str(r["verifier_role"]),
                    executor_role=r.get("executor_role"),
                    passed=bool(r["passed"]),
                    checks=[],
                    artifact_digest=r.get("artifact_digest"),
                    failure_reason=r.get("failure_reason"),
                    verified_at=str(r["verified_at"]),
                )
            )
        return out

    def _checkpoint(self, label: str) -> None:
        assert self.queue is not None
        write_checkpoint(self.run_directory, self.state, self.queue.all_tasks(), label)

    def _block(self, reason: str, unblock: str) -> None:
        self.state.status = RunStatus.BLOCKED
        self.state.blocked_reason = reason
        self.state.unblock_requirement = unblock
        save_state(self.run_directory, self.state)
        self.ledger.record_event("blocked", {"reason": reason, "unblock": unblock})

    # -- planning ------------------------------------------------------------

    def plan(self) -> list[Task]:
        tasks = self.use_case.build_plan(self.contract, self.ctx.config)
        planner.validate_plan(self.contract, tasks)
        self.queue = TaskQueue(tasks, self.ledger)
        self.state.status = RunStatus.PLANNED
        save_state(self.run_directory, self.state)
        atomic_write_json(self.run_directory / "plan.json", [t.to_dict() for t in tasks])
        self._checkpoint("planned")
        self.ledger.record_event("planned", {"task_count": len(tasks)})
        return tasks

    # -- main loop -----------------------------------------------------------

    def run(self, interrupt_after: int | None = None) -> RunResult:
        if self.queue is None:
            self.plan()
        assert self.queue is not None
        self.state.status = RunStatus.RUNNING
        save_state(self.run_directory, self.state)
        try:
            gate_a, gate_b = self._run_to_review(interrupt_after)
        except SimulatedInterruption:
            self.state.status = RunStatus.INTERRUPTED
            save_state(self.run_directory, self.state)
            self.ledger.record_event("interrupted", {"simulated": True})
            raise
        except BudgetExhausted as exc:
            self.breaker_budget(exc)
            raise
        except CircuitOpen as exc:
            self._block(exc.reason, exc.unblock_requirement)
            raise

        pack_dir: Path | None = None
        if gate_b is not None and gate_b.verdict.value in (
            "GOAL_MATCH",
            "GOAL_MATCH_WITH_CAVEATS",
        ):
            pack_dir = self._finalize_success(gate_a, gate_b)
        else:
            self._finalize_not_delivered(gate_a, gate_b)
        return RunResult(
            state=self.state,
            gate_a=gate_a,
            gate_b=gate_b,
            pack_dir=pack_dir,
            verifications=self.verifications,
        )

    def breaker_budget(self, exc: BudgetExhausted) -> None:
        write_blocking_report(
            self.run_directory,
            f"budget exhausted: {exc}",
            "increase the budget in a new contract version or accept partial output",
        )
        self._block(str(exc), "increase budget via a new contract version")

    def _run_to_review(
        self, interrupt_after: int | None
    ) -> tuple[e2e_reviewer.GateAResult, e2e_reviewer.GateBResult]:
        assert self.queue is not None
        executed = 0
        repair_rounds = 0
        recovery = RecoveryController(self.queue, self.breaker, self.ledger)

        while True:
            executed = self._execute_pending_tasks(recovery, interrupt_after, executed)
            self._verify_stage("all-tasks", recovery)
            evidence_cov = self._verify_claims()
            final_output = self.use_case.build_final_output(self.ctx)
            (self.run_directory / "artifacts" / "final-output.md").write_text(
                final_output, encoding="utf-8"
            )
            stability = self._verify_stability()
            gate_a, gate_b = self._e2e_review(evidence_cov, stability)
            if not gate_b.repair_needed:
                return gate_a, gate_b
            repair_rounds += 1
            if repair_rounds > MAX_REPAIR_ROUNDS:
                self.breaker.human_required(
                    f"goal-match score {gate_b.score} still below 70 after "
                    f"{MAX_REPAIR_ROUNDS} automatic repair rounds; human decision required"
                )
            weak = e2e_reviewer.repair_targets(self._last_gate_b_inputs, gate_b)
            new_tasks = self.use_case.repair_tasks(weak, self.ctx, self.queue.all_tasks())
            if not new_tasks:
                self.breaker.human_required(
                    f"goal-match score {gate_b.score} below 70 and the use case has no "
                    "further automatic repair available; human decision required"
                )
            self.state.status = RunStatus.REPAIRING
            save_state(self.run_directory, self.state)
            for task in new_tasks:
                recovery.create_repair_task_from(task)
            self.ledger.record_event(
                "auto_repair_round",
                {"round": repair_rounds, "added": [t.task_id for t in new_tasks]},
            )

    def _execute_pending_tasks(
        self, recovery: RecoveryController, interrupt_after: int | None, executed: int
    ) -> int:
        assert self.queue is not None
        while not self.queue.complete():
            task = self.queue.next_task()
            if task is None:
                pending = [
                    t.task_id
                    for t in self.queue.all_tasks()
                    if t.status not in (TaskStatus.VERIFIED, TaskStatus.SKIPPED_WITH_REASON)
                ]
                if pending:
                    self.breaker.human_required(
                        f"tasks {pending} cannot become ready (unsatisfiable dependencies)"
                    )
                break
            self.state.current_task_id = task.task_id
            save_state(self.run_directory, self.state)
            self.budget.charge(iterations=1)
            self.state.iterations += 1
            self.breaker.check_duplicate_action(task.action, {"task_id": task.task_id})
            self.queue.transition(task.task_id, TaskStatus.RUNNING, actor="executor")
            try:
                outcome = self.use_case.execute_task(task, self.ctx)
            except SimulatedInterruption:
                raise
            except LoopEngineeringError as exc:
                self.queue.transition(
                    task.task_id, TaskStatus.FAILED, detail=str(exc), actor="executor"
                )
                recovery.handle_task_failure(task, str(exc))
                continue
            self.queue.transition(task.task_id, TaskStatus.EXECUTED, actor="executor")
            # Persist immediately: a crash between execution and verification
            # must leave the EXECUTED-but-unverified status visible to resume.
            self._checkpoint(f"executed-{task.task_id}")
            executed += 1
            if interrupt_after is not None and executed >= interrupt_after:
                # Model a hard crash after execution, before verification:
                # the resumed run must redo this task, not trust it.
                raise SimulatedInterruption(
                    f"simulated crash after task {task.task_id} executed (pre-verification)"
                )

            result = loop1_task.verify_task(task, self.run_directory)
            self._persist_verification(result)
            if result.passed:
                self.queue.transition(
                    task.task_id, TaskStatus.VERIFIED, actor=loop1_task.VERIFIER_ROLE
                )
                self._persist_claims(outcome.claims, task.task_id)
                self.ctx.claims.extend(outcome.claims)
                self.ctx.uncertainties.extend(outcome.uncertainties)
                # Loop 2 runs after every workstream/stage: fire it the moment
                # this task's stage has no non-terminal tasks left.
                stage = self.use_case.stage_of(task)
                stage_tasks = [
                    t for t in self.queue.all_tasks() if self.use_case.stage_of(t) == stage
                ]
                if all(
                    t.status in (TaskStatus.VERIFIED, TaskStatus.SKIPPED_WITH_REASON)
                    for t in stage_tasks
                ):
                    self._verify_stage(stage, recovery)
            else:
                self.queue.transition(
                    task.task_id,
                    TaskStatus.FAILED,
                    detail=result.failure_reason or "verification failed",
                    actor=loop1_task.VERIFIER_ROLE,
                )
                recovery.handle_task_failure(task, result.failure_reason or "verification failed")
            self.breaker.record_action(
                task.action, {"task_id": task.task_id}, result.artifact_digest
            )
            verified_ids = ",".join(t.task_id for t in self.queue.by_status(TaskStatus.VERIFIED))
            self.breaker.record_iteration(verified_ids)
            self._checkpoint(f"after-{task.task_id}")
        return executed

    # -- verification stages ---------------------------------------------------

    def _verify_stage(self, stage: str, recovery: RecoveryController) -> None:
        assert self.queue is not None
        result = loop2_drift.verify_plan(
            self.contract, self.queue.all_tasks(), recovery.plan_changes, stage=stage
        )
        self._persist_verification(result)
        if not result.passed:
            self.breaker.human_required(
                f"goal-drift verification failed at stage {stage}: {result.failure_reason}"
            )

    def _verify_claims(self) -> loop3_evidence.EvidenceCoverage:
        results, coverage = loop3_evidence.verify_claims(self.ctx.claims)
        for r in results:
            self._persist_verification(r)
        self.ledger.record_event("evidence_verified", coverage.to_dict())
        return coverage

    def _verify_stability(self) -> loop4_stability.StabilityReport | None:
        if int(self.contract.get("replication_count", 1)) < len(loop4_stability.REQUIRED_VARIANTS):
            return None
        runs = [
            self.use_case.run_variant(variant, self.ctx)
            for variant in loop4_stability.REQUIRED_VARIANTS
        ]
        result, report = loop4_stability.verify_stability(runs)
        self._persist_verification(result)
        atomic_write_json(self.run_directory / "verifications" / "stability.json", report.to_dict())
        return report

    _last_gate_b_inputs: e2e_reviewer.GateBInputs

    def _e2e_review(
        self,
        evidence_cov: loop3_evidence.EvidenceCoverage,
        stability: loop4_stability.StabilityReport | None,
    ) -> tuple[e2e_reviewer.GateAResult, e2e_reviewer.GateBResult]:
        assert self.queue is not None
        tasks = self.queue.all_tasks()
        stability_required = int(self.contract.get("replication_count", 1)) >= len(
            loop4_stability.REQUIRED_VARIANTS
        )
        gate_a = e2e_reviewer.review_process(
            self.state, tasks, self.verifications, self.run_directory, stability_required
        )
        cov = planner.coverage(self.contract, tasks)
        expected = [str(d) for d in self.contract["expected_output"]["deliverables"]]
        final_output = self.use_case.build_final_output(self.ctx)
        inputs = e2e_reviewer.GateBInputs(
            requirements_total=len(cov.covered_requirements) + len(cov.uncovered_requirements),
            requirements_covered=len(cov.covered_requirements),
            deliverables_expected=expected,
            deliverables_present=self.use_case.deliverables_present(self.ctx),
            north_star_captured="north_star_metric" in self.contract,
            scope_violations=len(cov.orphan_task_ids),
            evidence_coverage=evidence_cov,
            uncertainty_disclosed="cannot be concluded" in final_output.lower()
            or "uncertaint" in final_output.lower(),
            actionable_conclusion="## Verdict" in final_output,
        )
        self._last_gate_b_inputs = inputs
        gate_b = e2e_reviewer.score_goal_match(inputs, gate_a)
        self._persist_verification(e2e_reviewer.as_verification_result(gate_a, gate_b))
        self._stability_report = stability
        self._evidence_cov = evidence_cov
        return gate_a, gate_b

    # -- finalization ----------------------------------------------------------

    _stability_report: loop4_stability.StabilityReport | None = None
    _evidence_cov: loop3_evidence.EvidenceCoverage | None = None

    def _finalize_success(
        self, gate_a: e2e_reviewer.GateAResult, gate_b: e2e_reviewer.GateBResult
    ) -> Path:
        assert self.queue is not None
        assert self._evidence_cov is not None
        self.state.status = RunStatus.COMPLETE
        self.state.current_task_id = None
        save_state(self.run_directory, self.state)
        self._checkpoint("complete")

        verdict = gate_b.verdict
        ns = metrics_mod.north_star(self.contract, self.state, verdict)
        leading = metrics_mod.leading_metrics(
            tasks=self.queue.all_tasks(),
            verifications=self.verifications,
            state=self.state,
            actions=self.breaker.actions,
            evidence=self._evidence_cov,
            stability=self._stability_report,
            goal_match_score=gate_b.score,
        )
        cov = planner.coverage(self.contract, self.queue.all_tasks())
        pack = PackInputs(
            contract=self.contract,
            state=self.state,
            tasks=self.queue.all_tasks(),
            verifications=self.verifications,
            claims=self.ctx.claims,
            evidence_coverage=self._evidence_cov,
            coverage=cov,
            gate_a=gate_a,
            gate_b=gate_b,
            north_star=ns,
            leading=leading,
            final_output_markdown=self.use_case.build_final_output(self.ctx),
            learning_receipt=self.use_case.learning_receipt(self.ctx),
            stability=self._stability_report,
            scorecards=self.use_case.scorecards(self.ctx),
            unresolved_uncertainties=sorted(set(self.ctx.uncertainties)),
            limitations=self.use_case.limitations(self.ctx),
            run_directory=self.run_directory,
        )
        outputs_root = Path(self.ctx.config.get("outputs_root", "outputs"))
        pack_dir = build_pack(pack, outputs_root)
        self.ledger.record_event(
            "run_complete",
            {"verdict": verdict.value, "score": gate_b.score, "pack": str(pack_dir)},
        )
        return pack_dir

    def _finalize_not_delivered(
        self,
        gate_a: e2e_reviewer.GateAResult | None,
        gate_b: e2e_reviewer.GateBResult | None,
    ) -> None:
        self.state.status = RunStatus.FAILED
        save_state(self.run_directory, self.state)
        detail = {
            "gate_a": gate_a.verdict.value if gate_a else None,
            "gate_b": gate_b.verdict.value if gate_b else None,
            "score": gate_b.score if gate_b else None,
        }
        write_blocking_report(
            self.run_directory,
            f"run finished without a deliverable verdict: {detail}",
            "review the end-to-end report; the output must not be delivered as success",
        )
        self.ledger.record_event("run_not_delivered", detail)
