"""The first deterministic Category Health Analyst agent."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from category_health.agent.planner import ExecutionPlan, PlanOperation, build_plan
from category_health.audit import AuditSink, AuditTrail
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.ports import MetricsRepository
from category_health.domain.query import AnalyticsQuerySpec


class QueryData(BaseModel):
    """Records returned for one site and one semantic period."""

    site_id: int
    period: Literal["snapshot", "current", "comparison"]
    records: tuple[CategorySiteMetrics, ...]
    available_date_range: DateRange | None = None


class AgentResult(BaseModel):
    """Structured output of one deterministic agent run."""

    trace_id: UUID
    query: AnalyticsQuerySpec
    plan: ExecutionPlan
    data: tuple[QueryData, ...]


class AnalyticsAgent:
    """Plan and execute validated analytics requests."""

    def __init__(self, repository: MetricsRepository, audit_sink: AuditSink) -> None:
        self._repository = repository
        self._audit_sink = audit_sink

    def run(self, query: AnalyticsQuerySpec, audit: AuditTrail | None = None) -> AgentResult:
        audit = audit or AuditTrail(self._audit_sink)

        with audit.step("validate_query", input_object=query) as step:
            if not query.is_executable:
                raise ValueError(
                    f"Query is not executable; unresolved fields: {query.unresolved_fields}"
                )
            step.set_output({"is_executable": True})
            step.set_output_object(query)

        with audit.step("plan_query", input_object=query) as step:
            plan = build_plan(query)
            step.set_output({"operation": plan.operation.value})
            step.set_output_object(plan)

        with audit.step("execute_plan", input_object=plan) as step:
            data = tuple(self._execute(plan))
            step.set_output(
                {
                    "result_groups": len(data),
                    "record_count": sum(len(group.records) for group in data),
                }
            )
            step.set_output_object(data)

        result = AgentResult(trace_id=audit.trace_id, query=query, plan=plan, data=data)
        return result

    def _execute(self, plan: ExecutionPlan) -> list[QueryData]:
        if plan.operation == PlanOperation.SNAPSHOT:
            return [self._snapshot_for_site(plan, site_id) for site_id in plan.site_ids]

        if plan.operation in {PlanOperation.DAILY_TREND, PlanOperation.CHANGE_ANALYSIS}:
            assert plan.date_range is not None
            return [
                QueryData(
                    site_id=site_id,
                    period="current",
                    records=tuple(
                        self._repository.latest_per_day(plan.category_id, site_id, plan.date_range)
                    ),
                    available_date_range=self._repository.available_date_range(
                        plan.category_id, site_id
                    ),
                )
                for site_id in plan.site_ids
            ]

        if plan.operation == PlanOperation.SITE_COMPARISON:
            return self._daily_or_snapshot_by_site(plan)

        assert plan.operation == PlanOperation.PERIOD_COMPARISON
        assert plan.date_range is not None
        assert plan.comparison_range is not None
        result: list[QueryData] = []
        for site_id in plan.site_ids:
            result.append(
                QueryData(
                    site_id=site_id,
                    period="comparison",
                    records=tuple(
                        self._repository.latest_per_day(
                            plan.category_id, site_id, plan.comparison_range
                        )
                    ),
                    available_date_range=self._repository.available_date_range(
                        plan.category_id, site_id
                    ),
                )
            )
            result.append(
                QueryData(
                    site_id=site_id,
                    period="current",
                    records=tuple(
                        self._repository.latest_per_day(
                            plan.category_id, site_id, plan.date_range
                        )
                    ),
                    available_date_range=self._repository.available_date_range(
                        plan.category_id, site_id
                    ),
                )
            )
        return result

    def _daily_or_snapshot_by_site(self, plan: ExecutionPlan) -> list[QueryData]:
        if plan.date_range is None:
            return [self._snapshot_for_site(plan, site_id) for site_id in plan.site_ids]
        return [
            QueryData(
                site_id=site_id,
                period="current",
                records=tuple(
                    self._repository.latest_per_day(plan.category_id, site_id, plan.date_range)
                ),
                available_date_range=self._repository.available_date_range(
                    plan.category_id, site_id
                ),
            )
            for site_id in plan.site_ids
        ]

    def _snapshot_for_site(self, plan: ExecutionPlan, site_id: int) -> QueryData:
        if plan.date_range is not None:
            records = self._repository.latest_per_day(plan.category_id, site_id, plan.date_range)
            record = max(records, key=lambda row: row.observed_date) if records else None
        else:
            record = self._repository.latest_update(plan.category_id, site_id)
        return QueryData(
            site_id=site_id,
            period="snapshot",
            records=(record,) if record is not None else (),
            available_date_range=self._repository.available_date_range(
                plan.category_id, site_id
            ),
        )
