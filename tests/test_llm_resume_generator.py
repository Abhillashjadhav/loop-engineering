"""Tests for agent/llm_resume_generator.py — the generate -> critique ->
iterate resume generator.

No network / no Claude CLI: every LLM call is routed through an injectable
`runner` stub that returns canned JSON keyed off the prompt, so the controller
loop, the hybrid fabrication check, and the draft renderer are all exercised
deterministically.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent import llm_resume_generator as lrg  # noqa: E402
from agent import resume_pipeline as rp  # noqa: E402

PROFILE = json.loads((REPO_ROOT / "profile" / "master_profile.json").read_text())

# A draft whose company names match real master_profile experience entries.
DRAFT = {
    "executive_summary": "Senior product leader, 11+ years building AI "
                         "platforms and marketplaces.",
    "core_skills": ["GenAI Platforms", "Agentic AI", "RAG", "Developer Tooling"],
    "roles": [
        {"company": "Wayfair", "bullets": [
            "Built a GenAI developer platform by shipping agentic coding "
            "assistants across the engineering org.",
            "Shipped a Model Proxy governance layer by standardising "
            "multi-LLM orchestration and drift monitoring."]},
        {"company": "Amazon", "bullets": [
            "Scaled the Promotions Platform by rebuilding the AI/ML "
            "recommendation engine end to end."]},
    ],
    "core_competencies": [["AI/ML & Platform",
                           "RAG · agentic workflows · LLM orchestration"]],
}


class StubRunner:
    """Routes a prompt to canned JSON. `fitments` is consumed one per critic
    call so a test can script the controller's convergence behaviour."""

    def __init__(self, fitments=None, draft=None, claims=None):
        self.fitments = list(fitments or [])
        self.draft = draft if draft is not None else DRAFT
        self.claims = claims if claims is not None else []
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if "tailored resume draft" in prompt:
            return json.dumps(self.draft)
        if "hiring-side resume critic" in prompt:
            f = self.fitments.pop(0) if self.fitments else 75
            return json.dumps({"fitment": f, "overall": "ok", "bullets": []})
        if "Classify each resume bullet" in prompt:
            return json.dumps({"claims": self.claims})
        return None


# ---------------------------------------------------------------- generator

def test_generate_draft_parses_runner_output():
    draft = lrg.generate_draft(PROFILE, "Director PM, AI Platform",
                               runner=StubRunner())
    assert draft is not None
    assert draft["roles"][0]["company"] == "Wayfair"


def test_generate_draft_returns_none_on_garbage():
    assert lrg.generate_draft(PROFILE, "JD", runner=lambda p: "not json") is None


# ------------------------------------------------------------------- critic

def test_critique_draft_clamps_fitment():
    crit = lrg.critique_draft("JD", DRAFT, runner=StubRunner(fitments=[140]))
    assert crit["fitment"] == 100  # clamped into 0-100


def test_critique_dimensions_are_six():
    assert len(lrg.CRITIQUE_DIMENSIONS) == 6


# ------------------------------------------------------- fabrication check

def test_fabrication_check_flags_untraced_number():
    bad = {"roles": [{"company": "Wayfair",
                      "bullets": ["Drove $9.9B in invented new revenue."]}]}
    result = lrg.fabrication_check(bad, PROFILE, "JD", runner=StubRunner())
    assert result["counts"]["unverifiable"] >= 1
    assert result["ledger"][0]["label"] == "unverifiable"
    assert "$9.9B" in result["ledger"][0]["untraced_numbers"]


def test_fabrication_check_passes_profile_sourced_bullet():
    # A bullet lifted verbatim from the profile cannot contain an untraced
    # number — every numeric token is, by construction, in the profile.
    real_bullet = PROFILE["experience"][0]["achievements"][0]
    good = {"roles": [{"company": "Wayfair", "bullets": [real_bullet]}]}
    result = lrg.fabrication_check(good, PROFILE, "JD", runner=StubRunner())
    assert result["ledger"][0]["untraced_numbers"] == []
    assert result["ledger"][0]["label"] in ("traced", "jd_adjacent")


def test_fabrication_check_honours_llm_unverifiable_label():
    claims = [{"ref": "Wayfair#1", "label": "unverifiable",
               "evidence": "no such system in the fact base"}]
    result = lrg.fabrication_check(DRAFT, PROFILE, "JD",
                                   runner=StubRunner(claims=claims))
    w1 = next(e for e in result["ledger"] if e["ref"] == "Wayfair#1")
    assert w1["label"] == "unverifiable"


# --------------------------------------------------------- iteration loop

def test_iterate_stops_on_fitment_convergence():
    # 70 then 73 — delta 3 (<5) — controller stops after round 2.
    runner = StubRunner(fitments=[70, 73, 99])
    result = lrg.iterate(PROFILE, "Director PM, AI Platform", runner=runner)
    assert result["available"] is True
    assert len(result["rounds"]) == 2
    assert result["stop_reason"] == "fitment_converged"
    assert result["fitment"] == 73  # best of the two rounds


def test_iterate_runs_max_three_rounds_when_not_converging():
    # 60, 75, 90 — deltas of 15 — never converges — capped at 3 rounds.
    runner = StubRunner(fitments=[60, 75, 90])
    result = lrg.iterate(PROFILE, "Director PM", runner=runner)
    assert len(result["rounds"]) == 3
    assert result["stop_reason"] == "max_rounds"
    assert result["fitment"] == 90


def test_iterate_unavailable_when_generation_fails():
    result = lrg.iterate(PROFILE, "JD", runner=lambda p: "not json")
    assert result["available"] is False
    assert result["draft"] is None


def test_iterate_ledger_present_on_success():
    result = lrg.iterate(PROFILE, "Director PM", runner=StubRunner(fitments=[80]))
    assert result["ledger"]
    assert all("label" in e for e in result["ledger"])


# ------------------------------------------------------------------ ledger

def test_write_ledger_writes_sidecar(tmp_path):
    result = lrg.iterate(PROFILE, "Director PM", runner=StubRunner(fitments=[82]))
    pdf = tmp_path / "2026-05-17_Stripe_director-pm.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    ledger = lrg.write_ledger(pdf, result,
                              {"company": "Stripe", "title": "Director PM"})
    assert ledger.exists()
    assert ledger.name == "2026-05-17_Stripe_director-pm.ledger.md"
    body = ledger.read_text()
    assert "Final fitment" in body and "Claim ledger" in body


# ----------------------------------------------------- draft -> PDF render

def test_build_pdf_from_draft_renders(tmp_path):
    rp.BASE_FONT = "Helvetica"
    rp.BOLD_FONT = "Helvetica-Bold"
    rp.ITALIC_FONT = "Helvetica-Oblique"
    rp.BOLD_ITALIC_FONT = "Helvetica-BoldOblique"
    rp.SERIF_FONT = "Times-Roman"
    rp._register_fonts = lambda: None
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("Helvetica", normal="Helvetica", bold="Helvetica-Bold",
                       italic="Helvetica-Oblique", boldItalic="Helvetica-BoldOblique")
    for k in ("BASE_FONT", "BOLD_FONT", "ITALIC_FONT", "BOLD_ITALIC_FONT", "SERIF_FONT"):
        rp.build_styles.__globals__[k] = getattr(rp, k)

    profile = rp.patch_profile_for_skill_md(PROFILE)
    out = tmp_path / "draft.pdf"
    rp.build_pdf_from_draft(out, DRAFT, profile,
                            {"company": "Stripe", "title": "Director PM, AI"})
    assert out.exists()
    assert out.stat().st_size > 2000  # a real multi-element PDF, not empty


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
