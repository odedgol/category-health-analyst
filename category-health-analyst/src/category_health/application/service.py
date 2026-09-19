"""Typed application entry point for category-health use cases."""

from typing import Literal

from pydantic import BaseModel, ValidationError

from category_health.application.analysis import CategoryHealthAnalyzer
from category_health.application.output import AnalysisResponse
from category_health.application.requests import (
    AnalysisRequest,
    AnalysisRequestResolver,
    ToolResolutionError,
)
from category_health.catalogs.catalogs import MetricCatalog, SiteCatalog
from category_health.catalogs.categories import CategoryCatalog
from category_health.domain.ports import MetricsRepository
from category_health.domain.query import AnalysisQuery


class MetricOption(BaseModel):
    metric_id: str
    display_name: str
    unit: str
    accepted_names: tuple[str, ...]


class MetricCatalogResponse(BaseModel):
    status: Literal["ok"] = "ok"
    metrics: tuple[MetricOption, ...]


class ClarificationResponse(BaseModel):
    status: Literal["needs_clarification"] = "needs_clarification"
    message: str
    unresolved_fields: tuple[str, ...]
    available_metrics: tuple[MetricOption, ...] | None = None


ApplicationResponse = AnalysisResponse | ClarificationResponse


class CategoryHealthService:
    """Resolve one typed request and perform one deterministic analysis."""

    def __init__(
        self,
        *,
        repository: MetricsRepository,
        category_catalog: CategoryCatalog,
        site_catalog: SiteCatalog,
        metric_catalog: MetricCatalog,
    ) -> None:
        self._request_resolver = AnalysisRequestResolver(
            category_catalog,
            site_catalog,
            metric_catalog,
        )
        self._analyzer = CategoryHealthAnalyzer(repository)
        self._metric_catalog = metric_catalog

    def analyze(self, request: AnalysisRequest) -> ApplicationResponse:
        """Run the complete typed request flow."""
        try:
            query = self.resolve_request(request)
        except ToolResolutionError as error:
            return self.clarification_for(error)
        return self.analyze_query(query)

    def resolve_request(self, request: AnalysisRequest) -> AnalysisQuery:
        """Resolve user-facing references to canonical IDs."""
        return self._request_resolver.resolve(request)

    def analyze_query(self, query: AnalysisQuery) -> AnalysisResponse:
        """Perform the analysis selected by a canonical query."""
        return self._analyzer.analyze(query)

    def list_metrics(self) -> MetricCatalogResponse:
        """Return every supported metric and its accepted names."""
        return MetricCatalogResponse(metrics=self._available_metric_options())

    def invalid_request(self, error: ValidationError) -> ClarificationResponse:
        """Convert adapter validation failure to the application response contract."""
        return self.clarification_for(error)

    def clarification_for(
        self,
        error: ToolResolutionError | ValidationError,
    ) -> ClarificationResponse:
        """Return a typed clarification for a rejected request."""
        unresolved_fields = tuple(
            getattr(error, "unresolved_fields", ("arguments",))
        )
        return ClarificationResponse(
            message=str(error),
            unresolved_fields=unresolved_fields,
            available_metrics=(
                self._available_metric_options()
                if "metrics" in unresolved_fields
                else None
            ),
        )

    def _available_metric_options(self) -> tuple[MetricOption, ...]:
        return tuple(
            MetricOption(
                metric_id=metric.metric_id,
                display_name=metric.display_name,
                unit=metric.unit,
                accepted_names=(metric.display_name, metric.metric_id, *metric.aliases),
            )
            for metric in self._metric_catalog.metrics
        )
