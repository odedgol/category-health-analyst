"""Smoke test: confirms the package is importable and packaging metadata is wired correctly."""

import category_insights


def test_package_exposes_a_version() -> None:
    assert category_insights.__version__
