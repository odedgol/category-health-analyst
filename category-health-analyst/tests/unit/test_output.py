from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from category_health.application.output import (
    compare_observations,
    validate_metric_ids,
)
from category_health.domain.models import CategorySiteMetrics


def observation(day: int, coverage: str) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=100,
        site_id=77,
        observed_date=date(2026, 9, day),
        last_modified_at=datetime(2026, 9, day, 17, tzinfo=UTC),
        active_product_count=10,
        image_coverage_percentage=Decimal(coverage),
        image_count=18,
        has_title=True,
        aligned_aspects_count=9,
        misaligned_aspects_count=1,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )


def test_compare_observations_calculates_delta_deterministically() -> None:
    comparison = compare_observations(
        observation(9, "72"),
        observation(10, "64"),
        "image_coverage_percentage",
        "consecutive_observations",
    )

    assert comparison.delta == Decimal("-8")
    assert comparison.previous_value == Decimal("72")
    assert comparison.current_value == Decimal("64")
    assert comparison.delta_unit == "percentage_points"


def test_validate_metric_ids_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unknown metric field"):
        validate_metric_ids(("not_a_metric",))
