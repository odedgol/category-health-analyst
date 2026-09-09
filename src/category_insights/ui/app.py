"""Streamlit chat UI: the presentation layer over `agent.graph.answer_question`.

Runnable with `uv run streamlit run src/category_insights/ui/app.py`. The
chat itself talks to the agent layer only through `answer_question` — no
direct DB/Chroma/LLM calls. The category-list sidebar is the one other
thing this page reads, and it goes through `ListCategoriesCommand` (the
same Command class `mcp_server.server` exposes), never a raw repository
or SQL call, so the hexagonal boundary the rest of the system holds to
(see `docs/DESIGN.md`) still isn't crossed.

`st.cache_resource` (not `st.cache_data`) holds the `AdapterBundle` across
Streamlit's reruns: it wraps live DB/Chroma/LLM connections, which need to
survive a rerun unchanged, not be serialized into a data cache.
"""

import pandas as pd
import streamlit as st

from category_insights.agent.category_resolution import build_default_handlers
from category_insights.agent.graph import AnswerResult, answer_question
from category_insights.bootstrap import AdapterBundle, build_adapters
from category_insights.mcp_server.tools import ListCategoriesCommand, ListCategoriesInput
from category_insights.metrics import get_metric
from category_insights.settings import Settings

_HISTORY_TURNS = 6
"""How many prior chat messages to feed back into intent extraction as context."""


@st.cache_resource
def _load_adapters() -> AdapterBundle:
    return build_adapters(Settings())


def _render_category_sidebar(adapters: AdapterBundle) -> None:
    """Lists every known category (and its aliases) — so a user knows what to ask about.

    This exists because "I asked about a category that isn't in the
    catalog and got a wrong/uncertain guess back" is a real, confusing
    failure mode of `agent.category_resolution` (see `docs/CHANGELOG.md`)
    — showing the actual catalog upfront is cheaper than every user
    discovering its edges by trial and error.
    """
    with st.sidebar:
        st.subheader("Known categories")
        categories = (
            ListCategoriesCommand(adapters.repository).execute(ListCategoriesInput()).categories
        )
        table = pd.DataFrame(
            {
                "Category": [category.name for category in categories],
                "Also known as": [", ".join(category.aliases) for category in categories],
            }
        )
        st.dataframe(table, hide_index=True, use_container_width=True)


def _build_chart(result: AnswerResult) -> tuple[str, pd.DataFrame] | None:
    """Turn whichever structured data backs `result` into a `(chart kind, DataFrame)` pair.

    Mirrors `fetch_data_node`'s three branches (history / comparison /
    snapshot) one-for-one — exactly one of `result`'s structured fields
    is ever populated for a fetched answer, so this never has to pick
    between competing chart choices. `None` for a clarification, which
    has no numbers to chart at all.
    """
    if result.metric_series:
        columns = {
            get_metric(metric_key).display_name: {point.date: point.value for point in points}
            for metric_key, points in result.metric_series.items()
            if points
        }
        return ("line", pd.DataFrame(columns)) if columns else None

    if result.comparisons:
        rows = {}
        for comparison in result.comparisons:
            metric = get_metric(comparison.metric_key)
            period_a_label = comparison.period_a.label or str(comparison.period_a.start)
            period_b_label = comparison.period_b.label or str(comparison.period_b.start)
            rows[metric.display_name] = {
                period_a_label: comparison.value_a,
                period_b_label: comparison.value_b,
            }
        return ("bar", pd.DataFrame(rows).T) if rows else None

    if result.snapshot is not None and result.snapshot.metrics:
        values = {
            get_metric(key).display_name: value for key, value in result.snapshot.metrics.items()
        }
        return ("bar", pd.DataFrame({"Value": values}))

    return None


def _render_chart(kind: str, data: pd.DataFrame) -> None:
    if kind == "line":
        st.line_chart(data)
    else:
        st.bar_chart(data)


def main() -> None:
    st.set_page_config(page_title="Category Insights", page_icon="📊")
    st.title("Category Insights Agent")
    st.caption(
        "Ask about category-health metrics — image counts, taxonomy alignment, "
        "missing-category flags — across sites and date ranges."
    )

    adapters = _load_adapters()
    category_handlers = build_default_handlers(adapters.category_resolver_index)
    settings = Settings()

    _render_category_sidebar(adapters)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("chart") is not None:
                kind, data = message["chart"]
                _render_chart(kind, data)

    question = st.chat_input("Ask a question about a category...")
    if not question:
        return

    # Captured before appending the new question: the turns that precede it,
    # so a short reply to the assistant's last message (most importantly, a
    # clarifying question) is extracted in context instead of in a vacuum —
    # see `intent_extraction.extract_intent`'s `history` parameter.
    history = [(m["role"], m["content"]) for m in st.session_state.messages[-_HISTORY_TURNS:]]

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = answer_question(
                question, adapters, category_handlers, settings, history=history
            )
        st.markdown(result.text)
        chart = _build_chart(result)
        if chart is not None:
            _render_chart(*chart)
    st.session_state.messages.append({"role": "assistant", "content": result.text, "chart": chart})


if __name__ == "__main__":
    main()
