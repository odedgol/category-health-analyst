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

## Sprint 4 — MCP server

- **Agent-to-tool call path: in-process, not a live MCP transport.**
  `agent/graph.py` (Sprint 5) will call the Command classes in
  `mcp_server/tools.py` directly, using the same `AdapterBundle`
  constructed once at startup — it will not spawn or talk to
  `server.py` over stdio/HTTP. Rationale: `tools.py`/`server.py` were
  already split specifically so the tool logic is callable and testable
  without a transport; the real hexagonal boundary that matters is the
  domain ports, not the MCP wire format, and `mcp_server/tools.py` is
  itself just a thin adapter over those ports — same as a web app calling
  its own service layer instead of round-tripping through its own REST
  API. `server.py` stays fully runnable standalone
  (`uv run python -m category_insights.mcp_server.server`) for real
  external MCP clients (Claude Desktop, the MCP inspector), and is
  exercised by the same manual `call_tool` checks below.
- **`MetricKey` validates at input-model construction, not inside
  `execute()`.** An `Annotated[str, AfterValidator(...)]` type in
  `metrics.py`, reused by every tool input that takes a metric key —
  `GetMetricHistoryInput(metric_key="bogus")` raises `ValidationError`
  immediately, before a command, a repository, or SQL is ever involved.
  One validator, defined once, rather than re-checking in each command.
- **`MetricDataUnavailableError` is left to propagate** from
  `CompareMetricPeriodsCommand`, not caught and re-wrapped — there's
  nothing a generic catch-and-reraise here would add. The agent (Sprint
  5) is the layer that's expected to catch it and compose an honest
  answer, since only it has the context (the user's question) to decide
  how to phrase "no data for that."
- **Manually verified through the real MCP transport**, not just direct
  `.execute()` calls: `build_server()` registers all 6 tools;
  `server.call_tool(...)` against a seeded DB returned correct data for
  `list_categories`, `get_metric_history`, and `compare_metric_periods`.
  `search_category_notes` was confirmed correctly wired end-to-end but
  could only be exercised up to a real (expected) 401 from OpenAI, since
  this environment has no `OPENAI_API_KEY` — constructing
  `OpenAIEmbeddingFunction` requires a non-empty key even to build the
  collection, which is chromadb's own validation, not a gap in this
  codebase.

## Schema rework: real fields, multi-site

- The original 9 metrics (`image_coverage_pct`, `taxonomy_alignment_pct`,
  etc.) were invented percentages. Replaced with the fields a real
  category-health feed actually tracks — `image_count`,
  `aligned_tax_count`, `not_aligned_tax_count`, `missing_category_exists`
  — based on direct feedback from real production experience with this
  kind of data. Fewer, more concrete fields; nothing invented for
  variety's sake.
- **`site_id` is a real dimension of the daily metrics, not a label.**
  `category_daily_metrics` is keyed by `(category_id, site_id, date)` —
  the same category has different numbers per region, exactly like a
  real multi-region catalog. `categories` itself stays site-independent
  (a category is the same conceptual grouping everywhere; only its daily
  numbers differ by site).
- **Site resolution is deliberately *not* a Chain of Responsibility.**
  `sites.resolve_site()` is one plain function doing exact/alias
  matching over a fixed 5-entry registry. `agent.category_resolution`'s
  4-handler chain earns its keep because categories are an open-ended,
  aliased, fuzzy-matchable set; sites are a small closed list where a
  chain would be ceremony without benefit — reusing the same machinery
  everywhere "because it's the pattern already in the codebase" is
  exactly the kind of over-application this project is trying to avoid.
- **Site ids are eBay's real SiteID values** (developer.ebay.com's
  SiteID-to-GlobalID reference: US=0, Canada=2, UK=3, Australia=15,
  Germany=77), not an invented 0/1/2/3 scheme — a real, checkable
  numbering is more honest mock data.
- `missing_category_exists` is a 0/1 flag stored as the same `DOUBLE`
  column type as every other metric (so it fits the existing schema/
  formatting machinery unchanged) rather than a separate boolean column
  — `TrendDirection`/arrow/delta logic all still apply correctly to it
  unmodified (0 → 1 is `↑`/"worsened" for a lower-is-better metric).
- This rework touched every layer built so far (domain models, DB schema
  and queries, mock-data generation, the 2 fixture YAMLs, 3 MCP tool
  inputs) rather than being isolated to one file — a reminder that the
  metric/site shape is a foundational decision worth getting right
  before building much on top of it, not a detail to defer.

## Self-learning site resolution

- **`match_known_site` returns `None` on failure; `resolve_site` still
  defaults.** Splitting these apart (rather than adding a `strict: bool`
  flag to one function) is what lets
  `agent.site_resolution.resolve_site_with_learning` tell "the static
  registry didn't match" apart from "nothing at all was said" — those
  are different situations (one is worth asking an LLM about, the other
  isn't) that a single boolean-return function would conflate.
- **An uncertain LLM answer is never cached.** `SiteClassification.site_id
  = None`, or a `site_id` the model returns that isn't actually in
  `SITES_BY_ID` (never trusted blindly — always re-checked against the
  registry), both fall back to the default *without* writing to
  `learned_site_aliases`. Caching a wrong or "no answer" guess would
  permanently lock in a bad mapping — worse than asking the LLM again
  next time the same phrase comes up.
- **`--reset` (in `seed_mock_data.py`) does not touch
  `learned_site_aliases`.** Categories and metrics are mock data, fully
  regenerable from the seed; learned aliases are real accumulated value
  from real questions asked, not mock data, and wiping them on every
  reset would defeat the point of learning them at all.
- **This is still a plain function, not a Chain of Responsibility class**,
  even though it now has an LLM fallback step like `date_ranges.py` does.
  The similarity to `date_ranges.py`'s chain is structural (fast path,
  then LLM), not a reason to force the same class machinery — five sites
  is still a small enough closed set that a `Handler` per step would be
  ceremony, not clarity.
- **Manually verified against the real DuckDB file**, not just the
  in-memory test doubles: resolving an unrecognized site persists it to
  `learned_site_aliases`; a *fresh* `LearnedSiteAliases` instance
  (standing in for a new process reading the same file) resolves the
  same mention with zero LLM calls; `--reset` regenerates mock data but
  leaves the learned table untouched.

## Sprint 5 — Agent layer: LangGraph pipeline

- **Category resolution's 4-handler chain is a real Chain of
  Responsibility**, unlike sites — the payoff `sites.match_known_site`'s
  docstring promised. Only the first two handlers (`ExactNameHandler`,
  `AliasHandler`) are `confidence="high"`; `SubstringHandler` is
  `"medium"`; the semantic handler's tier is computed from the raw
  similarity score against the two configured thresholds. This module
  never decides what to *do* with a non-`"high"` match — that's
  `agent.graph`'s call — so the resolution logic stays testable
  independent of the clarification-question wording built on top of it.
- **The category-resolution vector index is a second, separate Chroma
  collection** (`category_resolution_index`), never `category_notes` —
  `vectorstore.py`'s contract from Sprint 3, finally exercised. It's
  (re)indexed inline on every `build_adapters()` call rather than via an
  offline seed script like the notes corpus: the category list is small
  and must always match the DB exactly, so an `upsert`-based reindex on
  every startup is simpler than keeping a second script in sync.
- **`date_ranges.py` and `site_resolution.py` share a shape, not a base
  class**: both are "fast deterministic path, then an LLM asked only for
  what falls through." Neither is a shared abstraction — matching the
  project's running rule (see the site-resolution entry above) that a
  shared *shape* doesn't obligate a shared *class*.
- **`category_insights_unexpected_delta_threshold` (defined in Sprint 1,
  unused until now)**: `agent.graph`'s `fetch_data_node` checks every
  computed `PeriodComparison`'s `pct_delta` against it, in percentage
  points, and routes to `retrieve_notes` even when `wants_explanation`
  is `False` if any comparison crossed it — a big enough swing is worth
  explaining whether or not the user thought to ask "why."
- **The graph has exactly one branch point before any tool call**:
  `resolve_category`'s result. A missing mention, an unrecognized one, or
  a non-`"high"`-confidence match all route to `clarify` — the graph
  never guesses at a category, matching the "asks for clarification"
  behavior planned for category resolution back in the site-resolution
  entry above (in contrast to sites, which default, and dates, which ask
  the LLM).
- **Manually verified against a freshly-seeded, real DuckDB warehouse**
  (`scripts.seed_mock_data --reset`): `list_categories` returned all 18
  fixture categories; `AliasHandler` resolved `"sneakers"` to `"Women's
  Running Shoes"` with zero LLM calls; a real `CompareMetricPeriodsCommand`
  call, run through `format_period_comparison`, produced a correct,
  readable sentence. `build_adapters()` with a dummy API key reached the
  real category-index embedding call before failing on the expected 401
  — same wall Sprint 3/4 hit; this environment still has no real key to
  verify the LLM-dependent paths (`extract_intent`, semantic category
  resolution) beyond the `FakeChatModel` test suite.

## Sprint 6 — Streamlit UI, final README

- **`ui/app.py` depends on nothing but `agent.graph.answer_question`** —
  no DB/Chroma/LLM import in the file at all. The hexagonal boundary
  promised since Sprint 0 holds all the way to the presentation layer.
- **`st.cache_resource`, not `st.cache_data`, holds the `AdapterBundle`**
  across Streamlit reruns — it wraps live connections (a DuckDB handle, a
  Chroma client, an LLM client) that must survive a rerun as the same
  objects, not be serialized into a data cache and reconstructed.
- **Manually verified the app boots**: `uv run streamlit run
  src/category_insights/ui/app.py` served HTTP 200 with a clean server
  log against the real seeded warehouse. No browser automation tool was
  available in this environment to drive an actual chat turn through it.
