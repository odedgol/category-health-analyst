# Guide 20 — OpenTelemetry-native Langfuse implementation

## What was implemented

Every `AuditTrail.step()` is now instrumented as one nested OpenTelemetry span through
the Langfuse Python SDK. The SDK is OpenTelemetry-native and exports asynchronously to
Langfuse over OTLP/HTTP.

The official Langfuse `CallbackHandler` is also passed to the Deep Agents/LangChain
graph invocation. It adds the graph, tool and model observations—including model
latency and token usage when returned by the provider—inside the same root trace.

The local JSONL audit remains the authoritative business record. Langfuse is an
optional operational view: missing credentials, initialization errors and exporter
failures do not stop an analysis.

## Runtime flow

```text
AnalysisSession.ask()
  -> AuditTrail.step("user_request")
       -> LangfuseStepObserver.observe_step() opens the root OTel span
       -> JsonlAuditSink records STARTED
       -> Langfuse CallbackHandler records LangChain, tool and LLM observations
       -> nested application steps open child OTel spans
       -> JsonlAuditSink records SUCCEEDED or FAILED
       -> the Langfuse span receives output/status and closes
```

The business audit UUID is also the OpenTelemetry trace ID. JSONL displays the UUID
with hyphens; OpenTelemetry and Langfuse display the same 128 bits as 32 lowercase
hexadecimal characters.

When an integration such as the MCP SDK already has an active OpenTelemetry trace,
the business audit adopts that trace ID and creates child observations without
overriding its context. This keeps the protocol request and deterministic analytics
in one tree. A standalone Streamlit request has no upstream trace, so the business
audit creates the root trace itself.

Observation types are semantic: `user_request` is an `agent`, `mcp_tool_call` is a
`tool`, model calls created by the LangChain callback are `generation` observations,
and deterministic implementation steps remain `span` observations.

## Configuration

Copy `.env.example` to `.env` inside the `category-health-analyst` directory and set
the real values there. The application deliberately does not search parent folders.

Alternatively, export the values in the shell that starts the app:

```bash
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
export LANGFUSE_TRACING_ENVIRONMENT="local"
export CATEGORY_HEALTH_APP_VERSION="0.1.0"
export OTEL_SERVICE_NAME="category-health-analyst"
```

The UI and command-line scripts load only `category-health-analyst/.env`. Existing
shell environment variables take precedence and are never overwritten by the file.

Then start the UI normally:

```bash
PYTHONPATH=src .venv/bin/streamlit run ui/app.py
```

When credentials are present, the execution panel provides a link to the full
Langfuse trace. Without credentials, it shows a compact local step table and retains
the complete JSON business audit in a collapsed fallback section.

## Trace identity and conversation sessions

Every trace receives a stable low-cardinality name, environment, application version,
service name and source tags. The Streamlit runtime also passes one `session_id` to
every turn in the same conversation. Selecting **New conversation** creates a new
session ID while keeping the browser runtime and mock database alive.

## Data safety

Root observations always export a focused request object and compact result object so
the tracing table is useful without opening child spans. Child spans export summaries
by default. Their full `input_object` and `output_object` values stay only in JSONL
unless this explicit option is enabled:

```bash
export CATEGORY_HEALTH_TELEMETRY_CAPTURE_OBJECTS=true
```

Keep it disabled until production redaction and data-retention policy are approved.
For example, `execute_plan` exports `record_count` rather than every database row, and
`calculate_and_project` exports status/value/comparison/warning counts. The complete
objects remain available in the append-only local audit.
This switch controls our custom business-audit objects. The official LangChain
callback separately captures model/tool prompts and responses so Langfuse can provide
LLM debugging. Therefore, configuring Langfuse credentials must itself be treated as
approval to send model traffic to that Langfuse project. Add collector/SDK masking
before using the integration with sensitive production prompts.

## Why the collector is not in this step

The Python SDK exports OTLP/HTTP directly to Langfuse, which is the shortest useful
local setup. A production deployment can place an OpenTelemetry Collector between the
app and Langfuse for central redaction, retries, sampling and multi-backend routing
without changing the `AuditTrail` instrumentation model.
