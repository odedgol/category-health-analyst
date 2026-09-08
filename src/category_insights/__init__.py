"""Category Insights Agent — a chatbot for e-commerce category-health metrics.

Package layout mirrors a hexagonal architecture: `domain` holds the
contracts and data shapes everything else depends on; `db`, `rag`, and
`mcp_server` are adapters implementing those contracts; `agent` is the
orchestration layer that turns a question into tool calls and an answer;
`ui` is the presentation layer.
"""

__version__ = "0.1.0"
