"""Second-pass orchestrator — parse saved web_fetch responses to candidates.

Reads `outputs/{date}/_fetch_responses/{source}_{slug}.json`,
dispatches each file to the matching adapter's `parse_response`, and
writes the consolidated candidate list to:

    outputs/{date}/_raw_candidates.jsonl

Filename convention is `{source}_{slug}.json` where source is
greenhouse / lever / ashby. The slug may itself contain underscores
(e.g. `national_pen`); only the leading source token before the first
`_` is used to pick the adapter.

Usage:
    python agent/sources/parse_responses.py --date 2026-04-29
    python agent/sources/parse_responses.py --date 2026-04-29 \
        --output-root outputs
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import greenhouse  # noqa: E402
import lever  # noqa: E402
import ashby  # noqa: E402


ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
}


def _load_company_lookup(queue_path: Path) -> dict[tuple[str, str], str]:
    """Map (source, slug) -> company display name from the fetch queue."""
    if not queue_path.exists():
        return {}
    try:
        data = json.loads(queue_path.read_text())
    except json.JSONDecodeError:
        return {}
    return {
        (entry["source"], entry["slug"]): entry.get("company") or entry["slug"]
        for entry in data.get("queue", [])
    }


def parse_all(responses_dir: Path,
              company_lookup: dict[tuple[str, str], str]) -> dict:
    """Walk every {source}_{slug}.json under responses_dir and parse it."""
    files = sorted(p for p in responses_dir.glob("*.json") if p.is_file())
    rows: list[dict] = []
    errors: list[dict] = []
    by_source_jobs: dict[str, int] = {ats: 0 for ats in ADAPTERS}

    for fp in files:
        stem = fp.stem  # e.g. "greenhouse_anthropic"
        if "_" not in stem:
            errors.append({"file": fp.name, "reason": "no source prefix"})
            continue
        source, slug = stem.split("_", 1)
        adapter = ADAPTERS.get(source)
        if adapter is None:
            errors.append({"file": fp.name, "reason": f"unknown source: {source}"})
            continue

        try:
            json_text = fp.read_text()
        except OSError as e:
            errors.append({"file": fp.name, "reason": f"read failed: {e}"})
            continue

        company = company_lookup.get((source, slug)) or slug
        jobs = adapter.parse_response(slug, json_text, company)
        by_source_jobs[source] += len(jobs)
        for j in jobs:
            rows.append(j.to_dict())

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "files_seen": len(files),
        "rows": rows,
        "by_source": by_source_jobs,
        "errors": errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--output-root", type=Path, default=Path("outputs"))
    args = ap.parse_args()

    day_dir = args.output_root / args.date
    responses_dir = day_dir / "_fetch_responses"
    queue_path = day_dir / "_fetch_queue.json"

    if not responses_dir.exists():
        print(f"ERROR: responses directory missing: {responses_dir}", file=sys.stderr)
        return 1

    company_lookup = _load_company_lookup(queue_path)
    result = parse_all(responses_dir, company_lookup)

    candidates_path = day_dir / "_raw_candidates.jsonl"
    with candidates_path.open("w") as f:
        for row in result["rows"]:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary_path = day_dir / "_parse_summary.json"
    summary_path.write_text(json.dumps({
        "generated_at": result["generated_at"],
        "files_seen": result["files_seen"],
        "rows_written": len(result["rows"]),
        "by_source": result["by_source"],
        "errors": result["errors"],
    }, indent=2, ensure_ascii=False))

    print(
        f"Parsed {result['files_seen']} response files -> "
        f"{len(result['rows'])} candidates "
        f"({result['by_source']}). "
        f"{len(result['errors'])} errors. "
        f"Output: {candidates_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
