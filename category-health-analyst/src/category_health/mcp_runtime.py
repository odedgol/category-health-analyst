"""Application-facing runtime used by the MCP protocol adapter."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from category_health.audit import AuditTrail
from category_health.bootstrap import CategoryHealthRuntime, create_demo_runtime
from category_health.domain.query import QueryIntent

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CategoryHealthMcpRuntime:
    """Translate independently audited MCP calls into application use cases."""

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        *,
        audit_path: Path | None = None,
        audit_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.application: CategoryHealthRuntime = create_demo_runtime(
            project_root,
            audit_path=audit_path
            or project_root / "audit" / "mcp" / "events.jsonl",
            audit_environment=audit_environment,
        )
        self.audit_sink = self.application.audit_sink

    def analyze(
        self,
        *,
        intent: QueryIntent,
        category: str,
        sites: list[str],
        metrics: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        comparison_start_date: str | None = None,
        comparison_end_date: str | None = None,
    ) -> dict[str, Any]:
        """Run one independently audited MCP analysis request."""

        arguments = {
            "intent": intent,
            "category": category,
            "sites": sites,
            "metrics": metrics,
            "start_date": start_date,
            "end_date": end_date,
            "comparison_start_date": comparison_start_date,
            "comparison_end_date": comparison_end_date,
        }
        request = {"tool": "analyze_category_health", **arguments}
        audit = self._new_audit("category-health-mcp-request", "mock-data")
        self.audit_sink.update_active_span(
            input=request,
            metadata={"businessTraceId": str(audit.trace_id)},
        )
        with audit.as_current():
            with audit.step(
                "mcp_tool_call",
                input_summary={
                    "intent": intent.value,
                    "category": category,
                    "site_count": len(sites),
                    "metric_count": len(metrics),
                    "start_date": start_date,
                    "end_date": end_date,
                },
                input_object=request,
            ) as step:
                result = self.application.tool_adapter.analyze(arguments, audit=audit)
                summary = self._analysis_summary(result, audit)
                step.set_output(
                    {
                        key: value
                        for key, value in summary.items()
                        if key != "warnings"
                    }
                )
                step.set_output_object(summary)
            self.audit_sink.update_active_span(output=summary)
            return result

    def list_metrics(self) -> dict[str, Any]:
        """Return the closed metric catalog with an independent audit trace."""

        audit = self._new_audit(
            "category-health-mcp-metric-catalog",
            "metric-catalog",
        )
        request = {"tool": "list_available_metrics"}
        self.audit_sink.update_active_span(
            input=request,
            metadata={"businessTraceId": str(audit.trace_id)},
        )
        with audit.as_current():
            with audit.step("mcp_tool_call", input_object=request) as step:
                result = self.application.tool_adapter.list_metrics(audit=audit)
                summary = {
                    "status": str(result.get("status")),
                    "trace_id": str(audit.trace_id),
                    "metric_count": len(result.get("metrics", [])),
                }
                step.set_output(summary)
                step.set_output_object(summary)
            self.audit_sink.update_active_span(output=summary)
            return result

    def close(self) -> None:
        """Flush observability and close the process-owned database connection."""

        self.application.close()

    def _new_audit(self, trace_name: str, scope_tag: str) -> AuditTrail:
        return AuditTrail(
            self.audit_sink,
            trace_id=self.audit_sink.current_trace_uuid(),
            trace_name=trace_name,
            tags=("category-health", "mcp", scope_tag),
        )

    @staticmethod
    def _analysis_summary(
        result: dict[str, Any],
        audit: AuditTrail,
    ) -> dict[str, Any]:
        return {
            "status": str(result.get("status")),
            "trace_id": str(audit.trace_id),
            "value_count": len(result.get("values", [])),
            "comparison_count": len(result.get("comparisons", [])),
            "warning_count": len(result.get("warnings", [])),
            "warnings": result.get("warnings", []),
        }
