"""Protocol-level tests for the category-health MCP server."""

from pathlib import Path
from uuid import UUID

import pytest
from mcp import Client

from category_health.mcp_server import CategoryHealthMcpRuntime, create_mcp_server


@pytest.fixture
def mcp_runtime(tmp_path: Path):
    runtime = CategoryHealthMcpRuntime(
        audit_path=tmp_path / "mcp-events.jsonl",
        audit_environment={},
    )
    yield runtime
    runtime.close()


@pytest.mark.anyio
async def test_mcp_lists_tools_and_calls_analysis(mcp_runtime) -> None:
    server = create_mcp_server(mcp_runtime)

    async with Client(server) as client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools.tools}
        assert tool_names == {"analyze_category_health", "list_available_metrics"}
        analyze_tool = next(
            tool for tool in tools.tools if tool.name == "analyze_category_health"
        )
        assert analyze_tool.input_schema["$defs"]["QueryIntent"]["enum"] == [
            "snapshot",
            "trend",
            "compare_periods",
            "compare_sites",
            "explain_change",
        ]
        assert "Two individual endpoint dates" in analyze_tool.input_schema[
            "properties"
        ]["intent"]["description"]

        result = await client.call_tool(
            "analyze_category_health",
            {
                "intent": "trend",
                "category": "20081",
                "sites": ["Germany"],
                "metrics": ["image coverage"],
                "start_date": "2026-09-09",
                "end_date": "2026-09-10",
            },
        )

    payload = result.structured_content
    assert payload["status"] == "ok"
    assert [value["value"] for value in payload["values"]] == ["72.0000", "64.0000"]
    assert payload["comparisons"][0]["delta"] == "-8.0000"
    assert payload["trace_id"]
    events = mcp_runtime.audit_sink.for_trace(UUID(payload["trace_id"]))
    completed = {
        event.step: event
        for event in events
        if event.status.value == "succeeded"
    }
    assert completed["execute_plan"].output_summary["record_count"] == 2
    assert completed["calculate_and_project"].output_summary == {
        "status": "ok",
        "value_count": 2,
        "comparison_count": 1,
        "warning_count": 0,
    }
    assert completed["mcp_tool_call"].output_object == {
        "status": "ok",
        "trace_id": payload["trace_id"],
        "value_count": 2,
        "comparison_count": 1,
        "warning_count": 0,
        "warnings": [],
    }


@pytest.mark.anyio
async def test_mcp_metric_catalog_is_complete(mcp_runtime) -> None:
    server = create_mcp_server(mcp_runtime)

    async with Client(server) as client:
        result = await client.call_tool("list_available_metrics", {})

    payload = result.structured_content
    assert payload["status"] == "ok"
    assert {metric["metric_id"] for metric in payload["metrics"]} == {
        "image_coverage_percentage",
        "image_count",
        "aligned_aspects_count",
        "misaligned_aspects_count",
        "aligned_aspects_percentage",
        "misaligned_aspects_percentage",
        "has_title",
    }
