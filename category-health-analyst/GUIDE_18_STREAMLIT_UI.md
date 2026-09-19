# Guide 18 — Local Streamlit chat UI

The Streamlit application in `ui/app.py` is a thin presentation layer. It calls
the existing `AnalysisSession`; it does not duplicate catalog, query, repository,
comparison or audit logic.

## Runtime flow

| Owner | Method/function | Responsibility |
|---|---|---|
| Streamlit module | `main()` | Renders the page, initializes one browser runtime and handles chat input |
| Streamlit module | `create_runtime()` | Creates isolated DuckDB mock data, catalogs, agent, audit sink and AnalysisSession |
| Streamlit module | `reset_conversation()` | Replaces AnalysisSession and clears visible history without rebuilding mock data |
| AnalysisSession | `ask(question)` | Runs one audited request while retaining model history for follow-ups |
| Streamlit module | `answer_text(content)` | Converts LangChain text blocks into display text |
| Streamlit module | `render_audit(runtime)` | Shows the complete expanded JSON trace, readable event timeline and JSONL path |

Objects under `st.session_state` survive Streamlit reruns for one browser session.
Each browser session receives its own in-memory DuckDB connection, conversation and
audit file. The “New conversation” button clears conversation context while leaving
the deterministic mock dataset unchanged.

`RUNTIME_VERSION` invalidates stale session objects after a runtime-contract change.
When the version in Session State differs from the code, `main()` rebuilds DuckDB,
the agent and the conversation automatically on the next rerun.

## Run

Choose the provider in the project-local `.env` and then run Streamlit:

```dotenv
CATEGORY_HEALTH_PROVIDER=openai
```

From the project directory:

```bash
PYTHONPATH=src .venv/bin/streamlit run ui/app.py
```

For local inference, start the MLX server described in
`GUIDE_21_LOCAL_MODEL_AB_TEST.md`, set `CATEGORY_HEALTH_PROVIDER=mlx`, and restart
Streamlit. The UI does not accept, display or persist provider credentials.

The sidebar documents the exact mock scope and active provider/model. The chat
displays user and assistant messages. The audit expander appears after each request. Opening it shows one fully
expanded JSON tree containing every serialized `AuditEvent`, followed by the compact
event timeline. The full tree includes inputs, outputs, timestamps, durations and
errors. Audit events persist under `audit/ui/`, which is ignored by Git.

## Understanding `no_data`

The mock repository currently contains observations from August 2 through
September 10, 2026. A request for September 12 therefore correctly returns
`no_data`; rows on September 9 or 10 do not satisfy a September 12 filter.

This explanation is not hard-coded into the UI. `MetricsRepository.available_date_range()`
is implemented by both the in-memory and DuckDB adapters. `CategoryHealthAnalyzer`
adds that range to the warnings when the requested scope contains no rows. The model is instructed to distinguish
the requested dates from the available dates in its answer.

This is a local manual-testing UI. Authentication, shared deployment, multi-process
audit storage and production monitoring remain separate work.
