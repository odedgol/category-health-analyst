"""Validate and resolve model-produced arguments into analytical requests."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from category_health.catalogs.catalogs import MetricCatalog, SiteCatalog
from category_health.catalogs.categories import CategoryCatalog
from category_health.domain.models import DateRange
from category_health.domain.query import AnalysisQuery, QueryIntent


class AnalysisRequest(BaseModel):
    """Untrusted analysis scope received from an interface adapter."""

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
    def validate_scope(self) -> "AnalysisRequest":
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
    ) -> None:
        self._category_catalog = category_catalog
        self._site_catalog = site_catalog
        self._metric_catalog = metric_catalog

    def resolve(
        self,
        request: AnalysisRequest,
    ) -> AnalysisQuery:
        """Resolve one validated request into a canonical analytics query."""

        candidates = self._category_catalog.candidates_by_name(request.category)
        category = self._category_catalog.resolve(request.category)
        if category is None:
            if len(candidates) > 1:
                raise ToolResolutionError(
                    f"Category is ambiguous: {request.category}. Choose an ID: "
                    + ", ".join(str(candidate.category_id) for candidate in candidates),
                    ("category",),
                )
            raise ToolResolutionError(
                f"Unknown category: {request.category}",
                ("category",),
            )

        sites = []
        for mention in request.sites:
            site = self._site_catalog.resolve(mention)
            if site is None:
                raise ToolResolutionError(f"Unknown site: {mention}", ("sites",))
            sites.append(site)

        metrics = []
        for mention in request.metrics:
            metric = self._metric_catalog.resolve(mention)
            if metric is None:
                raise ToolResolutionError(f"Unknown metric: {mention}", ("metrics",))
            metrics.append(metric)

        return AnalysisQuery(
            intent=request.intent,
            metric_ids=tuple(dict.fromkeys(metric.metric_id for metric in metrics)),
            category_id=category.category_id,
            site_ids=tuple(dict.fromkeys(site.site_id for site in sites)),
            date_range=request.date_range(),
            comparison_range=request.comparison_range(),
        )
