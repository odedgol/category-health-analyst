# Guide 14 — Inspecting the Full Audit Trace

## Goal

The CLI now prints both the final answer and the trace behind it.

The final answer is useful to a user. The audit trace is useful to the developer, reviewer, and investigator who needs to understand how that answer was produced.

## Trace stages

For a successful request, the trace contains pairs of events for each stage:

```text
validate_request
resolve_request
execute_snapshot / execute_trend / execute_compare_periods /
execute_compare_sites / execute_explain_change
analysis_response
```

Each pair contains a `started` event and a `succeeded` event. If a step fails, the second event is marked `failed` and includes the error type and message.

## Why both input and output are recorded

The trace lets us answer:

- Which tool did the model select?
- Which category, site, and metric IDs were resolved?
- Which QuerySpec was created?
- Which explicit analysis branch ran?
- Which dates and LMD values were retrieved?
- Which values reached the output layer?

This is more useful than logging only the final natural-language answer.

## Run it

```bash
export OPENAI_API_KEY="your-key"
PYTHONPATH=src .venv/bin/python scripts/run_openai_agent.py
```

The API key is not part of the trace and is never printed.
