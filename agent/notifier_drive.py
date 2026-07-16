"""Drive sync notifier — manifest-driven mirror of daily run artifacts.

Mirrors the existing `agent/sources/fetch_all.py -> web_fetch` pattern:
this Python module never invokes the Drive MCP itself (Python can't),
it just enumerates files into a manifest. The Routine agent reads the
manifest and calls the Drive MCP `create_file` tool per entry. After
upload, the agent feeds the per-file results back via this same module
so they get persisted alongside the rest of the daily artifacts.

Two CLI modes (one per function):

    # 9b: enumerate everything that should be mirrored to Drive
    python agent/notifier_drive.py --build-manifest --date 2026-05-02

    # 9d: log the agent's per-file upload outcomes
    cat results.json | python agent/notifier_drive.py --record-results --date 2026-05-02
    # or:
    python agent/notifier_drive.py --record-results --date 2026-05-02 --results-file results.json

The Drive MCP itself runs only inside the Routine agent (Claude Code Web's
sandbox does not surface it; that's expected).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


DEFAULT_PARENT_FOLDER_ID = "19_Z4ymdCgwenwQ-JdFM-NLqqY8J263Sv"
DEFAULT_PARENT_FOLDER_NAME = "Dream job Agent"


# Each entry: (relative glob, drive mime_type)
# brief.md is converted to a Google Doc on upload.
#
# Globs match date-stamped filenames per CLAUDE.md Step 6 (companion files)
# (e.g. resumes/2026-05-02_Microsoft_principal-pm-trust-safety.pdf) without
# modification — the date prefix doesn't change the suffix the glob keys on.
# `drive_name` is set from `path.name`, so the date prefix is preserved
# verbatim on upload.
_FILE_PATTERNS: list[tuple[str, str]] = [
    ("brief.md",                          "application/vnd.google-apps.document"),
    ("brief.html",                        "text/html"),
    ("resumes/*.pdf",                     "application/pdf"),
    ("resumes/*_gap_analysis.md",         "text/markdown"),
    ("resumes/*_crisp_answers.json",      "application/json"),
    ("resumes/*_interview_prep.md",       "text/markdown"),
]


def _enumerate_files(date_dir: Path) -> list[dict]:
    """Walk the daily output dir and return manifest entries.

    Each entry has: local_path (str), drive_name (str), mime_type (str).
    Patterns are evaluated in declaration order; sorted within each
    pattern for deterministic ordering.
    """
    files: list[dict] = []
    seen: set[str] = set()
    for pattern, mime_type in _FILE_PATTERNS:
        for path in sorted(date_dir.glob(pattern)):
            if not path.is_file():
                continue
            local = str(path)
            if local in seen:
                continue
            seen.add(local)
            files.append({
                "local_path": local,
                "drive_name": path.name,
                "mime_type": mime_type,
            })
    return files


def build_manifest(date: str,
                   parent_folder_id: str = DEFAULT_PARENT_FOLDER_ID,
                   output_root: Path | str = "outputs") -> dict:
    """Enumerate everything in outputs/{date}/ that should be uploaded.

    Writes the manifest to outputs/{date}/_drive_upload_manifest.json
    and returns the dict. The output_root parameter exists so tests can
    point this at a temporary directory, but the daily flow always uses
    the default `outputs/`.

    If outputs/{date}/ does not exist, the manifest is still written
    (with files=[]) so downstream consumers can rely on its presence.
    """
    output_root = Path(output_root)
    date_dir = output_root / date
    files = _enumerate_files(date_dir) if date_dir.exists() else []

    manifest = {
        "parent_folder_id": parent_folder_id,
        "date_subfolder_name": date,
        "files": files,
    }

    out_path = date_dir / "_drive_upload_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def record_upload_results(date: str,
                          results: list[dict],
                          output_root: Path | str = "outputs") -> dict:
    """Persist per-file Drive upload outcomes from the agent.

    `results` is a list of dicts shaped like
    {local_path, drive_id, drive_url, status} (status is typically
    "ok" / "failed" / "skipped"). The function:
      - writes outputs/{date}/_drive_upload_results.json with the full
        list plus a counts summary
      - appends a single summary line to outputs/{date}/trajectory.jsonl
        describing the run (uploaded N, failed M, skipped K)
    Returns the persisted summary dict.
    """
    output_root = Path(output_root)
    date_dir = output_root / date
    date_dir.mkdir(parents=True, exist_ok=True)

    counts = {"ok": 0, "failed": 0, "skipped": 0, "other": 0}
    for r in results:
        s = (r.get("status") or "").lower()
        counts[s if s in counts else "other"] += 1

    summary = {
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "date": date,
        "total": len(results),
        "counts": counts,
        "results": results,
    }

    (date_dir / "_drive_upload_results.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )

    traj_line = {
        "ts": summary["recorded_at"],
        "step": "9d",
        "tool": "notifier_drive",
        "decision": "drive_sync_recorded",
        "total": summary["total"],
        "ok": counts["ok"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
    }
    try:
        with (date_dir / "trajectory.jsonl").open("a") as f:
            f.write(json.dumps(traj_line, ensure_ascii=False) + "\n")
    except OSError:
        # Trajectory append shouldn't crash the run.
        pass

    return summary


def _read_results_input(args: argparse.Namespace) -> list[dict]:
    """Read the results JSON from stdin or --results-file."""
    if args.results_file:
        text = Path(args.results_file).read_text()
    else:
        text = sys.stdin.read()
    if not text.strip():
        return []
    data = json.loads(text)
    if isinstance(data, dict) and "results" in data:
        data = data["results"]
    if not isinstance(data, list):
        raise ValueError("results input must be a JSON list (or {results: [...]})")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-manifest", action="store_true",
                      help="Enumerate outputs/{date}/ and write _drive_upload_manifest.json")
    mode.add_argument("--record-results", action="store_true",
                      help="Read upload results from stdin (or --results-file) "
                           "and write _drive_upload_results.json + trajectory line")

    ap.add_argument("--date", required=True, help="Run date (YYYY-MM-DD)")
    ap.add_argument("--parent-folder-id", default=DEFAULT_PARENT_FOLDER_ID,
                    help="Drive folder ID to upload under (default: Dream job Agent)")
    ap.add_argument("--output-root", default="outputs", type=Path,
                    help="Root for daily output dirs (default: outputs)")
    ap.add_argument("--results-file", default=None,
                    help="(record-results only) path to JSON list of results; "
                         "defaults to reading from stdin")
    args = ap.parse_args()

    if args.build_manifest:
        manifest = build_manifest(
            date=args.date,
            parent_folder_id=args.parent_folder_id,
            output_root=args.output_root,
        )
        manifest_path = args.output_root / args.date / "_drive_upload_manifest.json"
        print(
            f"Manifest: {len(manifest['files'])} files staged for "
            f"Dream job Agent/{manifest['date_subfolder_name']}/ -> {manifest_path}"
        )
        return 0

    if args.record_results:
        try:
            results = _read_results_input(args)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"ERROR: bad results input: {e}", file=sys.stderr)
            return 1
        summary = record_upload_results(
            date=args.date,
            results=results,
            output_root=args.output_root,
        )
        print(
            f"Recorded {summary['total']} upload outcomes "
            f"(ok={summary['counts']['ok']}, "
            f"failed={summary['counts']['failed']}, "
            f"skipped={summary['counts']['skipped']})"
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
