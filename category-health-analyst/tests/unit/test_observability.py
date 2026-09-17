from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from category_health.agent.session import AnalysisSession
from category_health.audit import AuditTrail, InMemoryAuditSink
from category_health.observability import create_audit_sink


class FakeObservation:
    def __init__(self) -> None:
        self.updates = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class FakeLangfuseClient:
    def __init__(self, *, fail_to_start: bool = False) -> None:
        self.fail_to_start = fail_to_start
        self.active_trace_id = None
        self.calls = []
        self.observations = []
        self.current_span_updates = []
        self.flushed = False

    def get_current_trace_id(self):
        return self.active_trace_id

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        if self.fail_to_start:
            raise RuntimeError("telemetry unavailable")
        previous = self.active_trace_id
        trace_context = kwargs.get("trace_context")
        if trace_context:
            self.active_trace_id = trace_context["trace_id"]
        observation = FakeObservation()
        self.calls.append(kwargs)
        self.observations.append(observation)
        try:
            yield observation
        finally:
            self.active_trace_id = previous

    def get_trace_url(self, *, trace_id: str) -> str:
        return f"https://langfuse.example/trace/{trace_id}"

    def update_current_span(self, **kwargs) -> None:
        self.current_span_updates.append(kwargs)

    def flush(self) -> None:
        self.flushed = True


class AttributeContextRecorder:
    def __init__(self) -> None:
        self.calls = []

    @contextmanager
    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        yield


CONFIG = {
    "LANGFUSE_PUBLIC_KEY": "pk-test",
    "LANGFUSE_SECRET_KEY": "sk-test",
    "LANGFUSE_BASE_URL": "https://langfuse.example",
}


def test_unconfigured_sink_keeps_local_audit_only(tmp_path) -> None:
    sink = create_audit_sink(tmp_path / "audit.jsonl", environment={})
    audit = AuditTrail(sink)

    with audit.step("user_request"):
        pass

    assert sink.telemetry_enabled is False
    assert len(sink.for_trace(audit.trace_id)) == 2
    assert sink.trace_url(audit.trace_id) is None
    assert sink.langchain_callbacks() == []


def test_nested_steps_use_one_trace_and_capture_outputs(tmp_path) -> None:
    client = FakeLangfuseClient()
    attributes = AttributeContextRecorder()
    sink = create_audit_sink(
        tmp_path / "audit.jsonl",
        environment=CONFIG,
        client=client,
        attribute_context_factory=attributes,
    )
    audit = AuditTrail(
        sink,
        trace_name="category-health-test",
        session_id="conversation-1",
        tags=("category-health", "test"),
    )

    with audit.step("user_request", input_object={"question": "hello"}):
        with audit.step("resolve_category", {"mention": "Antiques"}) as step:
            step.set_output({"category_id": 20081})

    assert sink.telemetry_enabled is True
    assert [call["name"] for call in client.calls] == [
        "user_request",
        "resolve_category",
    ]
    assert client.calls[0]["trace_context"] == {"trace_id": audit.trace_id.hex}
    assert client.calls[1]["trace_context"] is None
    assert client.calls[0]["input"]["object"] == {"question": "hello"}
    assert attributes.calls == [
        {
            "trace_name": "category-health-test",
            "session_id": "conversation-1",
            "tags": ["category-health", "test"],
            "version": "0.1.0",
            "environment": "local",
            "metadata": {"businessTraceId": str(audit.trace_id)},
        }
    ]
    assert client.observations[1].updates[-1]["output"] == {
        "summary": {"category_id": 20081}
    }
    assert sink.trace_url(audit.trace_id).endswith(audit.trace_id.hex)


def test_sequential_requests_each_start_their_own_trace(tmp_path) -> None:
    client = FakeLangfuseClient()
    sink = create_audit_sink(
        tmp_path / "audit.jsonl", environment=CONFIG, client=client
    )
    first = AuditTrail(sink)
    second = AuditTrail(sink)

    with first.step("user_request"):
        pass
    with second.step("user_request"):
        pass

    assert client.calls[0]["trace_context"] == {"trace_id": first.trace_id.hex}
    assert client.calls[1]["trace_context"] == {"trace_id": second.trace_id.hex}


def test_object_capture_requires_explicit_opt_in(tmp_path) -> None:
    client = FakeLangfuseClient()
    config = {**CONFIG, "CATEGORY_HEALTH_TELEMETRY_CAPTURE_OBJECTS": "true"}
    sink = create_audit_sink(tmp_path / "audit.jsonl", environment=config, client=client)
    audit = AuditTrail(sink)

    with audit.step("resolve_category", input_object={"question": "hello"}):
        pass

    assert client.calls[0]["input"]["object"] == {"question": "hello"}


def test_non_root_object_is_hidden_without_opt_in(tmp_path) -> None:
    client = FakeLangfuseClient()
    sink = create_audit_sink(
        tmp_path / "audit.jsonl", environment=CONFIG, client=client
    )
    audit = AuditTrail(sink)

    with audit.step("resolve_category", input_object={"category": "Antiques"}):
        pass

    assert client.calls[0]["input"] == {"summary": {}}


def test_mcp_business_span_inherits_active_trace_and_is_a_tool(tmp_path) -> None:
    client = FakeLangfuseClient()
    active_trace_id = uuid4()
    client.active_trace_id = active_trace_id.hex
    attributes = AttributeContextRecorder()
    sink = create_audit_sink(
        tmp_path / "audit.jsonl",
        environment=CONFIG,
        client=client,
        attribute_context_factory=attributes,
    )
    audit = AuditTrail(
        sink,
        trace_id=sink.current_trace_uuid(),
        trace_name="category-health-mcp-request",
        tags=("category-health", "mcp"),
    )

    with audit.step(
        "mcp_tool_call", input_object={"tool": "analyze_category_health"}
    ):
        pass

    assert audit.trace_id == active_trace_id
    assert client.calls[0]["trace_context"] is None
    assert client.calls[0]["as_type"] == "tool"
    assert attributes.calls[0]["trace_name"] == "category-health-mcp-request"
    assert attributes.calls[0]["tags"] == ["category-health", "mcp"]


def test_upstream_span_can_be_enriched(tmp_path) -> None:
    client = FakeLangfuseClient()
    sink = create_audit_sink(
        tmp_path / "audit.jsonl", environment=CONFIG, client=client
    )

    sink.update_active_span(input={"category": "20081"}, output={"status": "ok"})

    assert client.current_span_updates == [
        {"input": {"category": "20081"}, "output": {"status": "ok"}}
    ]


def test_telemetry_failure_does_not_break_business_audit(tmp_path) -> None:
    sink = create_audit_sink(
        tmp_path / "audit.jsonl",
        environment=CONFIG,
        client=FakeLangfuseClient(fail_to_start=True),
    )
    audit = AuditTrail(sink)

    with audit.step("user_request"):
        pass

    assert [event.status.value for event in sink.for_trace(audit.trace_id)] == [
        "started",
        "succeeded",
    ]


def test_analysis_session_passes_observability_callback_to_langchain() -> None:
    callback = object()

    class CallbackSink(InMemoryAuditSink):
        def langchain_callbacks(self):
            return [callback]

    class Agent:
        invocation_config = None

        def invoke(self, payload, config):
            self.invocation_config = config
            return {
                "messages": [*payload["messages"], SimpleNamespace(content="done")]
            }

    agent = Agent()
    sink = CallbackSink()
    session = AnalysisSession(agent, sink, session_id="conversation-1")

    session.ask("Show image coverage")

    assert agent.invocation_config == {
        "recursion_limit": 20,
        "callbacks": [callback],
    }
    root_event = next(
        event
        for event in sink.for_trace(session.last_trace_id)
        if event.step == "user_request" and event.status.value == "succeeded"
    )
    assert root_event.output_object == {"status": "ok", "answer": "done"}
