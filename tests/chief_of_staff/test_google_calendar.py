"""Tests-first contract for the Google Calendar LIVE read-only adapter.

Committed RED before the implementation. The adapter is exercised through an
injectable transport (no network in tests, and nothing fake is ever labeled
LIVE — the mode flips to LIVE only after a real read through the configured
transport succeeds). Credentials/config/caches live only under the
fail-closed private boundary.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from loop_engineering.use_cases.personal_chief_of_staff.adapters.google_calendar import (
    CalendarAuthError,
    CalendarPermissionError,
    CalendarRateLimitError,
    CalendarUnavailableError,
    GoogleCalendarAdapter,
    MalformedResponseError,
    ReadOnlyAdapterError,
)
from loop_engineering.use_cases.personal_chief_of_staff.models import (
    AdapterMode,
    CalendarItem,
)
from loop_engineering.use_cases.personal_chief_of_staff.privacy import PrivacyViolation
from loop_engineering.use_cases.personal_chief_of_staff.schedule import free_gaps

NOW = "2026-07-20T06:00:00+00:00"
SECRET_TOKEN = "ya29.SECRET-DO-NOT-LOG"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("/config/private/\n/runs/private/\n", encoding="utf-8")
    cfg = tmp_path / "config/private"
    cfg.mkdir(parents=True)
    (cfg / "google_calendar.json").write_text(
        json.dumps({"calendar_ids": ["primary"], "window_days_past": 1, "window_days_ahead": 14}),
        encoding="utf-8",
    )
    (cfg / "google_calendar_token.json").write_text(
        json.dumps(
            {
                "access_token": SECRET_TOKEN,
                "expires_at": "2026-12-31T00:00:00+00:00",
                "scope": "https://www.googleapis.com/auth/calendar.readonly",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def gevent(
    eid: str,
    start: dict[str, str],
    end: dict[str, str],
    summary: str | None = "Meeting",
    status: str = "confirmed",
    transparency: str | None = None,
    recurring_id: str | None = None,
    attendees: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    e: dict[str, Any] = {"id": eid, "start": start, "end": end, "status": status}
    if summary is not None:
        e["summary"] = summary
    if transparency:
        e["transparency"] = transparency
    if recurring_id:
        e["recurringEventId"] = recurring_id
    if attendees:
        e["attendees"] = attendees
    return e


def make_transport(pages: list[dict[str, Any]], log: list[str] | None = None):  # type: ignore[no-untyped-def]
    """Fake transport returning canned Google API pages; records URLs."""
    calls = {"i": 0}

    def transport(url: str, headers: dict[str, str]) -> tuple[int, str]:
        if log is not None:
            log.append(url)
        page = pages[min(calls["i"], len(pages) - 1)]
        calls["i"] += 1
        if isinstance(page.get("__status__"), int):
            return page["__status__"], page.get("__body__", "")
        return 200, json.dumps(page)

    return transport


def adapter(repo: Path, pages: list[dict[str, Any]], log: list[str] | None = None):  # type: ignore[no-untyped-def]
    return GoogleCalendarAdapter(root=repo, transport=make_transport(pages, log), now_iso=NOW)


# --- normalization -----------------------------------------------------------


def test_live_read_normalizes_and_flips_mode_to_live(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "e1",
                        {
                            "dateTime": "2026-07-20T09:00:00-07:00",
                            "timeZone": "America/Los_Angeles",
                        },
                        {
                            "dateTime": "2026-07-20T09:45:00-07:00",
                            "timeZone": "America/Los_Angeles",
                        },
                        attendees=[{"email": "r@x.com"}],
                    )
                ]
            }
        ],
    )
    assert a.mode is not AdapterMode.LIVE, "LIVE claimed before any real read executed"
    items = a.events()
    assert a.mode is AdapterMode.LIVE  # only now
    (item,) = items
    assert isinstance(item, CalendarItem)
    assert item.event_id.endswith("e1")
    assert item.start == "2026-07-20T09:00:00-07:00"
    assert item.timezone == "America/Los_Angeles"
    assert item.busy is True and item.all_day is False
    assert item.retrieved_at == NOW
    assert item.attendees == ["r@x.com"]


def test_pagination_and_cross_page_duplicate_dedup(repo: Path) -> None:
    log: list[str] = []
    e_dup = gevent(
        "dup",
        {"dateTime": "2026-07-20T10:00:00+00:00"},
        {"dateTime": "2026-07-20T11:00:00+00:00"},
    )
    a = adapter(
        repo,
        [
            {"items": [e_dup], "nextPageToken": "p2"},
            {
                "items": [
                    e_dup,
                    gevent(
                        "e2",
                        {"dateTime": "2026-07-20T12:00:00+00:00"},
                        {"dateTime": "2026-07-20T13:00:00+00:00"},
                    ),
                ]
            },
        ],
        log,
    )
    items = a.events()
    assert [i.event_id.split(":")[-1] for i in items] == ["dup", "e2"], (
        "duplicate across pages kept"
    )
    assert any("pageToken=p2" in u for u in log), "second page never requested"


def test_all_day_event_normalized(repo: Path) -> None:
    a = adapter(
        repo,
        [{"items": [gevent("d1", {"date": "2026-07-21"}, {"date": "2026-07-22"}, "Offsite")]}],
    )
    (item,) = a.events()
    assert item.all_day is True
    assert item.start == "2026-07-21T00:00:00+00:00"
    assert item.end == "2026-07-22T00:00:00+00:00"


def test_overnight_event_blocks_next_morning(repo: Path) -> None:
    """Planted: an overnight live event must not be schedulable over."""
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "night",
                        {"dateTime": "2026-07-20T22:00:00+00:00"},
                        {"dateTime": "2026-07-21T10:30:00+00:00"},
                    )
                ]
            }
        ],
    )
    gaps = free_gaps(a.events(), "2026-07-21")
    assert all(s.isoformat() >= "2026-07-21T10:30:00+00:00" for s, _ in gaps), (
        "planted failure: overnight live event was schedulable over"
    )


def test_timezone_and_dst_boundary_preserved(repo: Path) -> None:
    # US DST fall-back day 2026-11-01: offsets differ before/after transition.
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "dst",
                        {
                            "dateTime": "2026-11-01T01:30:00-07:00",
                            "timeZone": "America/Los_Angeles",
                        },
                        {
                            "dateTime": "2026-11-01T02:30:00-08:00",
                            "timeZone": "America/Los_Angeles",
                        },
                    )
                ]
            }
        ],
    )
    (item,) = a.events()
    assert item.start.endswith("-07:00") and item.end.endswith("-08:00")
    from datetime import datetime

    dur = datetime.fromisoformat(item.end) - datetime.fromisoformat(item.start)
    assert dur.total_seconds() == 2 * 3600  # absolute duration across the transition


def test_recurring_instances_keep_recurrence_identity(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "r1_20260720",
                        {"dateTime": "2026-07-20T15:00:00+00:00"},
                        {"dateTime": "2026-07-20T15:30:00+00:00"},
                        recurring_id="r1",
                    ),
                    gevent(
                        "r1_20260721",
                        {"dateTime": "2026-07-21T15:00:00+00:00"},
                        {"dateTime": "2026-07-21T15:30:00+00:00"},
                        recurring_id="r1",
                    ),
                ]
            }
        ],
    )
    items = a.events()
    assert [i.recurring_event_id for i in items] == ["r1", "r1"]
    assert len({i.event_id for i in items}) == 2


def test_cancelled_events_excluded(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "ok",
                        {"dateTime": "2026-07-20T09:00:00+00:00"},
                        {"dateTime": "2026-07-20T10:00:00+00:00"},
                    ),
                    gevent(
                        "gone",
                        {"dateTime": "2026-07-20T11:00:00+00:00"},
                        {"dateTime": "2026-07-20T12:00:00+00:00"},
                        status="cancelled",
                    ),
                ]
            }
        ],
    )
    assert [i.event_id.split(":")[-1] for i in a.events()] == ["ok"]


def test_transparent_event_does_not_block_free_time(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "focusday",
                        {"dateTime": "2026-07-21T09:00:00+00:00"},
                        {"dateTime": "2026-07-21T18:00:00+00:00"},
                        transparency="transparent",
                    )
                ]
            }
        ],
    )
    (item,) = a.events()
    assert item.busy is False
    gaps = free_gaps([item], "2026-07-21")
    assert gaps, "transparent (free) event wrongly consumed the whole day"


def test_overlapping_events_both_preserved_and_both_block(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "a",
                        {"dateTime": "2026-07-21T09:00:00+00:00"},
                        {"dateTime": "2026-07-21T11:00:00+00:00"},
                    ),
                    gevent(
                        "b",
                        {"dateTime": "2026-07-21T10:00:00+00:00"},
                        {"dateTime": "2026-07-21T12:00:00+00:00"},
                    ),
                ]
            }
        ],
    )
    items = a.events()
    assert len(items) == 2
    gaps = free_gaps(items, "2026-07-21")
    assert all(s.isoformat() >= "2026-07-21T12:00:00+00:00" for s, _ in gaps)


def test_untitled_event_gets_placeholder(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "u1",
                        {"dateTime": "2026-07-20T09:00:00+00:00"},
                        {"dateTime": "2026-07-20T10:00:00+00:00"},
                        summary=None,
                    )
                ]
            }
        ],
    )
    assert a.events()[0].title == "(untitled)"


def test_repeated_identical_reads_materially_identical(repo: Path) -> None:
    pages = [
        {
            "items": [
                gevent(
                    "z",
                    {"dateTime": "2026-07-20T09:00:00+00:00"},
                    {"dateTime": "2026-07-20T10:00:00+00:00"},
                ),
                gevent(
                    "a",
                    {"dateTime": "2026-07-20T11:00:00+00:00"},
                    {"dateTime": "2026-07-20T12:00:00+00:00"},
                ),
            ]
        }
    ]
    one = [i.to_dict() for i in adapter(repo, pages).events()]
    two = [i.to_dict() for i in adapter(repo, pages).events()]
    assert one == two


# --- failure modes (loud, typed, redacted) -----------------------------------


def test_missing_credentials_unavailable_with_remediation(repo: Path) -> None:
    (repo / "config/private/google_calendar_token.json").unlink()
    a = GoogleCalendarAdapter(root=repo, transport=make_transport([{}]), now_iso=NOW)
    assert a.mode is AdapterMode.UNAVAILABLE
    assert "token" in a.setup_instructions().lower()
    with pytest.raises(CalendarAuthError, match="credential"):
        a.events()


def test_expired_token_fails_loudly(repo: Path) -> None:
    tok = repo / "config/private/google_calendar_token.json"
    data = json.loads(tok.read_text())
    data["expires_at"] = "2026-01-01T00:00:00+00:00"  # long past
    tok.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CalendarAuthError, match="expired"):
        adapter(repo, [{}]).events()


def test_401_maps_to_auth_error(repo: Path) -> None:
    with pytest.raises(CalendarAuthError):
        adapter(repo, [{"__status__": 401, "__body__": "Invalid Credentials"}]).events()


def test_insufficient_scope_refused_upfront(repo: Path) -> None:
    tok = repo / "config/private/google_calendar_token.json"
    data = json.loads(tok.read_text())
    data["scope"] = "https://www.googleapis.com/auth/calendar"  # broader than readonly
    tok.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CalendarPermissionError, match="least-privilege"):
        adapter(repo, [{}]).events()


def test_403_maps_to_permission_error(repo: Path) -> None:
    with pytest.raises(CalendarPermissionError):
        adapter(
            repo,
            [
                {
                    "__status__": 403,
                    "__body__": json.dumps(
                        {"error": {"errors": [{"reason": "insufficientPermissions"}]}}
                    ),
                }
            ],
        ).events()


def test_rate_limit_maps_to_rate_limit_error(repo: Path) -> None:
    with pytest.raises(CalendarRateLimitError):
        adapter(repo, [{"__status__": 429, "__body__": "rate limited"}]).events()


def test_api_unavailable_maps_to_unavailable_error(repo: Path) -> None:
    with pytest.raises(CalendarUnavailableError):
        adapter(repo, [{"__status__": 503, "__body__": "backend error"}]).events()


def test_malformed_response_fails_loudly(repo: Path) -> None:
    with pytest.raises(MalformedResponseError):
        adapter(repo, [{"__status__": 200, "__body__": "<html>not json</html>"}]).events()


def test_mode_never_live_after_failure(repo: Path) -> None:
    a = adapter(repo, [{"__status__": 503, "__body__": "down"}])
    with pytest.raises(CalendarUnavailableError):
        a.events()
    assert a.mode is not AdapterMode.LIVE, "planted: LIVE claimed without a successful read"


# --- privacy + read-only guarantees ------------------------------------------


def test_secrets_and_event_content_absent_from_errors(repo: Path) -> None:
    body = json.dumps({"error": "boom", "detail": "attendee=secret.person@x.com"})
    a = adapter(repo, [{"__status__": 500, "__body__": body}])
    with pytest.raises(CalendarUnavailableError) as exc:
        a.events()
    msg = str(exc.value)
    assert SECRET_TOKEN not in msg, "token leaked into error"
    assert "secret.person@x.com" not in msg, "response body leaked into error"


def test_private_boundary_enforced_for_config(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("# no private boundary\n", encoding="utf-8")
    with pytest.raises(PrivacyViolation):
        GoogleCalendarAdapter(root=tmp_path, transport=make_transport([{}]), now_iso=NOW)


def test_write_attempt_is_blocked(repo: Path) -> None:
    """Planted: any outbound calendar write must be refused."""
    a = adapter(repo, [{"items": []}])
    block = CalendarItem(
        "f1", "[Focus] X", "2026-07-21T09:00:00+00:00", "2026-07-21T10:00:00+00:00"
    )
    with pytest.raises(ReadOnlyAdapterError):
        a.create_focus_block(block)


def test_transport_urls_are_read_only_gets(repo: Path) -> None:
    log: list[str] = []
    adapter(repo, [{"items": []}], log).events()
    assert log, "no read executed"
    for url in log:
        assert "/calendars/" in url and "/events" in url
        assert "method=" not in url  # no method smuggling; transport is GET-only by contract


# --- status / connection check -----------------------------------------------


def test_status_reports_honest_state(repo: Path) -> None:
    a = adapter(
        repo,
        [
            {
                "items": [
                    gevent(
                        "e1",
                        {"dateTime": "2026-07-20T09:00:00+00:00"},
                        {"dateTime": "2026-07-20T09:30:00+00:00"},
                    )
                ]
            }
        ],
    )
    before = a.status()
    assert before["mode"] != "LIVE" and before["authenticated"] is True
    a.events()
    after = a.status()
    assert after["mode"] == "LIVE"
    assert after["last_read_at"] == NOW
    assert after["events_read"] == 1 and after["calendars_read"] == 1


def test_connection_check_is_read_only_and_reports(repo: Path) -> None:
    log: list[str] = []
    a = adapter(repo, [{"items": []}], log)
    report = a.connection_check()
    assert report["ok"] is True and report["mode"] == "LIVE"
    assert all("/events" in u for u in log)


# --- fixture mode unchanged ---------------------------------------------------


def test_fixture_adapter_behavior_unchanged(repo: Path) -> None:
    from loop_engineering.use_cases.personal_chief_of_staff.adapters.fixtures import (
        FixtureCalendarAdapter,
    )

    demo = Path("use_cases/personal-chief-of-staff/demo").resolve()
    f = FixtureCalendarAdapter(demo)
    assert f.mode is AdapterMode.FIXTURE
    events = f.events()
    assert len(events) == 4  # demo calendar unchanged
    assert all(e.busy for e in events)  # new field defaults keep old semantics
