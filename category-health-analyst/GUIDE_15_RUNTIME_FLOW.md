# Guide 15 — Runtime Flow

The complete current architecture and interview walkthrough are documented in
[`ARCHITECTURE.md`](ARCHITECTURE.md). This guide is the compact navigation map.

## Conversational request

```text
ui/app.py: main
  -> bootstrap.py: ConversationRuntime
  -> agent/session.py: AnalysisSession.ask
  -> agent/deep_agent.py: analyze_category_health tool
  -> application/service.py: CategoryHealthService.analyze
  -> application/requests.py: AnalysisRequestResolver.resolve
  -> application/analysis.py: CategoryHealthAnalyzer.analyze
  -> one explicit method: _snapshot / _trend / _compare_periods /
                          _compare_sites / _explain_change
  -> domain/ports.py: MetricsRepository
  -> repositories/duckdb.py: DuckDbMetricsRepository
  -> application/output.py: AnalysisResponse + compare_observations
  -> Deep Agent presentation
  -> AnalysisSession history and structured result
  -> Streamlit answer and chart
```

## MCP request

```text
mcp_server.py: analyze_category_health
  -> mcp_runtime.py: CategoryHealthMcpRuntime.analyze
  -> application/service.py: CategoryHealthService.analyze
  -> the same deterministic pipeline
  -> structured MCP response
```

MCP does not invoke the project's local LLM. The MCP host performs language
interpretation and this server performs deterministic analytics.

## Responsibility boundary

The model may choose a tool, intent and structured arguments. The application owns
validation, catalog resolution, intent routing, repository selection, latest-LMD rules,
calculations, warnings and no-data behavior.

For a stage-by-stage example with each class, method, input and output, read
section 5 of `ARCHITECTURE.md`.
