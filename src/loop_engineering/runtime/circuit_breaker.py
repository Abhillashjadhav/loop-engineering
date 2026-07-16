"""Circuit breakers (spec §8).

Trip conditions:
- same action repeated twice without new evidence;
- same failure repeated twice;
- no measurable progress across three iterations;
- task maximum attempts reached;
- budget exhausted;
- unsafe or forbidden action requested;
- required public source inaccessible;
- identity cannot be confidently resolved;
- human decision or credentials required.

A tripped breaker never terminates silently: it writes a blocking report with
the exact unblock requirement and raises CircuitOpen.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from loop_engineering.domain.errors import CircuitOpen
from loop_engineering.domain.models import Task, utc_now
from loop_engineering.runtime.duplicate_detection import ActionRegistry

BLOCKING_REPORT = "BLOCKED.md"


def write_blocking_report(
    run_directory: str | Path, reason: str, unblock_requirement: str, context: str = ""
) -> Path:
    path = Path(run_directory) / "reports" / BLOCKING_REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Run blocked\n\n"
        f"- **When:** {utc_now()}\n"
        f"- **Reason:** {reason}\n"
        f"- **Exact unblock requirement:** {unblock_requirement}\n"
    )
    if context:
        body += f"\n## Context\n\n{context}\n"
    path.write_text(body, encoding="utf-8")
    return path


class CircuitBreaker:
    """Aggregates trip conditions for one run."""

    def __init__(
        self,
        run_directory: str | Path,
        no_progress_limit: int = 3,
        same_failure_limit: int = 2,
    ) -> None:
        self.run_directory = Path(run_directory)
        self.no_progress_limit = no_progress_limit
        self.same_failure_limit = same_failure_limit
        self.actions = ActionRegistry()
        self._failure_counts: dict[str, int] = {}
        self._progress_marks: list[str] = []
        self._stagnant_iterations = 0

    def _trip(self, reason: str, unblock: str, context: str = "") -> None:
        write_blocking_report(self.run_directory, reason, unblock, context)
        raise CircuitOpen(reason, unblock)

    # -- conditions ---------------------------------------------------------

    def check_duplicate_action(self, action: str, params: dict[str, object]) -> None:
        if self.actions.is_repeat_without_new_evidence(action, dict(params)):
            self._trip(
                f"action repeated twice without new evidence: {action}",
                "change the approach or provide new evidence before retrying this action",
            )

    def record_action(
        self, action: str, params: dict[str, object], evidence_digest: str | None
    ) -> None:
        self.actions.record(action, dict(params), evidence_digest)

    def record_failure(self, failure_signature: str) -> None:
        key = hashlib.sha256(failure_signature.encode("utf-8")).hexdigest()[:16]
        self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
        if self._failure_counts[key] >= self.same_failure_limit:
            self._trip(
                f"same failure repeated {self._failure_counts[key]} times: {failure_signature}",
                "diagnose the root cause; a different repair strategy or human input is required",
            )

    def record_iteration(self, progress_mark: str) -> None:
        """progress_mark should change when measurable progress happened
        (e.g. digest of verified-task ids)."""
        if self._progress_marks and self._progress_marks[-1] == progress_mark:
            self._stagnant_iterations += 1
        else:
            self._stagnant_iterations = 0
        self._progress_marks.append(progress_mark)
        if self._stagnant_iterations >= self.no_progress_limit:
            self._trip(
                f"no measurable progress across {self._stagnant_iterations + 1} iterations",
                "the loop is stalled; human review of the blocking task is required",
            )

    def check_task_attempts(self, task: Task) -> None:
        if task.attempts >= task.max_attempts:
            self._trip(
                f"task {task.task_id} reached max attempts ({task.max_attempts})",
                f"human decision required on task {task.task_id}: "
                "amend the plan, relax the pass condition with approval, or skip with reason",
            )

    def budget_exhausted(self, detail: str) -> None:
        self._trip(
            f"budget exhausted: {detail}",
            "increase the budget in a new contract version or accept partial output",
        )

    def forbidden_action(self, action: str) -> None:
        self._trip(
            f"unsafe or forbidden action requested: {action}",
            "the contract forbids this action; a contract amendment with explicit "
            "user approval is required",
        )

    def source_inaccessible(self, source: str) -> None:
        self._trip(
            f"required public source inaccessible: {source}",
            f"provide access to {source} or supply an equivalent evidence snapshot",
        )

    def identity_unresolved(self, subject: str, detail: str) -> None:
        self._trip(
            f"identity cannot be confidently resolved for subject: {subject} ({detail})",
            "provide at least two corroborating public profile attributes for the subject",
        )

    def human_required(self, what: str) -> None:
        self._trip(
            f"human decision or credentials required: {what}",
            what,
        )
