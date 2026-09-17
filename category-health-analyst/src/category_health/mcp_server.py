"""MCP boundary for the deterministic category-health analytics engine."""

import atexit
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

import duckdb
from mcp.server import MCPServer
from pydantic import Field

from category_health.agent.deep_agent import (
    build_analysis_tool,
    build_metric_catalog_tool,
)
from category_health.audit import AuditTrail, current_audit
from category_health.catalogs.catalogs import (
    MetricCatalog,
    SiteCatalog,
    load_metric_catalog,
    load_site_catalog,
)
from category_health.catalogs.categories import load_category_catalog
from category_health.config import load_local_environment
from category_health.domain.query import QueryIntent
from category_health.observability import CompositeAuditSink, create_audit_sink
from category_health.repositories.duckdb import DuckDbMetricsRepository
from category_health.repositories.mock_data import seed_mock_data

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_local_environment(PROJECT_ROOT / ".env")
os.environ.setdefault("OTEL_SERVICE_NAME", "category-health-analyst")


class CategoryHealthMcpRuntime:
    """Own the shared catalogs, mock database, audit sink, and domain tools."""

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
        *,
        audit_path: Path | None = None,
        audit_environment: Mapping[str, str] | None = None,
    ) -> None:
        self.project_root = project_root
        load_local_environment(project_root / ".env")

        self.connection = duckdb.connect(":memory:")
        repository = DuckDbMetricsRepository(self.connection)
        seed_mock_data(repository)

        self.site_catalog: SiteCatalog = load_site_catalog(
            project_root / "data" / "sites.yaml"
        )
        self.metric_catalog: MetricCatalog = load_metric_catalog(
            project_root / "data" / "metrics.yaml"
        )
        self.audit_sink: CompositeAuditSink = create_audit_sink(
            audit_path or project_root / "audit" / "mcp" / "events.jsonl",
            environment=audit_environment,
        )
        category_catalog = load_category_catalog(
            project_root / "data" / "categories_source.txt"
        )
        self._analyze = build_analysis_tool(
            repository=repository,
            category_catalog=category_catalog,
            site_catalog=self.site_catalog,
            metric_catalog=self.metric_catalog,
            audit_sink=self.audit_sink,
        )
        self._list_metrics = build_metric_catalog_tool(
            self.metric_catalog, self.audit_sink
        )

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

        request = {
            "tool": "analyze_category_health",
            "intent": intent,
            "category": category,
            "sites": sites,
            "metrics": metrics,
            "start_date": start_date,
            "end_date": end_date,
            "comparison_start_date": comparison_start_date,
            "comparison_end_date": comparison_end_date,
        }
        audit = AuditTrail(
            self.audit_sink,
            trace_id=self.audit_sink.current_trace_uuid(),
            trace_name="category-health-mcp-request",
            tags=("category-health", "mcp", "mock-data"),
        )
        self.audit_sink.update_active_span(
            input=request,
            metadata={"businessTraceId": str(audit.trace_id)},
        )
        token = current_audit.set(audit)
        try:
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
                result = self._analyze(
                    intent=intent,
                    category=category,
                    sites=sites,
                    metrics=metrics,
                    start_date=start_date,
                    end_date=end_date,
                    comparison_start_date=comparison_start_date,
                    comparison_end_date=comparison_end_date,
                )
                compact_result = {
                    "status": str(result.get("status")),
                    "trace_id": str(audit.trace_id),
                    "value_count": len(result.get("values", [])),
                    "comparison_count": len(result.get("comparisons", [])),
                    "warning_count": len(result.get("warnings", [])),
                    "warnings": result.get("warnings", []),
                }
                step.set_output(
                    {
                        "status": compact_result["status"],
                        "trace_id": compact_result["trace_id"],
                        "value_count": compact_result["value_count"],
                        "comparison_count": compact_result["comparison_count"],
                        "warning_count": compact_result["warning_count"],
                    }
                )
                step.set_output_object(compact_result)
            self.audit_sink.update_active_span(output=compact_result)
            return result
        finally:
            current_audit.reset(token)

    def list_metrics(self) -> dict[str, Any]:
        """Return the closed metric catalog with an independent audit trace."""

        audit = AuditTrail(
            self.audit_sink,
            trace_id=self.audit_sink.current_trace_uuid(),
            trace_name="category-health-mcp-metric-catalog",
            tags=("category-health", "mcp", "metric-catalog"),
        )
        self.audit_sink.update_active_span(
            input={"tool": "list_available_metrics"},
            metadata={"businessTraceId": str(audit.trace_id)},
        )
        token = current_audit.set(audit)
        try:
            with audit.step(
                "mcp_tool_call", input_object={"tool": "list_available_metrics"}
            ) as step:
                result = self._list_metrics()
                compact_result = {
                    "status": str(result.get("status")),
                    "trace_id": str(audit.trace_id),
                    "metric_count": len(result.get("metrics", [])),
                }
                step.set_output(
                    compact_result
                )
                step.set_output_object(compact_result)
            self.audit_sink.update_active_span(output=compact_result)
            return result
        finally:
            current_audit.reset(token)

    def close(self) -> None:
        """Flush observability and close the process-owned DuckDB connection."""

        self.audit_sink.flush()
        self.connection.close()


class _RuntimeProvider:
    """Delay database and telemetry initialization until the first tool call."""

    def __init__(self, runtime: CategoryHealthMcpRuntime | None = None) -> None:
        self._runtime = runtime

    def get(self) -> CategoryHealthMcpRuntime:
        if self._runtime is None:
            self._runtime = CategoryHealthMcpRuntime()
        return self._runtime

    def close(self) -> None:
        if self._runtime is not None:
            self._runtime.close()
            self._runtime = None


def create_mcp_server(
    runtime: CategoryHealthMcpRuntime | None = None,
) -> MCPServer:
    """Build the MCP protocol adapter around one category-health runtime."""

    runtime_provider = _RuntimeProvider(runtime)
    server = MCPServer(
        "Category Health Analyst",
        instructions=(
            "Use list_available_metrics for metric discovery. Use "
            "analyze_category_health for deterministic category/site analysis. "
            "The analysis response contains tool-computed values, comparisons, "
            "warnings, and a business audit trace_id. Never calculate new deltas "
            "outside the returned result."
        ),
    )

    @server.tool()
    def list_available_metrics() -> dict[str, Any]:
        """List every supported metric, ID, unit, and accepted name."""

        return runtime_provider.get().list_metrics()

    @server.tool()
    def analyze_category_health(
        intent: Annotated[
            QueryIntent,
            Field(
                description="snapshot, trend, compare_periods, compare_sites, or "
                "explain_change. Two individual endpoint dates are one trend range, "
                "not two periods."
            ),
        ],
        category: Annotated[
            str, Field(description="A category ID or an unambiguous category name.")
        ],
        sites: Annotated[
            list[str],
            Field(
                min_length=1,
                description="Site IDs, country names, abbreviations, or catalog "
                "aliases. For A minus B, pass [B, A].",
            ),
        ],
        metrics: Annotated[
            list[str],
            Field(
                min_length=1,
                description="Metric IDs, display names, or accepted aliases. Include "
                "only requested metrics.",
            ),
        ],
        start_date: Annotated[
            str | None,
            Field(description="Primary ISO date range start (YYYY-MM-DD)."),
        ] = None,
        end_date: Annotated[
            str | None,
            Field(description="Primary ISO date range end (YYYY-MM-DD)."),
        ] = None,
        comparison_start_date: Annotated[
            str | None,
            Field(description="Comparison ISO range start; only for compare_periods."),
        ] = None,
        comparison_end_date: Annotated[
            str | None,
            Field(description="Comparison ISO range end; only for compare_periods."),
        ] = None,
    ) -> dict[str, Any]:
        """Analyze category health using audited, deterministic repository calculations."""

        return runtime_provider.get().analyze(
            intent=intent,
            category=category,
            sites=sites,
            metrics=metrics,
            start_date=start_date,
            end_date=end_date,
            comparison_start_date=comparison_start_date,
            comparison_end_date=comparison_end_date,
        )

    server.category_health_runtime_provider = runtime_provider
    return server


mcp = create_mcp_server()
atexit.register(mcp.category_health_runtime_provider.close)


def main() -> None:
    """Run the local MCP server over stdio."""

    mcp.run()


if __name__ == "__main__":
    main()
