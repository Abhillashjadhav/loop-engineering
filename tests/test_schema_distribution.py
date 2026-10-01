"""The packaged schemas used at runtime remain identical to public root copies."""

from __future__ import annotations

import json
import shutil
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

import jsonschema
import pytest
from tests.conftest import REPO_ROOT


def assert_schema_parity(root: Path, package: Traversable) -> None:
    root_names = {path.name for path in root.iterdir() if path.name.endswith(".json")}
    package_names = {path.name for path in package.iterdir() if path.name.endswith(".json")}
    assert root_names == package_names, (
        f"schema filename sets differ: root={sorted(root_names)}, package={sorted(package_names)}"
    )
    assert root_names
    for name in sorted(package_names):
        packaged_bytes = package.joinpath(name).read_bytes()
        assert root.joinpath(name).read_bytes() == packaged_bytes, f"schema copy differs: {name}"
        jsonschema.Draft202012Validator.check_schema(json.loads(packaged_bytes))


def test_root_schemas_match_runtime_package() -> None:
    assert_schema_parity(REPO_ROOT / "schemas", files("loop_engineering").joinpath("schemas"))


@pytest.mark.parametrize("damage", ["root_missing", "package_extra", "root_changed"])
def test_schema_parity_detects_missing_extra_and_changed_copy(tmp_path: Path, damage: str) -> None:
    root = tmp_path / "root"
    package = tmp_path / "package"
    shutil.copytree(REPO_ROOT / "schemas", root)
    shutil.copytree(REPO_ROOT / "src" / "loop_engineering" / "schemas", package)
    name = "goal-contract.schema.json"
    if damage == "root_missing":
        (root / name).unlink()
    elif damage == "package_extra":
        (package / "extra.schema.json").write_text("{}", encoding="utf-8")
    else:
        (root / name).write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError):
        assert_schema_parity(root, package)
