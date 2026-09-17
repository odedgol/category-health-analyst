from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
import pytest
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.repositories.duckdb import DuckDbMetricsRepository


def _update(day: int, hour: int, coverage: str, site_id: int = 77) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=10,
        site_id=site_id,
        observed_date=date(2026, 9, day),
        last_modified_at=datetime(2026, 9, day, hour, tzinfo=UTC),
        active_product_count=100,
        image_coverage_percentage=Decimal(coverage),
        image_count=180,
        has_title=True,
        aligned_aspects_count=450,
        misaligned_aspects_count=50,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )


def _repository() -> DuckDbMetricsRepository:
    return DuckDbMetricsRepository(duckdb.connect(":memory:"))


def _range() -> DateRange:
    return DateRange(start=date(2026, 9, 8), end=date(2026, 9, 10))


def test_duckdb_preserves_same_day_updates() -> None:
    repository = _repository()
    repository.add_update(_update(10, 8, "72"))
    repository.add_update(_update(10, 14, "69"))

    updates = repository.list_updates(10, 77, _range())

    assert len(updates) == 2
    assert [update.image_coverage_percentage for update in updates] == [
        Decimal("72.0000"),
        Decimal("69.0000"),
    ]


def test_duckdb_selects_latest_lmd_per_day() -> None:
    repository = _repository()
    repository.add_update(_update(8, 8, "72"))
    repository.add_update(_update(9, 8, "70"))
    repository.add_update(_update(10, 8, "72"))
    repository.add_update(_update(10, 14, "69"))

    daily = repository.latest_per_day(10, 77, _range())

    assert [update.observed_date.day for update in daily] == [8, 9, 10]
    assert [update.image_coverage_percentage for update in daily] == [
        Decimal("72.0000"),
        Decimal("70.0000"),
        Decimal("69.0000"),
    ]


def test_duckdb_rejects_exact_duplicate() -> None:
    repository = _repository()
    update = _update(10, 8, "69")
    repository.add_update(update)

    with pytest.raises(ValueError, match="Duplicate metric update"):
        repository.add_update(update)
