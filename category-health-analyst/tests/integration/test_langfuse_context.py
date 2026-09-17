"""Real Langfuse/OTel context tests that never export over the network."""

from pathlib import Path

from langfuse import Langfuse, propagate_attributes
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from category_health.audit import AuditTrail
from category_health.observability import create_audit_sink


def test_business_tool_inherits_upstream_trace_and_attributes(tmp_path: Path) -> None:
    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key="pk-test",
        secret_key="sk-test",
        base_url="http://127.0.0.1:9",
        span_exporter=exporter,
        flush_at=1_000,
    )
    sink = create_audit_sink(
        tmp_path / "audit.jsonl",
        environment={
            "LANGFUSE_PUBLIC_KEY": "pk-test",
            "LANGFUSE_SECRET_KEY": "sk-test",
            "LANGFUSE_TRACING_ENVIRONMENT": "local",
            "CATEGORY_HEALTH_APP_VERSION": "0.1.0",
        },
        client=client,
        attribute_context_factory=propagate_attributes,
    )

    try:
        with client.start_as_current_observation(
            name="mcp.tools/call",
            as_type="tool",
            input={"request": "local-test"},
        ):
            audit = AuditTrail(
                sink,
                trace_id=sink.current_trace_uuid(),
                trace_name="category-health-mcp-request",
                session_id="conversation-1",
                tags=("category-health", "mcp", "mock-data"),
            )
            with audit.step(
                "mcp_tool_call",
                input_object={"tool": "analyze_category_health"},
            ) as step:
                step.set_output({"status": "ok", "value_count": 2})
                step.set_output_object({"status": "ok", "value_count": 2})
        client.flush()

        spans = {span.name: span for span in exporter.get_finished_spans()}
        upstream = spans["mcp.tools/call"]
        business = spans["mcp_tool_call"]
        attributes = business.attributes

        assert business.context.trace_id == upstream.context.trace_id
        assert business.parent.span_id == upstream.context.span_id
        assert upstream.attributes["langfuse.trace.name"] == (
            "category-health-mcp-request"
        )
        assert upstream.attributes["langfuse.trace.tags"] == (
            "category-health",
            "mcp",
            "mock-data",
        )
        assert attributes["langfuse.observation.type"] == "tool"
        assert attributes["langfuse.trace.name"] == "category-health-mcp-request"
        assert attributes["session.id"] == "conversation-1"
        assert attributes["langfuse.environment"] == "local"
        assert attributes["langfuse.version"] == "0.1.0"
        assert attributes["langfuse.trace.tags"] == (
            "category-health",
            "mcp",
            "mock-data",
        )
        assert "langfuse.observation.input" in attributes
        assert "langfuse.observation.output" in attributes
    finally:
        client.shutdown()
