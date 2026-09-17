# Guide 16 — Comparisons, questions, and durable local audit

The project continues with mock data. The data source is independent of the
analytics rules: both the in-memory and DuckDB adapters implement
`MetricsRepository`. Production preparation does not require real source data.
This iteration is a local application milestone, not a production-readiness claim.

## Comparison policy

| Intent | Python calculation | Direction and limitations |
|---|---|---|
| snapshot | Latest observed day inside the supplied range; latest LMD without a range | Returns facts, no change calculation |
| trend | One comparison for each pair of consecutive available observations | Current minus previous; gaps are disclosed |
| compare_periods | Last observed snapshot in each period | Current period minus comparison period; **not a sum or average of days** |
| compare_sites | Snapshots on common observed dates | Second site minus first; unmatched dates are omitted and disclosed |
| explain_change | First versus last available observation | Describes changes; does not infer business causes |

The latest-snapshot policy for periods is our explicit v1 implementation choice.
It answers “how did the end state differ?” It does not answer “what was the average
across the month?” Those are different analyses. Summing daily populations or image
counts can count the same products repeatedly. Averaging percentages without a
defined weighting policy can misrepresent the result.

Percentages use **percentage points**. Counts use a signed count difference.
Booleans preserve true/false, return `changed`, and have a null arithmetic delta.
Every comparison includes both site IDs, observed dates, LMDs, values and its method.
Zero is a real value; missing data never becomes zero. When a requested scope has
no rows, the response also reports the repository's actual available date range
for that category/site when one exists.

`ok` means usable complete output for the selected method. `partial` includes
warnings (including limited evidence for change analysis); `no_data` has no
observations. A missing period produces no fabricated comparison. A one-day trend
returns its observation and explains why no delta can be calculated.

## Class and method flow — actual execution order

| Owner / class | Method or function | What it receives | What it does / returns |
|---|---|---|---|
| CLI module (no class) | `main()` | Environment and optional `--chat` | Creates repository, catalogs, persistent sink, agent and session |
| Mock module (no class) | `seed_mock_data(repository)` | Empty MetricsRepository | Inserts reproducible aggregate observations |
| Adapter module (no class) | `create_category_health_deep_agent(...)` | Model and dependencies | Constructs the graph and two closed domain tools |
| Adapter module (no class) | `build_analysis_tool(...)` | Repository, catalogs, audit sink | Creates ToolRegistry and AnalyticsAgent and returns a nested function |
| Adapter module (no class) | `build_metric_catalog_tool(...)` | MetricCatalog and audit sink | Returns the nested `list_available_metrics()` discovery function |
| AnalysisSession | `ask(question)` | User text and existing session history | Starts a fresh request trace, supplies today's date and invokes the graph |
| Framework graph | `invoke(...)` | Message history and tool schema | Runs model/tool iterations, returning messages |
| Nested adapter function (no class) | `list_available_metrics()` | No arguments | Returns every catalog metric, unit and accepted name; audits the complete object |
| Nested adapter function (no class) | `analyze_category_health(...)` | Model-selected scope and intent | Reuses the request audit, calls registry, agent and output projection |
| ToolRegistry | `resolve(call, audit)` | ToolCall and shared AuditTrail | Audits tool selection and dispatches its registered handler |
| ToolRegistry | `_analyze_category_health(...)` | Tool arguments | Validates, resolves catalogs and constructs AnalyticsQuerySpec |
| AnalyzeCategoryHealthInput | `model_validate(...)`, inherited from Pydantic | Raw arguments | Parses the schema and calls `validate_scope()` |
| AnalyzeCategoryHealthInput | `validate_scope()` | Parsed fields | Rejects partial/reversed dates, excessive ranges and invalid combinations |
| CategoryCatalog | `resolve()` / `candidates_by_name()` | Category reference | Returns a unique category or supplies ambiguity candidates |
| SiteCatalog / MetricCatalog | `resolve()` | Human reference | Resolves static aliases to stable IDs |
| AnalyzeCategoryHealthInput | `date_range()` / `comparison_range()` | Validated dates | Constructs DateRange objects |
| AnalyticsQuerySpec | Pydantic constructor | Resolved IDs and intent | Validates query requirements, including two distinct comparison sites |
| AnalyticsAgent | `run(query, audit)` | QuerySpec and same audit | Validates, builds plan, retrieves data and returns AgentResult |
| Planner module (no class) | `build_plan(query)` | QuerySpec | Returns a deterministic ExecutionPlan |
| AnalyticsAgent | `_execute(plan)` | ExecutionPlan | Calls repository for selected sites and ranges |
| DuckDbMetricsRepository | `latest_per_day()` | Category, site and dates | Returns all columns using highest LMD per day |
| DuckDbMetricsRepository | `available_date_range()` | Category and site | Returns actual minimum and maximum observed dates, independent of the requested range |
| DuckDbMetricsRepository | `_to_model()` | DB tuple | Returns CategorySiteMetrics with UTC LMD |
| Output module (no class) | `expose_requested_metrics(result)` | Complete AgentResult | Selects requested values, detects missing data and chooses comparison pairs |
| Output module (no class) | `compare_observations(...)` | Two source rows, metric and method | Returns one typed deterministic comparison |
| Nested adapter function | `analyze_category_health(...)` resumes | AnalysisResponse | Audits complete calculation output and returns JSON to the model |
| AnalysisSession | `ask(...)` resumes | Framework result messages | Audits returned messages and final answer; retains history for the next question |
| CLI module | `main()` resumes | Answer and trace | Prints readable text, trace ID, errors and audited objects |

Calculation currently lives in `agent/output.py`; there is no separate calculation
engine class. The old `compare_percentages()` utility remains, but the current
output path uses `compare_observations()`.

## Questions and clarification

Unknown or ambiguous references return `needs_clarification` with a message and
unresolved fields. Ambiguous categories include candidate IDs. The model is instructed
to ask the user rather than invent a resolution.

The CLI's `--chat` mode retains user, assistant and tool messages. This lets the model
interpret “and in the UK?” using prior scope. History is local to the running
`AnalysisSession`; cross-process conversation persistence is not implemented.
Language understanding remains model-dependent and needs live evaluation.

Invalid arguments rejected inside our tool appear as failed validation plus an audited
clarification response. Errors rejected by the framework before entering our function
are visible in returned model messages on successful completion. Unexpected runtime
errors propagate and the request is marked failed; they are not mislabeled as ambiguity.

## Audit objects and persistence

`AnalysisSession.ask()` installs a request-scoped AuditTrail using a ContextVar.
Tool retries within that invocation reuse it; each next user turn gets a new trace.
`AuditTrail.step()` records started/succeeded/failed events, input/output objects,
duration and errors. `calculate_and_project` captures both source records and the
computed response. `model_messages` and `final_answer` capture the returned conversation.

`JsonlAuditSink.record()` appends one JSON event per line to `audit/events.jsonl`.
The file survives process exit and is ignored by Git. It contains questions and
business data, so treat it as application data. It is a local append log, not yet a
multi-process production audit service with retention and rotation.

UTC conversion happens explicitly before DuckDB TIMESTAMP insertion.
Source LMD must have a timezone. This avoids shifting timestamps based on the
database session timezone.

## Run with mock data

From `/Users/ogoldberg/Programming/work_demo/category-health-analyst`, with the API key
already configured in your environment:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_openai_agent.py --chat
```

Mock scope: category 20081, sites Germany (77) and UK (3), August 2 through
September 10, 2026. Each day has two updates. These fixed dates make tests reproducible;
queries outside that interval should report missing data.

Try these in order:

1. Show image coverage for category 20081 in Germany from September 1 to September 3, 2026.
2. And in the UK?
3. Compare Germany to the UK for category 20081, image coverage, September 1–3, 2026.
4. Compare the latest image coverage snapshot in September 1–3 against August 29–31, 2026, for category 20081 in Germany.
5. Show has_title for category 20081 in Germany from September 1 to September 7, 2026.
6. Show image coverage for Armor in Germany from September 1 to September 3, 2026.

Run offline tests without credentials or model charges:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

The regression suite covers both repository implementations, exact comparison
counts, units, boolean transitions, period endpoints, site date matching, missing
data, 30-day requests, timezones, argument errors, conversation history, retries,
failure auditing and JSONL persistence. A real Deep Agents graph is also executed
with a scripted model to check tool dispatch and request-trace propagation.

## Remaining production work

Deployment, authentication/authorization, multi-user isolation, bounded conversation
history, durable conversation storage, audit retention, provider timeout policy and
live language evaluations still require work. Mock data remains the intended source
through that preparation. Replacing the data source later should only require a new
MetricsRepository adapter and the same adapter contract tests.
