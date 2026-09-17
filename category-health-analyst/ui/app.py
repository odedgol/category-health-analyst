"""Small local chat UI for the category-health analyst."""

import json
from pathlib import Path
from uuid import uuid4

import streamlit as st
from category_health.bootstrap import (
    ConversationRuntime,
    create_demo_conversation_runtime,
)
from category_health.charts import build_chart_specs
from category_health.config import load_local_environment
from category_health.model_provider import (
    ModelProvider,
    ModelSettings,
    load_model_settings,
    local_server_error,
)

PROJECT_ROOT = Path(__file__).parents[1]
RUNTIME_VERSION = 10

load_local_environment(PROJECT_ROOT / ".env")


def answer_text(content: object) -> str:
    """Convert LangChain text blocks into text suitable for the chat UI."""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if parts:
            return "\n".join(parts)
    return json.dumps(content, indent=2, default=str)


def create_runtime(model_settings: ModelSettings) -> ConversationRuntime:
    """Create isolated mock data, conversation state and audit for one browser session."""

    session_id = str(uuid4())
    return create_demo_conversation_runtime(
        PROJECT_ROOT,
        audit_path=PROJECT_ROOT / "audit" / "ui" / f"{session_id}.jsonl",
        source="streamlit",
        session_id=session_id,
        model_settings=model_settings,
    )


def reset_conversation(runtime: ConversationRuntime) -> None:
    """Clear model and UI history while retaining the session's mock database."""

    runtime.start_new_conversation()
    st.session_state.chat_messages = []
    st.session_state.last_trace_id = None


def charts_for_analysis(
    runtime: ConversationRuntime,
    analysis_output: dict | None,
) -> list[dict]:
    """Build charts directly from the structured analysis tool result."""

    if analysis_output is None:
        return []
    return build_chart_specs(
        analysis_output,
        site_labels=runtime.site_labels,
        metric_labels=runtime.metric_labels,
    )


def render_charts(charts: list[dict]) -> None:
    """Render chart specifications using native Streamlit charts."""

    for chart in charts:
        with st.container(border=True):
            st.markdown(f"**{chart['title']}**")
            chart_method = st.line_chart if chart["kind"] == "line" else st.bar_chart
            chart_method(
                chart["rows"],
                x="Date",
                y="Value",
                color="Series" if chart["multiple_series"] else "primary",
                x_label="Date",
                y_label=chart["y_label"],
                height=320,
            )


def render_audit(runtime: ConversationRuntime) -> None:
    """Show all events for the most recent user request."""

    trace_id = st.session_state.get("last_trace_id")
    if trace_id is None:
        return
    audit_sink = runtime.audit_sink
    events = audit_sink.for_trace(trace_id)
    with st.expander(f"Execution trace · {trace_id}", expanded=False):
        failed = sum(event.status.value == "failed" for event in events)
        completed = [event for event in events if event.status.value != "started"]
        total_ms = sum(event.duration_ms or 0 for event in completed)
        st.caption(
            f"{len(completed)} completed steps · {failed} failed · "
            f"{total_ms:.2f} ms cumulative step time"
        )
        trace_url = audit_sink.trace_url(trace_id)
        if trace_url:
            st.link_button(
                "Open full trace in Langfuse",
                trace_url,
                icon=":material/open_in_new:",
                width="stretch",
            )
        else:
            st.info(
                "Langfuse is not configured. The complete business audit is still "
                "saved locally."
            )

        rows = [
            {
                "Step": event.step,
                "Status": event.status.value,
                "Duration (ms)": round(event.duration_ms or 0, 2),
                "Error": event.error_message or "",
            }
            for event in completed
        ]
        st.dataframe(rows, width="stretch", hide_index=True)

        with st.expander("Local business audit (JSON)", expanded=False):
            st.caption(f"Append-only source: {audit_sink.path}")
            st.json(
                [event.model_dump(mode="json") for event in events],
                expanded=False,
            )


def main() -> None:
    st.set_page_config(page_title="Category Health Analyst", page_icon="📊")
    st.title("Category Health Analyst")
    st.caption("Ask questions in English about the reproducible mock dataset.")

    model_settings = load_model_settings()
    if configuration_error := model_settings.configuration_error():
        st.error(configuration_error)
        st.code(
            "Copy .env.example to .env, configure the selected provider, then restart Streamlit."
        )
        st.stop()
    if server_error := local_server_error(model_settings):
        st.error("The local Qwen model server is not running.")
        st.write(server_error)
        st.code(
            "HF_HUB_DISABLE_XET=1 mlx_lm.server \\\n"
            "  --model mlx-community/Qwen3-8B-4bit \\\n"
            "  --host 127.0.0.1 --port 8080 --temp 0",
            language="bash",
        )
        st.caption("Start it in a separate terminal, then refresh this page.")
        st.stop()

    if (
        "runtime" not in st.session_state
        or st.session_state.get("runtime_version") != RUNTIME_VERSION
    ):
        with st.spinner("Preparing the local agent and mock data..."):
            st.session_state.runtime = create_runtime(model_settings)
            st.session_state.runtime_version = RUNTIME_VERSION
        st.session_state.chat_messages = []
        st.session_state.last_trace_id = None
    runtime = st.session_state.runtime

    with st.sidebar:
        st.header("Local demo")
        st.write("**Data:** Mock aggregates")
        st.write("**Category:** 20081 · Antiques")
        st.write("**Sites:** Germany (77), UK (3)")
        st.write("**Dates:** 2026-08-02 through 2026-09-10")
        st.write(f"**Provider:** `{runtime.model_settings.provider.value}`")
        st.write(f"**Model:** `{runtime.model_settings.display_name}`")
        if runtime.model_settings.base_url:
            st.write(f"**Endpoint:** `{runtime.model_settings.base_url}`")
        observability = (
            "Langfuse + local JSONL"
            if runtime.audit_sink.telemetry_enabled
            else "Local JSONL"
        )
        st.write(f"**Observability:** {observability}")
        st.caption(f"Session: {runtime.session_id}")
        if st.button("New conversation", width="stretch"):
            reset_conversation(runtime)
            st.rerun()

    if not st.session_state.chat_messages:
        st.info(
            "Try: Compare image coverage for category 20081 in Germany "
            "between September 9 and September 10, 2026."
        )

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_charts(message.get("charts", []))

    if question := st.chat_input("Ask about category health..."):
        st.session_state.chat_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"), st.spinner("Analyzing mock data..."):
            charts = []
            try:
                answer = runtime.analysis_session.ask(question)
                response = answer_text(answer.content)
            except Exception as error:
                if model_settings.provider is ModelProvider.MLX and type(error).__name__ == "OpenAIConnectionError":
                    response = (
                        "The connection to the local Qwen server was lost. Restart "
                        "`mlx_lm.server` on port 8080, then try again."
                    )
                else:
                    response = (
                        "The request failed before a complete answer was produced. "
                        f"Error type: `{type(error).__name__}`. Inspect the audit below."
                    )
                st.error(response)
            else:
                st.markdown(response)
                charts = charts_for_analysis(
                    runtime,
                    runtime.analysis_session.last_analysis_output,
                )
                render_charts(charts)
        st.session_state.chat_messages.append(
            {"role": "assistant", "content": response, "charts": charts}
        )
        st.session_state.last_trace_id = runtime.analysis_session.last_trace_id

    render_audit(runtime)


if __name__ == "__main__":
    main()
