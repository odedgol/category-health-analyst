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

## Sprint 2 — DB layer + mock data

- **Injection-safety story:** every caller-supplied *value* (category id,
  date) reaches SQL only via a `?` placeholder. `metric_key` is the one
  exception — it becomes a *column name*, and SQL has no placeholder
  syntax for identifiers. The safe pattern for that case is an allowlist
  check: `get_metric(metric_key)` (backed by the fixed `METRICS` registry)
  runs before the key ever touches a query string, raising `KeyError`
  immediately for anything not in the registry. `db/connection.py`'s
  schema DDL uses the same allowlist (`METRICS`) to build column
  definitions — also safe, since that registry is fixed at import time,
  never derived from a request. `ruff`'s `S608` (possible SQL injection)
  fires on both of these legitimate cases; each is annotated with a
  `# noqa: S608` plus a comment explaining why, rather than disabled
  globally.
- `insert_categories`/`insert_metric_points` are on `DuckDbRepository`
  but deliberately **not** part of the `MetricsRepository` protocol — the
  agent and MCP tools only ever read, so write access isn't part of the
  contract they depend on. Only `mock_data.py`'s seed path uses them,
  and it depends on the concrete `DuckDbRepository` class for that reason.
- `compare_periods` raises `MetricDataUnavailableError` (not a silent
  `NULL`-derived NaN) when a period has no data — an expected, answerable
  condition the agent is expected to catch at its boundary and turn into
  an honest "I don't have data for that" response.
- Mock data generation is a pure function of `(fixtures, days, end_date,
  seed)` — no I/O beyond reading the fixture YAML — so it's fully unit
  tested without a database. `scripts/seed_mock_data.py` is the only
  place that wires generation to persistence, and it does so by calling
  `DuckDbRepository` methods, never raw SQL.
- Each injected event applies its full magnitude starting on its
  configured day, then linearly recovers a fraction of itself over a
  recovery window and stays at that partial offset — a dip that's
  findable both immediately ("did X drop last week?") and later ("why is
  X still not back to normal?"), without ever fully healing.

## Sprint 3 — RAG layer

- **Category filter before similarity, not after:** `ChromaNoteRetriever`
  passes `where={"category_id": category_id}` into Chroma's own `query()`
  call, so the ANN search itself never considers another category's
  chunks — this is not a post-hoc Python filter over a larger result set.
  `test_retrieve_filters_by_category_id_before_similarity` proves it: a
  more textually similar note in a different category never leaks in.
- **Test isolation surprised us:** `chromadb.EphemeralClient()` with
  default settings shares an internal system cache across calls within
  one process — a collection built in one test was still visible (with
  its data) in the next, since both got the same in-memory system. Fixed
  by constructing the client with `allow_reset=True` and calling
  `.reset()` in the `chroma_client` fixture. Logged as an example of a
  library behavior that isn't obvious from its name — "Ephemeral" reads
  as "isolated," but isolation had to be forced explicitly.
- **`FakeEmbeddingFunction` subclasses Chroma's `EmbeddingFunction`**
  rather than just duck-typing its `__call__` — Chroma's runtime calls
  `.embed_query()` and `.name()` internally, and `embed_query`'s default
  implementation only exists if you actually inherit from the Protocol
  class (a Protocol can serve as a concrete base, not just a structural
  check). This fake never makes a network call or downloads a model, so
  RAG tests stay fast and fully offline.
- **Manual verification used a real local embedding model**
  (`chromadb`'s bundled all-MiniLM-L6-v2 ONNX model), not the test fake —
  no `OPENAI_API_KEY` was available in this environment. This exercises
  every line of production code except `EmbeddingProvider`'s OpenAI call
  itself; the README will flag that seeding the real index needs a key.
- Chunking (`chunk_note_body`) splits on sentence boundaries only past
  400 characters — every note in the curated corpus is short enough to
  stay a single chunk, matching the spec's "most will be one chunk."
