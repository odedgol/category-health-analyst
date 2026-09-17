from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
from category_health.agent.core import AnalyticsAgent
from category_health.audit import InMemoryAuditSink
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent
from category_health.repositories.duckdb import DuckDbMetricsRepository


def _update(day: int, hour: int, coverage: str) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=20081,
        site_id=77,
        observed_date=date(2026, 9, day),
        last_modified_at=datetime(2026, 9, day, hour, tzinfo=UTC),
        active_product_count=100,
        image_count=180,
        has_title=True,
        image_coverage_percentage=Decimal(coverage),
        aligned_aspects_count=450,
        misaligned_aspects_count=50,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )


def test_agent_plans_executes_and_audits_a_trend_query() -> None:
    repository = DuckDbMetricsRepository(duckdb.connect(":memory:"))
    repository.add_update(_update(9, 8, "72"))
    repository.add_update(_update(10, 8, "70"))
    repository.add_update(_update(10, 14, "64"))
    sink = InMemoryAuditSink()
    agent = AnalyticsAgent(repository, sink)

    result = agent.run(
        AnalyticsQuerySpec(
            intent=QueryIntent.TREND,
            metric_ids=("image_coverage_percentage",),
            category_id=20081,
            site_ids=(77,),
            date_range=DateRange(start=date(2026, 9, 9), end=date(2026, 9, 10)),
            confidence=0.99,
        )
    )

    assert result.plan.operation.value == "daily_trend"
    assert [row.image_coverage_percentage for row in result.data[0].records] == [
        Decimal("72.0000"),
        Decimal("64.0000"),
    ]
    assert [event.step for event in sink.for_trace(result.trace_id)] == [
        "validate_query",
        "validate_query",
        "plan_query",
        "plan_query",
        "execute_plan",
        "execute_plan",
    ]
