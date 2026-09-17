from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.repositories.in_memory import InMemoryMetricsRepository


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


def _range() -> DateRange:
    return DateRange(start=date(2026, 9, 8), end=date(2026, 9, 10))


def test_same_day_updates_are_preserved() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(_update(10, 8, "72"))
    repository.add_update(_update(10, 14, "69"))

    updates = repository.list_updates(10, 77, _range())

    assert len(updates) == 2
    assert [update.image_coverage_percentage for update in updates] == [
        Decimal("72"),
        Decimal("69"),
    ]


def test_latest_per_day_keeps_only_the_latest_lmd() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(_update(8, 8, "72"))
    repository.add_update(_update(9, 8, "70"))
    repository.add_update(_update(10, 8, "72"))
    repository.add_update(_update(10, 14, "69"))

    daily = repository.latest_per_day(10, 77, _range())

    assert [update.observed_date.day for update in daily] == [8, 9, 10]
    assert [update.image_coverage_percentage for update in daily] == [
        Decimal("72"),
        Decimal("70"),
        Decimal("69"),
    ]


def test_date_range_is_inclusive() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(_update(8, 8, "72"))
    repository.add_update(_update(10, 8, "69"))

    updates = repository.latest_per_day(10, 77, _range())

    assert [update.observed_date.day for update in updates] == [8, 10]


def test_category_and_site_filtering_prevents_data_leaks() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(_update(10, 8, "69"))
    repository.add_update(_update(10, 9, "88", site_id=3))

    assert repository.latest_per_day(10, 77, _range())[0].site_id == 77
    assert repository.latest_per_day(10, 3, _range())[0].site_id == 3
    assert repository.latest_per_day(99, 77, _range()) == []


def test_exact_duplicate_update_is_rejected() -> None:
    repository = InMemoryMetricsRepository()
    update = _update(10, 8, "69")
    repository.add_update(update)

    with pytest.raises(ValueError, match="Duplicate metric update"):
        repository.add_update(update)
