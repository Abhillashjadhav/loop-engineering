"""End-to-end dry-run test for the Drive sync manifest pipeline.

Builds a temp `outputs/2026-05-02/` directory using the date-stamped
date-stamped filename convention, then exercises both CLI modes of
agent/notifier_drive.py:

  1. --build-manifest writes _drive_upload_manifest.json with the
     correct schema, file count, MIME types, and date-prefixed
     drive_name values.
  2. --record-results consumes a results JSON file and writes
     _drive_upload_results.json with the right counts.

This is a pure dry-run — no Drive MCP, no network. The Routine agent
is what calls the actual Drive MCP per manifest entry; this test
verifies the manifest-and-results contract that wraps the MCP calls.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "agent" / "notifier_drive.py"

DATE = "2026-05-02"
COMPANY = "Acme"
ROLE_SLUG = "director-pm"
PARENT_FOLDER_ID = "19_Z4ymdCgwenwQ-JdFM-NLqqY8J263Sv"


def _populate_outputs(output_root: Path) -> dict[str, Path]:
    """Lay down a synthetic outputs/{date}/ tree with date-stamped names."""
    date_dir = output_root / DATE
    resumes_dir = date_dir / "resumes"
    resumes_dir.mkdir(parents=True)

    files = {
        "brief_md":   date_dir / "brief.md",
        "brief_html": date_dir / "brief.html",
        "pdf":        resumes_dir / f"{DATE}_{COMPANY}_{ROLE_SLUG}.pdf",
        "gap":        resumes_dir / f"{DATE}_{COMPANY}_{ROLE_SLUG}_gap_analysis.md",
        "crisp":      resumes_dir / f"{DATE}_{COMPANY}_{ROLE_SLUG}_crisp_answers.json",
        "prep":       resumes_dir / f"{DATE}_{COMPANY}_{ROLE_SLUG}_interview_prep.md",
    }

    files["brief_md"].write_text("# Brief\n\nDaily summary stub.")
    files["brief_html"].write_text("<html><body><h1>Brief</h1></body></html>")
    # 1 KB binary PDF stub (real-looking enough; we don't parse it)
    files["pdf"].write_bytes(b"%PDF-1.4\n" + b"\x00" * 1024)
    files["gap"].write_text("Gap: no on-call SaaS metrics in profile.")
    files["crisp"].write_text(json.dumps({"foo": "bar"}))
    files["prep"].write_text("Q1: tell me about scaling a B2B platform.")
    return files


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke notifier_drive.py with the given args; return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_build_manifest_with_date_stamped_filenames(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    files = _populate_outputs(output_root)

    proc = _run_script(
        "--build-manifest",
        "--date", DATE,
        "--output-root", str(output_root),
    )
    assert proc.returncode == 0, (
        f"non-zero exit\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    manifest_path = output_root / DATE / "_drive_upload_manifest.json"
    assert manifest_path.exists(), "manifest file was not written"
    manifest = json.loads(manifest_path.read_text())  # raises on invalid JSON

    assert manifest["parent_folder_id"] == PARENT_FOLDER_ID
    assert manifest["date_subfolder_name"] == DATE
    assert isinstance(manifest["files"], list)
    assert len(manifest["files"]) == 6, (
        f"expected 6 file entries, got {len(manifest['files'])}: "
        f"{[f['drive_name'] for f in manifest['files']]}"
    )

    # Map drive_name -> entry for assertion-by-name (don't depend on order)
    by_drive_name = {f["drive_name"]: f for f in manifest["files"]}

    expected = {
        "brief.md":                                            "application/vnd.google-apps.document",
        "brief.html":                                          "text/html",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}.pdf":                   "application/pdf",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_gap_analysis.md":       "text/markdown",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_crisp_answers.json":    "application/json",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_interview_prep.md":     "text/markdown",
    }

    missing = set(expected) - set(by_drive_name)
    assert not missing, f"missing drive_name entries in manifest: {missing}"

    for drive_name, mime in expected.items():
        entry = by_drive_name[drive_name]
        assert entry["mime_type"] == mime, (
            f"{drive_name}: expected mime_type={mime!r}, got {entry['mime_type']!r}"
        )
        assert entry["drive_name"] == Path(entry["local_path"]).name, (
            f"{drive_name}: drive_name should equal local filename "
            f"(date prefix preserved on upload), got drive_name={entry['drive_name']!r} "
            f"vs local filename={Path(entry['local_path']).name!r}"
        )

    # The 4 PDFs/companions live under resumes/ and keep their date prefix
    for drive_name in (
        f"{DATE}_{COMPANY}_{ROLE_SLUG}.pdf",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_gap_analysis.md",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_crisp_answers.json",
        f"{DATE}_{COMPANY}_{ROLE_SLUG}_interview_prep.md",
    ):
        entry = by_drive_name[drive_name]
        assert entry["local_path"].endswith(f"resumes/{drive_name}"), (
            f"{drive_name} should live under resumes/, got {entry['local_path']}"
        )
        assert drive_name.startswith(f"{DATE}_"), (
            f"{drive_name} should be date-stamped"
        )

    # And the local files all actually exist (sanity)
    for f in files.values():
        assert f.exists(), f"fixture file missing: {f}"


def test_record_results_writes_results_file_and_counts(tmp_path: Path) -> None:
    output_root = tmp_path / "outputs"
    date_dir = output_root / DATE
    date_dir.mkdir(parents=True)

    fake_results = [
        {
            "local_path": str(date_dir / "brief.md"),
            "drive_id": "drv_brief_001",
            "drive_url": "https://drive.google.com/file/d/drv_brief_001",
            "status": "ok",
        },
        {
            "local_path": str(date_dir / "resumes" / f"{DATE}_{COMPANY}_{ROLE_SLUG}.pdf"),
            "drive_id": "",
            "drive_url": "",
            "status": "failed",
        },
    ]
    results_file = tmp_path / "fake_results.json"
    results_file.write_text(json.dumps(fake_results))

    proc = _run_script(
        "--record-results",
        "--date", DATE,
        "--output-root", str(output_root),
        "--results-file", str(results_file),
    )
    assert proc.returncode == 0, (
        f"non-zero exit\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    results_path = output_root / DATE / "_drive_upload_results.json"
    assert results_path.exists(), "results file was not written"
    payload = json.loads(results_path.read_text())

    assert payload["total"] == 2
    assert payload["counts"]["ok"] == 1
    assert payload["counts"]["failed"] == 1
    assert payload["counts"]["skipped"] == 0

    # trajectory got a single drive_sync_recorded line
    traj = (output_root / DATE / "trajectory.jsonl").read_text().splitlines()
    assert any(
        json.loads(line).get("decision") == "drive_sync_recorded"
        for line in traj if line.strip()
    ), f"expected drive_sync_recorded in trajectory.jsonl, got: {traj}"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
