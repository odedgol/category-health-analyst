# Category Insights Agent

A chatbot that lets a product manager ask natural-language questions about
e-commerce category health metrics — image counts, taxonomy alignment, and
missing-category flags, per category and per site — and get accurate,
trend-aware answers, including relative date ranges ("last week") and
grounded explanations of *why* a metric moved.

**Status:** all 6 planned sprints are complete — see
[`docs/FEATURES.md`](docs/FEATURES.md) for what's built and
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) for sprint-by-sprint history.

## Architecture at a glance

Hexagonal (ports & adapters): a `domain` layer defines the contracts
(`Protocol`s) and data shapes everything else depends on. `db`, `rag`, and
`mcp_server` are adapters implementing those contracts. `agent` is the
orchestration/logic layer — a LangGraph pipeline — that turns a question
into tool calls and a grounded answer. `ui` is the Streamlit presentation
layer. Full rationale in [`docs/DESIGN.md`](docs/DESIGN.md).

The agent calls the same MCP `Command` classes `mcp_server.server` exposes
directly, in-process — it doesn't go over the MCP transport to talk to
its own tools. `mcp_server.server` stays runnable standalone for external
MCP clients (Claude Desktop, the MCP inspector).

## Setup

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
# then edit .env and set OPENAI_API_KEY
```

`.env.example` documents every setting — an OpenAI-compatible
`OPENAI_API_KEY` is the only one you need to change for a real run;
everything else (DB path, resolution/similarity thresholds, mock-data
seed) has a workable default.

## Seed the mock data

Two independent seed steps — the metrics warehouse and the notes vector
index. The category-resolution vector index doesn't need a separate
step: it's small and rebuilt inline from the current category list every
time `build_adapters()` runs (see `bootstrap.py`).

```bash
uv run python -m scripts.seed_mock_data --reset      # DuckDB warehouse: categories + daily metrics
uv run python -m scripts.seed_notes_index --reset     # Chroma: category_notes vector collection
```

Both are idempotent-by-`--reset`: safe to rerun. `seed_mock_data.py`
takes `--days` (default 120) and `--seed` (defaults to the configured
`CATEGORY_INSIGHTS_MOCK_DATA_SEED`) if you want a different data shape.

## Run it

**Chat UI (Streamlit):**

```bash
uv run streamlit run src/category_insights/ui/app.py
```

**MCP server**, for an external MCP client (Claude Desktop, the MCP
inspector) rather than the chat UI:

```bash
uv run python -m category_insights.mcp_server.server
```

## Tests and linting

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests never make a real network call — LLM calls go through a
`FakeChatModel` test double, and vector-store tests use a deterministic,
offline `FakeEmbeddingFunction` (see `tests/conftest.py`).
