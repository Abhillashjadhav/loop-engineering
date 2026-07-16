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


class ScopeViolation(LoopEngineeringError):
    """Work attempted outside the contract's scope or allowed actions."""
