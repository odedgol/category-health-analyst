"""Orchestration / logic layer: turns a free-text question into a grounded answer.

Currently home to `site_resolution.py` (site mention -> site_id, with LLM
fallback + learning) and `llm.py` (`ChatModelProvider`, the one place the
chat model provider is chosen). The rest of the agent layer — intent
extraction, category resolution, date-range parsing, and the LangGraph
pipeline that ties them together — is still pending.
"""
