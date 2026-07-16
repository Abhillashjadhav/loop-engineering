"""Output-integrity invariants for the daily pipeline.

CLAUDE.md hard rule 8: don't silently fail. Historically the pipeline only
caught *exceptions* — but an empty pipeline (0 candidates, 0 resumes, an
empty Drive folder) is a valid PROGRAM state that throws nothing.
`skip_apify=True` once produced exactly that: a "successful" run with zero
outputs, invisible to every check.

This module makes empty / implausible stage outputs LOUD. Each `check_*`
helper raises `PipelineIntegrityError` on violation; `run_daily.main()`
catches it, writes a structured `RUN_FAILED.md` into the date folder, and
exits non-zero so the GitHub Actions job is marked failed.

Adaptation note: the original task spec placed this at
`pipeline/invariants.py`. The repo keeps every orchestrator module under
`agent/` and `run_daily.py` imports `from agent import ...`; a new
top-level `pipeline/` package would fragment the import path. This module
therefore lives at `agent/invariants.py`. Behaviour matches the spec.

Invariant for resume generation is intentionally CONDITIONAL: `0 resumes`
is only a violation when there were fits. A genuine "no fits today" run
legitimately produces 0 resumes (CLAUDE.md edge case) and must not fail.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


class PipelineIntegrityError(Exception):
    """Raised when a stage output violates a plausibility invariant."""

    def __init__(self, stage: str, expected: str, actual: str, likely_cause: str):
        self.stage = stage
        self.expected = expected
        self.actual = actual
        self.likely_cause = likely_cause
        super().__init__(
            f"[{stage}] expected {expected}, got {actual} — {likely_cause}"
        )


def write_run_failed(date_dir: Path, err: "PipelineIntegrityError") -> None:
    """Write a structured RUN_FAILED.md into the date folder.

    This file is the deliberate, loud artifact: a run that produced an
    implausible output leaves a visible failure marker on the daily-runs
    branch instead of a silently-empty outputs folder.
    """
    date_dir.mkdir(parents=True, exist_ok=True)
    content = (
        "# RUN FAILED — pipeline integrity violation\n\n"
        f"- **Timestamp (UTC):** {datetime.now(timezone.utc).isoformat()}\n"
        f"- **Stage:** {err.stage}\n"
        f"- **Expected:** {err.expected}\n"
        f"- **Actual:** {err.actual}\n"
        f"- **Likely cause:** {err.likely_cause}\n\n"
        "The run was halted at this stage. Downstream stages (scoring, resume\n"
        "generation, Drive upload, Gmail draft) did NOT execute.\n\n"
        "Empty pipelines are valid *program* states and would otherwise pass\n"
        "silently — this file exists so the failure is impossible to miss.\n\n"
        "## What to do\n\n"
        "1. Open `trajectory.jsonl` in this folder; find the failing step.\n"
        "2. Address the likely cause above.\n"
        "3. Re-trigger the workflow for this date once fixed.\n"
    )
    (date_dir / "RUN_FAILED.md").write_text(content)


# --------------------------------------------------------------------------
# Per-stage checks. Each raises PipelineIntegrityError on violation; the
# caller (run_daily.main) is responsible for catching, writing RUN_FAILED.md,
# and exiting non-zero.
# --------------------------------------------------------------------------

def check_gmail_extraction(urls: int) -> None:
    """After Gmail extraction: at least one LinkedIn job URL must be found."""
    if urls <= 0:
        raise PipelineIntegrityError(
            stage="gmail-extraction",
            expected="> 0 LinkedIn job URLs from Gmail alerts",
            actual=f"{urls} URLs",
            likely_cause=(
                "Gmail OAuth token expired/missing, the JobAlerts label is "
                "empty, or no LinkedIn alert emails landed in the lookback "
                "window. Verify GMAIL_REFRESH_TOKEN and that alert emails "
                "are arriving; widen --days if the window is genuinely quiet."
            ),
        )


def check_apify_fetch(raw_rows: int, gmail_urls: int) -> None:
    """After source fetch: raw candidates must be >= 50% of the Gmail URL count.

    This is the invariant that would have caught the original skip_apify
    incident — when Apify is silently skipped the candidate pool collapses
    relative to the Gmail signal.
    """
    floor = 0.5 * gmail_urls
    if raw_rows < floor:
        raise PipelineIntegrityError(
            stage="source-fetch",
            expected=f">= {floor:.0f} raw candidates (50% of {gmail_urls} Gmail URLs)",
            actual=f"{raw_rows} raw candidates",
            likely_cause=(
                "Apify and/or Greenhouse silently returned little or nothing "
                "— likely skip_apify enabled, APIFY_TOKEN missing, or both "
                "upstream sources errored. The candidate pool collapsed "
                "relative to the Gmail signal."
            ),
        )


def check_scoring(scored_count: int) -> None:
    """After scoring: at least one candidate must have been scored."""
    if scored_count <= 0:
        raise PipelineIntegrityError(
            stage="scoring",
            expected="> 0 scored candidates",
            actual=f"{scored_count} scored",
            likely_cause=(
                "The rule filter dropped every candidate or the filtered "
                "file was empty. Check _filter_summary.json for the drop "
                "histogram (title_no_match / location / decline-list)."
            ),
        )


def check_resume_generation(resumes: int, fit_count: int) -> None:
    """After resume generation: one PDF per fit.

    CONDITIONAL: 0 resumes is only a violation when there WERE fits. A
    genuine 'no fits today' run produces 0 resumes legitimately
    (CLAUDE.md edge case 'Zero >=80% matches: still send the email').
    """
    if fit_count > 0 and resumes <= 0:
        raise PipelineIntegrityError(
            stage="resume-generation",
            expected=f"{fit_count} resume PDFs (one per fit)",
            actual=f"{resumes} resumes",
            likely_cause=(
                "Resume generation silently failed for every fit — ReportLab "
                "error, font registration failure, or an exception swallowed "
                "inside generate_resumes()."
            ),
        )


def check_drive_preupload(local_pdfs: int, expected_fits: int) -> None:
    """Before Drive upload: PDF count on disk must equal the (clean) fit count."""
    if local_pdfs != expected_fits:
        raise PipelineIntegrityError(
            stage="drive-preupload",
            expected=f"{expected_fits} local PDFs (one per non-quarantined fit)",
            actual=f"{local_pdfs} PDFs on disk",
            likely_cause=(
                "PDF count on disk does not match the post-quarantine fit "
                "count — a resume failed to write, or a path was lost "
                "between generation and upload."
            ),
        )


def check_gmail_predraft(attached_pdfs: int, fit_count: int) -> None:
    """Before Gmail draft: attached PDF count must equal the (clean) fit count."""
    if attached_pdfs != fit_count:
        raise PipelineIntegrityError(
            stage="gmail-predraft",
            expected=f"{fit_count} PDFs attached to the draft",
            actual=f"{attached_pdfs} attached",
            likely_cause=(
                "Attachment count does not match fits — a PDF was dropped "
                "between Drive upload and Gmail draft assembly."
            ),
        )
