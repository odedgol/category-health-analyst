# Category Health Analyst Architecture

This document is the source of truth for the current design. The central rule is:

> The LLM interprets. The deterministic core calculates.

## 1. Before the refactor

The runtime behavior was correct, but the package structure hid the system story:

```text
Streamlit / CLI / evaluation / MCP
        |
        +-- each assembled catalogs, repositories, audit and agent differently
        |
        v
agent/deep_agent.py
        |
        +-- framework adapter
        +-- application construction
        +-- tool construction
        v
ToolRegistry -> AnalyticsAgent -> repository -> output
```

The main problems were:

- `mcp_server.py` mixed protocol definitions, DuckDB creation, mock seeding,
  catalogs, telemetry, request auditing and lifecycle management.
- Streamlit, CLI, evaluation and MCP duplicated dependency construction.
- Deterministic use-case orchestration lived behind framework-oriented agent code.
- `ToolRegistry` represented one fixed tool and added dispatch indirection without
  isolating a real extension point.
- `AnalyticsAgent`, `AgentResult` and `QueryData` made deterministic analytics
  objects sound probabilistic.
- `models.py` configured model providers while `domain/models.py` contained the
  actual business models.
- Streamlit read application results back out of audit events to build charts,
  making observability part of the functional data path.
- Several learning guides described the earlier class names and flow.

The parts that were already strong and remain unchanged are the repository port,
the DuckDB and in-memory adapters, immutable domain records, catalog resolution,
the explicit query specification, deterministic analysis, LMD selection, metric
semantics, warnings and comparison direction.

## 2. After the refactor

```text
┌──────────────────────────────────────────────────────────────┐
│ Interfaces                                                   │
│ Streamlit UI              MCP protocol                       │
│ ui/app.py                 mcp_server.py                       │
└───────────────┬──────────────────────┬───────────────────────┘
                │                      │
                v                      v
┌──────────────────────────────────────────────────────────────┐
│ Interface adapters                                           │
│ AnalysisSession + Deep Agent      CategoryHealthMcpRuntime    │
│ agent/session.py                  mcp_runtime.py               │
│ agent/deep_agent.py + agent/tools.py                          │
└───────────────────────────┬──────────────────────────────────┘
                            v
┌──────────────────────────────────────────────────────────────┐
│ Application                                                  │
│ CategoryHealthService -> CategoryHealthAnalyzer              │
│ request resolution -> one explicit intent branch -> response │
└───────────────────────────┬──────────────────────────────────┘
                            v
┌──────────────────────────────────────────────────────────────┐
│ Domain                                                       │
│ models, query contract, repository port                      │
└───────────────────────────┬──────────────────────────────────┘
                            v
┌──────────────────────────────────────────────────────────────┐
│ Infrastructure                                               │
│ DuckDB adapter, mock seed, model provider, JSONL, Langfuse    │
└──────────────────────────────────────────────────────────────┘
```

`bootstrap.py` is the composition root. It is the only place that assembles the
local demo choice of DuckDB, mock data, catalogs, audit sinks and model-backed
conversation. The deterministic application depends on `MetricsRepository`, not
on DuckDB or mock data.

There are two valid entry paths:

### Conversational path

```text
User -> Streamlit/CLI -> AnalysisSession -> Deep Agent -> domain tool
     -> CategoryHealthToolAdapter -> CategoryHealthService
     -> deterministic result -> Deep Agent presentation
     -> User
```

The LLM interprets language, selects a tool and extracts arguments. It does not
calculate metric deltas or query DuckDB directly.

### MCP path

```text
Host LLM -> MCP schema -> CategoryHealthMcpRuntime
         -> CategoryHealthService -> structured result -> host LLM
```

The MCP server does not start a second LLM. The host owns language interpretation;
this project owns validation, resolution, retrieval and calculation.

## 3. File responsibility map

| File | Responsibility | Why it belongs there |
|---|---|---|
| `ui/app.py` | Own Streamlit runtime state and the chat interaction | The entry point now reads as the UI flow |
| `ui/presentation.py` | Render answers, charts and trace details | Streamlit presentation is isolated from orchestration |
| `mcp_server.py` | Define MCP tools and protocol schemas | It is a thin protocol adapter |
| `mcp_runtime.py` | Add MCP audit context and submit one argument object | Isolates request lifecycle from protocol declarations |
| `bootstrap.py` | Construct concrete local/demo dependencies | Composition roots may know infrastructure choices |
| `agent/session.py` | Own conversation history and one trace per turn | Conversation state belongs at the LLM boundary |
| `agent/deep_agent.py` | Assemble Deep Agents with the approved tools and model | Framework construction stays in one small module |
| `agent/tools.py` | Define the two model-facing domain tool schemas | Tool contracts are separate from framework assembly |
| `agent/prompt.py` | Define the LLM interpretation and presentation policy | Prompt behavior can be read without infrastructure code |
| `application/service.py` | Provide the deterministic application entry point | One place answers “where does an analysis request enter?” |
| `application/requests.py` | Validate arguments and resolve catalog references | Converts untrusted model output to a canonical query |
| `application/analysis.py` | Execute the five explicit analysis branches | Keeps deterministic behavior visible in one place |
| `application/output.py` | Define response models and atomic delta calculation | Keeps output contracts separate from orchestration |
| `tool_adapter.py` | Convert tool dictionaries and wrap the typed flow with audit | Keeps serialization and telemetry outside business logic |
| `domain/models.py` | Define aggregate records and date ranges | These are business data structures |
| `domain/query.py` | Define intents and `AnalysisQuery` | Stable boundary after language interpretation |
| `domain/ports.py` | Define `MetricsRepository` | The application depends on a port, not a database |
| `repositories/duckdb.py` | Implement the repository port with DuckDB | Concrete persistence adapter |
| `repositories/in_memory.py` | Implement the repository port for tests | Fast deterministic adapter |
| `repositories/mock_data.py` | Seed reproducible aggregate observations | Local/demo infrastructure only |
| `catalogs/` | Load and resolve category, site and metric references | Canonical identity resolution is deterministic |
| `model_provider.py` | Configure hosted or local model clients | Model SDK configuration is infrastructure |
| `audit.py` | Define trace events and explicit step lifecycle | Business audit contract is framework-independent |
| `observability.py` | Persist JSONL and optionally export to Langfuse | Telemetry integration stays outside business logic |
| `charts.py` | Convert structured results to chart specs | Deterministic presentation transformation |
| `evaluation.py` | Score model behavior against expected results | Evaluation is a development boundary |

## 3.1 Complete flow inventory

The project has eight explicit flows. None uses audit as application state:

1. **Analysis:** `AnalysisRequest → AnalysisQuery → AnalysisResponse`.
2. **Conversation:** `AnalysisSession → Deep Agent → domain tool → final answer`.
3. **Metric discovery:** `list_available_metrics → MetricCatalogResponse`.
4. **Clarification:** invalid or ambiguous request → typed clarification; no query runs.
5. **MCP:** protocol schema → `CategoryHealthMcpRuntime` → shared tool adapter.
6. **Streamlit:** session runtime → answer → deterministic chart specs → trace display.
7. **Evaluation:** scenario turn → audited evidence → score → persisted report.
8. **Bootstrap/observability:** composition root creates replaceable infrastructure;
   JSONL remains authoritative and Langfuse remains optional and fail-open.

## 4. Major changes

### One application entry point

Before: tool construction, catalog resolution and deterministic execution were
spread across the Deep Agent adapter.

After: `CategoryHealthService.analyze()` owns the complete typed deterministic use
case; `CategoryHealthToolAdapter` owns untrusted dictionaries, serialization and
audit; `CategoryHealthService.list_metrics()` owns metric discovery.

Why better: Streamlit, CLI, MCP, evaluation and future interfaces reuse one API.

### One composition root

Before: each interface knew how to create DuckDB, seed data, load catalogs and
configure telemetry.

After: `create_demo_runtime()` and `create_demo_conversation_runtime()` assemble
those dependencies in `bootstrap.py`.

Why better: replacing DuckDB later changes composition, not analytics behavior.

### Thin MCP boundary

Before: `mcp_server.py` mixed protocol, application and infrastructure concerns.

After: `mcp_server.py` declares schemas and delegates. `mcp_runtime.py` translates
the request to application calls; `bootstrap.py` creates infrastructure.

Why better: each file stays at one conceptual level.

### Honest naming

Before: `AnalyticsAgent`, `AnalyticsEngine`, `ExecutionPlan` and `QueryData`
obscured a flow that only has five known operations.

After: `CategoryHealthAnalyzer.analyze()` visibly routes to `_snapshot()`,
`_trend()`, `_compare_periods()`, `_compare_sites()` or `_explain_change()`.

Why better: a reader can predict behavior from names.

### Removed fake registry abstraction

Before: a generic `ToolRegistry` dispatched exactly one analysis tool.

After: `AnalysisRequestResolver.resolve()` explicitly validates and canonicalizes
one analysis request.

Why better: less indirection and no imaginary extension point.

### Observability is no longer a data bus

Before: Streamlit searched audit events to recover the result needed for charts.

After: `AnalysisSession.last_analysis_output` receives the actual tool response,
and Streamlit builds charts from it directly. Audit remains for diagnostics and
telemetry only.

Why better: changing trace detail cannot break UI behavior.

## 5. One-question walkthrough

Question:

```text
What is the image coverage for Antiques in Germany?
```

| Stage | File | Class/function | Input | Output | Responsibility |
|---|---|---|---|---|---|
| 1 | `ui/app.py` | `main()` | User text | Call to session | Capture and render chat interaction |
| 2 | `agent/session.py` | `AnalysisSession.ask()` | Question, history and today's date | Final AI message | Own turn history, trace and model invocation |
| 3 | `agent/deep_agent.py` | Deep Agent | Natural language | Tool selection and arguments | Interpret language only |
| 4 | `agent/tools.py` | `analyze_category_health()` | `snapshot`, `Antiques`, `Germany`, `image coverage` | JSON-safe response | Delegate the selected tool |
| 5 | `tool_adapter.py` | `CategoryHealthToolAdapter.analyze()` | Untrusted arguments | Audited JSON-safe response | Validate and serialize at the external boundary |
| 6 | `application/service.py` | `CategoryHealthService.resolve_request()` | `AnalysisRequest` | `AnalysisQuery` | Start the clean typed business flow |
| 7 | `application/requests.py` | `AnalysisRequestResolver.resolve()` | `AnalysisRequest` | `AnalysisQuery` | Validate and canonicalize references |
| 8 | `catalogs/categories.py` | `CategoryCatalog.resolve()` | `Antiques` | Category ID `20081` | Resolve category identity |
| 9 | `catalogs/catalogs.py` | `SiteCatalog.resolve()` | `Germany` | Site ID `77` | Resolve site identity |
| 10 | `catalogs/catalogs.py` | `MetricCatalog.resolve()` | `image coverage` | `image_coverage_percentage` | Resolve metric identity |
| 11 | `application/analysis.py` | `CategoryHealthAnalyzer.analyze()` | `AnalysisQuery` | Selected branch | Route explicitly by intent |
| 12 | `application/analysis.py` | `_snapshot()` | Resolved IDs and range | `AnalysisResponse` | Retrieve and expose the latest requested values |
| 13 | `repositories/duckdb.py` | `latest_update()` | Category `20081`, site `77` | Latest aggregate row | Read through repository semantics |
| 14 | `application/output.py` | `compare_observations()` | Two complete observations | Typed delta | Apply one atomic comparison rule |
| 15 | `agent/deep_agent.py` | Deep Agent | Structured tool result | Natural-language answer | Present without recalculating |
| 16 | `agent/session.py` | `AnalysisSession.ask()` | Agent messages | History and structured output | Retain follow-up and chart data |
| 17 | `ui/app.py` | `render_charts()` | Chart specs | Streamlit chart | Present output visually |

For trend and comparison requests, the selected analysis branch also reads daily records, applies
latest-LMD semantics, pair comparable observations and calculate deltas. The LLM
receives those deltas; it never performs the subtraction.

## 6. Invariants preserved

- Multiple same-day updates are reduced by greatest `last_modified_at`.
- Missing dates are never filled with zero.
- Period comparison uses the latest snapshot per period, not an average.
- Site comparison uses matching dates only.
- Site delta remains second requested site minus first requested site.
- Boolean transitions are reported without numeric subtraction.
- Ambiguous or unknown catalog references require clarification.
- MCP tool names and schemas remain unchanged.
- Local JSONL audit remains authoritative; Langfuse remains optional and fail-open.

## 7. Behavior verification

Baseline before refactoring:

```text
116 passed
```

After refactoring and added boundary tests:

```text
117 passed
```

New tests cover the application service, composition root and explicit audit
context. Existing integration tests still verify resolution, LMD behavior,
comparison direction, warnings, tool propagation and MCP contracts.

## 8. Interview explanation

### 30 seconds

Category Health Analyst is a ports-and-adapters application with a probabilistic
language boundary and a deterministic analytics core. An LLM turns English into a
typed tool call. `CategoryHealthService` validates and resolves it, plans a closed
operation, reads aggregate observations through a repository port and calculates
comparisons in Python. Streamlit and MCP are adapters; DuckDB, MLX/OpenAI and
Langfuse are replaceable infrastructure assembled in one bootstrap.

### Two minutes

The system separates interpretation from truth. The LLM understands phrasing,
chooses between discovery and analysis, extracts scope and presents the response.
It cannot query arbitrary SQL or calculate deltas. Its arguments enter
`CategoryHealthToolAdapter`, where Pydantic validates the external dictionary. The
typed request then enters `CategoryHealthService`, where static catalogs convert
names into canonical IDs. `AnalysisQuery` is the stable intermediate form.
`CategoryHealthAnalyzer.analyze()` maps it directly to one of five explicit methods and executes
through `MetricsRepository`. The DuckDB adapter applies latest-LMD selection. The
output projector exposes only requested fields and computes comparisons, warnings
and no-data behavior deterministically.

The composition root assembles the local runtime using in-memory DuckDB and mock
data. A production repository can be injected without changing the service,
planner or calculations. Streamlit owns UI; MCP exposes the same service to an
external host without invoking a second model. Every stage emits an append-only
local audit event, optionally mirrored to Langfuse. Observability is fail-open and
is not used as application state.

### Main design decisions

1. A typed query spec separates language interpretation from execution.
2. Calculations and data semantics stay outside prompts.
3. A repository port makes storage replaceable.
4. One composition root assembles concrete dependencies.
5. One application service is shared by every interface.
6. JSONL audit is authoritative and Langfuse is optional.

### Why separate the LLM from analytics

LLM output is probabilistic and provider-dependent. Metric arithmetic, date
semantics, LMD selection and comparison direction must be repeatable and testable.
This lets us evaluate interpretation independently from data correctness and switch
models without rewriting business rules.

### Why Ports & Adapters helps

The application speaks to `MetricsRepository`; it does not know DuckDB. Tests use
an in-memory adapter, the demo uses DuckDB, and production can add another adapter.
The same principle keeps Streamlit, MCP, Deep Agents and Langfuse at the edges.

### Trade-offs

- A closed intent enum requires explicit support for new operations, but makes
  behavior safe, testable and auditable.
- Static catalogs require maintenance, but prevent invented identities and aliases.
- Complete rows use more internal data than narrow field queries, but support
  consistent calculations, follow-ups and audit.
- Detailed audit adds code and storage, but provides cross-layer traceability.
