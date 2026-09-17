# Category Health Analyst

An educational, auditable category-health assistant built around one rule:

> The LLM interprets. The deterministic core calculates.

The default setup uses `mlx-community/Qwen3-8B-4bit` through `mlx_lm` on Apple
Silicon, reproducible aggregate mock data in DuckDB, Streamlit for chat, MCP for
external hosts, and optional Langfuse tracing.

## Start here

- [Architecture and interview walkthrough](ARCHITECTURE.md)
- [Domain decisions](DOMAIN_DECISIONS.md)
- [Compact runtime flow](GUIDE_15_RUNTIME_FLOW.md)
- [Local model setup and evaluation](GUIDE_21_LOCAL_MODEL_AB_TEST.md)
- [MCP setup](GUIDE_22_MCP_SERVER.md)

## Setup

```bash
uv sync
cp .env.example .env
```

Keep `CATEGORY_HEALTH_PROVIDER=mlx` for local inference. In one terminal, start the
model server:

```bash
HF_HUB_DISABLE_XET=1 mlx_lm.server \
  --model mlx-community/Qwen3-8B-4bit \
  --host 127.0.0.1 --port 8080 --temp 0
```

In another terminal, start the UI:

```bash
PYTHONPATH=src .venv/bin/streamlit run ui/app.py
```

## Other entry points

Interactive CLI:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_openai_agent.py --chat
```

Offline deterministic evaluation:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py
```

MCP server over stdio:

```bash
uv run category-health-mcp
```

## Tests

```bash
.venv/bin/python -m pytest
```

The current mock scope is category `20081` (Antiques), Germany (`77`) and UK
(`3`), from 2026-08-02 through 2026-09-10. Queries outside that interval should
return explicit no-data warnings rather than fabricated values.
