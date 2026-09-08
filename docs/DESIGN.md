# Design

Architecture and design-pattern decisions for the Category Insights Agent,
recorded as they're made — this file grows sprint by sprint, it isn't
written after the fact.

## Sprint 0 — bootstrap

- Repository initialized with a `main` branch; each subsequent layer is
  built on a `sprint/0N-<name>` feature branch and merged with
  `git merge --no-ff` after review, so sprint history stays visible.
- CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`,
  and `pytest` on every push to `main` or a `sprint/*` branch.
- Architecture is hexagonal (ports & adapters): `domain/` defines
  `Protocol` contracts and Pydantic models with zero I/O; `db/`, `rag/`,
  and `mcp_server/` are adapters implementing those contracts; `agent/` is
  the orchestration/logic layer; `ui/` is presentation. See the plan file
  for the full layer map and rationale for each design pattern used
  (Chain of Responsibility, Command, Provider, Factory, dependency
  injection) — summarized here as each layer lands.

## Sprint 1 — domain contracts + metric registry

- `domain/models.py` and `domain/ports.py` have zero I/O and zero
  framework imports beyond `pydantic`, `typing`, and the `langchain_core`
  message/runnable types needed to type `ChatModel`'s signature (not to
  call it) — the domain layer can be read and reasoned about without
  knowing DuckDB, Chroma, or LangGraph exist.
- All four ports (`MetricsRepository`, `NoteRetriever`,
  `CategoryResolverIndex`, `ChatModel`) are `typing.Protocol` — structural
  typing, so adapters and test fakes satisfy them without inheriting from
  anything. This is the DI seam: every adapter is constructed once and
  passed in as one of these protocols, never imported directly by a
  consumer.
- `CategorySnapshot.metrics` is a `dict[str, float]` keyed by metric key,
  not one field per metric — adding a metric to the registry never
  requires a domain model change (Open/Closed).
- `NoteChunk` is split from `Note` (adds `score`, present only after
  retrieval) rather than giving `Note` an always-empty `score` field.
- `compare_periods` convention fixed here to avoid ambiguity downstream:
  `period_a` = earlier/baseline, `period_b` = later/comparison,
  `pct_delta = (value_b - value_a) / value_a`.
- `TrendDirection` uses `enum.StrEnum` (not `class X(str, Enum)`) per
  ruff's `UP042`.
