"""P4 — Rich span-level tracing for the agent.

The existing `trajectory.jsonl` captures step-level events (start, observation,
decision). This module adds a parallel `traces.jsonl` that captures each
external call (Claude CLI invocation, Gmail API call, Apify request, etc.)
with prompt/completion/latency/cost-estimate metadata.

Why a parallel file instead of merging into trajectory.jsonl:
    - Trajectory is human-grep-able (one line per decision). Traces are
      machine-grep-able (one line per IO call, with full payloads).
    - Trajectory stays compact (~30 lines/run). Traces can be MB/run.
    - Trajectory is committed to git for forensics. Traces are too large;
      they go to artifacts upload only.

Span schema:
    {
      "ts": ISO8601 UTC,
      "trace_id": run-scoped UUID,
      "span_id": span UUID,
      "parent_span_id": parent or null,
      "kind": "claude_cli" | "gmail_api" | "apify" | "greenhouse" | "drive_api" | "webfetch",
      "name": short label (e.g. "score Stripe Staff PM"),
      "start_ms": epoch ms,
      "end_ms": epoch ms,
      "duration_ms": int,
      "input": {prompt|query|url|...},   # truncated to 4KB per field
      "output": {response|status|...},   # truncated to 4KB per field
      "tokens": {input: int, output: int} (best-effort),
      "model": "claude-opus-4-7" | "...",
      "status": "ok" | "error" | "timeout",
      "error": str or null,
      "metadata": {...}
    }

Usage:
    from agent.tracing import Tracer
    tracer = Tracer(date_dir)
    with tracer.span("claude_cli", name="score Stripe", model="claude-opus-4-7",
                      input={"prompt": prompt}) as span:
        result = subprocess.run(...)
        span.set_output({"response": result.stdout, "rc": result.returncode})
        span.set_tokens(input=approx_tokens(prompt), output=approx_tokens(result.stdout))

When CLAUDE_CODE_OAUTH_TOKEN is exported, claude CLI also emits its own
session.jsonl under ~/.claude/projects/ — Tracer.attach_claude_session_log()
copies those into the run-scoped traces.jsonl for unified replay.
"""
from __future__ import annotations

import contextlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


_MAX_FIELD_BYTES = 4096


def _truncate(obj: Any, limit: int = _MAX_FIELD_BYTES) -> Any:
    """Truncate any string values in a dict to `limit` bytes."""
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + f"...<+{len(obj)-limit}b>"
    if isinstance(obj, dict):
        return {k: _truncate(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate(v, limit) for v in obj]
    return obj


def _approx_tokens(text: str) -> int:
    """Quick token estimate (4 chars ≈ 1 token for English/code)."""
    return len(text) // 4 if text else 0


class _Span:
    def __init__(self, tracer: "Tracer", kind: str, name: str,
                 parent_span_id: str | None = None,
                 input_data: dict | None = None,
                 model: str | None = None,
                 metadata: dict | None = None):
        self.tracer = tracer
        self.kind = kind
        self.name = name
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_span_id = parent_span_id
        self.input = input_data or {}
        self.output: dict = {}
        self.tokens = {"input": 0, "output": 0}
        self.model = model
        self.metadata = metadata or {}
        self.status = "ok"
        self.error: str | None = None
        self.start_ms = int(time.time() * 1000)
        self.end_ms: int | None = None

    def set_output(self, data: dict) -> None:
        self.output.update(data)

    def set_tokens(self, *, input: int = 0, output: int = 0) -> None:
        self.tokens = {"input": input, "output": output}

    def set_error(self, msg: str, status: str = "error") -> None:
        self.status = status
        self.error = msg[:1000]

    def to_dict(self) -> dict:
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.tracer.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "kind": self.kind,
            "name": self.name,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": (self.end_ms - self.start_ms) if self.end_ms else None,
            "input": _truncate(self.input),
            "output": _truncate(self.output),
            "tokens": self.tokens,
            "model": self.model,
            "status": self.status,
            "error": self.error,
            "metadata": _truncate(self.metadata),
        }


class Tracer:
    """Append-only span writer for a single run."""

    def __init__(self, date_dir: Path, trace_id: str | None = None):
        self.date_dir = date_dir
        self.trace_id = trace_id or uuid.uuid4().hex
        self.path = date_dir / "traces.jsonl"
        self.date_dir.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def span(self, kind: str, name: str, **kwargs: Any) -> Iterator[_Span]:
        sp = _Span(self, kind, name, **kwargs)
        try:
            yield sp
        except Exception as e:  # noqa: BLE001
            sp.set_error(f"{type(e).__name__}: {e}")
            raise
        finally:
            sp.end_ms = int(time.time() * 1000)
            self._write(sp.to_dict())

    def event(self, kind: str, name: str, **fields: Any) -> None:
        """One-shot trace entry (no enclosing span)."""
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": None,
            "kind": kind,
            "name": name,
            **{k: _truncate(v) for k, v in fields.items()},
        }
        self._write(rec)

    def _write(self, rec: dict) -> None:
        try:
            with self.path.open("a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            # Tracing must never crash the run.
            pass


def approx_tokens(text: str) -> int:
    """Public token estimator for callers."""
    return _approx_tokens(text)
