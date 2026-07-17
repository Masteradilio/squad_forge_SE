# LocalForge OS — Cost Benchmark Report (V5.2 demo)

| Provider | Calls | Tokens (in+out) | USD |
| :--- | :---: | :---: | :---: |
| ollama (gemma4:12b)            | 13 | 3186+1704 | $0.0000 |
| openrouter (minimaxai/minimax-m3) |  2 |   82+592  | $0.0029 |
| **Total LocalForge Actual**    | **15** | **5564** | **$0.0029** |

## Competitor API-only hypothetical baselines (same workload)

| Provider | Hypothetical USD | Savings vs LocalForge |
| :--- | :---: | :---: |
| OpenAI GPT-5.5 large       | $0.1555 | $0.1526 |
| Anthropic Claude Opus 4.8 | $0.1453 | $0.1424 |
| Google Gemini 2.5 Pro    | $0.0398 | $0.0368 |

*Source: `localforge costs report --run 1` snapshot on 2026-07-17.*

## Interpretation

Total actual spend: **$0.0029 USD** for 13 local Ollama calls plus 2 paid
Chief Engineer repairs (recorded in `model_call_ledger`). Three of the
five tasks reached PR_READY via the local Ollama lane (gemma4:12b with
the configured `LOCALFORGE_LLM_NUM_CTX=32768` context window). The
remaining two tasks exhausted the absolute recovery budget after three
cycles and were escalated to `BLOCKED_NEEDS_HUMAN_REVIEW`.

The OpenAI / Anthropic / Google baselines are token-cost simulations
against public pricing snapshots, **not** actual invoices. The
LocalForge cost ledger records the real spend `ModelCallLedgerService`
persisted during the run.
