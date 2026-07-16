"""Typed errors. Every hard stop maps to one of these — never a silent exit."""

from __future__ import annotations


class LoopEngineeringError(Exception):
    """Base class for all Loop Engineering errors."""


class ContractViolation(LoopEngineeringError):
    """The goal contract was mutated, its digest mismatches, or it failed validation."""


class InvalidTransition(LoopEngineeringError):
    """An atomic task attempted a status transition the state machine forbids."""


class SelfVerificationError(LoopEngineeringError):
    """The executor role attempted to verify its own work (PD-04)."""


class SequencingViolation(LoopEngineeringError):
    """A next task was requested while a prior task is unverified or failed (PD-04)."""


class BudgetExhausted(LoopEngineeringError):
    """The run's time/token/iteration budget is spent."""


class CircuitOpen(LoopEngineeringError):
    """A circuit breaker tripped. Carries the exact unblock requirement."""

    def __init__(self, reason: str, unblock_requirement: str) -> None:
        super().__init__(f"{reason} — unblock: {unblock_requirement}")
        self.reason = reason
        self.unblock_requirement = unblock_requirement


class ScopeViolation(LoopEngineeringError):
    """Work attempted outside the contract's scope or allowed actions."""


class EvidenceRuleViolation(LoopEngineeringError):
    """A claim was asserted without meeting the evidence independence rules."""


class ProvenanceRuleViolation(LoopEngineeringError):
    """An exact AI-authorship percentage (or similar unprovable provenance claim)
    was asserted without direct provenance evidence (PD-04, PD-08)."""


class IdentityUnresolved(LoopEngineeringError):
    """Subject identity could not be confidently resolved; analysis is blocked."""


class LiveAccessUnavailable(LoopEngineeringError):
    """A live data source (web/GitHub) is not reachable from this environment."""
