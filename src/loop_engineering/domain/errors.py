"""Typed errors. Every hard stop maps to one of these — never a silent exit."""

from __future__ import annotations


class LoopEngineeringError(Exception):
    """Base class for all Loop Engineering errors."""


class ContractViolation(LoopEngineeringError):
    """The goal contract was mutated, its digest mismatches, or it failed validation."""


class BudgetExhausted(LoopEngineeringError):
    """The run's time/token/iteration budget is spent."""
