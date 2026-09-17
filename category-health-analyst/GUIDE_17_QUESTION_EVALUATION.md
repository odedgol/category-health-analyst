# Guide 17 — Evaluate questions against expected evidence

We now have ten scenarios (twelve turns) in `evals/questions.yaml`.
They cover metric discovery, trends, sites, period endpoints, booleans, no data,
site follow-ups, relative dates, category clarification and missing dates.
Questions are in English, consistent with the project's teaching language.

## What the checker establishes

A fluent answer is not evidence that the query or calculation was correct.
The checker reads structured audit events for each turn and checks:

- intent, category, sites (including subtraction order), metrics and both date ranges;
- result status, every exposed value, comparison count, numeric delta and unit;
- complete metric discovery through `list_available_metrics`, without analysis;
- whether the tool executed despite a requirement to ask for clarification.

All successfully built queries and projected outputs are checked. An incorrect
successful call followed by a corrected call still fails the turn.
Validation errors recovered before a successful call are counted in
`recovered_errors` so retries remain visible.

A `pass` validates structured tool evidence and a small closed set of known wording
regressions. The wording guard currently catches unsupported claims about averages,
statistical significance, value judgments and resolved aliases being unsupported.
The final answer still needs human review for claims outside that closed set,
omitted limitations and units.
A clarification turn passes structurally only when the audit contains a successful
`clarification` event and contains no built query or calculated output. This proves
that execution stopped safely; it does not grade how well the question was worded.

## Classes and functions in order

| Owner | Method/function | Input | Output / responsibility |
|---|---|---|---|
| Script module | `evaluate_questions.main()` | Flags and YAML cases | Loads mocks, catalogs, sink and optional live model; runs each case |
| AnalysisSession | `__init__(..., today=...)` | Graph, sink and reference date | Fresh history per case, fixed September 10, 2026 for reproducibility |
| AnalysisSession | `ask(question)` | One English turn | Actual model/tool execution, shared history within that case and trace |
| JsonlAuditSink | `record(event)` | Audit event | Durable per-run evidence in events.jsonl |
| Evaluation module | `score_turn(expectation, events)` | Golden expectations and current-turn events | pass/fail, mismatch details and retries |
| Evaluation module | `same_value(actual, expected)` | Two scalar values | Exact numeric comparison despite Decimal formatting; booleans stay distinct |
| Script module | local `save()` function | Accumulated turn results | Writes report.json after every completed turn |

The `today` override is supplied only by the evaluator. Normal CLI sessions still
use the actual date. Expected numbers are written explicitly in YAML rather than
derived by the same calculation function being evaluated.

## Offline verification versus live evaluation

Default execution supplies each golden structured query directly to the domain
tool. It verifies that expected results agree with the mock fixture and the checker.
It does **not** test language understanding, follow-up resolution, or date extraction.
Clarification turns are skipped in this mode.

```bash
cd /Users/ogoldberg/Programming/work_demo/category-health-analyst
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py
```

Live mode sends the actual English questions to the selected provider. OpenAI uses
`OPENAI_API_KEY` and incurs API usage; MLX uses the configured local endpoint.
Start with a single case:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --live --case coverage_trend
```

Run the same case against local MLX:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --provider mlx --case coverage_trend
```

Run a controlled OpenAI-versus-MLX comparison:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --compare
```

See `GUIDE_21_LOCAL_MODEL_AB_TEST.md` for setup and interpretation.

Then run the suite:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --live
```

List available cases:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --list
```

Each run prints the report location under `audit/evaluations/<unique-run-id>/`.
`report.json` records mode, model, fixed date, original questions, expectations,
answers, trace IDs, mismatch details and counts. `events.jsonl` contains detailed
query and calculation evidence. These local files are excluded from Git.

Each case starts a fresh session. Turns inside a case share history. If a runtime
error occurs, dependent follow-up turns are not run; other cases continue.
The process exits nonzero for failures or runtime errors. A zero exit code confirms
the structured checks only; final natural-language wording remains a separate
review concern.

## Regression: query qualifiers inside metric names

A live run showed that the model can send `daily image count` or
`daily image coverage` as the tool's metric argument. `daily` describes the query
operation, not the stored metric. `MetricCatalog.resolve()` now follows this exact
sequence:

1. Normalize punctuation and case and try an exact catalog alias.
2. If that fails, remove words from a small closed qualifier allow-list such as
   `daily`, `latest`, `trend`, and `comparison`.
3. Require another exact catalog alias match.

This is intentionally not fuzzy matching. For example, `daily quality score trend`
still fails because `quality score` is not a known metric.

To rerun only the affected live conversations:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --live --case follow_up_site
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --live --case ambiguous_category
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --live --case missing_dates
```

## Acceptance and limitations

First establish correct tool scope/results and review all clarification/final answers.
Repeat live evaluations to measure variability; one successful run is not a
reliability estimate. A failure should produce a targeted regression test before
changing prompts or business rules.

This initial suite is deliberately small. It does not yet cover all paraphrases,
Hebrew input, malicious prompts, concurrency, model-provider failures or long
conversations. Those remain later additions. Live execution must be performed
before claiming that question understanding passes.
