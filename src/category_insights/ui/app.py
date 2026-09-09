"""Streamlit chat UI: the presentation layer over `agent.graph.answer_question`.

Runnable with `uv run streamlit run src/category_insights/ui/app.py`. Talks
to the agent layer only through `answer_question` — no direct DB, Chroma,
or LLM calls happen here, matching the hexagonal boundary the rest of the
system holds to (see `docs/DESIGN.md`).

`st.cache_resource` (not `st.cache_data`) holds the `AdapterBundle` across
Streamlit's reruns: it wraps live DB/Chroma/LLM connections, which need to
survive a rerun unchanged, not be serialized into a data cache.
"""

import streamlit as st

from category_insights.agent.category_resolution import build_default_handlers
from category_insights.agent.graph import answer_question
from category_insights.bootstrap import AdapterBundle, build_adapters
from category_insights.settings import Settings


@st.cache_resource
def _load_adapters() -> AdapterBundle:
    return build_adapters(Settings())


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

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a question about a category...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = answer_question(question, adapters, category_handlers, settings)
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
