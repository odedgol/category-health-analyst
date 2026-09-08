# Changelog

One entry per sprint merge, newest first.

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
