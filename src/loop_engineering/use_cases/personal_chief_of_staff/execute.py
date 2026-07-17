"""Safe execution + approval gates (fail closed).

Safe actions (drafts, briefs, issue proposals, reminders, focus-block
proposals) execute automatically. Anything that reaches outside — send,
forward, cancel, move external meeting, delete, publish, apply, submit,
merge, destructive GitHub, LinkedIn publish — is prohibited without explicit
approval and is blocked here regardless of any priority score. Focus-block
creation is gated behind exactly one schedule approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import CalendarAdapter
from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    ActionProposal,
    ApprovalRequirement,
    ProposalStatus,
)
from loop_engineering.use_cases.personal_chief_of_staff.schedule import ProposedSchedule

# Safe action types that never leave the local workspace.
SAFE_ACTIONS = {
    "gmail_draft",
    "meeting_brief",
    "focus_block_proposal",
    "reminder",
    "github_issue_proposal",
    "project_recovery_prompt",
    "document_action_extract",
    "interview_prep_session",
    "speaking_followup_draft",
    "waiting_on_followup_draft",
}


class ProhibitedActionError(RuntimeError):
    """A prohibited action was attempted without explicit approval."""


@dataclass
class ExecutionResult:
    executed: list[ActionProposal] = field(default_factory=list)
    blocked: list[ActionProposal] = field(default_factory=list)
    requires_approval: list[ActionProposal] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "executed": [a.to_dict() for a in self.executed],
            "blocked": [a.to_dict() for a in self.blocked],
            "requires_approval": [a.to_dict() for a in self.requires_approval],
        }


def classify_requirement(action_type: str, contract: OperatingContract) -> ApprovalRequirement:
    """Fail closed: prohibited types need explicit approval; only the known
    SAFE_ACTIONS are auto-executable; everything else also needs approval."""
    if contract.is_prohibited(action_type):
        return ApprovalRequirement.EXPLICIT
    if action_type in SAFE_ACTIONS:
        return ApprovalRequirement.NONE
    return ApprovalRequirement.EXPLICIT


def execute_safe(proposals: list[ActionProposal], contract: OperatingContract) -> ExecutionResult:
    """Execute only safe proposals; queue/blocks everything requiring approval.

    A prohibited action can never be auto-executed here — it is recorded as
    blocked with status BLOCKED_PROHIBITED. This is the fail-closed gate.
    """
    result = ExecutionResult()
    for p in proposals:
        requirement = classify_requirement(p.action_type, contract)
        if contract.is_prohibited(p.action_type):
            p.status = ProposalStatus.BLOCKED_PROHIBITED
            p.execution_evidence = (
                "blocked: prohibited action requires explicit user approval "
                "(never auto-executed regardless of priority)"
            )
            result.blocked.append(p)
            continue
        if requirement is ApprovalRequirement.NONE:
            p.status = ProposalStatus.EXECUTED
            p.execution_evidence = f"safe action performed locally: {p.action_type} → {p.target}"
            result.executed.append(p)
        else:
            p.status = ProposalStatus.PROPOSED
            result.requires_approval.append(p)
    return result


def approve_and_create_focus_blocks(
    schedule: ProposedSchedule,
    calendar: CalendarAdapter,
    approved: bool,
) -> list[str]:
    """Create focus blocks — ONLY when the schedule has been approved once.

    Returns the created event ids. Raises if called without approval, so a
    focus block can never be created without the single explicit approval.
    """
    if not approved:
        raise ProhibitedActionError(
            "focus blocks require one explicit schedule approval before creation"
        )
    created: list[str] = []
    for block in schedule.blocks:
        event_id = calendar.create_focus_block(block.to_calendar_item())
        created.append(event_id)
    return created
