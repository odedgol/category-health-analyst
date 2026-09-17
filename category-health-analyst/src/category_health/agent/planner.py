"""Turn a validated QuerySpec into an explicit execution plan."""

from enum import StrEnum

from pydantic import BaseModel

from category_health.domain.models import DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent


class PlanOperation(StrEnum):
    SNAPSHOT = "snapshot"
    DAILY_TREND = "daily_trend"
    PERIOD_COMPARISON = "period_comparison"
    SITE_COMPARISON = "site_comparison"
    CHANGE_ANALYSIS = "change_analysis"


class ExecutionPlan(BaseModel):
    """An explicit, auditable instruction for the repository layer."""

    operation: PlanOperation
    category_id: int
    site_ids: tuple[int, ...]
    metric_ids: tuple[str, ...]
    date_range: DateRange | None = None
    comparison_range: DateRange | None = None


def build_plan(query: AnalyticsQuerySpec) -> ExecutionPlan:
    """Compile a QuerySpec into one supported deterministic operation."""

    if not query.is_executable:
        raise ValueError(f"Query is not executable; unresolved fields: {query.unresolved_fields}")
    if query.category_id is None:
        raise ValueError("An executable query must have a category_id")

    operation_by_intent = {
        QueryIntent.SNAPSHOT: PlanOperation.SNAPSHOT,
        QueryIntent.TREND: PlanOperation.DAILY_TREND,
        QueryIntent.COMPARE_PERIODS: PlanOperation.PERIOD_COMPARISON,
        QueryIntent.COMPARE_SITES: PlanOperation.SITE_COMPARISON,
        QueryIntent.EXPLAIN_CHANGE: PlanOperation.CHANGE_ANALYSIS,
    }
    operation = operation_by_intent[query.intent]

    if (
        operation in {PlanOperation.DAILY_TREND, PlanOperation.CHANGE_ANALYSIS}
        and query.date_range is None
    ):
        raise ValueError(f"{operation.value} requires a date_range")

    if (
        operation == PlanOperation.PERIOD_COMPARISON
        and (query.date_range is None or query.comparison_range is None)
    ):
        raise ValueError("period_comparison requires two date ranges")

    return ExecutionPlan(
        operation=operation,
        category_id=query.category_id,
        site_ids=query.site_ids,
        metric_ids=query.metric_ids,
        date_range=query.date_range,
        comparison_range=query.comparison_range,
    )
