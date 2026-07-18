"""Fixture + manual-import adapters: load raw items and calendar from JSON.

These implement the same protocols as future live connectors. They read from
a directory of JSON files (a private import dir, or the committed synthetic
demo). Nothing here contacts a network; the mode is stated honestly as
FIXTURE (bundled synthetic) or MANUAL_IMPORT (user-exported files).
"""

from __future__ import annotations

import json
from pathlib import Path

from loop_engineering.use_cases.personal_chief_of_staff.adapters.base import RawItem
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    AdapterMode,
    CalendarItem,
    Flexibility,
    SourceType,
)

SETUP_HINTS = {
    "google_calendar": (
        "Google Calendar: create an OAuth client, grant calendar.readonly + "
        "calendar.events, place token at config/private/google_token.json, then "
        "swap FixtureCalendarAdapter for the live GoogleCalendarAdapter."
    ),
    "gmail": (
        "Gmail: OAuth with gmail.readonly + gmail.compose (compose only creates "
        "DRAFTS; sending always needs explicit approval). Token at "
        "config/private/gmail_token.json."
    ),
    "github": (
        "GitHub: set GITHUB_TOKEN (repo:read, no write scopes needed for "
        "discovery). The live adapter reads your open PRs, review requests, and issues."
    ),
    "drive": (
        "Google Drive: OAuth with drive.readonly; export target docs, or wire the "
        "live DriveAdapter to pull named documents into data/private/."
    ),
    "chat_context": (
        "ChatGPT/Claude project context: export conversations/checkpoints as "
        "Markdown or JSON into data/private/chat_context/ (MANUAL_IMPORT). No "
        "direct API access is claimed."
    ),
}


class FixtureSourceAdapter:
    """Reads RawItems from ``<dir>/<name>.json`` (a list of item dicts)."""

    def __init__(
        self,
        name: str,
        directory: Path,
        mode: AdapterMode = AdapterMode.FIXTURE,
        setup: str = "",
    ) -> None:
        self.name = name
        self.mode = mode
        self._dir = Path(directory)
        self._setup = setup or SETUP_HINTS.get(name, f"Configure the {name} connector.")

    def fetch(self) -> list[RawItem]:
        path = self._dir / f"{self.name}.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            RawItem(
                source_type=str(d.get("source_type", self.name)),
                reference=str(d["reference"]),
                title=str(d.get("title", "")),
                body=str(d.get("body", "")),
                timestamp=str(d.get("timestamp", "")),
                meta=dict(d.get("meta", {})),
            )
            for d in data
        ]

    def setup_instructions(self) -> str:
        return self._setup


class FixtureCalendarAdapter:
    """Reads CalendarItems from ``<dir>/calendar.json`` and records created
    focus blocks in-memory (a live adapter would call the Calendar API)."""

    def __init__(self, directory: Path, mode: AdapterMode = AdapterMode.FIXTURE) -> None:
        self.name = "google_calendar"
        self.mode = mode
        self._dir = Path(directory)
        self.created_blocks: list[CalendarItem] = []

    def events(self) -> list[CalendarItem]:
        path = self._dir / "calendar.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        out: list[CalendarItem] = []
        for d in data:
            out.append(
                CalendarItem(
                    event_id=str(d["event_id"]),
                    title=str(d.get("title", "")),
                    start=str(d["start"]),
                    end=str(d["end"]),
                    attendees=[str(a) for a in d.get("attendees", [])],
                    flexibility=Flexibility(d.get("flexibility", "fixed")),
                    source=SourceType.CALENDAR,
                    preparation_tasks=[str(x) for x in d.get("preparation_tasks", [])],
                    followup_tasks=[str(x) for x in d.get("followup_tasks", [])],
                )
            )
        return out

    def create_focus_block(self, item: CalendarItem) -> str:
        # Fixture mode records the block so the demo can prove the one-approval
        # flow end to end without touching a real calendar.
        self.created_blocks.append(item)
        return f"fixture-block-{len(self.created_blocks)}"

    def setup_instructions(self) -> str:
        return SETUP_HINTS["google_calendar"]
