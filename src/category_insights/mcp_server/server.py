"""Wires the 6 Command classes to the `mcp` SDK. No logic lives here.

Runnable standalone (`uv run python -m category_insights.mcp_server.server`)
for external MCP clients (Claude Desktop, the MCP inspector). The agent
(Sprint 5) does not talk to this process — it calls the same Command
classes in-process, built from the same `AdapterBundle`, so there's no
transport overhead between the agent and its own tools. See
`docs/DESIGN.md` for the rationale.
"""

from datetime import date

from mcp.server.mcpserver import MCPServer

from category_insights.bootstrap import build_adapters
from category_insights.mcp_server.tools import (
    CompareMetricPeriodsCommand,
    CompareMetricPeriodsInput,
    CompareMetricPeriodsOutput,
    GetCategorySnapshotCommand,
    GetCategorySnapshotInput,
    GetCategorySnapshotOutput,
    GetMetricHistoryCommand,
    GetMetricHistoryInput,
    GetMetricHistoryOutput,
    ListCategoriesCommand,
    ListCategoriesInput,
    ListCategoriesOutput,
    ListMetricsCommand,
    ListMetricsInput,
    ListMetricsOutput,
    SearchCategoryNotesCommand,
    SearchCategoryNotesInput,
    SearchCategoryNotesOutput,
)
from category_insights.settings import Settings


def build_server(settings: Settings | None = None) -> MCPServer:
    """Construct an `MCPServer` with all 6 category-insights tools registered."""
    adapters = build_adapters(settings or Settings())

    list_categories_command = ListCategoriesCommand(adapters.repository)
    list_metrics_command = ListMetricsCommand()
    get_metric_history_command = GetMetricHistoryCommand(adapters.repository)
    compare_metric_periods_command = CompareMetricPeriodsCommand(adapters.repository)
    get_category_snapshot_command = GetCategorySnapshotCommand(adapters.repository)
    search_category_notes_command = SearchCategoryNotesCommand(adapters.note_retriever)

    server = MCPServer(
        name="category-insights",
        instructions=(
            "Tools for e-commerce category-health metrics: numeric lookups "
            "(list_categories, list_metrics, get_metric_history, "
            "compare_metric_periods, get_category_snapshot) and retrieval-only "
            "note search (search_category_notes). Category ids come from "
            "list_categories — these tools take category_id, never a free-text name."
        ),
    )

    @server.tool()
    def list_categories() -> ListCategoriesOutput:
        """List every category, with its id, display name, and aliases."""
        return list_categories_command.execute(ListCategoriesInput())

    @server.tool()
    def list_metrics() -> ListMetricsOutput:
        """List every tracked metric: its key, unit, trend direction, and meaning."""
        return list_metrics_command.execute(ListMetricsInput())

    @server.tool()
    def get_metric_history(
        category_id: int, metric_key: str, start_date: date, end_date: date
    ) -> GetMetricHistoryOutput:
        """Fetch the daily history of one metric for one category over a date range."""
        return get_metric_history_command.execute(
            GetMetricHistoryInput(
                category_id=category_id,
                metric_key=metric_key,
                start_date=start_date,
                end_date=end_date,
            )
        )

    @server.tool()
    def compare_metric_periods(
        category_id: int,
        metric_key: str,
        period_a_start: date,
        period_a_end: date,
        period_b_start: date,
        period_b_end: date,
    ) -> CompareMetricPeriodsOutput:
        """Compare one metric's average value between an earlier period (a) and a later one (b)."""
        return compare_metric_periods_command.execute(
            CompareMetricPeriodsInput(
                category_id=category_id,
                metric_key=metric_key,
                period_a_start=period_a_start,
                period_a_end=period_a_end,
                period_b_start=period_b_start,
                period_b_end=period_b_end,
            )
        )

    @server.tool()
    def get_category_snapshot(
        category_id: int, as_of_date: date | None = None
    ) -> GetCategorySnapshotOutput:
        """Fetch every metric for one category on one day (defaults to the latest available day)."""
        return get_category_snapshot_command.execute(
            GetCategorySnapshotInput(category_id=category_id, as_of_date=as_of_date)
        )

    @server.tool()
    def search_category_notes(
        category_id: int, query: str, top_k: int = 3
    ) -> SearchCategoryNotesOutput:
        """Retrieve analyst notes for one category that are similar to `query` (retrieval only)."""
        return search_category_notes_command.execute(
            SearchCategoryNotesInput(category_id=category_id, query=query, top_k=top_k)
        )

    return server


def main() -> None:
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
