"""Duplicate-action detection.

The same action repeated twice without new evidence is a circuit-breaker
condition (spec §8): it means the loop is spinning, not progressing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def action_fingerprint(action: str, params: dict[str, Any] | None = None) -> str:
    payload = json.dumps(
        {"action": action, "params": params or {}}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ActionRegistry:
    """Tracks (action fingerprint, evidence digest) pairs across a run."""

    def __init__(self) -> None:
        self._seen: dict[str, list[str | None]] = {}

    def record(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        evidence_digest: str | None = None,
    ) -> str:
        fp = action_fingerprint(action, params)
        self._seen.setdefault(fp, []).append(evidence_digest)
        return fp

    def is_repeat_without_new_evidence(
        self, action: str, params: dict[str, Any] | None = None
    ) -> bool:
        """True when this exact action already ran twice and the most recent
        repetition brought no new evidence digest."""
        fp = action_fingerprint(action, params)
        digests = self._seen.get(fp, [])
        if len(digests) < 2:
            return False
        return digests[-1] == digests[-2]

    def occurrences(self, action: str, params: dict[str, Any] | None = None) -> int:
        return len(self._seen.get(action_fingerprint(action, params), []))

    def to_dict(self) -> dict[str, list[str | None]]:
        return {k: list(v) for k, v in self._seen.items()}
