# OpenRouter Chief Engineer Setup

LocalForge V2 uses a paid OpenRouter model as the default Chief Engineer lane
for architecture contracts, hard failures, contract changes, and final PR
review. OmniRoute remains the economy-first lane for ordinary agent work.

## Environment

Create a root `.env` with:

```env
OPENROUTER_PAID_MODEL=~deepseek/deepseek-v4-flash-latest
OPENROUTER_FREE_MODEL=nvidia/nemotron-3.5-lightning:free
OPENROUTER_API_KEY=sk-or-...
NVIDIA_LLM_MODEL=minimaxai/minimax-m3
NVIDIA_API_KEY=nvapi-...
```

The leading `~` is part of the current OpenRouter alias model ID. The legacy
`OPENROUTER_MODEL` name is still accepted as a paid-model alias.

The API key is loaded only when Chief Engineer execution is needed. It is not
returned by the API, written to artifacts, or copied into the model-call ledger.

## Economy-First Defaults

Every paid call must have a reason code, compact prompt bundle, structured JSON
schema, and ledger entry. Run budgets can cap:

- `max_paid_calls`
- `max_paid_input_tokens`
- `max_paid_output_tokens`
- `max_paid_usd`

When a cap is exceeded, LocalForge must fail safe with an actionable summary
instead of spending more credits.

## Chief Engineer Responsibilities

Use the paid OpenRouter lane for:

- architecture planning and contract freeze;
- high-risk task classification;
- contract change review;
- hard failure triage and semantic repair planning;
- final PR review after deterministic gates.

If the paid route has a transient availability failure, ForgeOS tries the
configured OpenRouter FREE route and then the direct NVIDIA FREE route. An
explicit `LOCALFORGE_CHIEF_PROVIDER` still overrides this default.

Do not use it for:

- bulk code generation;
- formatting;
- repeated full-log summarization;
- simple docs and mechanical edits.

## Troubleshooting

- Missing `OPENROUTER_API_KEY`: local-only workflows still run, but paid Chief
  Engineer calls fail with setup guidance.
- Insufficient credits: the run should stop at a safe terminal state and the
  ledger should show the failed paid call.
- Unexpected high spend: lower the run budgets before starting unattended mode.
