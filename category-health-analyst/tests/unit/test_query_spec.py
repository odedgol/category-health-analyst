from datetime import date

import pytest
from category_health.domain.models import DateRange
from category_health.domain.query import AnalysisQuery, QueryIntent
from pydantic import ValidationError


def _last_week() -> DateRange:
    return DateRange(start=date(2026, 9, 1), end=date(2026, 9, 7))


def test_complete_trend_query_is_valid() -> None:
    query = AnalysisQuery(
        intent=QueryIntent.TREND,
        metric_ids=("image_coverage_percentage",),
        category_id=20081,
        site_ids=(77,),
        date_range=_last_week(),
    )

    assert query.category_id == 20081


def test_trend_requires_a_date_range() -> None:
    with pytest.raises(ValidationError, match="trend requires date_range"):
        AnalysisQuery(
            intent=QueryIntent.TREND,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
        )


def test_resolved_query_requires_a_category() -> None:
    with pytest.raises(ValidationError, match="category_id"):
        AnalysisQuery(
            intent=QueryIntent.SNAPSHOT,
            metric_ids=("image_count",),
            site_ids=(77,),
        )


def test_period_comparison_requires_two_ranges() -> None:
    with pytest.raises(ValidationError, match="requires date_range"):
        AnalysisQuery(
            intent=QueryIntent.COMPARE_PERIODS,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
            date_range=_last_week(),
        )


def test_site_comparison_requires_exactly_two_sites() -> None:
    with pytest.raises(ValidationError, match="exactly two"):
        AnalysisQuery(
            intent=QueryIntent.COMPARE_SITES,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
        )


def test_resolved_query_rejects_legacy_confidence() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        AnalysisQuery(
            intent=QueryIntent.SNAPSHOT,
            metric_ids=("image_count",),
            category_id=20081,
            site_ids=(77,),
            confidence=1.0,
        )
