# Guide 21 — Local MLX model and controlled A/B evaluation

We are not replacing the production model by intuition. We run the same questions,
mock database, tools, calculations and evidence checks against two model providers.
Only the language model changes.

## The experiment

```text
same question suite
        |
        +--> OpenAI baseline --> deterministic tools --> audit scorer
        |
        +--> local MLX model --> deterministic tools --> audit scorer
                                                     |
                                                     +--> comparison.json
```

This is an offline A/B evaluation, not live user traffic. It measures:

- structured pass rate: did the model select the right tool and arguments?
- per-question and complete-suite latency;
- status agreement between providers;
- failures, errors and clarification behavior.

It does not automatically judge final-answer style or factual claims written after
the tool result. Those answers still require human review.

## Candidate strategy

The active model is the local `mlx-community/Qwen3-8B-4bit`. Hosted OpenAI models
are retained only as optional evaluation baselines. Our Python tool performs the database work and
calculations, so the model's main job is narrow: understand the question and
construct a valid tool call. Even for that narrow job, promotion requires repeated
clean evaluation runs because one reversed comparison operand changes the business
answer.

## Configuration

The project loads only `/Users/ogoldberg/Programming/work_demo/category-health-analyst/.env`.
It never searches a parent folder. Add these values to that file:

```dotenv
CATEGORY_HEALTH_PROVIDER=mlx
CATEGORY_HEALTH_MODEL=openai:gpt-5.4-mini
CATEGORY_HEALTH_MLX_MODEL=mlx-community/Qwen3-8B-4bit
CATEGORY_HEALTH_MLX_BASE_URL=http://127.0.0.1:8080/v1
CATEGORY_HEALTH_MLX_API_KEY=not-needed
```

`CATEGORY_HEALTH_PROVIDER` controls the UI and normal CLI. The A/B command ignores
that selector and intentionally runs both configured providers.

## Terminal 1: start MLX

```bash
cd /Users/ogoldberg/Programming/work_demo/category-health-analyst
mlx_lm.server \
  --model mlx-community/Qwen3-8B-4bit \
  --host 127.0.0.1 \
  --port 8080 \
  --temp 0
```

Keep this terminal open. The first load can take longer than later requests.
The server is bound to localhost because `mlx_lm.server` is a development server,
not an internet-facing production service.

## Terminal 2: test one case first

```bash
cd /Users/ogoldberg/Programming/work_demo/category-health-analyst
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py \
  --provider mlx \
  --case coverage_trend
```

Then compare both providers on that case:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py \
  --compare \
  --case coverage_trend
```

Finally run the complete experiment:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py --compare
```

The output folder contains `openai/report.json`, `mlx/report.json`, both JSONL audit
files, and `comparison.json`. No API keys are written to these reports.

Any two existing reports can be compared without paying for another model run. The
first report is the baseline and the second is the candidate; they may use different
providers or two different models from the same provider:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py \
  --compare-reports path/to/baseline/report.json path/to/candidate/report.json
```

## Run the app with MLX

After the local candidate passes the agreed threshold, change only:

```dotenv
CATEGORY_HEALTH_PROVIDER=mlx
```

Then restart Streamlit. The sidebar shows the active provider, model and local
endpoint. To switch back, set the provider to `openai` and restart.

The next production step is a local-first router with an OpenAI fallback when MLX
returns an invalid tool call or fails validation. That fallback is intentionally not
enabled yet: first we need real comparison evidence and a policy for when paid usage
is allowed.

## Experiment results

The production selection experiment produced this evidence:

| Candidate | Structured result | Suite time | Decision |
|---|---:|---:|---|
| `openai:gpt-5.5` | 12/12 | 58.27 s | Accurate baseline |
| `mlx-community/Qwen3-8B-4bit` | 10/12 | 86.53 s | Active local model; two gaps remain |
| `openai:gpt-5.4-nano` | 10/12 | 39.86 s | Rejected: comparison failures |
| `openai:gpt-5-mini` | Failed the period gate | 46.70 s for one case | Rejected |
| `openai:gpt-5.4-mini`, run 1 | 12/12 | 33.01 s | Passed |
| `openai:gpt-5.4-mini`, run 2 | 12/12 | 37.58 s | Hosted reference only |

The two complete `gpt-5.4-mini` runs passed 24/24 turns. Using the conservative
second run, it was about 35.5% faster than the `gpt-5.5` baseline. At the published
standard token prices at evaluation time, the measured suite cost was approximately
$0.028 versus $0.204 for `gpt-5.5`, an estimated 86.3% reduction. This estimate
charges all reported input tokens at the uncached rate and excludes unrelated tool
fees.

The active project setting is:

```dotenv
CATEGORY_HEALTH_PROVIDER=mlx
CATEGORY_HEALTH_MODEL=openai:gpt-5.4-mini
CATEGORY_HEALTH_MLX_MODEL=mlx-community/Qwen3-8B-4bit
```

Switching to a hosted model is an explicit operator decision: change
`CATEGORY_HEALTH_PROVIDER` to `openai` and restart the CLI or Streamlit process.

### Local-model findings

The 4B candidate demonstrated that the architecture works locally. One complete run
passed all 12 structured turns, but a later run produced 9 passes, 2 structured
failures and 1 wording review. The unstable cases involved operand order, audited
clarification and unsupported final-answer phrasing. Therefore 4B is a useful fast
development model, but it is not approved as the production replacement.

The 8B candidate was then evaluated on this Mac. Its latest complete run passed
10/12 turns in 86.53 seconds. Failures involved site-comparison operand order and
missing-date clarification. It was both less accurate and slower than the hosted
baseline. It nevertheless remains the active model because this project's
requirement is local inference. The next engineering task is to eliminate those two
routing gaps without silently switching providers.

Start that candidate with:

```bash
HF_HUB_DISABLE_XET=1 mlx_lm.server \
  --model mlx-community/Qwen3-8B-4bit \
  --host 127.0.0.1 \
  --port 8080 \
  --temp 0
```

`HF_HUB_DISABLE_XET=1` uses the standard resumable download path, which was much
faster on this Mac's current network. The application also sends
`enable_thinking=false` for MLX requests. Tool routing is a short structured task;
without this flag Qwen3-8B consumed the entire 512-token server budget on reasoning
and returned no tool call.

Then evaluate the exact loaded model explicitly:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_questions.py \
  --provider mlx \
  --model mlx-community/Qwen3-8B-4bit
```
