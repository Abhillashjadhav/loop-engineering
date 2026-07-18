"""Cross-run private task-register persistence.

An append-only JSONL journal under the fail-closed private-data boundary
(``runs/private/cos/state/journal.jsonl``, resolved through ``private_path``
so a non-private location can never be written). State is reconstructed by
replaying events, so every TaskSource and its confidence survives verbatim.

Integrity model:
- every event line carries a sha256 over its canonical content;
- a torn TRAILING line (interrupted write) is recovered by atomic truncation
  to the last valid event — crash-safe resume;
- a corrupt MIDDLE event fails loudly (`CorruptStateError`) — the journal is
  evidence, never silently repaired;
- appends are single ``write()`` calls of one line + fsync; rewrites
  (migration, recovery) go through a temp file + ``os.replace``.

Semantics:
- ingestion is idempotent: an observation is content-addressed (digest over
  the task minus volatile timestamps) and appended at most once;
- terminal states are protected: a DONE/DROPPED task re-observed with the
  SAME evidence stays terminal; genuinely NEW evidence resurfaces it into
  INBOX for confirmation — never silently ACTIVE;
- DONE requires completion evidence (no false completion claims);
- status updates support optimistic conflict detection via ``expected`` —
  a stale writer gets ``ConflictError`` instead of silently overwriting;
- the journal is versioned (header event); older formats are migrated
  atomically, newer formats are refused.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from loop_engineering.use_cases.personal_chief_of_staff.models import (
    DecisionCheckpoint,
    Energy,
    Origin,
    SourceType,
    Task,
    TaskSource,
    TaskStatus,
)

SCHEMA_VERSION = 1
DEFAULT_JOURNAL = "runs/private/cos/state/journal.jsonl"

#: Task fields excluded from the observation digest: they vary run to run
#: without representing new evidence. `deadline` is DERIVED data — relative
#: cues ("by tomorrow", "by Friday") re-resolve against each run's clock, so
#: including it would make an unchanged email look like new evidence every
#: day (review finding #1). The raw deadline TEXT lives in the source
#: excerpt, so a genuinely changed deadline still changes the digest.
_VOLATILE_FIELDS = ("created_at", "updated_at", "status", "deadline")

TERMINAL = (TaskStatus.DONE, TaskStatus.DROPPED)


class ConflictError(RuntimeError):
    """A status update was based on a stale view of the task."""


class CorruptStateError(RuntimeError):
    """The journal is damaged beyond safe automatic recovery."""


class MissingProvenanceError(ValueError):
    """A task without any source may never enter the register."""


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _obs_digest(task_dict: dict[str, Any]) -> str:
    stable = {k: v for k, v in task_dict.items() if k not in _VOLATILE_FIELDS}
    return _sha(stable)


def _task_from_dict(d: dict[str, Any]) -> Task:
    return Task(
        id=str(d["id"]),
        title=str(d["title"]),
        description=str(d["description"]),
        sources=[
            TaskSource(
                source_type=SourceType(s["source_type"]),
                source_reference=str(s["source_reference"]),
                source_excerpt=str(s["source_excerpt"]),
                inferred_or_explicit=Origin(s["inferred_or_explicit"]),
                confidence=float(s["confidence"]),
                inference_reason=str(s.get("inference_reason", "")),
            )
            for s in d["sources"]
        ],
        goal_ids=[str(g) for g in d.get("goal_ids", [])],
        project=str(d.get("project", "")),
        deadline=d.get("deadline"),
        urgency=int(d.get("urgency", 0)),
        impact=int(d.get("impact", 0)),
        strategic_value=int(d.get("strategic_value", 0)),
        external_commitment=bool(d.get("external_commitment", False)),
        estimated_minutes=int(d.get("estimated_minutes", 30)),
        energy=Energy(d.get("energy", "medium")),
        dependency_ids=[str(x) for x in d.get("dependency_ids", [])],
        blocked_by=str(d.get("blocked_by", "")),
        waiting_on=str(d.get("waiting_on", "")),
        status=TaskStatus(d.get("status", "active")),
        evidence_of_completion=str(d.get("evidence_of_completion", "")),
        created_at=str(d.get("created_at", "")),
        updated_at=str(d.get("updated_at", "")),
    )


class RegisterStore:
    """Append-only, privacy-guarded, crash-safe task-register journal."""

    def __init__(self, root: Path | None = None, relative: str = DEFAULT_JOURNAL) -> None:
        from loop_engineering.use_cases.personal_chief_of_staff.privacy import private_path

        self.journal_path = private_path(relative, root=root)
        self._events: list[dict[str, Any]] = []
        self._recovered = False
        self._load()

    # -- journal I/O ---------------------------------------------------------

    def _event_sha(self, event: dict[str, Any]) -> str:
        core = {k: event[k] for k in ("v", "seq", "kind", "at", "payload")}
        return _sha(core)

    def _load(self) -> None:
        self._events = []
        if not self.journal_path.is_file():
            return
        raw_lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        if raw_lines:
            # A torn FIRST line (crash during the first-ever append) must fall
            # through to the integrity loop, which recovers trailing tears —
            # never a raw JSONDecodeError (review finding #2).
            try:
                first = json.loads(raw_lines[0] or "{}")
                if not isinstance(first, dict) or not isinstance(first.get("payload", {}), dict):
                    first = None
            except json.JSONDecodeError:
                first = None
            if first is not None:
                # Version gate BEFORE any migration guess: a header claiming a
                # newer schema is refused outright, never "migrated" downward.
                if first.get("kind") == "header":
                    claimed = int(first.get("payload", {}).get("schema_version", 0))
                    if claimed > SCHEMA_VERSION:
                        raise CorruptStateError(
                            f"journal schema version {claimed} is newer than supported "
                            f"{SCHEMA_VERSION} — refusing to read"
                        )
                if "sha" not in first and first.get("kind") != "header":
                    self._migrate_v0(raw_lines)
                    raw_lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        parsed: list[dict[str, Any]] = []
        for i, line in enumerate(raw_lines):
            try:
                event = json.loads(line)
                ok = self._event_sha(event) == event.get("sha")
            except (json.JSONDecodeError, KeyError, TypeError):
                event, ok = None, False
            if not ok:
                if i == len(raw_lines) - 1:
                    # Torn trailing write: recover to the last valid event.
                    self._rewrite(parsed)
                    self._recovered = True
                    break
                raise CorruptStateError(
                    f"journal event {i} failed integrity verification and is not the "
                    "trailing line — refusing silent repair; restore from backup or "
                    "inspect the journal manually"
                )
            assert event is not None
            parsed.append(event)
        if parsed:
            header = parsed[0]
            if header.get("kind") != "header":
                raise CorruptStateError("journal missing header event")
            version = int(header["payload"].get("schema_version", 0))
            if version > SCHEMA_VERSION:
                raise CorruptStateError(
                    f"journal schema version {version} is newer than supported "
                    f"{SCHEMA_VERSION} — refusing to read"
                )
        self._events = parsed

    def _append(self, kind: str, payload: dict[str, Any], at: str) -> None:
        if not self._events:
            header = {
                "v": SCHEMA_VERSION,
                "seq": 0,
                "kind": "header",
                "at": at,
                "payload": {"schema_version": SCHEMA_VERSION},
            }
            header["sha"] = self._event_sha(header)
            self._write_line(header, mode="w")
            self._events.append(header)
        event = {
            "v": SCHEMA_VERSION,
            "seq": len(self._events),
            "kind": kind,
            "at": at,
            "payload": payload,
        }
        event["sha"] = self._event_sha(event)
        self._write_line(event, mode="a")
        self._events.append(event)

    def _write_line(self, event: dict[str, Any], mode: str) -> None:
        with self.journal_path.open(mode, encoding="utf-8") as fh:
            fh.write(_canon(event) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _rewrite(self, events: list[dict[str, Any]]) -> None:
        tmp = self.journal_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for e in events:
                fh.write(_canon(e) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.journal_path)

    def _migrate_v0(self, raw_lines: list[str]) -> None:
        """v0 journals (no header, no per-event sha) → v1, atomically."""
        migrated: list[dict[str, Any]] = []
        header = {
            "v": SCHEMA_VERSION,
            "seq": 0,
            "kind": "header",
            "at": "",
            "payload": {"schema_version": SCHEMA_VERSION},
        }
        header["sha"] = self._event_sha(header)
        migrated.append(header)
        for i, line in enumerate(raw_lines):
            if not line.strip():
                continue
            try:
                old = json.loads(line)
                event = {
                    "v": SCHEMA_VERSION,
                    "seq": len(migrated),
                    "kind": str(old["kind"]),
                    "at": str(old.get("at", "")),
                    "payload": dict(old["payload"]),
                }
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                if i == len(raw_lines) - 1:
                    break  # torn v0 tail: recover to the last valid event
                raise CorruptStateError(
                    f"v0 journal event {i} is unreadable and not the trailing line"
                ) from exc
            event["sha"] = self._event_sha(event)
            migrated.append(event)
        self._rewrite(migrated)

    # -- write API -----------------------------------------------------------

    def ingest(self, tasks: list[Task], at: str) -> int:
        """Record observations; content-addressed, so re-ingestion is a no-op.

        Returns the number of NEW observations appended."""
        seen = {e["payload"]["obs_digest"] for e in self._events if e["kind"] == "observed"}
        appended = 0
        for t in tasks:
            if not t.sources:
                raise MissingProvenanceError(
                    f"task {t.id!r} has no source — refusing to persist unprovenanced work"
                )
            d = t.to_dict()
            digest = _obs_digest(d)
            if digest in seen:
                continue
            self._append("observed", {"task": d, "obs_digest": digest}, at)
            seen.add(digest)
            appended += 1
        return appended

    def set_status(
        self,
        task_id: str,
        status: TaskStatus,
        evidence: str = "",
        expected: TaskStatus | None = None,
        at: str = "",
    ) -> None:
        current = self.status_of(task_id)
        if current is None:
            raise KeyError(f"unknown task {task_id!r}")
        if expected is not None and current is not expected:
            raise ConflictError(
                f"task {task_id!r} is {current.value!r}, not the expected "
                f"{expected.value!r} — refresh before updating (no silent overwrite)"
            )
        if status is TaskStatus.DONE and not evidence.strip():
            raise ValueError("completion requires evidence — a task is never done on assertion")
        self._append(
            "status",
            {"task_id": task_id, "status": status.value, "evidence": evidence},
            at,
        )

    def append_checkpoint(self, checkpoint: DecisionCheckpoint, at: str) -> None:
        payload = {"checkpoint": checkpoint.to_dict()}
        if not self._payload_exists("checkpoint", payload):
            self._append("checkpoint", payload, at)

    def append_artifact(self, proposal_dict: dict[str, Any], at: str) -> None:
        payload = {"proposal": proposal_dict}
        if not self._payload_exists("artifact", payload):
            self._append("artifact", payload, at)

    def _payload_exists(self, kind: str, payload: dict[str, Any]) -> bool:
        """Content-addressed idempotency for non-observation events: an
        identical checkpoint/artifact is recorded once, so a repeated run with
        unchanged inputs appends nothing."""
        digest = _sha(payload)
        return any(e["kind"] == kind and _sha(e["payload"]) == digest for e in self._events)

    # -- read API ------------------------------------------------------------

    def event_count(self) -> int:
        return len(self._events)

    @property
    def recovered(self) -> bool:
        return self._recovered

    def view(self) -> list[Task]:
        """Reconstruct the register: observations merged per task id (all
        provenance kept), status overrides applied, terminal states protected."""
        obs_by_id: dict[str, list[dict[str, Any]]] = {}
        status_events: dict[str, list[dict[str, Any]]] = {}
        for e in self._events:
            if e["kind"] == "observed":
                obs_by_id.setdefault(str(e["payload"]["task"]["id"]), []).append(e)
            elif e["kind"] == "status":
                status_events.setdefault(str(e["payload"]["task_id"]), []).append(e)

        tasks: list[Task] = []
        for tid, observations in obs_by_id.items():
            base = _task_from_dict(observations[-1]["payload"]["task"])
            base.created_at = str(observations[0]["payload"]["task"].get("created_at", ""))
            # Union provenance across every observation, in journal order.
            merged: list[TaskSource] = []
            seen_src: set[tuple[str, str, str]] = set()
            for o in observations:
                for s in _task_from_dict(o["payload"]["task"]).sources:
                    key = (s.source_type.value, s.source_reference, s.source_excerpt)
                    if key not in seen_src:
                        merged.append(s)
                        seen_src.add(key)
            base.sources = merged

            updates = status_events.get(tid, [])
            if updates:
                last = updates[-1]
                base.status = TaskStatus(last["payload"]["status"])
                if base.status is TaskStatus.DONE:
                    base.evidence_of_completion = str(last["payload"]["evidence"])
                # Terminal protection: observations AFTER the terminal status
                # with genuinely new content resurface into INBOX, never ACTIVE.
                if base.status in TERMINAL:
                    last_seq = int(last["seq"])
                    fresh = [o for o in observations if int(o["seq"]) > last_seq]
                    if fresh:
                        base.status = TaskStatus.INBOX
                        # Resurfaced work is NOT complete: stale completion
                        # evidence must not travel with it (review finding #7).
                        base.evidence_of_completion = ""
            tasks.append(base)
        tasks.sort(key=lambda t: t.id)
        return tasks

    def status_of(self, task_id: str) -> TaskStatus | None:
        for t in self.view():
            if t.id == task_id:
                return t.status
        return None

    def checkpoints(self) -> list[DecisionCheckpoint]:
        out: list[DecisionCheckpoint] = []
        for e in self._events:
            if e["kind"] != "checkpoint":
                continue
            c = e["payload"]["checkpoint"]
            out.append(
                DecisionCheckpoint(
                    timestamp=str(c.get("timestamp", "")),
                    approved_decisions=[str(x) for x in c.get("approved_decisions", [])],
                    rejected_ideas=[str(x) for x in c.get("rejected_ideas", [])],
                    open_questions=[str(x) for x in c.get("open_questions", [])],
                    prohibited_actions=[str(x) for x in c.get("prohibited_actions", [])],
                    next_steps=[str(x) for x in c.get("next_steps", [])],
                    context_digest=str(c.get("context_digest", "")),
                )
            )
        return out

    def state_digest(self) -> str:
        """Deterministic digest of the reconstructed register."""
        return _sha([t.to_dict() for t in self.view()])
