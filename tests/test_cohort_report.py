"""Deterministic cohort-report renderers (flagship comparison + A-H answers)."""

from __future__ import annotations

import json

import pytest

from loop_engineering.use_cases.github_authority_audit import cohort_report


def comparison() -> dict:
    dims = {}
    favors = {
        "product_scope": "pm_skills",
        "technical_depth": "insufficient",
        "verification_quality": "pm_agent_os",
        "tests_and_ci": "pm_skills",
        "originality_of_frameworks": "pm_agent_os",
        "installation_and_activation": "pm_skills",
        "user_experience": "pm_skills",
        "ecosystem_compatibility": "pm_skills",
        "community_contribution_design": "pm_skills",
        "distribution_mechanics": "pm_skills",
        "success_attribution": "parity",
        "ai_assistance_transparency": "parity",
    }
    for key, side in favors.items():
        dims[key] = {
            "pm_skills": f"{key} facts A",
            "pm_agent_os": f"{key} facts B",
            "assessment": f"{key} assessment",
            "favors": side,
            "confidence": "medium",
            "evidence": [
                {"origin": "readme", "url": "u", "excerpt": "e"},
                {"origin": "file_listing", "url": "u2", "excerpt": "e2"},
            ],
        }
    return {
        "comparison": "pm-skills vs PM-agent-OS",
        "dimensions": dims,
        "success_attribution": {"pm_skills": "sX", "pm_agent_os": "sY", "note": "n"},
        "caveats": ["inner files not snapshotted"],
    }


def person(subject: str, tech: float, dist: float) -> dict:
    return {
        "subject": subject,
        "login": subject.lower().replace(" ", ""),
        "aggregate_scores": {
            "substantive_technical_depth": tech,
            "human_reasoning_evidence": 50.0,
            "educational_strength": 40.0,
            "distribution_strength": dist,
            "ai_assisted_creation_likelihood": 10.0,
            "shallow_templated_share_pct": 0.0,
            "claim_evidence_integrity": 60.0,
            "confidence": 70.0,
        },
    }


def card(repo: str, deep: bool, tech: float = 40.0) -> dict:
    return {
        "repo": repo,
        "deep_inspected": deep,
        "scores": {
            "technical_proficiency": tech,
            "claim_evidence_integrity": 60.0,
            "educational_value": 50.0,
        },
    }


@pytest.fixture
def inputs() -> dict:
    return {"comparison": comparison(), "config": {"flagships": {}}}


def test_flagship_report_covers_all_dimensions_and_caveats(inputs: dict) -> None:
    md = cohort_report.render_flagship_comparison(inputs)
    for key in comparison()["dimensions"]:
        assert f"## {key}" in md
    assert "Caveats" in md and "inner files not snapshotted" in md
    assert "never as quality" in md  # popularity firewall stated


def test_answers_a_h_all_sections_and_determinism(inputs: dict) -> None:
    persons = [
        person("Abhillash Jadhav", 20.0, 5.0),
        person("Chip Huyen", 60.0, 80.0),
        person("Eugene Yan", 55.0, 40.0),
    ]
    cards = {
        "Abhillash Jadhav": [card("pm-evals", True, 30.0), card("misc", False, 90.0)],
        "Chip Huyen": [card("sniffly", True, 70.0)],
        "Eugene Yan": [card("obsidian-copilot", True, 60.0)],
    }
    md1 = cohort_report.render_answers_a_h(persons, cards, inputs)
    md2 = cohort_report.render_answers_a_h(list(reversed(persons)), cards, inputs)
    assert md1 == md2  # order-insensitive determinism
    for letter in "ABCDEFGH":
        assert f"## {letter}." in md1
    # B must ignore non-deep-inspected repos even when they score higher.
    assert "pm-evals" in md1 and "misc" not in md1
    # G buckets follow the recorded favors values.
    assert "verification_quality" not in md1.split("## G.")[1].split("## H.")[0]
    assert "installation_and_activation" in md1.split("## G.")[1].split("## H.")[0]
    # H picks packaging/distribution gaps first, exactly three.
    h_section = md1.split("## H.")[1]
    assert h_section.count("Close the") == 3


def test_load_inputs_absent_means_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert cohort_report.load_inputs(tmp_path) is None
    (tmp_path / "comparisons").mkdir()
    (tmp_path / "comparisons" / "x.json").write_text(json.dumps(comparison()))
    assert cohort_report.load_inputs(tmp_path) is None  # config still missing
    (tmp_path / "audit-config.yaml").write_text("flagships: {}\n")
    loaded = cohort_report.load_inputs(tmp_path)
    assert loaded is not None and "dimensions" in loaded["comparison"]
