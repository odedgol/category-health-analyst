"""Shared pytest fixtures.

Fixtures are added here as the sprint that needs them lands, rather than
stubbed out ahead of time — a fixture with no current user is dead weight
until something actually depends on it.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import duckdb
import pytest

from category_insights.db.connection import bootstrap_schema
from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import Category, MetricPoint


@pytest.fixture
def fixed_now() -> date:
    """A fixed reference date for deterministic date-range parsing tests.

    Never call `date.today()` inside parsing logic — always resolve
    relative phrases ("last week") against an explicit `now` so tests
    don't depend on when they happen to run.
    """
    return date(2026, 6, 15)


@pytest.fixture
def temp_duckdb(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """A fresh, schema-bootstrapped DuckDB file under pytest's tmp_path."""
    connection = duckdb.connect(str(tmp_path / "test_warehouse.duckdb"))
    bootstrap_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def seeded_repository(temp_duckdb: duckdb.DuckDBPyConnection) -> DuckDbRepository:
    """A `DuckDbRepository` pre-loaded with two categories and 10 days of hand-crafted metrics.

    Category 1's `image_coverage_pct` rises linearly from 80 to 89
    (higher-is-better improvement) and `duplicate_rate_pct` falls from 5
    to 1.5 (lower-is-better improvement) — fixed, known values so
    `compare_periods` and `get_metric_series` assertions don't depend on
    randomness.
    """
    repository = DuckDbRepository(temp_duckdb)
    repository.insert_categories(
        [
            Category(category_id=1, name="Test Category A", aliases=["alias-a"]),
            Category(category_id=2, name="Test Category B", aliases=[]),
        ]
    )

    points: list[MetricPoint] = []
    for day_offset in range(10):
        day = date(2026, 1, 1 + day_offset)
        points.append(
            MetricPoint(
                category_id=1,
                metric_key="image_coverage_pct",
                date=day,
                value=80.0 + day_offset,
            )
        )
        points.append(
            MetricPoint(
                category_id=1,
                metric_key="duplicate_rate_pct",
                date=day,
                value=5.0 - 0.35 * day_offset,
            )
        )
    repository.insert_metric_points(points)
    return repository
