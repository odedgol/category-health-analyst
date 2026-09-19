"""Application entry point for deterministic category-health use cases."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError

from category_health.application.analysis import CategoryHealthAnalyzer
from category_health.application.output import AnalysisResponse
from category_health.application.requests import (
    AnalysisRequest,
    AnalysisRequestResolver,
    ToolResolutionError,
)
from category_health.audit import AuditSink, AuditTrail
from category_health.catalogs.catalogs import MetricCatalog, SiteCatalog
from category_health.catalogs.categories import CategoryCatalog
from category_health.domain.ports import MetricsRepository


class ClarificationResponse(BaseModel):
    """A typed request for information required before analysis can run."""

    status: str = "needs_clarification"
    trace_id: UUID
    message: str
    unresolved_fields: tuple[str, ...]
    available_metrics: list[dict[str, Any]] | None = None


ApplicationResponse = AnalysisResponse | ClarificationResponse


class CategoryHealthService:
    """Validate, resolve, execute, and project category-health requests."""

    def __init__(
        self,
        *,
        repository: MetricsRepository,
        category_catalog: CategoryCatalog,
        site_catalog: SiteCatalog,
        metric_catalog: MetricCatalog,
        audit_sink: AuditSink,
    ) -> None:
        self._request_resolver = AnalysisRequestResolver(
            category_catalog=category_catalog,
            site_catalog=site_catalog,
            metric_catalog=metric_catalog,
            audit_sink=audit_sink,
        )
        self._analyzer = CategoryHealthAnalyzer(repository)
        self._metric_catalog = metric_catalog
        self._audit_sink = audit_sink

    def analyze(
        self,
        request: AnalysisRequest,
        *,
        audit: AuditTrail | None = None,
    ) -> ApplicationResponse:
        """Resolve one typed request and return its deterministic analysis."""

        audit = audit or AuditTrail(self._audit_sink)
        try:
            query = self._request_resolver.resolve(request, audit=audit)
        except ToolResolutionError as error:
            return self._clarification_response(error, audit)
        return self._analyzer.analyze(query, audit)

    def analyze_arguments(
        self,
        arguments: dict[str, Any],
        *,
        audit: AuditTrail | None = None,
    ) -> dict[str, Any]:
        """Validate untrusted adapter arguments before entering ``analyze``."""

        audit = audit or AuditTrail(self._audit_sink)
        try:
            request = AnalysisRequest.model_validate(arguments)
        except ValidationError as error:
            response = self._clarification_response(error, audit)
        else:
            response = self.analyze(request, audit=audit)
        return response.model_dump(mode="json", exclude_none=True)

    def list_metrics(self, *, audit: AuditTrail | None = None) -> dict[str, Any]:
        """Return every supported metric and its accepted names."""

        audit = audit or AuditTrail(self._audit_sink)
        response = {
            "status": "ok",
            "trace_id": str(audit.trace_id),
            "metrics": self._available_metric_options(),
        }
        with audit.step("list_available_metrics") as step:
            step.set_output(
                {
                    "metric_count": len(response["metrics"]),
                    "source": "metric_catalog",
                }
            )
            step.set_output_object(response)
        return response

    def _available_metric_options(self) -> list[dict[str, Any]]:
        """Describe the closed metric catalog for users and model tools."""

        return [
            {
                "metric_id": metric.metric_id,
                "display_name": metric.display_name,
                "unit": metric.unit,
                "accepted_names": [
                    metric.display_name,
                    metric.metric_id,
                    *metric.aliases,
                ],
            }
            for metric in self._metric_catalog.metrics
        ]

    def _clarification_response(
        self,
        error: ToolResolutionError | ValidationError,
        audit: AuditTrail,
    ) -> ClarificationResponse:
        unresolved_fields = tuple(
            getattr(error, "unresolved_fields", ("arguments",))
        )
        response = ClarificationResponse(
            trace_id=audit.trace_id,
            message=str(error),
            unresolved_fields=unresolved_fields,
            available_metrics=(
                self._available_metric_options()
                if "metrics" in unresolved_fields
                else None
            ),
        )
        with audit.step("clarification") as step:
            step.set_output_object(response)
        return response
