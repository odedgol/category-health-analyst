"""Deep Agent tool definitions for the category-health application."""

from collections.abc import Callable
from typing import Annotated, Any

from category_health.domain.query import QueryIntent
from category_health.tool_adapter import CategoryHealthToolAdapter


def create_analysis_tool(
    tool_adapter: CategoryHealthToolAdapter,
) -> Callable[..., dict[str, Any]]:
    """Expose the deterministic analysis flow to the language model."""

    def analyze_category_health(
        intent: Annotated[
            QueryIntent,
            "Use trend for one date range, including requests to compare a metric "
            "between two individual dates. Use compare_periods only when the user "
            "provides two complete date ranges: a primary range and a comparison range.",
        ],
        category: str,
        sites: Annotated[
            list[str],
            "Only requested sites. For 'A minus B', use [B, A] because the "
            "tool computes second minus first.",
        ],
        metrics: Annotated[
            list[str],
            "Only metrics explicitly requested by the user. Never add other "
            "catalog metrics unless the user asks for all metrics.",
        ],
        start_date: str | None = None,
        end_date: str | None = None,
        comparison_start_date: str | None = None,
        comparison_end_date: str | None = None,
    ) -> dict[str, Any]:
        """Analyze complete category/site metric rows for the requested scope."""

        return tool_adapter.analyze(
            {
                "intent": intent,
                "category": category,
                "sites": sites,
                "metrics": metrics,
                "start_date": start_date,
                "end_date": end_date,
                "comparison_start_date": comparison_start_date,
                "comparison_end_date": comparison_end_date,
            }
        )

    return analyze_category_health


def create_metric_catalog_tool(
    tool_adapter: CategoryHealthToolAdapter,
) -> Callable[..., dict[str, Any]]:
    """Expose metric discovery to the language model."""

    def list_available_metrics() -> dict[str, Any]:
        """List all supported metric names, IDs, units, and accepted aliases."""

        return tool_adapter.list_metrics()

    return list_available_metrics
