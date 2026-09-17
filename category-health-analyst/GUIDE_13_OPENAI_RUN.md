# Guide 13 — Running the Agent with OpenAI

## Goal

This guide connects the Deep Agents wrapper to an OpenAI chat model without storing credentials in code.

## Credential rule

The API key is read from:

```text
OPENAI_API_KEY
```

The key must remain in the shell environment or a local secrets manager. It must not be committed to Git, written into YAML, or printed in logs.

## Model configuration

The model is configured separately through:

```text
CATEGORY_HEALTH_MODEL
```

If it is not set, the demo uses `openai:gpt-5.4-mini`. The model name can be changed without changing the analytics code.

## Run the demo

From the project directory:

```bash
export OPENAI_API_KEY="your-key"
export CATEGORY_HEALTH_MODEL="openai:gpt-5.4-mini"
PYTHONPATH=src .venv/bin/python scripts/run_openai_agent.py
```

The demo uses an in-memory DuckDB database with two sample updates. It does not call eBay or modify production data.

## Request customization

The prompt can be changed without editing Python:

```bash
export CATEGORY_HEALTH_PROMPT="Compare image coverage for category 20081 in Germany between September 9 and September 10, 2026."
```

## What happens internally

```text
OpenAI model
    ↓
selects analyze_category_health
    ↓
catalog resolution + validation
    ↓
complete row retrieval
    ↓
metric projection
    ↓
natural-language response
```

The model can choose the tool, but it cannot bypass the repository or invent a database query.
