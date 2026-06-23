# OpenRouter Chief Engineer Setup

LocalForge V2 can use a paid OpenRouter model as a scarce Chief Engineer for
architecture contracts, hard failures, contract changes, and final PR review.
Local models still handle bounded low/medium-risk work.

## Environment

Create a root `.env` with:

```env
OPENROUTER_MODEL=minimax/minimax-m3
OPENROUTER_API_KEY=sk-or-...
```

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

Use OpenRouter for:

- architecture planning and contract freeze;
- high-risk task classification;
- contract change review;
- hard failure triage and semantic repair planning;
- final PR review after deterministic gates.

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
