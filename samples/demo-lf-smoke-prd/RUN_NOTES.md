# Demo: `lf-smoke-prd` (`E:/tmp/lf-smoke2`)

End-to-end run captured on **2026-07-17 02:08 UTC** against a
five-task PRD that imports into a `pure-Python stats utility`
module. Concretely: mean, median, Pearson correlation, CLI flag
parser, and unit tests.

## Result

| Status | Count |
| :--- | :---: |
| PR_READY | 3 |
| BLOCKED_NEEDS_HUMAN_REVIEW | 2 |
| READY (never claimed) | 0 |
| FAILED_SAFE | 0 |
| Recovery cycles used | 3 / 3 |
| Paid USD spent (cumulative) | **$0.0029** |

The Squad delivered three of five tasks and exhausted the absolute
recovery budget on the remaining two after three cycles. The Chief
Engineer lane made two paid calls during the cycle — one through
NVIDIA NIM (which rejected `response_format=json_object` against
the free-tier model with HTTP 200 + `{"error": "Model unavailable"}`
embedded in the body) and one through the OpenRouter fallback that
succeeded.

## Why the recovery loop did not close at 5/5 on this run

Two of the tasks (`Provides a CLI flag parser to choose operation` and
`Includes unit tests covering the happy path with deterministic inputs`)
hit `runtime_actions = None` validation cycles repeatedly. Each cycle
issued local Ollama calls that ultimately produced file paths outside
the allowed contract (e.g.
`src/computes_the_arithmetic_mean_of_1_float.py`). The Scrum Master
recovery loop then re-raised the task and the next pipeline attempt
re-emitted the same misnamed files. After three recovery cycles the
absolute ceiling held: the run closed as
`BLOCKED_NEEDS_HUMAN_REVIEW` rather than as `FAILED` and the
budget was preserved at $0.0029 USD.

## Evidence the V5.2 Chief Engineer fix works

`localforge/model_call_ledger` records every call:

| Provider | Model | Calls | USD |
| :--- | :--- | :---: | :---: |
| ollama | gemma4:12b | 13 | $0.0000 |
| openrouter | minimaxai/minimax-m3 | 2 | $0.0029 |

Before V5.2 the NIM free tier rejected `response_format=json_object`
with a `{"error": "Model unavailable"}` payload that the runtime
treated as a successful schema reply. After V5.2:

* `OpenAICompatibleProvider._looks_like_upstream_error` detects the
  embedded error inside the first choice and re-raises a distinct
  `LLMError("Upstream model error ...")`.
* `FallbackLLMProvider` catches that specific
  `LLMError` pattern (`model unavailable`,
  `model cannot process this request`, `engine unavailable`,
  `service temporarily unavailable`) and routes the call to the
  configured fallback.
* `OpenAICompatibleProvider` reads `LOCALFORGE_LLM_MAX_OUTPUT_TOKENS`
  and forwards `LOCALFORGE_LLM_NUM_CTX` as Ollama `options.num_ctx`.

The two paid OpenRouter records above are the two Chief Engineer
repair plans that reached the working fallback after the NIM free
tier rejected them.

## Cost benchmark

`cost_benchmark.md` reflects the same run:

| LocalForge Actual | OpenAI API-only | Anthropic API-only | Google API-only |
| :---: | :---: | :---: | :---: |
| $0.0029 | $0.1555 | $0.1453 | $0.0398 |

## V4 benchmark verdict

`scripts/run_benchmark_v4_only.classify_benchmark_status` on the
captured ledger:

* STATUS: `PARTIAL` (3 PR_READY, 2 BLOCKED_NEEDS_HUMAN_REVIEW).
* Blockers: (a) 2 BLOCKED tasks, (b) 5 PR_READY required but only 3
  present, (c) `chief_only` 0 paid since we only had 2 successful
  Chief calls.

`PARTIAL` is the honest verdict.

## How to reproduce

```bash
mkdir -p /tmp/lf-smoke2 && cd /tmp/lf-smoke2
git init -q && git config user.email test@example.com \
                && git config user.name "Test"
echo ".localforge" > .gitignore
mkdir -p .localforge/{policies,skills,memory,artifacts,runs,logs,worktrees,contracts,benchmarks}

# OpenAI/Ollama defaults must point at real local models. The .env in
# the repo root overrides these via `LOCALFORGE_DEFAULT_MODEL`, so the
# demo sets them in the environment instead.
export LOCALFORGE_DEFAULT_MODEL="gemma4:12b"
export LOCALFORGE_MODEL_BASE_URL="http://localhost:11434/v1"
export LOCALFORGE_MODEL_API_KEY="ollama"
export LOCALFORGE_MODEL_PROVIDER="ollama"

# Bigger Ollama context window (default Ollama hands out 2 KiB; the
# local lanes benefit from the model's full context budget).
export LOCALFORGE_LLM_NUM_CTX=32768
export LOCALFORGE_LLM_MAX_OUTPUT_TOKENS=4096

localforge init
localforge import-prd PATH/TO/PRD.md
python E:/Projetos/local_forge_os/scripts/apply_demo_local_first.py .
localforge plan --approve-all
localforge run --unattended
localforge costs report
```

`run_summary.md` and `cost_benchmark.md` are produced automatically
during the run.

## Caveats

* Demo uses 30 max_active_model_calls and 900s max_task_duration;
  smaller tasks are easy but the CLI flag parser + unit tests pair
  remains the hardest work for the local lane.
* Chief Engineer lane is paid API. If neither NVIDIA NIM nor
  OpenRouter returns successful responses, the recovery loop still
  escalates honestly. Removing the Chief Engineer lane entirely is
  possible by setting `chief_engineer.enabled = False`.
* The V5.2 fix added a fallback path; the previous behaviour on a
  malformed upstream payload looped until the absolute budget was
  exhausted without distributing work to the fallback.
