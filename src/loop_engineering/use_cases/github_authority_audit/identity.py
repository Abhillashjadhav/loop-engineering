"""Subject identity verification (spec §10).

Never assume identity from a URL. At least two independent public profile
attributes must corroborate before repositories are analysed. Ambiguity
blocks analysis — it does not degrade into a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loop_engineering.domain.errors import IdentityUnresolved

MIN_MATCHED_ATTRIBUTES = 2

#: Profile attributes eligible as identity evidence.
ATTRIBUTE_KEYS = ("name", "company", "blog", "twitter", "linkedin", "location", "bio_keywords")


@dataclass
class IdentityResult:
    subject: str
    login: str
    confirmed: bool
    matched_attributes: list[str]
    collisions: list[str] = field(default_factory=list)
    confidence: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "login": self.login,
            "confirmed": self.confirmed,
            "matched_attributes": list(self.matched_attributes),
            "collisions": list(self.collisions),
            "confidence": self.confidence,
            "notes": self.notes,
        }


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def _match_attribute(key: str, expected: Any, profile: dict[str, Any]) -> bool:
    if key == "bio_keywords":
        bio = _norm(str(profile.get("bio", "")))
        keywords = [str(k) for k in expected] if isinstance(expected, list) else [str(expected)]
        return bool(bio) and all(_norm(k) in bio for k in keywords)
    actual = profile.get(key)
    if actual is None or expected is None:
        return False
    return _norm(str(expected)) in _norm(str(actual)) or _norm(str(actual)) in _norm(str(expected))


def verify_identity(
    subject: str,
    candidate_login: str,
    expected_attributes: dict[str, Any],
    profile: dict[str, Any],
    other_candidates: list[dict[str, Any]] | None = None,
) -> IdentityResult:
    """Corroborate the candidate profile against expected public attributes.

    Raises IdentityUnresolved when fewer than two attributes match or when a
    collision (another candidate matching equally well) cannot be ruled out.
    """
    matched = [
        key
        for key in ATTRIBUTE_KEYS
        if key in expected_attributes and _match_attribute(key, expected_attributes[key], profile)
    ]

    collisions: list[str] = []
    for other in other_candidates or []:
        other_login = str(other.get("login", "?"))
        if other_login == candidate_login:
            continue
        other_matched = [
            key
            for key in ATTRIBUTE_KEYS
            if key in expected_attributes and _match_attribute(key, expected_attributes[key], other)
        ]
        if len(other_matched) >= len(matched) and len(other_matched) >= MIN_MATCHED_ATTRIBUTES:
            collisions.append(other_login)

    if len(matched) < MIN_MATCHED_ATTRIBUTES:
        raise IdentityUnresolved(
            f"subject {subject!r}: only {len(matched)} attribute(s) matched for "
            f"candidate {candidate_login!r} ({matched}); {MIN_MATCHED_ATTRIBUTES} required"
        )
    if collisions:
        raise IdentityUnresolved(
            f"subject {subject!r}: candidate {candidate_login!r} collides with "
            f"{collisions} — identity cannot be confidently resolved"
        )

    confidence = min(100, 40 + 20 * len(matched))
    return IdentityResult(
        subject=subject,
        login=candidate_login,
        confirmed=True,
        matched_attributes=matched,
        collisions=[],
        confidence=confidence,
        notes=f"{len(matched)} public attributes corroborate; no unresolved collisions",
    )
