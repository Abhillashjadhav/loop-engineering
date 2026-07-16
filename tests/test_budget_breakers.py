"""Budgets (circuit breakers and duplicate detection join in a later PR)."""

from __future__ import annotations

import pytest

from loop_engineering.domain.errors import BudgetExhausted
from loop_engineering.runtime.budget import Budget


def test_budget_exhaustion() -> None:
    budget = Budget(max_iterations=2)
    budget.charge(iterations=1)
    budget.charge(iterations=1)
    with pytest.raises(BudgetExhausted, match="iteration budget"):
        budget.charge(iterations=1)


def test_budget_time_and_token_limits() -> None:
    budget = Budget(max_iterations=100, max_minutes=1.0, max_tokens=10)
    with pytest.raises(BudgetExhausted, match="time budget"):
        budget.charge(minutes=1.5)
    budget = Budget(max_iterations=100, max_tokens=10)
    with pytest.raises(BudgetExhausted, match="token budget"):
        budget.charge(tokens=11)


def test_budget_from_contract_defaults() -> None:
    budget = Budget.from_contract({"budget": {"max_iterations": 7}})
    assert budget.max_iterations == 7
    assert budget.max_minutes is None and budget.max_tokens is None
