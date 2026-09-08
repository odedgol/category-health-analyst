# Category Insights Agent

A chatbot that lets a product manager ask natural-language questions about
e-commerce category health metrics — image coverage, taxonomy alignment,
attribute completeness, and more — and get accurate, trend-aware answers,
including relative date ranges ("last week") and grounded explanations of
*why* a metric moved.

**Status:** under active sprint-based development — see
[`docs/FEATURES.md`](docs/FEATURES.md) for what's built so far and
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) for sprint-by-sprint history. This
file becomes the full setup/usage guide in the final sprint.

## Architecture at a glance

Hexagonal (ports & adapters): a `domain` layer defines the contracts
(`Protocol`s) and data shapes everything else depends on. `db`, `rag`, and
`mcp_server` are adapters implementing those contracts. `agent` is the
orchestration/logic layer that turns a question into tool calls and a
grounded answer. `ui` is the Streamlit presentation layer. Full rationale
in [`docs/DESIGN.md`](docs/DESIGN.md).
