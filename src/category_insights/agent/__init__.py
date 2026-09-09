"""Orchestration / logic layer: turns a free-text question into a grounded answer.

- `llm.py` — `ChatModelProvider`, the one place the chat model provider is
  chosen.
- `site_resolution.py` — site mention -> site_id, with LLM fallback +
  persisted learning.
- `date_ranges.py` — date phrase -> `DateRange`, fast deterministic parse
  first, LLM fallback for anything it doesn't recognize.
- `intent_extraction.py` — free-text question -> `QueryIntent`, leaving
  `category_mention`/`site_mention` unresolved and delegating date phrases
  to `date_ranges.py`.
- `category_resolution.py` — the 4-handler Chain of Responsibility that
  turns `category_mention` into a `CategoryMatch`, with a confidence tier
  the caller decides whether to trust.
- `answer_formatting.py` — pure functions turning tool results into
  human-readable answer text.
- `graph.py` — the LangGraph pipeline (`build_graph`/`answer_question`)
  that wires every step above into one question-answering flow, calling
  the same Command classes `mcp_server.server` exposes, in-process.

Sprint 5 is complete; every module above is implemented and tested.
"""
