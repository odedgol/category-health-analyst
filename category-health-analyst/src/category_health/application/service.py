"""Application entry point for deterministic category-health use cases."""

from typing import Any

from pydantic import ValidationError

from category_health.application.engine import AnalyticsEngine
from category_health.application.output import expose_requested_metrics
from category_health.application.requests import (
    AnalysisRequestResolver,
    ToolResolutionError,
)
from category_health.audit import AuditSink, AuditTrail
from category_health.catalogs.catalogs import MetricCatalog, SiteCatalog
from category_health.catalogs.categories import CategoryCatalog
from category_health.domain.ports import MetricsRepository


def metric_options(metric_catalog: MetricCatalog) -> list[dict[str, Any]]:
    """Return the complete model-facing representation of the metric catalog."""

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
        for metric in metric_catalog.metrics
    ]


def list_metric_catalog(
    metric_catalog: MetricCatalog,
    audit_sink: AuditSink,
    *,
    audit: AuditTrail | None = None,
) -> dict[str, Any]:
    """Run the deterministic metric-discovery use case."""

    audit = audit or AuditTrail(audit_sink)
    response = {
        "status": "ok",
        "trace_id": str(audit.trace_id),
        "metrics": metric_options(metric_catalog),
    }
    with audit.step("list_available_metrics") as step:
        step.set_output(
            {
                "metric_count": len(metric_catalog.metrics),
                "source": "metric_catalog",
            }
        )
        step.set_output_object(response)
    return response


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
        self._analytics = AnalyticsEngine(repository, audit_sink)
        self._metric_catalog = metric_catalog
        self._audit_sink = audit_sink

    def analyze(
        self,
        arguments: dict[str, Any],
        *,
        audit: AuditTrail | None = None,
    ) -> dict[str, Any]:
        """Run the complete deterministic analysis use case."""

        audit = audit or AuditTrail(self._audit_sink)
        try:
            query = self._request_resolver.resolve(arguments, audit=audit)
        except (ToolResolutionError, ValidationError) as error:
            return self._clarification_response(error, audit)

        result = self._analytics.run(query, audit=audit)
        with audit.step("calculate_and_project", input_object=result) as step:
            response = expose_requested_metrics(result).model_dump(mode="json")
            step.set_output(
                {
                    "status": response["status"],
                    "value_count": len(response["values"]),
                    "comparison_count": len(response["comparisons"]),
                    "warning_count": len(response["warnings"]),
                }
            )
            step.set_output_object(response)
        return response

    def list_metrics(self, *, audit: AuditTrail | None = None) -> dict[str, Any]:
        """Return every supported metric and its accepted names."""

        return list_metric_catalog(
            self._metric_catalog,
            self._audit_sink,
            audit=audit,
        )

    def _clarification_response(
        self,
        error: ToolResolutionError | ValidationError,
        audit: AuditTrail,
    ) -> dict[str, Any]:
        unresolved_fields = list(getattr(error, "unresolved_fields", ("arguments",)))
        response: dict[str, Any] = {
            "status": "needs_clarification",
            "trace_id": str(audit.trace_id),
            "message": str(error),
            "unresolved_fields": unresolved_fields,
        }
        if "metrics" in unresolved_fields:
            response["available_metrics"] = metric_options(self._metric_catalog)
        with audit.step("clarification") as step:
            step.set_output_object(response)
        return response
