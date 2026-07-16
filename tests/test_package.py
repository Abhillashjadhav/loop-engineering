"""Package skeleton sanity."""

from __future__ import annotations

import loop_engineering


def test_package_importable_with_version() -> None:
    assert loop_engineering.__version__
