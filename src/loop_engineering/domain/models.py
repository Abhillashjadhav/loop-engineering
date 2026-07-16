"""Core dataclasses and enums.

Everything here serializes to plain dicts (JSON/JSONL/YAML) — file-backed state
is a locked V1 constraint.
"""

from __future__ import annotations


def utc_now() -> str:
    """ISO-8601 UTC timestamp used across all persisted records."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
