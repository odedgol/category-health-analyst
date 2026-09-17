from datetime import date

import pytest
from category_health.application.planner import PlanOperation, build_plan
from category_health.domain.models import DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent


def _query(intent: QueryIntent, **overrides: object) -> AnalyticsQuerySpec:
    values: dict[str, object] = {
        "intent": intent,
        "metric_ids": ("image_count",),
        "category_id": 20081,
        "site_ids": (77,),
        "confidence": 0.9,
    }
    values.update(overrides)
    return AnalyticsQuerySpec(**values)


def test_planner_maps_intents_to_operations() -> None:
    assert build_plan(_query(QueryIntent.SNAPSHOT)).operation == PlanOperation.SNAPSHOT
    assert (
        build_plan(
            _query(
                QueryIntent.TREND,
                date_range=DateRange(start=date(2026, 9, 1), end=date(2026, 9, 3)),
            )
        ).operation
        == PlanOperation.DAILY_TREND
    )


def test_trend_without_date_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="date_range"):
        build_plan(_query(QueryIntent.TREND))
