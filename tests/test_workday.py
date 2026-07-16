"""Tests for the Workday public-CXS connector (agent/sources/workday.py).

Network is never touched here — parse_postings is a pure function and
fetch_one is exercised with a mocked `requests`, so these run anywhere
(including the egress-restricted dev sandbox).
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "sources"))
import workday  # noqa: E402

UNIFIED_KEYS = {"source", "company", "title", "location", "url", "apply_url",
                "posted_at", "raw_id", "department", "description_excerpt"}

ENTRY = {"display": "Boeing", "host": "boeing.wd1.myworkdayjobs.com",
         "tenant": "boeing", "site": "EXTERNAL_CAREERS"}


def test_registry_loads_seed():
    reg = workday.load_registry()
    assert len(reg) >= 1
    assert all({"host", "tenant", "site"} <= set(t) for t in reg)


def test_load_registry_missing_file_is_nonfatal(tmp_path):
    assert workday.load_registry(tmp_path / "nope.json") == []


def test_parse_postings_schema_and_url():
    postings = [{
        "title": "Senior Manager, AI Product Management",
        "externalPath": "/job/Bengaluru/Senior-Manager--AI-Product_R-12345",
        "locationsText": "Bengaluru, India",
        "postedOn": "Posted 2 Days Ago",
    }]
    jobs = workday.parse_postings(ENTRY, postings)
    assert len(jobs) == 1
    j = jobs[0]
    assert set(j.keys()) == UNIFIED_KEYS
    assert j["source"] == "workday"
    assert j["company"] == "Boeing"
    assert j["raw_id"] == "R-12345"
    assert j["url"] == ("https://boeing.wd1.myworkdayjobs.com/en-US/"
                        "EXTERNAL_CAREERS/job/Bengaluru/Senior-Manager--AI-Product_R-12345")
    assert j["apply_url"] == j["url"]


def test_parse_postings_drops_titleless():
    jobs = workday.parse_postings(ENTRY, [{"title": "", "externalPath": "/x"}])
    assert jobs == []


def _mock_resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_fetch_one_paginates_until_total():
    # total (21) exceeds one page (PAGE_SIZE=20) so a second page is fetched,
    # then the loop stops once offset (40) >= total.
    full = [{"title": f"Director, Product {i}", "externalPath": f"/job/a_R-{i}"}
            for i in range(workday.PAGE_SIZE)]
    page1 = {"total": 21, "jobPostings": full}
    page2 = {"total": 21, "jobPostings": [
        {"title": "GPM, Platform", "externalPath": "/job/c_R-99"}]}
    with patch.object(workday, "requests") as mock_req:
        mock_req.post.side_effect = [_mock_resp(page1), _mock_resp(page2)]
        jobs = workday.fetch_one(ENTRY, pause_seconds=0)
    assert len(jobs) == 21
    assert mock_req.post.call_count == 2  # stopped once offset >= total


def test_fetch_one_nonfatal_on_http_error():
    with patch.object(workday, "requests") as mock_req:
        mock_req.post.return_value = _mock_resp({}, status=403)
        assert workday.fetch_one(ENTRY, pause_seconds=0) == []


def test_fetch_one_nonfatal_on_exception():
    with patch.object(workday, "requests") as mock_req:
        mock_req.post.side_effect = RuntimeError("boom")
        assert workday.fetch_one(ENTRY, pause_seconds=0) == []


def test_fetch_one_missing_slug_returns_empty():
    assert workday.fetch_one({"display": "X"}, pause_seconds=0) == []
