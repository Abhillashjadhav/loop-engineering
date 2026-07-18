"""Google Calendar LIVE adapter — strictly read-only.

Implements the existing ``CalendarAdapter`` protocol against the Google
Calendar v3 REST API with a least-privilege ``calendar.readonly`` token.
Honesty rules baked in:

- the adapter NEVER reports LIVE until authentication succeeded AND a real
  calendar read has executed through the configured transport;
- there is no write path: ``create_focus_block`` always raises
  ``ReadOnlyAdapterError`` (focus-block creation stays outside this adapter);
- credentials, config, and read-metadata caches live only under the
  fail-closed private boundary (``config/private/``, ``runs/private/``);
- errors are typed and REDACTED: no token, no response body, no event
  content, no attendee data ever appears in an exception or diagnostic.

Transport is injectable (``transport(url, headers) -> (status, body)``) so
tests exercise every failure mode offline; the default transport performs a
real HTTPS GET. Determinism: the clock is an input (``now_iso``) — expiry
checks, the read window, and ``retrieved_at`` stamps all derive from it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from loop_engineering.use_cases.personal_chief_of_staff.models import (
    AdapterMode,
    CalendarItem,
    Flexibility,
    SourceType,
)

Transport = Callable[[str, dict[str, str]], tuple[int, str]]

API_BASE = "https://www.googleapis.com/calendar/v3"
READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CONFIG_REL = "config/private/google_calendar.json"
TOKEN_REL = "config/private/google_calendar_token.json"
LAST_READ_REL = "runs/private/cos/state/calendar-last-read.json"
PAGE_SIZE = 250
MAX_PAGES = 100  # hard cap per calendar: typed error, never a runaway loop


class CalendarAuthError(RuntimeError):
    """Credentials missing, expired, or rejected."""


class CalendarPermissionError(RuntimeError):
    """Insufficient or over-broad (non-least-privilege) permissions."""


class CalendarRateLimitError(RuntimeError):
    """The API rate limit was reached."""


class CalendarUnavailableError(RuntimeError):
    """The API could not be reached or returned a server error."""


class MalformedResponseError(RuntimeError):
    """Response or configuration data that cannot be used safely."""


class ReadOnlyAdapterError(RuntimeError):
    """A write was attempted through the read-only calendar adapter."""


def _default_transport(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """Real HTTPS GET. GET-only by construction — no method parameter exists."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise CalendarUnavailableError(
            f"Google Calendar API unreachable ({type(exc.reason).__name__})"
        ) from None


class GoogleCalendarAdapter:
    """Read-only live calendar source behind the CalendarAdapter protocol."""

    def __init__(
        self,
        root: Path | None = None,
        transport: Transport | None = None,
        now_iso: str = "",
    ) -> None:
        from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path

        self.name = "google_calendar"
        self._root = root
        self._transport: Transport = transport or _default_transport
        self._now_iso = now_iso
        self._last_read_at = ""
        self._events_read = 0
        self._calendars_read = 0

        self._config_path = private_path(CONFIG_REL, root=root, ensure_parent=False)
        self._token_path = private_path(TOKEN_REL, root=root, ensure_parent=False)
        self._config = self._load_json(self._config_path) or {
            "calendar_ids": ["primary"],
            "window_days_past": 1,
            "window_days_ahead": 14,
        }
        self._token = self._load_json(self._token_path)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    # -- honest mode/status ---------------------------------------------------

    @property
    def mode(self) -> AdapterMode:
        """LIVE only after authentication succeeded AND a real read executed."""
        return AdapterMode.LIVE if self._last_read_at else AdapterMode.UNAVAILABLE

    def _auth_problem(self) -> str | None:
        """None when credentials look usable; otherwise a redacted reason."""
        if not self._token or not str(self._token.get("access_token", "")).strip():
            return "credentials missing"
        expires = str(self._token.get("expires_at", ""))
        if expires and self._now_iso and expires <= self._now_iso:
            return "token expired"
        return None

    def _check_scope(self) -> None:
        scope = str(self._token.get("scope", "")) if self._token else ""
        if not scope.strip():
            # Fail CLOSED: an undeclared scope is not assumed least-privilege
            # (review finding #2).
            raise CalendarPermissionError(
                "token scope not declared — this adapter is least-privilege only; "
                f"re-issue the token with {READONLY_SCOPE!r} and record the scope field"
            )
        if READONLY_SCOPE not in scope.split():
            raise CalendarPermissionError(
                "token scope is not least-privilege: expected "
                f"{READONLY_SCOPE!r}; re-issue the token with the read-only scope"
            )

    def status(self) -> dict[str, Any]:
        problem = self._auth_problem()
        return {
            "mode": self.mode.value,
            "authenticated": problem is None,
            "auth_state": problem or "token present (read-only scope)",
            "last_read_at": self._last_read_at,
            "events_read": self._events_read,
            "calendars_read": self._calendars_read,
            "remediation": "" if problem is None else self.setup_instructions(),
        }

    def setup_instructions(self) -> str:
        return (
            "Google Calendar (read-only): create an OAuth token with ONLY the "
            f"{READONLY_SCOPE} scope and save it as {TOKEN_REL} "
            '({"access_token": "...", "expires_at": "<ISO>", "scope": "..."}); '
            f"optional window/calendar config in {CONFIG_REL}. Nothing is ever "
            "written to your calendar by this adapter."
        )

    # -- read path ------------------------------------------------------------

    def events(self) -> list[CalendarItem]:
        problem = self._auth_problem()
        if problem:
            raise CalendarAuthError(f"Google Calendar {problem} — {self.setup_instructions()}")
        self._check_scope()

        window_start, window_end = self._window()
        headers = {"Authorization": f"Bearer {self._token['access_token']}"}  # type: ignore[index]
        items: list[CalendarItem] = []
        seen_ids: set[str] = set()
        calendar_ids = [str(c) for c in self._config.get("calendar_ids", ["primary"])]
        if not calendar_ids:
            raise MalformedResponseError(
                f"no calendars configured — add at least one entry to calendar_ids in {CONFIG_REL}"
            )
        for calendar_id in calendar_ids:
            page_token = ""
            seen_tokens: set[str] = set()
            pages = 0
            while True:
                pages += 1
                if pages > MAX_PAGES:
                    raise MalformedResponseError(
                        f"calendar {calendar_id!r}: exceeded {MAX_PAGES} pages — "
                        "refusing a runaway pagination loop (review finding #1)"
                    )
                params = {
                    "timeMin": window_start,
                    "timeMax": window_end,
                    "singleEvents": "true",
                    "maxResults": str(PAGE_SIZE),
                    "orderBy": "startTime",
                }
                if page_token:
                    params["pageToken"] = page_token
                url = (
                    f"{API_BASE}/calendars/{quote(calendar_id, safe='')}/events?{urlencode(params)}"
                )
                payload = self._get(url, headers, calendar_id)
                for raw in payload.get("items", []):
                    if not isinstance(raw, dict):
                        raise MalformedResponseError(
                            f"calendar {calendar_id!r}: event entry is not an object"
                        )
                    normalized = self._normalize(raw, calendar_id, seen_ids)
                    if normalized is not None:
                        items.append(normalized)
                page_token = str(payload.get("nextPageToken", "") or "")
                if not page_token:
                    break
                if page_token in seen_tokens:
                    raise MalformedResponseError(
                        f"calendar {calendar_id!r}: server repeated page token — "
                        "refusing an infinite pagination loop (review finding #1)"
                    )
                seen_tokens.add(page_token)
        items.sort(key=lambda i: (i.start, i.event_id))
        self._last_read_at = self._now_iso
        self._events_read = len(items)
        self._calendars_read = len(calendar_ids)
        self._persist_last_read()
        return items

    def _window(self) -> tuple[str, str]:
        now = datetime.fromisoformat(self._now_iso.replace("Z", "+00:00"))
        past = int(self._config.get("window_days_past", 1))
        ahead = int(self._config.get("window_days_ahead", 14))
        return (
            (now - timedelta(days=past)).isoformat(),
            (now + timedelta(days=ahead)).isoformat(),
        )

    def _get(self, url: str, headers: dict[str, str], calendar_id: str) -> dict[str, Any]:
        status, body = self._transport(url, headers)
        # REDACTION RULE: neither the response body nor any header ever enters
        # an exception message — only the status code, calendar id, and a
        # fixed-vocabulary reason.
        if status == 401:
            raise CalendarAuthError(
                f"Google Calendar rejected the token for calendar {calendar_id!r} "
                "(HTTP 401: expired or revoked) — re-issue the read-only token"
            )
        if status == 403:
            reason = self._safe_403_reason(body)
            if reason == "rate_limit":
                raise CalendarRateLimitError(
                    f"Google Calendar rate limit reached (HTTP 403) for {calendar_id!r} — "
                    "retry later"
                )
            raise CalendarPermissionError(
                f"insufficient Google Calendar permission for {calendar_id!r} "
                "(HTTP 403) — grant the calendar.readonly scope"
            )
        if status == 429:
            raise CalendarRateLimitError(
                f"Google Calendar rate limit reached (HTTP 429) for {calendar_id!r} — retry later"
            )
        if status >= 500:
            raise CalendarUnavailableError(
                f"Google Calendar API unavailable (HTTP {status}) for {calendar_id!r}"
            )
        if status != 200:
            raise CalendarUnavailableError(
                f"Google Calendar API returned HTTP {status} for {calendar_id!r}"
            )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise MalformedResponseError(
                f"Google Calendar returned unparseable data for {calendar_id!r} (content redacted)"
            ) from None
        if not isinstance(payload, dict):
            raise MalformedResponseError(
                f"Google Calendar returned a non-object payload for {calendar_id!r}"
            )
        return payload

    @staticmethod
    def _safe_403_reason(body: str) -> str:
        """Classify a 403 WITHOUT quoting the body anywhere."""
        try:
            data = json.loads(body)
            errors = data.get("error", {}).get("errors", [])
            reasons = {str(e.get("reason", "")) for e in errors if isinstance(e, dict)}
        except (json.JSONDecodeError, AttributeError):
            return "permission"
        if reasons & {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}:
            return "rate_limit"
        return "permission"

    def _normalize(
        self, raw: dict[str, Any], calendar_id: str, seen_ids: set[str]
    ) -> CalendarItem | None:
        raw_id = str(raw.get("id", ""))
        if not raw_id:
            raise MalformedResponseError(f"calendar {calendar_id!r}: event without id")
        if raw_id in seen_ids:
            return None  # duplicate across pages/calendars
        if str(raw.get("status", "confirmed")) == "cancelled":
            return None
        seen_ids.add(raw_id)

        start_obj = raw.get("start", {}) or {}
        end_obj = raw.get("end", {}) or {}
        all_day = "date" in start_obj
        if all_day != ("date" in end_obj):
            raise MalformedResponseError(
                f"calendar {calendar_id!r}: event {raw_id!r} mixes all-day and "
                "timed start/end (review finding #3)"
            )
        if all_day:
            start_date = str(start_obj.get("date", "") or "")
            end_date = str(end_obj.get("date", "") or "")
            if not start_date or not end_date:
                raise MalformedResponseError(
                    f"calendar {calendar_id!r}: event {raw_id!r} has an empty all-day date"
                )
            start = f"{start_date}T00:00:00+00:00"
            end = f"{end_date}T00:00:00+00:00"
        else:
            start = str(start_obj.get("dateTime", ""))
            end = str(end_obj.get("dateTime", ""))
        if not start or not end:
            raise MalformedResponseError(
                f"calendar {calendar_id!r}: event {raw_id!r} missing start/end"
            )
        return CalendarItem(
            event_id=f"gcal:{calendar_id}:{raw_id}",
            title=str(raw.get("summary") or "(untitled)"),
            start=start,
            end=end,
            attendees=[
                str(a.get("email", ""))
                for a in raw.get("attendees", [])
                if isinstance(a, dict) and a.get("email")
            ],
            flexibility=Flexibility.FIXED,
            source=SourceType.CALENDAR,
            timezone=str(start_obj.get("timeZone", "") or ""),
            all_day=all_day,
            busy=str(raw.get("transparency", "opaque")) != "transparent",
            event_status=str(raw.get("status", "confirmed")),
            recurring_event_id=str(raw.get("recurringEventId", "") or ""),
            retrieved_at=self._now_iso,
        )

    def _persist_last_read(self) -> None:
        from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path

        meta = private_path(LAST_READ_REL, root=self._root)
        meta.write_text(
            json.dumps(
                {
                    "last_read_at": self._last_read_at,
                    "events_read": self._events_read,
                    "calendars_read": self._calendars_read,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    # -- read-only guarantee ---------------------------------------------------

    def create_focus_block(self, item: CalendarItem) -> str:
        raise ReadOnlyAdapterError(
            "this adapter is read-only: no calendar write (create/update/move/"
            "delete) is available; focus-block creation is a separate, "
            "approval-gated capability outside this PR"
        )

    # -- connection check -------------------------------------------------------

    def connection_check(self) -> dict[str, Any]:
        """Read-only verification: perform a real read and report honestly."""
        try:
            events = self.events()
        except (
            CalendarAuthError,
            CalendarPermissionError,
            CalendarRateLimitError,
            CalendarUnavailableError,
            MalformedResponseError,
        ) as exc:
            return {
                "ok": False,
                "mode": self.mode.value,
                "error": str(exc),  # already redacted by construction
                "remediation": self.setup_instructions(),
            }
        return {
            "ok": True,
            "mode": self.mode.value,
            "events_read": len(events),
            "last_read_at": self._last_read_at,
        }
