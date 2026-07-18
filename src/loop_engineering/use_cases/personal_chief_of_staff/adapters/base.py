"""Adapter protocols + a fixture/manual base.

Every adapter declares its mode (LIVE / FIXTURE / MANUAL_IMPORT /
UNAVAILABLE) so the runtime and every brief can state, honestly, where each
piece of data came from. Live connectors are seams: the fixture and
manual-import adapters implement the exact same interface so wiring a real
Google/GitHub client later is a drop-in, and the MVP never fakes a live
integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from loop_engineering.use_cases.personal_chief_of_staff.models import (
    AdapterMode,
    CalendarItem,
)


@dataclass
class RawItem:
    """A source record before task extraction (email, doc, PR, chat export)."""

    source_type: str
    reference: str
    title: str
    body: str
    timestamp: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    """Reads raw items from one information source."""

    name: str
    mode: AdapterMode

    def fetch(self) -> list[RawItem]: ...

    def setup_instructions(self) -> str: ...


@runtime_checkable
class CalendarAdapter(Protocol):
    name: str
    mode: AdapterMode

    def events(self) -> list[CalendarItem]: ...

    def create_focus_block(self, item: CalendarItem) -> str:
        """Create a focus block; returns an event id. Only ever called after
        the schedule has been approved (enforced by the executor)."""
        ...

    def setup_instructions(self) -> str: ...


class UnavailableAdapter:
    """Stands in for a connector that is not configured. Never fabricates."""

    def __init__(self, name: str, setup: str) -> None:
        self.name = name
        self.mode = AdapterMode.UNAVAILABLE
        self._setup = setup

    def fetch(self) -> list[RawItem]:
        return []

    def events(self) -> list[CalendarItem]:
        return []

    def create_focus_block(self, item: CalendarItem) -> str:
        raise RuntimeError(f"{self.name} is UNAVAILABLE; cannot create focus block")

    def setup_instructions(self) -> str:
        return self._setup
