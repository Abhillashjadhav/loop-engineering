"""Run budgets: iterations, minutes, tokens. Exhaustion trips a circuit breaker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loop_engineering.domain.errors import BudgetExhausted


@dataclass
class Budget:
    max_iterations: int
    max_minutes: float | None = None
    max_tokens: int | None = None
    spent_iterations: int = 0
    spent_minutes: float = 0.0
    spent_tokens: int = 0
    _log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_contract(cls, contract: dict[str, Any]) -> Budget:
        raw = dict(contract.get("budget", {}))
        return cls(
            max_iterations=int(raw.get("max_iterations", 100)),
            max_minutes=float(raw["max_minutes"]) if "max_minutes" in raw else None,
            max_tokens=int(raw["max_tokens"]) if "max_tokens" in raw else None,
        )

    def charge(self, iterations: int = 0, minutes: float = 0.0, tokens: int = 0) -> None:
        """Record spend, then raise BudgetExhausted if any limit is crossed."""
        self.spent_iterations += iterations
        self.spent_minutes += minutes
        self.spent_tokens += tokens
        self._log.append({"iterations": iterations, "minutes": minutes, "tokens": tokens})
        self.assert_within()

    def assert_within(self) -> None:
        if self.spent_iterations > self.max_iterations:
            raise BudgetExhausted(
                f"iteration budget exhausted: {self.spent_iterations}/{self.max_iterations}"
            )
        if self.max_minutes is not None and self.spent_minutes > self.max_minutes:
            raise BudgetExhausted(
                f"time budget exhausted: {self.spent_minutes:.1f}/{self.max_minutes:.1f} minutes"
            )
        if self.max_tokens is not None and self.spent_tokens > self.max_tokens:
            raise BudgetExhausted(f"token budget exhausted: {self.spent_tokens}/{self.max_tokens}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "max_minutes": self.max_minutes,
            "max_tokens": self.max_tokens,
            "spent_iterations": self.spent_iterations,
            "spent_minutes": self.spent_minutes,
            "spent_tokens": self.spent_tokens,
        }
