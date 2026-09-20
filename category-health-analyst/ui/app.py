"""Small local chat UI for the category-health analyst."""

from pathlib import Path
from uuid import uuid4

import streamlit as st

from category_health.bootstrap import (
    ConversationRuntime,
    create_demo_conversation_runtime,
)
from category_health.config import load_local_environment
from category_health.model_provider import (
    ModelProvider,
    ModelSettings,
    load_model_settings,
    local_server_error,
)
from ui.presentation import answer_text, charts_for_analysis, render_audit, render_charts

PROJECT_ROOT = Path(__file__).parents[1]
RUNTIME_VERSION = 13

load_local_environment(PROJECT_ROOT / ".env")


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


def require_valid_model_settings() -> ModelSettings:
    """Stop rendering with an actionable message when the model is unavailable."""

    settings = load_model_settings()
    if configuration_error := settings.configuration_error():
        st.error(configuration_error)
        st.code(
            "Copy .env.example to .env, configure the selected provider, then restart Streamlit."
        )
        st.stop()
    if server_error := local_server_error(settings):
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
    return settings


def runtime_for_session(model_settings: ModelSettings) -> ConversationRuntime:
    """Reuse one runtime until code changes require a clean reconstruction."""

    if (
        "runtime" not in st.session_state
        or st.session_state.get("runtime_version") != RUNTIME_VERSION
    ):
        with st.spinner("Preparing the local agent and mock data..."):
            st.session_state.runtime = create_runtime(model_settings)
            st.session_state.runtime_version = RUNTIME_VERSION
        st.session_state.chat_messages = []
        st.session_state.last_trace_id = None
    return st.session_state.runtime


def render_sidebar(runtime: ConversationRuntime) -> None:
    """Render local dataset, model and observability context."""

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


def render_conversation_history() -> None:
    """Replay user-visible messages and their deterministic charts."""

    if not st.session_state.chat_messages:
        st.info(
            "Try: Compare image coverage for category 20081 in Germany "
            "between September 9 and September 10, 2026."
        )

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            render_charts(message.get("charts", []))


def answer_question(
    question: str,
    runtime: ConversationRuntime,
    model_settings: ModelSettings,
) -> None:
    """Run one conversation turn and commit its visible UI state."""

    st.session_state.chat_messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    charts = []
    with st.chat_message("assistant"), st.spinner("Analyzing mock data..."):
        try:
            answer = runtime.analysis_session.ask(question)
            response = answer_text(answer.content)
        except Exception as error:
            response = request_failure_message(error, model_settings)
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


def request_failure_message(error: Exception, settings: ModelSettings) -> str:
    """Translate infrastructure failures into useful UI guidance."""

    if (
        settings.provider is ModelProvider.MLX
        and type(error).__name__ == "OpenAIConnectionError"
    ):
        return (
            "The connection to the local Qwen server was lost. Restart "
            "`mlx_lm.server` on port 8080, then try again."
        )
    return (
        "The request failed before a complete answer was produced. "
        f"Error type: `{type(error).__name__}`. Inspect the audit below."
    )


def main() -> None:
    st.set_page_config(page_title="Category Health Analyst", page_icon="📊")
    st.title("Category Health Analyst")
    st.caption("Ask questions in English about the reproducible mock dataset.")

    model_settings = require_valid_model_settings()
    runtime = runtime_for_session(model_settings)
    render_sidebar(runtime)
    render_conversation_history()
    if question := st.chat_input("Ask about category health...", submit_mode="disable"):
        answer_question(question, runtime, model_settings)

    render_audit(runtime)


if __name__ == "__main__":
    main()
