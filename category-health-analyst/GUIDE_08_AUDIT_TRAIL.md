# Guide 08 — Auditing and Flow Analysis

## Goal of this guide

When the system is complete, we should be able to answer:

- Which steps ran?
- In what order?
- How long did each step take?
- What did each step receive?
- What did each step produce?
- Where did a failure occur?
- Why did the system ask for clarification?
- Which model, repository, or resolver was used?

This requires a trace that follows one user request through the system.

## Trace versus log

A normal log is usually an isolated message:

```text
Resolved category 20081
```

An audit trail connects events belonging to one request:

```text
trace_id = abc123

extract_query       succeeded   42 ms
resolve_category    succeeded   3 ms
resolve_site        succeeded   1 ms
validate_query      succeeded   2 ms
plan_query          succeeded   1 ms
execute_query       succeeded   8 ms
compose_answer      succeeded   4 ms
```

## Event structure

Each audit event contains:

```text
event_id
trace_id
sequence
step
status
started_at
completed_at
duration_ms
input_summary
output_summary
input_object
output_object
error
```

## Why summaries instead of raw payloads

The audit trail should help debug behavior without copying everything into logs.

We should avoid storing:

- API keys
- Full prompts by default
- Large database results
- Personal data
- Entire evidence documents

Instead, record summaries such as:

```json
{
  "category_mention": "Germany",
  "resolved_site_id": 77,
  "candidate_count": 1
}
```

For important domain objects, the audit trail can also store a JSON-safe snapshot:

```json
{
  "intent": "trend",
  "category_id": 20081,
  "site_ids": [77]
}
```

Object snapshots make it possible to inspect not only which step ran, but exactly how an object changed between steps. They should still be subject to redaction and size limits before production use.

The policy can later be extended with configurable redaction.

## Lifecycle of one step

Each logical step produces two events:

```text
step_started
    ↓
step_succeeded
```

If an exception occurs:

```text
step_started
    ↓
step_failed
```

This makes incomplete traces visible.

## Trace-scoped audit trail

The orchestrator creates one `AuditTrail` per user request:

```python
audit = AuditTrail(sink=sink)

with audit.step("resolve_category", {"mention": "Antiques"}) as step:
    category = catalog.resolve("Antiques")
    step.set_output({"category_id": category.category_id})
```

Objects can be audited explicitly:

```python
with audit.step("validate_query", input_object=query_spec) as step:
    validated_query = validate(query_spec)
    step.set_output_object(validated_query)
```

Future pipeline nodes will receive the same trail object.

## Acceptance criteria

- Every event has a trace ID.
- Events have increasing sequence numbers.
- Successful steps record duration and output summaries.
- Failed steps record the exception type and message.
- A trace can be retrieved as an ordered list.
- One trace cannot leak events from another trace.
- The audit layer has no database, LLM, or UI dependency.

## What we will build next

We will wire the audit trail into deterministic resolution and query planning. Later, the same interface can write to a file, DuckDB table, OpenTelemetry, or another observability backend without changing business logic.
