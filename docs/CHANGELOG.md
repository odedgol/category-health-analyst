# Changelog

One entry per sprint merge, newest first.

## Sprint 4 — MCP server (unreleased)

- Added `bootstrap.py` (`AdapterBundle` + `build_adapters()`) — the
  Factory/composition root that constructs the real `DuckDbRepository`
  and `ChromaNoteRetriever` once, used by `server.py` (and, from Sprint
  5, `ui/app.py`).
- Added `metrics.MetricKey` — a `Pydantic` `Annotated` type validating a
  metric key against the registry at model-construction time, so an
  unknown key is rejected with a clear `ValidationError` before any
  repository/SQL code runs. Reused by every tool input that takes one.
- Added `mcp_server/tools.py`: the 6 tools as Command classes
  (`ListCategoriesCommand`, `ListMetricsCommand`,
  `GetMetricHistoryCommand`, `CompareMetricPeriodsCommand`,
  `GetCategorySnapshotCommand`, `SearchCategoryNotesCommand`), each with
  its own Pydantic input/output models and ports injected via
  constructor.
- Added `mcp_server/server.py`, wiring the 6 commands to the `mcp` SDK
  (`MCPServer`) — wiring only, no logic. Decided (and documented in
  `docs/DESIGN.md`): the agent will call these Command classes directly,
  in-process, not over a live MCP transport; `server.py` stays runnable
  standalone for external MCP clients.
- Manually verified end-to-end through the real MCP server transport
  (`call_tool`): `list_categories`, `get_metric_history`, and
  `compare_metric_periods` all returned correct real data from a seeded
  DB; `search_category_notes` was confirmed correctly wired, failing
  only on the expected real-OpenAI 401 from a dummy test key.

## Sprint 3 — RAG layer (unreleased)

- Added `vectorstore.py`: `EmbeddingProvider` (the one place
  `OPENAI_API_KEY`/`OPENAI_EMBEDDING_MODEL` are read to build a Chroma
  embedding function) and `get_persistent_client()`, shared by this
  sprint's notes collection and Sprint 5's category-resolution index.
- Added `fixtures/category_notes.yaml`: 10 curated analyst notes — 7
  explaining the 4 injected events from Sprint 2's fixture, 3 general-
  context notes for categories with no event (so retrieval sometimes
  honestly finds nothing).
- Added `mock_notes.py` (loader), `rag/notes_store.py` (chunking +
  `category_notes` collection build, cosine space), `rag/retriever.py`
  (`ChromaNoteRetriever`, filters by `category_id` before ranking,
  drops anything below `min_similarity`), and `scripts/seed_notes_index.py`.
- Manually verified end-to-end with a real local embedding model (no
  OpenAI key available in this environment): a "why did taxonomy
  alignment drop" query for Women's Running Shoes correctly retrieves
  and ranks both taxonomy-migration notes; the same style of query for a
  category with zero notes correctly returns `[]`, not a guess.

## Sprint 2 — DB layer + mock data (unreleased)

- Added `db/connection.py` (schema bootstrap/reset) and
  `db/repository.py::DuckDbRepository`, implementing `MetricsRepository`
  against DuckDB with parameterized queries throughout.
- Added `MetricDataUnavailableError` (`domain/ports.py`) — raised by
  `compare_periods` when a period has no data, instead of a silent or
  crashing average.
- Added `fixtures/categories.yaml`: 18 curated categories, 4 with aliases,
  4 with an injected metric event (taxonomy alignment, image coverage,
  orphan rate, price anomaly rate).
- Added `mock_data.py` (pure generator: trend + noise + event-with-partial-
  recovery, deterministic per seed) and `scripts/seed_mock_data.py` (CLI).
- Verified end-to-end: 120-day seed produces 18 categories × 120 rows;
  Women's Running Shoes' `taxonomy_alignment_pct` drops from ~93 to ~78
  exactly at the configured event day.

## Sprint 1 — domain contracts + metric registry (unreleased)

- Added `Settings` (`settings.py`) — the single place environment variables
  are read.
- Added the metric registry (`metrics.py`): `TrendDirection`,
  `MetricDefinition`, the 9 canonical metrics, and `get_metric()`.
- Added the domain layer (`domain/`): Pydantic models for every object
  that crosses a boundary (`Category`, `MetricPoint`, `CategorySnapshot`,
  `DateRange`, `PeriodComparison`, `Note`, `NoteChunk`, `QueryIntent`,
  `CategoryMatch`), and the four port `Protocol`s (`MetricsRepository`,
  `NoteRetriever`, `CategoryResolverIndex`, `ChatModel`) that adapters will
  implement starting next sprint.
- `DateRange` validates `start <= end` at construction time.

## Sprint 0 — bootstrap (unreleased)

- Initialized git repo, `pyproject.toml` (uv-managed), ruff/pytest config,
  `.gitignore`, `.env.example`, CI workflow, and `docs/` skeleton.
