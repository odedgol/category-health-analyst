from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from category_health.domain.calculations import (
    CategorySiteMetrics,
    compare_percentages,
    latest_update,
)


def _update(hour: int, coverage: str) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=10,
        site_id=77,
        observed_date=date(2026, 9, 10),
        last_modified_at=datetime(2026, 9, 10, hour, tzinfo=UTC),
        active_product_count=100,
        image_coverage_percentage=Decimal(coverage),
        image_count=180,
        has_title=True,
        aligned_aspects_count=450,
        misaligned_aspects_count=50,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )


def test_compare_percentages_returns_percentage_points() -> None:
    result = compare_percentages(Decimal("72"), Decimal("69"))

    assert result.absolute_delta == Decimal("-3")
    assert result.percentage_point_delta == Decimal("-3")


def test_latest_update_uses_lmd() -> None:
    result = latest_update([_update(14, "69"), _update(8, "72")])

    assert result.last_modified_at.hour == 14
    assert result.image_coverage_percentage == Decimal("69")


def test_latest_update_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty collection"):
        latest_update([])
