"""Local browser dashboard — a single self-contained HTML file.

No network, no external assets (CSP-safe). Renders Today, Top priorities,
Calendar, Overdue, Blocked, Waiting-on, Projects, Goals, Inbox, Approval
queue, Recently completed, and the three briefs — every task line carrying
its source and confidence. Deterministic: content derives only from the
RunResult, which is itself deterministic.
"""

from __future__ import annotations

import html
from typing import Any

from loop_engineering.use_cases.personal_chief_of_staff.runner import RunResult


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _task_row(task_dict: dict[str, Any]) -> str:
    conf = task_dict["confidence"]
    origin = task_dict["inferred_or_explicit"]
    src = task_dict["sources"][0] if task_dict["sources"] else {}
    where = f"{src.get('source_type', '?')}:{src.get('source_reference', '?')}" if src else "—"
    badge = "explicit" if origin == "explicit" else "inferred"
    dead = f" · ⏰{_esc(task_dict['deadline'])}" if task_dict.get("deadline") else ""
    return (
        f"<tr><td>{_esc(task_dict['title'])}{dead}</td>"
        f"<td><span class='b {badge}'>{badge}</span></td>"
        f"<td>{conf:.2f}</td><td class='src'>{_esc(where)}</td>"
        f"<td>{_esc(task_dict['status'])}</td></tr>"
    )


def _table(title: str, task_dicts: list[dict[str, Any]]) -> str:
    rows = "".join(_task_row(t) for t in task_dicts) or (
        "<tr><td colspan='5' class='muted'>(none)</td></tr>"
    )
    return (
        f"<section><h2>{_esc(title)} <span class='count'>{len(task_dicts)}</span></h2>"
        "<table><thead><tr><th>Task</th><th>Origin</th><th>Conf</th>"
        f"<th>Source</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )


def render_dashboard(result: RunResult) -> str:
    d = result.to_dict()
    tasks = d["register"]["tasks"]

    def by(pred: Any) -> list[dict[str, Any]]:
        return [t for t in tasks if pred(t)]

    overdue = [
        t for t in tasks if t["deadline"] and t["deadline"] < result.day and t["status"] != "done"
    ]
    scored_tasks = [s["task"] for s in d["scored"]]
    top = scored_tasks[:3]
    goals = result.contract.goals

    approval_rows = (
        "".join(
            f"<tr><td>{_esc(a['action_type'])}</td><td>{_esc(a['target'])}</td>"
            f"<td>{_esc(a['risk'])}</td><td>{_esc(a['status'])}</td></tr>"
            for a in d["safe_execution"]["requires_approval"] + d["safe_execution"]["blocked"]
        )
        or "<tr><td colspan='4' class='muted'>(nothing awaiting approval)</td></tr>"
    )

    goals_rows = "".join(
        f"<tr><td>{_esc(g.id)}</td><td>{_esc(g.title)}</td><td>{g.priority}</td></tr>"
        for g in goals
    )

    briefs_html = "".join(
        f"<details><summary>{name.title()} brief</summary><pre>{_esc(text)}</pre></details>"
        for name, text in result.briefs.items()
    )

    style = """
    :root{color-scheme:light dark}
    body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:1.5rem;
      max-width:1100px;margin:auto;line-height:1.45}
    h1{margin:0 0 .25rem} .sub{color:#888;margin:0 0 1.5rem;font-size:.9rem}
    section{margin:1.25rem 0;border:1px solid #8883;border-radius:8px;padding:1rem;overflow-x:auto}
    h2{margin:0 0 .5rem;font-size:1.05rem} .count{color:#888;font-weight:400;font-size:.85rem}
    table{width:100%;border-collapse:collapse;font-size:.86rem}
    th,td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid #8882;vertical-align:top}
    .src{color:#888;font-family:ui-monospace,monospace;font-size:.8rem}
    .muted{color:#aaa} .b{padding:.05rem .4rem;border-radius:4px;font-size:.75rem}
    .explicit{background:#2e7d3233;color:#2e7d32} .inferred{background:#ef6c0033;color:#ef6c00}
    pre{white-space:pre-wrap;font-size:.8rem;background:#8881;padding:.75rem;border-radius:6px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
    @media(max-width:720px){.grid{grid-template-columns:1fr}}
    """
    drift = d["drift"]
    drift_banner = (
        "<section style='border-color:#c62828'><h2>⚠️ Drift violations</h2><ul>"
        + "".join(f"<li>{_esc(v)}</li>" for v in drift["violations"])
        + "</ul></section>"
        if not drift["ok"]
        else "<section style='border-color:#2e7d32'><h2>✓ No drift violations</h2></section>"
    )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chief of Staff — {_esc(result.day)}</title><style>{style}</style></head><body>
<h1>Personal Chief of Staff</h1>
<p class="sub">Day {_esc(result.day)} · run {_esc(result.run_id)} · deterministic ·
{len(tasks)} tasks · {d["schedule"]["free_minutes"]} min free</p>
{drift_banner}
<div class="grid">
{_table("Today — Top priorities", top)}
{_table("Overdue", overdue)}
{_table("Blocked", by(lambda t: t["status"] == "blocked" or t["blocked_by"]))}
{_table("Waiting on others", by(lambda t: t["status"] == "waiting_on_other" or t["waiting_on"]))}
{_table("Inbox (newly inferred)", by(lambda t: t["status"] == "inbox"))}
{_table("Recently completed", by(lambda t: t["status"] == "done"))}
</div>
<section><h2>Calendar &amp; proposed focus blocks</h2><table><thead><tr><th>Block</th>
<th>Start</th><th>End</th></tr></thead><tbody>{
        "".join(
            f"<tr><td>{_esc(b['title'])}</td><td>{_esc(b['start'])}</td><td>{_esc(b['end'])}</td></tr>"
            for b in d["schedule"]["blocks"]
        )
        or "<tr><td colspan='3' class='muted'>(none)</td></tr>"
    }
</tbody></table><p class="muted">{_esc(d["schedule"]["note"])}</p></section>
<section><h2>Approval queue</h2><table><thead><tr><th>Action</th><th>Target</th>
<th>Risk</th><th>Status</th></tr></thead><tbody>{approval_rows}</tbody></table></section>
<section><h2>Goals</h2><table><thead><tr><th>ID</th><th>Goal</th><th>Priority</th></tr>
</thead><tbody>{goals_rows}</tbody></table></section>
<section><h2>Briefs</h2>{briefs_html}</section>
</body></html>"""
