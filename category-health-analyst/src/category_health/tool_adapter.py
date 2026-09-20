"""Dictionary and audit boundary shared by agent and MCP tools."""

from typing import Any

from pydantic import ValidationError

from category_health.application.requests import AnalysisRequest, ToolResolutionError
from category_health.application.service import (
    CategoryHealthService,
    ClarificationResponse,
)
from category_health.audit import AuditSink, AuditTrail, current_audit


class CategoryHealthToolAdapter:
    """Translate untrusted tool arguments around the clean application flow."""

    def __init__(self, service: CategoryHealthService, audit_sink: AuditSink) -> None:
        self._service = service
        self._audit_sink = audit_sink

    def analyze(
        self,
        arguments: dict[str, Any],
        *,
        audit: AuditTrail | None = None,
    ) -> dict[str, Any]:
        """Validate, execute, audit, and serialize one tool call."""
        audit = audit or current_audit.get() or AuditTrail(self._audit_sink)
        try:
            with audit.step("validate_request", input_object=arguments) as step:
                request = AnalysisRequest.model_validate(arguments)
                step.set_output_object(request)
        except ValidationError as error:
            return self._record_clarification(self._service.invalid_request(error), audit)

        try:
            with audit.step("resolve_request", input_object=request) as step:
                query = self._service.resolve_request(request)
                step.set_output_object(query)
        except ToolResolutionError as error:
            return self._record_clarification(self._service.clarification_for(error), audit)

        with audit.step(f"execute_{query.intent.value}", input_object=query) as step:
            response = self._service.analyze_query(query)
            step.set_output(self._response_summary(response.model_dump(mode="json")))

        # Keep ``delta: null`` for boolean transitions; null is part of that metric's
        # public contract, not an omitted optional field.
        result = response.model_dump(mode="json")
        result["trace_id"] = str(audit.trace_id)
        with audit.step("analysis_response", input_object=query) as step:
            step.set_output(self._response_summary(result))
            step.set_output_object(result)
        return result

    def list_metrics(self, *, audit: AuditTrail | None = None) -> dict[str, Any]:
        """Audit and serialize the typed metric catalog."""
        audit = audit or current_audit.get() or AuditTrail(self._audit_sink)
        with audit.step("list_available_metrics") as step:
            response = self._service.list_metrics()
            result = response.model_dump(mode="json")
            result["trace_id"] = str(audit.trace_id)
            step.set_output({"metric_count": len(response.metrics)})
            step.set_output_object(result)
            return result

    @staticmethod
    def _response_summary(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": result.get("status"),
            "value_count": len(result.get("values", [])),
            "comparison_count": len(result.get("comparisons", [])),
            "warning_count": len(result.get("warnings", [])),
        }

    def _record_clarification(
        self,
        response: ClarificationResponse,
        audit: AuditTrail,
    ) -> dict[str, Any]:
        result = response.model_dump(mode="json", exclude_none=True)
        result["trace_id"] = str(audit.trace_id)
        with audit.step("clarification") as step:
            step.set_output_object(result)
        return result
