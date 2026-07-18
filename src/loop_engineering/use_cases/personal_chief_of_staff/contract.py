"""Personal Operating Contract — the locked context that every brief,
recommendation, and action is checked against (context-drift protection).

The contract is data, versioned and approver-stamped. Prohibited actions
fail closed: an action matching a prohibited pattern is blocked regardless
of any priority score. Goals, approved priorities, rejected ideas, and
terminology are the anchors used to detect drift before output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from loop_engineering.use_cases.personal_chief_of_staff.models import Goal

# Actions that ALWAYS require explicit per-action approval. Matched against an
# ActionProposal.action_type; if it matches, execution is blocked in
# safe-execution mode. Fail-closed: unknown high-risk verbs are treated as
# requiring approval by the executor, this list is the explicit floor.
PROHIBITED_WITHOUT_APPROVAL = (
    "send_email",
    "forward_email",
    "cancel_meeting",
    "move_external_meeting",
    "delete_data",
    "publish_content",
    "apply_to_job",
    "submit_conference_application",
    "create_external_commitment",
    "merge_code",
    "destructive_github",
    "linkedin_publish",
)

# The default locked goal registry (PD: current top-level goals). Amendable
# later through the versioned goal-contract flow (approver + reason + version).
DEFAULT_GOALS: tuple[Goal, ...] = (
    Goal(
        id="G1",
        title="Land a Principal/Director/Sr Director AI Product role",
        outcome="Signed offer for a senior AI PM role",
        priority=1,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G2",
        title="Complete Production Engineering OS V3 and pm-evals Web",
        outcome="Both shipped and usable",
        priority=2,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G3",
        title="Complete and meaningfully package existing technical products",
        outcome="Existing products packaged, documented, installable",
        priority=3,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G4",
        title="Build visible technical authority and distribution",
        outcome="Growing audience and cited work",
        priority=4,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G5",
        title="Secure conference, podcast, community, and institute speaking",
        outcome="Confirmed speaking engagements",
        priority=5,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G6",
        title="Complete existing work without unnecessary new repositories",
        outcome="Finished work, no repo sprawl",
        priority=6,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
    Goal(
        id="G7",
        title="Maintain health, personal commitments, sustainable capacity",
        outcome="Sustainable daily rhythm honored",
        priority=7,
        status="active",
        source="operating_contract",
        approved_at="2026-07-17T00:00:00+00:00",
    ),
)


@dataclass
class OperatingContract:
    version: int = 1
    approved_by: str = "abhillash"
    approved_at: str = "2026-07-17T00:00:00+00:00"
    goals: list[Goal] = field(default_factory=lambda: list(DEFAULT_GOALS))
    approved_priorities: list[str] = field(
        default_factory=lambda: [
            "external deadlines and commitments",
            "interviews, applications, recruiters, job-search outcomes",
            "completion of meaningful products and projects",
            "speaking, distribution, and authority-building",
            "blocked dependencies and people waiting",
            "administration and maintenance",
        ]
    )
    decisions: list[str] = field(default_factory=list)
    rejected_ideas: list[str] = field(
        default_factory=lambda: [
            "creating new repositories for work that fits an existing repo",
            "automatic LinkedIn publishing",
        ]
    )
    terminology: dict[str, str] = field(
        default_factory=lambda: {
            "PEOS": "Production Engineering OS",
            "authority": "public technical credibility and distribution",
        }
    )
    project_boundaries: list[str] = field(
        default_factory=lambda: [
            "no new repositories without explicit approval",
            "cohort audit and completed audits are frozen — do not modify",
        ]
    )
    prohibited_actions: list[str] = field(default_factory=lambda: list(PROHIBITED_WITHOUT_APPROVAL))
    ownership_boundaries: list[str] = field(
        default_factory=lambda: ["never act on behalf of another person without approval"]
    )
    open_questions: list[str] = field(default_factory=list)
    response_preferences: dict[str, str] = field(
        default_factory=lambda: {
            "planning": "realistic, no overscheduling",
            "tone": "direct, source-backed, honest about uncertainty",
        }
    )
    confirm_threshold: float = 0.6  # tasks below this confidence need confirmation

    def is_prohibited(self, action_type: str) -> bool:
        return action_type in set(self.prohibited_actions)

    def goal_ids(self) -> set[str]:
        return {g.id for g in self.goals}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["goals"] = [g.to_dict() for g in self.goals]
        return d
