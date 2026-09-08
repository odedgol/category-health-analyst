"""Domain layer: contracts and data shapes, no I/O, no framework dependencies.

`models.py` holds the Pydantic models that cross every boundary in the
system (DB rows, MCP tool I/O, agent state). `ports.py` holds the
`Protocol` interfaces that `db/`, `rag/`, and `agent/category_resolution.py`
implement as adapters. Nothing in this package imports DuckDB, Chroma,
LangGraph, or any other infrastructure library.
"""
