"""Tests for agent/sources/apify_linkedin.py.

All network calls to Apify are mocked. Verifies:
  - parse_response correctly maps Apify dataset items to Job dataclasses
  - missing config returns []
  - placeholder token returns []
  - max_jobs_per_run budget cap is enforced across queries
  - per-query failures are non-fatal
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "agent" / "sources"))

import apify_linkedin  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_apify_env(monkeypatch):
    """Default to APIFY_TOKEN unset so file-based tests stay deterministic.

    Tests that need the env var set should call monkeypatch.setenv themselves.
    """
    monkeypatch.delenv(apify_linkedin.TOKEN_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

def test_parse_response_maps_standard_apify_fields():
    raw_items = [
        {
            "id": "abc123",
            "title": "Director, Product Management - AI Platform",
            "companyName": "Anthropic",
            "location": "Bengaluru, Karnataka, India",
            "link": "https://www.linkedin.com/jobs/view/abc123",
            "postedAt": "2 days ago",
            "descriptionText": "Lead the AI Platform team to ship agentic systems...",
        },
        {
            "jobId": "xyz789",
            "jobTitle": "Principal Product Manager, GenAI",
            "company": "Microsoft",
            "location": "Hyderabad, India",
            "jobUrl": "https://www.linkedin.com/jobs/view/xyz789",
            "postedTimeAgo": "1 week ago",
            "description": "x" * 800,
        },
    ]
    jobs = apify_linkedin.parse_response(raw_items, "Director Product AI", "India")

    assert len(jobs) == 2

    j0 = jobs[0]
    assert j0.source == "linkedin_apify"
    assert j0.company == "Anthropic"
    assert j0.title == "Director, Product Management - AI Platform"
    assert j0.location == "Bengaluru, Karnataka, India"
    assert j0.url == "https://www.linkedin.com/jobs/view/abc123"
    assert j0.posted_at == "2 days ago"
    assert j0.raw_id == "abc123"
    assert j0.description_excerpt is not None
    assert j0.description_excerpt.startswith("Lead the AI Platform")

    j1 = jobs[1]
    assert j1.title == "Principal Product Manager, GenAI"
    assert j1.company == "Microsoft"
    assert j1.url == "https://www.linkedin.com/jobs/view/xyz789"
    assert j1.posted_at == "1 week ago"
    assert j1.raw_id == "xyz789"
    # 800-char description trimmed to 500
    assert j1.description_excerpt is not None
    assert len(j1.description_excerpt) == 500


def test_parse_response_tolerates_missing_optional_fields():
    raw_items = [{"title": "Group PM, Platform", "companyName": "Stripe"}]
    jobs = apify_linkedin.parse_response(raw_items, "GPM Platform", "Bengaluru")
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Group PM, Platform"
    assert j.company == "Stripe"
    # location falls back to the query location when item omits it
    assert j.location == "Bengaluru"
    assert j.url == ""
    assert j.posted_at is None
    assert j.raw_id is None


def test_parse_response_skips_non_dict_items():
    raw_items = [None, "garbage", 42, {"title": "Director Product", "companyName": "X"}]
    jobs = apify_linkedin.parse_response(raw_items, "Director Product", "India")
    assert len(jobs) == 1
    assert jobs[0].company == "X"


# ---------------------------------------------------------------------------
# load_config / placeholder & missing
# ---------------------------------------------------------------------------

def test_load_config_returns_none_when_file_missing(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert apify_linkedin.load_config(missing) is None


def test_load_config_returns_none_for_placeholder_token(tmp_path):
    cfg_path = tmp_path / "apify_config.json"
    cfg_path.write_text(json.dumps({
        "apify_token": "REPLACE_WITH_ACTUAL_TOKEN",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }))
    assert apify_linkedin.load_config(cfg_path) is None


def test_load_config_returns_dict_when_token_set(tmp_path):
    cfg_path = tmp_path / "apify_config.json"
    cfg_path.write_text(json.dumps({
        "apify_token": "apify_api_real_token_value",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }))
    cfg = apify_linkedin.load_config(cfg_path)
    assert cfg is not None
    assert cfg["apify_token"] == "apify_api_real_token_value"


def test_load_config_returns_none_for_malformed_json(tmp_path):
    cfg_path = tmp_path / "apify_config.json"
    cfg_path.write_text("{not valid json")
    assert apify_linkedin.load_config(cfg_path) is None


# ---------------------------------------------------------------------------
# Env-var-first token resolution
# ---------------------------------------------------------------------------

def _write_placeholder_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "apify_config.json"
    cfg_path.write_text(json.dumps({
        "apify_token": "REPLACE_WITH_ACTUAL_TOKEN",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }))
    return cfg_path


def test_env_var_token_overrides_json_placeholder(tmp_path, monkeypatch):
    """APIFY_TOKEN env var set → uses env value, ignores JSON placeholder."""
    cfg_path = _write_placeholder_config(tmp_path)
    monkeypatch.setenv(apify_linkedin.TOKEN_ENV_VAR, "apify_api_from_env_xyz")
    cfg = apify_linkedin.load_config(cfg_path)
    assert cfg is not None
    # Resolved token comes from env, not from the placeholder in the JSON.
    assert cfg["apify_token"] == "apify_api_from_env_xyz"
    # Other config fields still come from the JSON file unchanged.
    assert cfg["actor_id"] == "valig/linkedin-jobs-scraper"
    assert cfg["max_jobs_per_run"] == 500
    assert cfg["memory_mb"] == 128


def test_env_var_missing_and_json_placeholder_returns_none(tmp_path, monkeypatch):
    """env var unset + JSON placeholder → None, warning logged, no API call."""
    cfg_path = _write_placeholder_config(tmp_path)
    monkeypatch.setattr(apify_linkedin, "CONFIG_PATH", cfg_path)
    monkeypatch.delenv(apify_linkedin.TOKEN_ENV_VAR, raising=False)

    # Capture trajectory writes by redirecting TRAJECTORY_PATH to tmp_path.
    traj_path = tmp_path / "trajectory.jsonl"
    monkeypatch.setattr(apify_linkedin, "TRAJECTORY_PATH", traj_path)

    with patch.object(apify_linkedin, "requests") as mock_requests:
        result = apify_linkedin.run_all_queries()

    assert result == []
    mock_requests.post.assert_not_called()
    assert traj_path.exists(), "expected a non-fatal warning in trajectory.jsonl"
    log_lines = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assert any(
        rec.get("source") == "linkedin_apify"
        and "no real token" in rec.get("warning", "")
        for rec in log_lines
    )


def test_env_var_set_with_json_placeholder_env_wins_and_api_called(tmp_path, monkeypatch):
    """env var set + JSON placeholder → env wins, API call uses env value."""
    cfg_path = _write_placeholder_config(tmp_path)
    monkeypatch.setattr(apify_linkedin, "CONFIG_PATH", cfg_path)
    monkeypatch.setenv(apify_linkedin.TOKEN_ENV_VAR, "apify_api_runtime_secret")

    item = {
        "id": "j1",
        "title": "Director Product AI",
        "companyName": "Acme",
        "location": "Bengaluru",
        "link": "https://example.com/j1",
    }
    n_queries = len(apify_linkedin.LINKEDIN_QUERIES)
    with patch.object(apify_linkedin, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_resp([item])
        result = apify_linkedin.run_all_queries()

    # n_queries fired, 1 job each = n_queries jobs aggregated.
    assert len(result) == n_queries
    assert mock_requests.post.call_count == n_queries
    # Every call must have used the env-var token.
    for call in mock_requests.post.call_args_list:
        assert call.kwargs["params"]["token"] == "apify_api_runtime_secret"


# ---------------------------------------------------------------------------
# run_all_queries — placeholder + missing config short-circuit
# ---------------------------------------------------------------------------

def test_run_all_queries_returns_empty_on_missing_config(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(apify_linkedin, "CONFIG_PATH", missing)
    # Even if requests.post would succeed, this must short-circuit.
    with patch.object(apify_linkedin, "requests") as mock_requests:
        result = apify_linkedin.run_all_queries()
        assert result == []
        mock_requests.post.assert_not_called()


def test_run_all_queries_returns_empty_for_placeholder_token(tmp_path, monkeypatch):
    cfg_path = tmp_path / "apify_config.json"
    cfg_path.write_text(json.dumps({
        "apify_token": "REPLACE_WITH_ACTUAL_TOKEN",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }))
    monkeypatch.setattr(apify_linkedin, "CONFIG_PATH", cfg_path)
    with patch.object(apify_linkedin, "requests") as mock_requests:
        result = apify_linkedin.run_all_queries()
        assert result == []
        mock_requests.post.assert_not_called()


# ---------------------------------------------------------------------------
# run_all_queries — happy path + budget cap + per-query failures
# ---------------------------------------------------------------------------

def _mock_resp(items, status_code=200):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = items
    r.text = json.dumps(items) if status_code < 400 else "boom"
    return r


def test_run_all_queries_aggregates_across_all_queries():
    config = {
        "apify_token": "real_token",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 5000,
        "memory_mb": 128,
    }
    item = {
        "id": "j1",
        "title": "Director Product AI",
        "companyName": "Acme",
        "location": "Bengaluru",
        "link": "https://example.com/j1",
    }
    n_queries = len(apify_linkedin.LINKEDIN_QUERIES)
    with patch.object(apify_linkedin, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_resp([item, dict(item, id="j2")])
        result = apify_linkedin.run_all_queries(config=config)

    # n_queries × 2 jobs each
    assert len(result) == n_queries * 2
    assert mock_requests.post.call_count == n_queries
    assert all(j["source"] == "linkedin_apify" for j in result)


def test_budget_cap_enforced_across_queries():
    config = {
        "apify_token": "real_token",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 5,
        "memory_mb": 128,
    }
    item = {
        "id": "j",
        "title": "Director Product AI",
        "companyName": "Acme",
        "location": "Bengaluru",
        "link": "https://example.com/j",
    }
    # Each query returns 3 items; budget is 5, so we should stop early.
    with patch.object(apify_linkedin, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_resp([item] * 3)
        result = apify_linkedin.run_all_queries(config=config)

    assert len(result) == 5
    # First call returns 3, second returns 3 (trimmed to 2), then break.
    assert mock_requests.post.call_count == 2


def test_per_query_failure_is_non_fatal():
    config = {
        "apify_token": "real_token",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }
    good_item = {
        "id": "j",
        "title": "Director Product AI",
        "companyName": "Acme",
        "location": "Bengaluru",
        "link": "https://example.com/j",
    }

    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First query: HTTP 500
            return _mock_resp({"error": "boom"}, status_code=500)
        if call_count["n"] == 2:
            # Second query: network exception
            raise ConnectionError("network down")
        # Remaining queries: 1 good item each
        return _mock_resp([good_item])

    n_queries = len(apify_linkedin.LINKEDIN_QUERIES)
    with patch.object(apify_linkedin, "requests") as mock_requests:
        mock_requests.post.side_effect = side_effect
        result = apify_linkedin.run_all_queries(config=config)

    # n_queries total: 2 fail, rest succeed × 1 item each
    assert len(result) == n_queries - 2
    assert mock_requests.post.call_count == n_queries


def test_run_query_posts_to_apify_endpoint_with_expected_payload():
    config = {
        "apify_token": "real_token",
        "actor_id": "valig/linkedin-jobs-scraper",
        "max_jobs_per_run": 500,
        "memory_mb": 128,
    }
    with patch.object(apify_linkedin, "requests") as mock_requests:
        mock_requests.post.return_value = _mock_resp([])
        apify_linkedin.run_query("Director Product AI", "Bengaluru",
                                 max_rows=50, config=config)

    args, kwargs = mock_requests.post.call_args
    assert args[0] == apify_linkedin._actor_url()
    assert kwargs["params"] == {"token": "real_token", "memory": 128}
    assert kwargs["json"] == {
        "title": "Director Product AI",
        "location": "Bengaluru",
        "limit": 50,
        "datePosted": apify_linkedin.DEFAULT_DATE_POSTED,
        "experienceLevel": apify_linkedin.EXPERIENCE_SENIOR_BAND,
    }


def test_linkedin_queries_count_matches_constant():
    # 35 strategic queries as of 2026-06-18 expansion (was 10)
    assert len(apify_linkedin.LINKEDIN_QUERIES) == 35


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
