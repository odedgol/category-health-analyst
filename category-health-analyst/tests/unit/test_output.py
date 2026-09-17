from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from category_health.agent.core import AgentResult, QueryData
from category_health.agent.output import expose_requested_metrics
from category_health.agent.planner import ExecutionPlan, PlanOperation
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent


def _result(metric_ids: tuple[str, ...]) -> AgentResult:
    record = CategorySiteMetrics(
        category_id=100,
        site_id=77,
        observed_date=date(2026, 9, 9),
        last_modified_at=datetime(2026, 9, 9, 17, tzinfo=UTC),
        active_product_count=10,
        image_coverage_percentage=Decimal("72"),
        image_count=18,
        has_title=True,
        aligned_aspects_count=9,
        misaligned_aspects_count=1,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )
    query = AnalyticsQuerySpec(
        intent=QueryIntent.TREND,
        metric_ids=metric_ids,
        category_id=100,
        site_ids=(77,),
        date_range=DateRange(start=date(2026, 9, 9), end=date(2026, 9, 9)),
        confidence=1,
    )
    plan = ExecutionPlan(
        operation=PlanOperation.DAILY_TREND,
        category_id=100,
        site_ids=(77,),
        metric_ids=metric_ids,
        date_range=query.date_range,
    )
    return AgentResult(
        trace_id=uuid4(),
        query=query,
        plan=plan,
        data=(QueryData(site_id=77, period="current", records=(record,)),),
    )


def test_output_exposes_only_requested_metrics() -> None:
    response = expose_requested_metrics(
        _result(("image_coverage_percentage", "has_title"))
    )

    assert [(value.metric_id, value.value) for value in response.values] == [
        ("image_coverage_percentage", Decimal("72")),
        ("has_title", True),
    ]
    assert response.values[0].last_modified_at.hour == 17
    assert response.comparisons == ()


def test_output_calculates_trend_delta_deterministically() -> None:
    first = _result(("image_coverage_percentage",))
    second = first.model_copy(deep=True)
    second.data[0].records[0].observed_date = date(2026, 9, 10)
    second.data[0].records[0].image_coverage_percentage = Decimal("64")
    second.data[0].records = (first.data[0].records[0], second.data[0].records[0])

    response = expose_requested_metrics(second)

    assert response.comparisons[0].delta == Decimal("-8")
    assert response.comparisons[0].previous_value == Decimal("72")
    assert response.comparisons[0].current_value == Decimal("64")


def test_output_rejects_unknown_metric_field() -> None:
    with pytest.raises(ValueError, match="Unknown metric field"):
        expose_requested_metrics(_result(("not_a_metric",)))
