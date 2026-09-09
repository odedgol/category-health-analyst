# Changelog

One entry per sprint merge, newest first.

## Example category names in the clarifying question (unreleased)

Raised directly: what happens when someone asking a question genuinely
doesn't know the right words for it? Before this, "I don't recognize
that category" (or "which category are you asking about?") left them
guessing, unless they separately noticed the sidebar.

- `agent/graph.py` gained `_example_categories_hint()`: both
  clarification messages (`category_mention is None`, and "don't
  recognize") now end with `"For example: <2-3 real category names>."`,
  pulled from the same `list_categories()` call the node already makes —
  no extra query. Deliberately *not* attached to the `"medium"`-
  confidence "did you mean X?" message, which already names one concrete
  category to confirm.
- Manually verified for real: `"how to ask questions"` ->
  `"Which category are you asking about? For example: Women's Running
  Shoes, Laptop Chargers, Vintage Vinyl Records."`

## Conversation history, category sidebar, and charts (unreleased)

Found live-testing the Streamlit app: asking "how to ask questions" (no
category mentioned) correctly produced "Which category are you asking
about?" — but replying to it, with anything at all, produced the exact
same clarifying question again. From the user's side the app looked
stuck/frozen. Root cause: `agent.graph` had no memory of its own
previous turn. Every message was extracted by `intent_extraction` in
total isolation, so a short reply like `"laptop chargers"` had no way to
be understood as *answering* the prior clarification rather than being a
new, categoryless question on its own.

- `intent_extraction.extract_intent()` gained a `history:
  list[ConversationTurn]` parameter (recent turns, oldest first),
  included in the extraction prompt with an explicit instruction to read
  a short reply in context. `agent.graph.AgentState`/`answer_question()`
  and `ui/app.py` thread the real chat history through on every turn —
  `ui/app.py` caps it at the last `_HISTORY_TURNS` (6) messages, so
  prompt size doesn't grow unbounded over a long conversation.
  `date_ranges`/`site_resolution` are untouched — this is specific to
  category clarification, the only multi-turn flow the graph has.
- Manually verified for real (real `OPENAI_API_KEY`, real DB): "how to
  ask questions" → "Which category are you asking about?" → "laptop
  chargers" now correctly resolves to the Laptop Chargers category and
  returns its real data, instead of asking the same question again.
- A wiring-level test (`test_history_is_threaded_from_answer_question_
  into_extract_intent`) confirms `history` actually reaches
  `extract_intent` — `FakeChatModel` can't prove the *model* uses it
  correctly (it ignores prompt content), only that the plumbing is
  correct; the real-key run above is what proves the behavior.

Also, requested alongside the fix:

- **Category-list sidebar**: `ui/app.py` now shows every known category
  and its aliases in the sidebar (via `ListCategoriesCommand` — the same
  Command class `mcp_server.server` exposes, not a raw repository call),
  so a user can see the actual catalog instead of guessing at names and
  hitting the clarification flow.
- **Chart alongside the text answer**: `answer_question()` now returns
  `AnswerResult` (a `text: str` plus whichever of `metric_series` /
  `comparisons` / `snapshot` backed it) instead of a bare string.
  `ui/app.py` renders a line chart for a history question, a bar chart
  for a comparison or a snapshot, next to the same text answer as
  before. `format_answer_node`/`format_answer` (the text) and the chart
  are two views of the *same* underlying data, not one derived from the
  other — `fetch_data_node` computes both from one tool call per metric,
  never twice.
- Manually verified `AnswerResult`'s chart-relevant fields against real
  data for all three shapes (snapshot, multi-day history, month-over-
  month comparison) — correct values, correctly shaped for
  `st.line_chart`/`st.bar_chart`.

## Category catalog: add the missing men's shoes category (unreleased)

Found live-testing the Streamlit app: asking about "Men's Running Shoes"
always resolved to "Women's Running Shoes" instead. Not a matching bug —
the mock catalog (`fixtures/categories.yaml`) genuinely had no men's
shoes category at all, only "Women's Running Shoes" and, unrelatedly,
"Men's Dress Shirts." Every resolver (substring and semantic alike) was
correctly finding the *closest available* category; there just wasn't a
correct one to find.

- Added category 19, "Men's Running Shoes" (aliases: `"men's sneakers"`,
  `"men's running sneakers"`), to `fixtures/categories.yaml` — a real
  e-commerce catalog would split running shoes by gender, and the mock
  data should model that the same way it already does for "Women's
  Running Shoes" and "Men's Dress Shirts" separately.
- Deliberately no alias overlap with category 1's aliases (`"sneakers"`,
  `"running sneakers"`, `"running shoes"`) — an ambiguous, ungendered
  mention like `"sneakers"` alone should still resolve to whichever
  category actually owns that exact alias, not silently redirect based
  on catalog-authoring order.
- Manually verified against a fresh reseed: `"Men's Running Shoes"`
  (exact name) and `"men's sneakers"` (alias) both resolve to category
  19 with zero LLM calls and return its own real metric data; a
  genuinely gender-ambiguous query (`"Shoes in US"`) still correctly
  falls back to a "did you mean" guess, since nothing in the mention
  itself disambiguates which one is meant.

## Sprint 6 — Streamlit UI, final README (unreleased)

- Added `ui/app.py`: a Streamlit chat UI over `agent.graph.answer_question`
  — no direct DB/Chroma/LLM calls, only the same `AdapterBundle` and
  `answer_question` entry point Sprint 5 built. `st.cache_resource` holds
  the adapter bundle across Streamlit reruns (live connections, not data
  to be re-pickled).
- `README.md` rewritten into the full setup/usage guide: install, `.env`
  setup, seeding mock data + the notes/category indexes, running the MCP
  server standalone, running the Streamlit app, and running the tests.
- Full `pytest`/`ruff check`/`ruff format --check` pass across the
  repository (136 tests).
- Manually verified `uv run streamlit run src/category_insights/ui/app.py`
  boots cleanly (HTTP 200, no errors in the server log) against the real,
  freshly-seeded warehouse and the project's real `OPENAI_API_KEY`. No
  browser automation tool was available in this environment to drive an
  actual chat turn through the page itself, but the same `answer_question`
  call the page makes was already verified for real — see Sprint 5.

## Sprint 5 — Agent layer: LangGraph pipeline (unreleased)

- Added `agent/intent_extraction.py`: `extract_intent()` turns a
  free-text question into a `QueryIntent` via one structured-output LLM
  call — `category_mention`/`site_mention` come back as raw text
  (resolving them is later steps' job), `metric_keys` is filtered against
  the metric registry so an invented key is dropped, and date phrases are
  handed to `date_ranges.py` to resolve.
- Added `agent/date_ranges.py`: `parse_known_phrase()` (fast,
  deterministic — today/yesterday/this-or-last week/month/quarter/"last N
  days"/"last N weeks", parameterized by an explicit `now`, never
  `date.today()`) and `resolve_date_range()`, which falls back to an LLM
  for a phrase the fast path doesn't recognize. A nonsensical LLM answer
  (`start` after `end`, or either side `null`) resolves to `None` rather
  than being trusted.
- Added `agent/category_resolution.py`: a 4-handler Chain of
  Responsibility (`ExactNameHandler` -> `AliasHandler` ->
  `SubstringHandler` -> `SemanticSearchHandler`) resolving a
  `category_mention` to a `CategoryMatch` with a confidence tier
  (`"high"`/`"medium"`/`"low"`). Backed by `ChromaCategoryResolverIndex`,
  a second Chroma collection (`category_resolution_index`) kept
  physically separate from `category_notes` per `vectorstore.py`'s
  contract. Only the first two handlers are `"high"` confidence by
  construction — a non-`"high"` match is a legitimate outcome for the
  caller to turn into a clarifying question, never silently acted on.
- Added `agent/answer_formatting.py`: pure functions turning a
  `PeriodComparison`/metric series/`CategorySnapshot`/notes into
  human-readable text — `PeriodComparison.improved` (not the raw sign of
  the delta) decides "improvement" vs "decline", so a lower-is-better
  metric that dropped still reads as good news.
- Added `agent/graph.py`: the LangGraph pipeline
  (`extract_intent -> resolve_site -> resolve_category -> [clarify |
  fetch_data -> [retrieve_notes] -> format_answer]`) and the
  `answer_question()` convenience entry point. A missing, unrecognized,
  or non-`"high"`-confidence category mention routes straight to
  `clarify` before any tool call. `retrieve_notes` runs when
  `intent.wants_explanation` is set, *or* when a computed comparison
  moved by more than `settings.category_insights_unexpected_delta_threshold`
  percentage points — the one setting from Sprint 1 that had gone unused
  until this sprint wired it in.
- `bootstrap.AdapterBundle` gained `category_resolver_index`, (re)indexed
  from the DB's current category list on every `build_adapters()` call —
  unlike the notes collection (seeded offline), this one is small enough,
  and needs to stay in sync with the DB closely enough, that reindexing
  inline on startup is simpler than a separate seed script.
- **A non-`"high"` category match is only offered as a "did you mean X?"
  when it's `"medium"` confidence.** A `"low"` match (the semantic
  handler's honest floor — real testing below saw a 0.23-similarity hit)
  now reads as "I don't recognize that category," not a specific,
  probably-wrong suggestion — naming a low-confidence guess reads as far
  more confident than the match actually is.
- Manually verified end-to-end against the real, freshly-seeded DuckDB
  warehouse (`uv run python -m scripts.seed_mock_data --reset` +
  `seed_notes_index --reset`), the real `category_resolution_index`
  Chroma collection, and the project's real `OPENAI_API_KEY` — not just
  `FakeChatModel`: `answer_question()` correctly answered a snapshot
  question, a 2-week history question, and a month-over-month comparison
  (with grounded notes attached, since it crossed
  `category_insights_unexpected_delta_threshold` without asking "why");
  a `"why did taxonomy alignment change"` question correctly retrieved
  and cited the real taxonomy-migration notes; both exact-name and
  alias mentions resolved with zero LLM calls, exactly as designed.
  This run is what caught the low-confidence "did you mean" issue above:
  `"kicks"` (a colloquial mention of Women's Running Shoes) landed as
  the semantic handler's top match at a low raw similarity score, and
  was, before the fix, offered as "did you mean 'Board Games'?" — wrong,
  and worse, *confidently* wrong. Rerunning the same query showed the
  exact score isn't perfectly stable call to call (OpenAI's embedding
  API isn't bit-for-bit deterministic, and this project's category
  corpus is small enough that a marginal mention can land right at the
  medium/low boundary) — which is itself the argument for the fix: the
  wording must be honest about *tier*, not chase an exact score. A
  clearly medium-confidence mention (`"tents"` -> "Outdoor Camping
  Tents") still correctly offers a "did you mean" after the fix — only
  the `"low"`-tier wording changed.

## Self-learning site resolution (unreleased)

Fixes a gap found while walking through the code: `sites.resolve_site()`
silently defaulted to the US site for any unrecognized mention, unlike
category resolution (asks for clarification) or date-range parsing
(falls back to the LLM). A user could ask about a site phrased in a way
not in the hardcoded alias list and silently get US data back.

- `sites.py` gains `match_known_site()` (returns `None` on no match,
  split out of `resolve_site()`, whose behavior is unchanged) — the
  primitive the learning-aware path needs to tell "matched" apart from
  "should ask the LLM."
- New `domain.ports.SiteAliasStore` port + `DuckDbRepository`
  implementation (`learned_site_aliases` table) — persists aliases the
  LLM has classified, surviving restarts and `--reset`.
- New `agent/site_resolution.py`: `LearnedSiteAliases` (in-memory cache
  over the store) and `resolve_site_with_learning()` — checks the static
  registry, then learned aliases, and only then asks the LLM to classify
  the mention against the closed set of 5 known sites (never open-ended
  generation). A valid answer is learned before being returned; an
  uncertain one (`None`, or an id the LLM invented that isn't a real
  site) falls back to the default **without** being cached, so a bad
  guess never gets locked in.
- Brought back `agent/llm.py::ChatModelProvider` and wired `chat_model` +
  `learned_site_aliases` into `bootstrap.AdapterBundle`.
- Manually verified against the real DuckDB warehouse file: resolving an
  unrecognized site name persists it; a fresh `LearnedSiteAliases`
  (simulating a new process) resolves the same mention with zero LLM
  calls; `--reset` regenerates mock metrics/categories but preserves
  learned aliases.

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
