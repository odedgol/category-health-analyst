from datetime import date

import pytest
from category_health.domain.models import DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent
from pydantic import ValidationError


def _last_week() -> DateRange:
    return DateRange(start=date(2026, 9, 1), end=date(2026, 9, 7))


def test_complete_trend_query_is_executable() -> None:
    query = AnalyticsQuerySpec(
        intent=QueryIntent.TREND,
        metric_ids=("image_coverage_percentage",),
        category_id=20081,
        site_ids=(77,),
        date_range=_last_week(),
        confidence=0.98,
    )

    assert query.is_executable is True


def test_missing_category_is_not_executable() -> None:
    query = AnalyticsQuerySpec(
        intent=QueryIntent.SNAPSHOT,
        metric_ids=("image_count",),
        site_ids=(77,),
        unresolved_fields=("category",),
        confidence=0.5,
    )

    assert query.is_executable is False


def test_period_comparison_requires_two_ranges() -> None:
    with pytest.raises(ValidationError, match="requires date_range"):
        AnalyticsQuerySpec(
            intent=QueryIntent.COMPARE_PERIODS,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
            date_range=_last_week(),
            confidence=0.9,
        )


def test_site_comparison_requires_exactly_two_sites() -> None:
    with pytest.raises(ValidationError, match="exactly two"):
        AnalyticsQuerySpec(
            intent=QueryIntent.COMPARE_SITES,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
            confidence=0.9,
        )


def test_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuerySpec(
            intent=QueryIntent.SNAPSHOT,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
            confidence=1.5,
        )
