"""Thin MCP protocol adapter for category-health application use cases."""

import atexit
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from category_health.domain.query import QueryIntent
from category_health.mcp_runtime import CategoryHealthMcpRuntime

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _RuntimeProvider:
    """Delay database and telemetry initialization until the first tool call."""

    def __init__(self, runtime: CategoryHealthMcpRuntime | None = None) -> None:
        self._runtime = runtime

    def get(self) -> CategoryHealthMcpRuntime:
        if self._runtime is None:
            self._runtime = CategoryHealthMcpRuntime(PROJECT_ROOT)
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
