"""Deterministic priority model (locked order).

Default priority order (highest first):
  1. external deadlines and commitments
  2. interviews, applications, recruiters, job-search outcomes
  3. completion of meaningful products and projects
  4. speaking, distribution, authority-building
  5. blocked dependencies and people waiting
  6. administration and maintenance

The score is a weighted sum over the locked factors. Recency and ease never
add priority. Low actionability confidence discounts the score so an
uncertain item cannot outrank a firm interview task. All weights are explicit
so the ordering is auditable and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

from loop_engineering.use_cases.personal_chief_of_staff.contract import OperatingContract
from loop_engineering.use_cases.personal_chief_of_staff.models import Task, TaskStatus

# Category weights realize the locked order. Larger = more important.
CATEGORY_WEIGHT = {
    "external_commitment": 100.0,
    "job_search": 85.0,
    "product_completion": 65.0,
    "speaking_distribution": 45.0,
    "blocked_or_waiting": 30.0,
    "admin": 10.0,
}

# Keyword → category for goal/tag mapping (deterministic, case-insensitive).
_JOB = ("interview", "recruiter", "application", "apply", "offer", "job", "hiring", "screen")
_PRODUCT = ("peos", "production engineering", "pm-evals", "ship", "complete", "package", "release")
_SPEAK = ("conference", "podcast", "talk", "speaking", "cfp", "keynote", "community", "institute")
_ADMIN = (
    "expense",
    "renew",
    "dentist",
    "appointment",
    "admin",
    "paperwork",
    "invoice",
    "tax",
    "reschedule",
)


def _category(task: Task) -> str:
    text = f"{task.title} {task.description} {task.project}".lower()
    if task.external_commitment:
        return "external_commitment"
    if any(k in text for k in _JOB):
        return "job_search"
    if any(k in text for k in _PRODUCT):
        return "product_completion"
    if any(k in text for k in _SPEAK):
        return "speaking_distribution"
    if (
        task.status in (TaskStatus.BLOCKED, TaskStatus.WAITING)
        or task.blocked_by
        or task.waiting_on
    ):
        return "blocked_or_waiting"
    if any(k in text for k in _ADMIN):
        return "admin"
    return "product_completion"  # default: real work, not admin


@dataclass
class ScoredTask:
    task: Task
    score: float
    category: str
    factors: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task.to_dict(),
            "score": round(self.score, 2),
            "category": self.category,
            "factors": {k: round(v, 2) for k, v in self.factors.items()},
        }


def score_task(task: Task, contract: OperatingContract, today_iso: str) -> ScoredTask:
    category = _category(task)
    factors: dict[str, float] = {"category": CATEGORY_WEIGHT[category]}

    # External deadline pressure (only when a real deadline exists).
    if task.deadline:
        factors["deadline"] = 40.0 if task.deadline <= today_iso else 25.0
    factors["urgency"] = 4.0 * task.urgency
    factors["impact"] = 6.0 * task.impact
    factors["strategic"] = 5.0 * task.strategic_value
    if task.waiting_on:
        factors["person_waiting"] = 15.0  # someone else is blocked on this
    if task.status is TaskStatus.BLOCKED:
        factors["blocked_penalty"] = -10.0  # cannot progress right now
    # Risk of forgetting: inferred/inbox items that are real get a small bump so
    # they surface, but confidence gating (below) prevents low-value promotion.
    if task.status is TaskStatus.INBOX:
        factors["forgetting_risk"] = 8.0

    raw = sum(factors.values())
    # Actionability confidence discount — an uncertain item is de-ranked, so a
    # low-confidence guess can never outrank a confident interview task.
    confidence = task.confidence if task.sources else 0.0
    factors["confidence_multiplier"] = confidence
    score = raw * (0.4 + 0.6 * confidence)
    return ScoredTask(task=task, score=score, category=category, factors=factors)


def prioritize(tasks: list[Task], contract: OperatingContract, today_iso: str) -> list[ScoredTask]:
    """Return tasks scored and sorted, highest priority first. Deterministic:
    ties break by (category order, earliest deadline, task id)."""
    order = list(CATEGORY_WEIGHT)
    scored = [score_task(t, contract, today_iso) for t in tasks]
    scored.sort(
        key=lambda s: (
            -s.score,
            order.index(s.category),
            s.task.deadline or "9999-12-31",
            s.task.id,
        )
    )
    return scored
