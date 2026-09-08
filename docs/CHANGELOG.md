# Changelog

One entry per sprint merge, newest first.

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
