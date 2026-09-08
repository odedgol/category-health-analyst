# Changelog

One entry per sprint merge, newest first.

## Schema rework: real fields, multi-site (unreleased)

Replaced the 9 invented percentage metrics with the fields a real
category-health feed actually tracks, based on direct production
experience: `image_count`, `aligned_tax_count`, `not_aligned_tax_count`,
`missing_category_exists` — plus a `site_id` dimension (data is now
tracked per category **and site/region**, not just per category), since
the same category has different numbers in different markets.

- Added `sites.py`: a small fixed registry (mirrors `metrics.py`'s
  pattern), using eBay's real SiteID values (US=0, Canada=2, UK=3,
  Australia=15, Germany=77) rather than an invented numbering, plus
  `resolve_site()` — plain exact/alias matching, not a Chain of
  Responsibility (a closed set of 5 regions doesn't need fuzzy matching).
- `metrics.METRICS` now has 4 entries instead of 9.
- `MetricPoint`, `CategorySnapshot`, `PeriodComparison` gained `site_id`;
  `QueryIntent` gained `site_mention`.
- Every `MetricsRepository` method (and DB schema: `category_daily_metrics`
  is now keyed by `(category_id, site_id, date)`) and the 3 relevant MCP
  tool inputs (`get_metric_history`, `compare_metric_periods`,
  `get_category_snapshot`) take `site_id`.
- The 4 curated events in `fixtures/categories.yaml` were remapped to the
  new metrics (taxonomy alignment → `aligned_tax_count`, image coverage →
  `image_count`, orphan rate → `missing_category_exists`, price anomaly →
  `not_aligned_tax_count`), and `fixtures/category_notes.yaml`'s prose
  updated to match.
- Manually verified: fresh 120-day seed (18 categories × 5 sites × 120
  days = 10,800 rows) shows the Women's Running Shoes event hitting only
  the US site while Canada is unaffected on the same day, and the
  Bicycle Helmets `missing_category_exists` flag flipping cleanly from
  0.0 to 1.0 exactly on its configured day.

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
