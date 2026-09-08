"""Tests for `DuckDbRepository` against a temp, schema-bootstrapped DuckDB file.

Values in `seeded_repository` (see conftest.py) are hand-crafted and
known, not randomly generated, so every assertion here is exact. All
seeded data is at site 0 (US) — `tests.conftest.SEEDED_SITE_ID`.
"""

from datetime import date

import pytest

from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import DateRange, MetricPoint
from category_insights.domain.ports import MetricDataUnavailableError
from tests.conftest import SEEDED_SITE_ID


def test_list_categories_returns_all_with_aliases(seeded_repository: DuckDbRepository) -> None:
    categories = seeded_repository.list_categories()
    assert [c.category_id for c in categories] == [1, 2]
    assert categories[0].name == "Test Category A"
    assert categories[0].aliases == ["alias-a"]
    assert categories[1].aliases == []


def test_get_metric_series_is_ordered_and_bounded(seeded_repository: DuckDbRepository) -> None:
    points = seeded_repository.get_metric_series(
        category_id=1,
        site_id=SEEDED_SITE_ID,
        metric_key="image_count",
        start=date(2026, 1, 3),
        end=date(2026, 1, 6),
    )
    assert [p.date for p in points] == [
        date(2026, 1, 3),
        date(2026, 1, 4),
        date(2026, 1, 5),
        date(2026, 1, 6),
    ]
    assert [p.value for p in points] == pytest.approx([82.0, 83.0, 84.0, 85.0])


def test_get_metric_series_unknown_metric_raises_key_error(
    seeded_repository: DuckDbRepository,
) -> None:
    with pytest.raises(KeyError):
        seeded_repository.get_metric_series(
            category_id=1,
            site_id=SEEDED_SITE_ID,
            metric_key="not_a_real_metric",
            start=date(2026, 1, 1),
            end=date(2026, 1, 2),
        )


def test_get_metric_series_returns_empty_when_category_has_no_data(
    seeded_repository: DuckDbRepository,
) -> None:
    points = seeded_repository.get_metric_series(
        category_id=2,
        site_id=SEEDED_SITE_ID,
        metric_key="image_count",
        start=date(2026, 1, 1),
        end=date(2026, 1, 10),
    )
    assert points == []


def test_get_metric_series_returns_empty_for_a_different_site(
    seeded_repository: DuckDbRepository,
) -> None:
    points = seeded_repository.get_metric_series(
        category_id=1,
        site_id=3,  # UK — seeded data is only at site 0 (US)
        metric_key="image_count",
        start=date(2026, 1, 1),
        end=date(2026, 1, 10),
    )
    assert points == []


def test_compare_periods_higher_is_better_improved(seeded_repository: DuckDbRepository) -> None:
    period_a = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 5))
    period_b = DateRange(start=date(2026, 1, 6), end=date(2026, 1, 10))

    comparison = seeded_repository.compare_periods(
        category_id=1,
        site_id=SEEDED_SITE_ID,
        metric_key="image_count",
        period_a=period_a,
        period_b=period_b,
    )

    assert comparison.value_a == pytest.approx(82.0)
    assert comparison.value_b == pytest.approx(87.0)
    assert comparison.absolute_delta == pytest.approx(5.0)
    assert comparison.pct_delta == pytest.approx(5.0 / 82.0)
    assert comparison.improved is True


def test_compare_periods_lower_is_better_improved(seeded_repository: DuckDbRepository) -> None:
    period_a = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 5))
    period_b = DateRange(start=date(2026, 1, 6), end=date(2026, 1, 10))

    comparison = seeded_repository.compare_periods(
        category_id=1,
        site_id=SEEDED_SITE_ID,
        metric_key="not_aligned_tax_count",
        period_a=period_a,
        period_b=period_b,
    )

    assert comparison.value_a == pytest.approx(4.3)
    assert comparison.value_b == pytest.approx(2.55)
    assert comparison.improved is True  # a drop in a lower-is-better metric is an improvement


def test_compare_periods_raises_when_no_data(seeded_repository: DuckDbRepository) -> None:
    period_a = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 5))
    period_b = DateRange(start=date(2026, 1, 6), end=date(2026, 1, 10))

    with pytest.raises(MetricDataUnavailableError):
        seeded_repository.compare_periods(
            category_id=2,
            site_id=SEEDED_SITE_ID,
            metric_key="image_count",
            period_a=period_a,
            period_b=period_b,
        )


def test_compare_periods_raises_for_a_different_site(seeded_repository: DuckDbRepository) -> None:
    period_a = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 5))
    period_b = DateRange(start=date(2026, 1, 6), end=date(2026, 1, 10))

    with pytest.raises(MetricDataUnavailableError):
        seeded_repository.compare_periods(
            category_id=1,
            site_id=3,  # UK — seeded data is only at site 0 (US)
            metric_key="image_count",
            period_a=period_a,
            period_b=period_b,
        )


def test_compare_periods_unknown_metric_raises_key_error(
    seeded_repository: DuckDbRepository,
) -> None:
    period = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 5))
    with pytest.raises(KeyError):
        seeded_repository.compare_periods(
            category_id=1,
            site_id=SEEDED_SITE_ID,
            metric_key="not_a_real_metric",
            period_a=period,
            period_b=period,
        )


def test_get_latest_snapshot_at_a_specific_as_of_date(seeded_repository: DuckDbRepository) -> None:
    snapshot = seeded_repository.get_latest_snapshot(
        category_id=1, site_id=SEEDED_SITE_ID, as_of_date=date(2026, 1, 4)
    )
    assert snapshot is not None
    assert snapshot.date == date(2026, 1, 4)
    assert snapshot.site_id == SEEDED_SITE_ID
    assert snapshot.metrics["image_count"] == pytest.approx(83.0)
    assert snapshot.metrics["not_aligned_tax_count"] == pytest.approx(3.95)


def test_get_latest_snapshot_defaults_to_most_recent(seeded_repository: DuckDbRepository) -> None:
    snapshot = seeded_repository.get_latest_snapshot(category_id=1, site_id=SEEDED_SITE_ID)
    assert snapshot is not None
    assert snapshot.date == date(2026, 1, 10)
    assert snapshot.metrics["image_count"] == pytest.approx(89.0)


def test_get_latest_snapshot_returns_none_for_unknown_category(
    seeded_repository: DuckDbRepository,
) -> None:
    assert seeded_repository.get_latest_snapshot(category_id=999, site_id=SEEDED_SITE_ID) is None


def test_get_latest_snapshot_returns_none_for_a_different_site(
    seeded_repository: DuckDbRepository,
) -> None:
    assert seeded_repository.get_latest_snapshot(category_id=1, site_id=3) is None


def test_insert_metric_points_upserts_rather_than_duplicates(
    seeded_repository: DuckDbRepository,
) -> None:
    seeded_repository.insert_metric_points(
        [
            MetricPoint(
                category_id=1,
                site_id=SEEDED_SITE_ID,
                metric_key="image_count",
                date=date(2026, 1, 1),
                value=999.0,
            )
        ]
    )
    points = seeded_repository.get_metric_series(
        category_id=1,
        site_id=SEEDED_SITE_ID,
        metric_key="image_count",
        start=date(2026, 1, 1),
        end=date(2026, 1, 1),
    )
    assert len(points) == 1
    assert points[0].value == pytest.approx(999.0)
