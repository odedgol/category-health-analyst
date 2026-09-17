from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from category_health.domain.models import CategorySiteMetrics, DateRange
from pydantic import ValidationError


def _metrics(**overrides: object) -> CategorySiteMetrics:
    values: dict[str, object] = {
        "category_id": 10,
        "site_id": 77,
        "observed_date": date(2026, 9, 10),
        "last_modified_at": datetime(2026, 9, 10, 14, 0, tzinfo=UTC),
        "active_product_count": 100,
        "image_coverage_percentage": Decimal("72"),
        "image_count": 180,
        "has_title": True,
        "aligned_aspects_count": 450,
        "misaligned_aspects_count": 50,
        "aligned_aspects_percentage": Decimal("90"),
        "misaligned_aspects_percentage": Decimal("10"),
    }
    values.update(overrides)
    return CategorySiteMetrics(**values)


def test_date_range_is_inclusive_and_ordered() -> None:
    result = DateRange(start=date(2026, 9, 1), end=date(2026, 9, 7))

    assert result.start == date(2026, 9, 1)
    assert result.end == date(2026, 9, 7)


def test_date_range_rejects_reverse_order() -> None:
    with pytest.raises(ValidationError, match="must not be after"):
        DateRange(start=date(2026, 9, 7), end=date(2026, 9, 1))


def test_metrics_accept_zero_active_products_as_zero_coverage() -> None:
    result = _metrics(active_product_count=0, image_coverage_percentage=Decimal("0"))

    assert result.image_coverage_percentage == 0


def test_metrics_reject_nonzero_coverage_with_zero_active_products() -> None:
    with pytest.raises(ValidationError, match="must be 0"):
        _metrics(active_product_count=0, image_coverage_percentage=Decimal("1"))


def test_metrics_reject_negative_counts() -> None:
    with pytest.raises(ValidationError):
        _metrics(image_count=-1)


def test_metrics_reject_aspect_percentages_that_do_not_sum_to_100() -> None:
    with pytest.raises(ValidationError, match="add up to 100"):
        _metrics(
            aligned_aspects_percentage=Decimal("80"),
            misaligned_aspects_percentage=Decimal("10"),
        )


def test_metrics_reject_lmd_before_observed_date() -> None:
    with pytest.raises(ValidationError, match="before observed_date"):
        _metrics(last_modified_at=datetime(2026, 9, 9, tzinfo=UTC))
