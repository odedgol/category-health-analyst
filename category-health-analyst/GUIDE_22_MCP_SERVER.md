# Guide 22 — Exposing Category Health through MCP

## What we are building

The Streamlit application is a user interface. MCP does not wrap that screen. It
wraps the reusable application capability underneath it:

```text
MCP host and its LLM
        |
        | typed MCP tool call
        v
Category Health MCP server
        |
        v
catalogs -> validation -> query plan -> DuckDB -> calculations -> audit
```

This separation matters. An MCP host such as Claude, Codex, or the MCP Inspector
owns the conversation. Our server owns the facts and calculations. It does not
run Qwen or OpenAI, so one request does not accidentally invoke a second model.

## Exposed tools

### `list_available_metrics`

Takes no arguments and returns the complete static metric catalog. This solves
metric discovery without requiring a category, site, or date.

### `analyze_category_health`

Accepts a typed analytical request:

- `intent`
- `category`
- `sites`
- `metrics`
- primary date range
- optional comparison date range

It calls the same deterministic pipeline used by the existing application and
returns values, calculated comparisons, warnings, status, and `trace_id`.

## Why `stdio` first

For a local server, the MCP host launches our command as a child process. MCP
messages travel through standard input and output. There is no additional port,
authentication layer, or always-running web service.

Because stdout carries the protocol, application diagnostics must use logging
to stderr rather than `print()`.

## Run it

From the project directory:

```bash
uv sync
uv run category-health-mcp
```

The second command appears to wait silently. That is correct: the server is
waiting for an MCP client to send a protocol message.

For an interactive development UI, launch the official MCP Inspector:

```bash
uv run mcp dev src/category_health/mcp_server.py:mcp
```

## Host configuration

An MCP host needs a command plus this project directory. The portable launch
command is:

```text
uv --directory /Users/ogoldberg/Programming/work_demo/category-health-analyst run category-health-mcp
```

Use the absolute path to the `uv` executable if the host does not inherit your
shell `PATH`.

## Request flow

1. The host's LLM converts the user's language into typed tool arguments.
2. MCP validates the tool schema before entering our function.
3. `CategoryHealthMcpRuntime.analyze()` creates one audit trace.
4. Existing catalogs resolve category, site, and metric names.
5. Existing validation and planning select the deterministic repository query.
6. DuckDB returns the latest update for each requested day.
7. Existing projection code calculates comparisons and warnings.
8. MCP serializes the structured result back to the host.

The returned `trace_id` links the client-visible response to
`audit/mcp/events.jsonl` and, when configured, Langfuse.

## MCP and Langfuse trace context

The MCP Python SDK instruments the protocol request with OpenTelemetry. The business
runtime reads that active trace ID, uses it as its `AuditTrail` ID, and adds a typed
`mcp_tool_call` observation below the protocol span. It also enriches the upstream
span with focused request and result objects.

The resulting Langfuse tree is one trace:

```text
MCP tools/call
└── mcp_tool_call [tool]
    ├── resolve_request [span]
    ├── execute_<intent> [span]
    └── analysis_response [span]
```

It is tagged with `category-health`, `mcp`, and `mock-data`, and receives the trace
name `category-health-mcp-request`. Full database objects remain local by default;
Langfuse receives useful counts, status and warnings without duplicating the complete
result payload at every level.

## Later production step

The tools and their schemas do not need to change when the mock DuckDB repository
is replaced. We replace the repository adapter behind the MCP boundary. For a
deployed service, the same server can move from `stdio` to Streamable HTTP and
add authentication at that boundary.
