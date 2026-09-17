# Guide 15 — Consistent Runtime Flow

Historical guide: the comparison, conversation and audit flow has since changed.
Use GUIDE_16_COMPARISONS_CONVERSATION_AUDIT.md for the current class/method map.

This guide follows one request from the command line to the final answer.

For every step, we identify:

- owner: class or module;
- method/function;
- input;
- output;
- responsibility.

## The request

```text
Show image coverage and misaligned aspects for category 20081
in Germany for September 9 and September 10, 2026.
```

## Step 1 — Start the application

Owner: `scripts/run_openai_agent.py`

Method: `main()`

Input:

- environment variables;
- the default prompt or `CATEGORY_HEALTH_PROMPT`;
- local catalog files;
- demo data.

Output:

- a configured DuckDB repository;
- loaded catalogs;
- an audit sink;
- a Deep Agents graph.

Responsibility:

`main()` assembles the application. It does not interpret the user request and it does not calculate metrics.

## Step 2 — Create the Deep Agent

Owner: `category_health.agent.deep_agent`

Function: `create_category_health_deep_agent()`

Input:

- model name, such as `openai:gpt-5.4-mini`;
- repository;
- category catalog;
- site catalog;
- metric catalog;
- audit sink.

Output:

- a compiled Deep Agents graph.

Responsibility:

- configure OpenAI through LangChain/Deep Agents;
- expose the domain tool;
- exclude filesystem, shell, and subagent tools;
- tell the LLM how to behave.

Important: this function creates the graph. It does not execute the user request.

## Step 3 — Build the domain tool

Owner: `category_health.agent.deep_agent`

Function: `build_analysis_tool()`

Input:

- repository;
- catalogs;
- audit sink.

Output:

- the nested function `analyze_category_health()`.

Responsibility:

Create a function that connects Deep Agents to our deterministic application core.

The function is nested because it captures the repository and catalogs in its closure.

## Step 4 — OpenAI selects the tool

Owner: Deep Agents framework and OpenAI model

Method called by our code:

```python
agent.invoke({"messages": [...]})
```

The framework calls the LLM. The LLM sees the tool schema and decides to call:

```text
analyze_category_health
```

Input produced by the LLM:

```json
{
  "intent": "trend",
  "category": "20081",
  "sites": ["Germany"],
  "metrics": ["image coverage", "misaligned aspects"],
  "start_date": "2026-09-09",
  "end_date": "2026-09-10"
}
```

Output:

- a framework tool call containing the tool name and arguments.

Responsibility:

OpenAI understands the English request and chooses the registered tool. It does not access DuckDB directly.

## Step 5 — Enter the domain tool

Owner: nested function in `deep_agent.py`

Function: `analyze_category_health()`

Input:

- `intent`;
- `category`;
- `sites`;
- `metrics`;
- dates.

First action:

```python
resolved = registry.resolve(
    ToolCall(name="analyze_category_health", arguments={...})
)
```

Output from this function:

```python
result = analytics_agent.run(resolved.query, audit=resolved.audit)
```

followed by:

```python
expose_requested_metrics(result).model_dump(mode="json")
```

Responsibility:

This function is the adapter. It delegates validation to `ToolRegistry`, execution to `AnalyticsAgent`, and response shaping to the output layer.

## Step 6 — Resolve the tool call

Owner: class `ToolRegistry`

Method: `ToolRegistry.resolve()`

File:

`src/category_health/agent/tools.py`

Input:

```python
ToolCall(
    name="analyze_category_health",
    arguments={...},
)
```

Output:

```python
ResolvedToolCall(
    tool_name="analyze_category_health",
    query=AnalyticsQuerySpec(...),
    audit=AuditTrail(...),
)
```

Responsibility:

- verify the tool name is registered;
- create the audit trail;
- record `select_tool`;
- call the registered handler;
- return the validated query and audit object.

## Step 7 — Validate and translate tool arguments

Owner: class `ToolRegistry`

Method: `ToolRegistry._analyze_category_health()`

Input:

- raw tool arguments from the LLM;
- audit trail.

### 7.1 Validate the argument shape

Owner: class `AnalyzeCategoryHealthInput`

Method:

```python
AnalyzeCategoryHealthInput.model_validate(arguments)
```

This checks:

- valid `QueryIntent`;
- non-empty category;
- at least one site;
- at least one metric;
- valid dates.

Output:

```python
AnalyzeCategoryHealthInput(...)
```

### 7.2 Resolve the category

Owner: class `CategoryCatalog`

Method:

```python
CategoryCatalog.resolve("20081")
```

Output:

```python
CategoryDefinition(category_id=20081, name="Antiques")
```

If the name is duplicated or unknown, the method returns no unique category and the tool raises a clarification error.

### 7.3 Resolve the sites

Owner: class `SiteCatalog`

Method:

```python
SiteCatalog.resolve("Germany")
```

Output:

```python
SiteDefinition(site_id=77, name="Germany", ...)
```

### 7.4 Resolve the metrics

Owner: class `MetricCatalog`

Method:

```python
MetricCatalog.resolve("image coverage")
MetricCatalog.resolve("misaligned aspects")
```

Output:

```text
image_coverage_percentage
misaligned_aspects_count
```

### 7.5 Build the QuerySpec

Owner: class `ToolRegistry`

Method: the `build_query` section inside `_analyze_category_health()`

Output:

```python
AnalyticsQuerySpec(
    intent=QueryIntent.TREND,
    category_id=20081,
    site_ids=(77,),
    metric_ids=(
        "image_coverage_percentage",
        "misaligned_aspects_count",
    ),
    date_range=DateRange(...),
)
```

Responsibility:

Convert language-layer values into stable internal IDs and a validated request object.

## Step 8 — Run the deterministic agent

Owner: class `AnalyticsAgent`

Method: `AnalyticsAgent.run()`

Input:

- `AnalyticsQuerySpec`;
- the existing `AuditTrail`.

Output:

```python
AgentResult(
    trace_id=...,
    query=...,
    plan=...,
    data=...,
)
```

Responsibility:

Coordinate validation, planning, repository retrieval, and audit events.

## Step 9 — Validate the QuerySpec

Owner: `AnalyticsAgent.run()`

Method:

```python
query.is_executable
```

The query is executable when:

- the category ID exists;
- required sites exist;
- no unresolved fields remain.

Output:

```text
validate_query succeeded
```

## Step 10 — Build the execution plan

Owner: module `category_health.agent.planner`

Function: `build_plan(query)`

Input:

```python
AnalyticsQuerySpec(intent=QueryIntent.TREND, ...)
```

Output:

```python
ExecutionPlan(
    operation=PlanOperation.DAILY_TREND,
    category_id=20081,
    site_ids=(77,),
    metric_ids=(...),
    date_range=...,
)
```

Responsibility:

Translate a validated intent into a deterministic operation. It does not call the LLM.

## Step 11 — Execute the plan

Owner: class `AnalyticsAgent`

Method: `AnalyticsAgent._execute(plan)`

For `PlanOperation.DAILY_TREND`, it calls:

```python
repository.latest_per_day(
    plan.category_id,
    site_id,
    plan.date_range,
)
```

Output:

```python
QueryData(
    site_id=77,
    period="current",
    records=(...complete rows...),
)
```

## Step 12 — Retrieve complete rows

Owner: class `DuckDbMetricsRepository`

Method: `DuckDbMetricsRepository.latest_per_day()`

Input:

- category ID `20081`;
- site ID `77`;
- date range September 9–10.

Output:

- one row for September 9;
- one row for September 10;
- every metric column in each row.

Responsibility:

- filter the database;
- select the latest LMD for each observed date;
- convert database rows into `CategorySiteMetrics` objects.

## Step 13 — Project and calculate the response

Owner: module `category_health.agent.output`

Function: `expose_requested_metrics(result)`

Input:

```python
AgentResult(...complete rows...)
```

Output:

```python
AnalysisResponse(
    values=(...),
    comparisons=(...),
)
```

The function:

- exposes only requested metrics;
- preserves date, site, and LMD;
- calculates numeric trend deltas.

For percentage metrics it calls:

```python
compare_percentages(Decimal("72"), Decimal("64"))
```

Output:

```text
delta = -8 percentage points
```

## Step 14 — Return to Deep Agents

The domain tool returns JSON-safe data to the Deep Agents framework.

The LLM receives the structured result and formats it as a table or explanation.

The LLM is responsible for wording, not for:

- resolving IDs;
- querying DuckDB;
- choosing LMD records;
- calculating the delta.

## Step 15 — Print the answer and audit

Owner: `scripts/run_openai_agent.py`

Method: `main()`

The script prints:

1. the final answer from the LLM;
2. every audit event stored in `InMemoryAuditSink`.

## Short call stack

```text
main()
  → create_category_health_deep_agent()
  → agent.invoke()
  → analyze_category_health()
  → ToolRegistry.resolve()
  → ToolRegistry._analyze_category_health()
  → AnalyzeCategoryHealthInput.model_validate()
  → CategoryCatalog.resolve()
  → SiteCatalog.resolve()
  → MetricCatalog.resolve()
  → AnalyticsQuerySpec(...)
  → AnalyticsAgent.run()
  → build_plan()
  → AnalyticsAgent._execute()
  → DuckDbMetricsRepository.latest_per_day()
  → expose_requested_metrics()
  → compare_percentages()
  → LLM final response
```
