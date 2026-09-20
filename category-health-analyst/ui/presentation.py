"""Render structured conversation results in Streamlit."""

import json

import streamlit as st

from category_health.bootstrap import ConversationRuntime
from category_health.charts import build_chart_specs


def answer_text(content: object) -> str:
    """Convert LangChain text blocks into displayable Markdown."""

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


def charts_for_analysis(
    runtime: ConversationRuntime,
    analysis_output: dict | None,
) -> list[dict]:
    """Build charts directly from the structured analysis result."""

    if analysis_output is None:
        return []
    return build_chart_specs(
        analysis_output,
        site_labels=runtime.site_labels,
        metric_labels=runtime.metric_labels,
    )


def render_charts(charts: list[dict]) -> None:
    """Render deterministic chart specifications."""

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
    """Show the most recent request trace without affecting application state."""

    trace_id = st.session_state.get("last_trace_id")
    if trace_id is None:
        return

    audit_sink = runtime.audit_sink
    events = audit_sink.for_trace(trace_id)
    with st.expander(f"Execution trace · {trace_id}", expanded=False):
        _render_trace_summary(audit_sink, trace_id, events)
        _render_trace_steps(events)
        with st.expander("Local business audit (JSON)", expanded=False):
            st.caption(f"Append-only source: {audit_sink.path}")
            st.json(
                [event.model_dump(mode="json") for event in events],
                expanded=False,
            )


def _render_trace_summary(audit_sink, trace_id, events: list) -> None:
    completed = [event for event in events if event.status.value != "started"]
    failed = sum(event.status.value == "failed" for event in completed)
    total_ms = sum(event.duration_ms or 0 for event in completed)
    st.caption(
        f"{len(completed)} completed steps · {failed} failed · "
        f"{total_ms:.2f} ms cumulative step time"
    )
    if trace_url := audit_sink.trace_url(trace_id):
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


def _render_trace_steps(events: list) -> None:
    completed = [event for event in events if event.status.value != "started"]
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
