"""Inventory hard rules: forks out of authored scoring, full pagination,
inaccessible content recorded honestly. (Rubric/classification tests join
with the scoring PR.)"""

from __future__ import annotations

from tests.conftest import GITHUB_FIXTURES

from loop_engineering.use_cases.github_authority_audit.datasource import FixtureDataSource
from loop_engineering.use_cases.github_authority_audit.inventory import build_inventory


def templater_inventory():  # type: ignore[no-untyped-def]
    ds = FixtureDataSource(GITHUB_FIXTURES)
    return build_inventory("synthetic-templater", ds.repositories("synthetic-templater"))


def test_forks_excluded_from_authored_scoring() -> None:
    ds = FixtureDataSource(GITHUB_FIXTURES)
    inv = build_inventory("synthetic-builder", ds.repositories("synthetic-builder"))
    authored_names = {r.name for r in inv.authored}
    assert "upstream-sdk" not in authored_names  # the fork
    assert "upstream-sdk" in {r.name for r in inv.forks}  # reported separately
    assert "legacy-experiments" in authored_names  # archived own work still authored


def test_pagination_all_pages_retrieved() -> None:
    ds = FixtureDataSource(GITHUB_FIXTURES)
    names = {r["name"] for r in ds.repositories("synthetic-builder")}
    assert "data-pipeline" in names  # lives on page-2


def test_inaccessible_repo_recorded_honestly() -> None:
    inv = templater_inventory()
    hidden = [r for r in inv.records if r.name == "hidden-repo"]
    assert hidden and hidden[0].inaccessible
    assert hidden[0].inaccessible_reason
    assert "hidden-repo" not in {r.name for r in inv.authored}
