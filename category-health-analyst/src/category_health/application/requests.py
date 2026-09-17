"""Validate and resolve model-produced arguments into analytical requests."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from category_health.audit import AuditSink, AuditTrail
from category_health.catalogs.catalogs import MetricCatalog, SiteCatalog
from category_health.catalogs.categories import CategoryCatalog
from category_health.domain.models import DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent


class AnalyzeCategoryHealthInput(BaseModel):
    """Validated arguments for the single general analysis tool."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    intent: QueryIntent
    category: str = Field(min_length=1)
    sites: tuple[str, ...] = Field(min_length=1)
    metrics: tuple[str, ...] = Field(min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    comparison_start_date: date | None = None
    comparison_end_date: date | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "AnalyzeCategoryHealthInput":
        for start, end in (
            (self.start_date, self.end_date),
            (self.comparison_start_date, self.comparison_end_date),
        ):
            if (start is None) != (end is None):
                raise ValueError("Provide both start and end dates.")
            if start and end:
                DateRange(start=start, end=end)
                if (end - start).days >= 366:
                    raise ValueError("Request at most 366 days per period.")
        if (
            self.intent
            in {QueryIntent.TREND, QueryIntent.EXPLAIN_CHANGE, QueryIntent.COMPARE_PERIODS}
            and self.start_date is None
        ):
            raise ValueError("This analysis requires an explicit date range.")
        if self.intent == QueryIntent.COMPARE_PERIODS:
            if self.comparison_start_date is None:
                raise ValueError("Period comparison requires two complete date ranges.")
        elif self.comparison_start_date is not None:
            raise ValueError("A comparison range is only valid for compare_periods.")
        if any(not value.strip() for value in (*self.sites, *self.metrics)):
            raise ValueError("Site and metric references cannot be blank.")
        return self

    def date_range(self) -> DateRange | None:
        if self.start_date is None or self.end_date is None:
            return None
        return DateRange(start=self.start_date, end=self.end_date)

    def comparison_range(self) -> DateRange | None:
        if self.comparison_start_date is None or self.comparison_end_date is None:
            return None
        return DateRange(
            start=self.comparison_start_date,
            end=self.comparison_end_date,
        )


class ToolResolutionError(ValueError):
    """An error that can be shown as a clarification request."""

    def __init__(self, message: str, unresolved_fields: tuple[str, ...]) -> None:
        super().__init__(message)
        self.unresolved_fields = unresolved_fields


class AnalysisRequestResolver:
    """Convert untrusted model arguments into a canonical analytics query."""

    def __init__(
        self,
        category_catalog: CategoryCatalog,
        site_catalog: SiteCatalog,
        metric_catalog: MetricCatalog,
        audit_sink: AuditSink,
    ) -> None:
        self._category_catalog = category_catalog
        self._site_catalog = site_catalog
        self._metric_catalog = metric_catalog
        self._audit_sink = audit_sink

    def resolve(
        self,
        arguments: dict[str, Any],
        audit: AuditTrail | None = None,
    ) -> AnalyticsQuerySpec:
        """Validate and resolve one analysis request."""

        audit = audit or AuditTrail(self._audit_sink)
        tool_call = {
            "name": "analyze_category_health",
            "arguments": arguments,
        }
        with audit.step("select_tool", input_object=tool_call) as step:
            step.set_output({"tool_name": "analyze_category_health"})
            step.set_output_object(tool_call)

        return self._resolve_analysis(arguments, audit)

    def _resolve_analysis(
        self, arguments: dict[str, Any], audit: AuditTrail
    ) -> AnalyticsQuerySpec:
        with audit.step("validate_tool_arguments", input_object=arguments) as step:
            tool_input = AnalyzeCategoryHealthInput.model_validate(arguments)
            step.set_output({"valid": True})
            step.set_output_object(tool_input)

        with audit.step("resolve_category", input_object=tool_input.category) as step:
            candidates = self._category_catalog.candidates_by_name(tool_input.category)
            category = self._category_catalog.resolve(tool_input.category)
            if category is None:
                if len(candidates) > 1:
                    raise ToolResolutionError(
                        f"Category is ambiguous: {tool_input.category}. Choose an ID: "
                        + ", ".join(str(c.category_id) for c in candidates),
                        ("category",),
                    )
                raise ToolResolutionError(f"Unknown category: {tool_input.category}", ("category",))
            step.set_output({"category_id": category.category_id})
            step.set_output_object(category)

        with audit.step("resolve_sites", input_object=tool_input.sites) as step:
            sites = []
            for mention in tool_input.sites:
                site = self._site_catalog.resolve(mention)
                if site is None:
                    raise ToolResolutionError(f"Unknown site: {mention}", ("sites",))
                sites.append(site)
            step.set_output({"site_count": len(sites)})
            step.set_output_object(sites)

        with audit.step("resolve_metrics", input_object=tool_input.metrics) as step:
            metrics = []
            for mention in tool_input.metrics:
                metric = self._metric_catalog.resolve(mention)
                if metric is None:
                    raise ToolResolutionError(f"Unknown metric: {mention}", ("metrics",))
                metrics.append(metric)
            step.set_output({"metric_count": len(metrics)})
            step.set_output_object(metrics)

        with audit.step("build_query") as step:
            query = AnalyticsQuerySpec(
                intent=tool_input.intent,
                metric_ids=tuple(dict.fromkeys(metric.metric_id for metric in metrics)),
                category_id=category.category_id,
                site_ids=tuple(dict.fromkeys(site.site_id for site in sites)),
                date_range=tool_input.date_range(),
                comparison_range=tool_input.comparison_range(),
                confidence=1.0,
            )
            step.set_output({"is_executable": query.is_executable})
            step.set_output_object(query)

        return query
