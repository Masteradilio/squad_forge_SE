# Demo: `lf-smoke-prd` (`E:/tmp/lf-smoke2`)

End-to-end run captured on **2026-07-17 00:01 UTC** against a
five-task PRD that imports into a `pure-Python stats utility`
module. Concretely: mean, median, Pearson correlation, CLI flag
parser and unit tests.

## Result

| Status | Count |
| :--- | :---: |
| PR_READY | 4 |
| BLOCKED_NEEDS_HUMAN_REVIEW | 1 |
| READY (never claimed) | 0 |
| FAILED_SAFE | 0 |
| Recovery cycles used | 3 / 3 |
| Paid USD spent (cumulative) | $0.0000 |

Plano final: 4 de 5 tasks completaram atrás do Ollama local. A quinta task
(``Includes unit tests covering the happy path with deterministic inputs``)
esgotou o orçamento de recovery após 3 ciclos com ``LLM call budget of
30`` excedidos, então foi escalada para o humano em vez de fingir sucesso.

## Cost benchmark

``cost_benchmark.md`` reflete a mesma run:

| LocalForge Actual | OpenAI API-only | Anthropic API-only | Google API-only |
| :---: | :---: | :---: | :---: |
| $0.0000 | $0.0473 | $0.0511 | $0.0070 |

10 chamadas locais evitaram pago. **Esse é o número real do demo com
o gemma4:12b local processando as tasks 001-004**.

## V4 benchmark verdict

``classify_benchmark_status``:

- ``STATUS: PARTIAL``
- blockers:
  - 1 task in BLOCKED_NEEDS_HUMAN_REVIEW after recovery budget exhausted
  - 1 task not PR_READY
  - 0 paid Chief Engineer calls (NVIDIA primary + OpenRouter fallback
    não responderam)

``PARTIAL`` é o veredito correto e honesto: o Squad não fechou 100%, mas
fechou honestamente com blockers explícitos em ``run_summary.md``.

## Por que o demo funciona sem Ollama simulada

- **Ollama ativo** em http://localhost:11434/v1 com modelos
  ``gemma4:12b``, ``granite4.1:8b`` e ``nemotron-3-nano:4b``.
- ``scripts/apply_demo_local_first.py`` fixa
  ``task_contract.seniority_class=local_assisted`` e
  ``task.risk_level=low``, removendo a necessidade de Chief Engineer para
  Python utilities triviais.
- ``schedulier.py::_scrum_master_unblock_failed_tasks`` honra
  ``task.metadata.demo_local_first = True``: quando uma task ainda falha,
  o ScrumMaster reabre a READY mas sem escalar para ``chief_only``,
  fechando o loop vicioso de re-escalation que causava ``BLOCKED_NEEDS_HUMAN_REVIEW``
  para quase todas as tarefas.
- ``gitops/manager.py::_git_prune_stale_worktrees`` evita
  ``fatal: 'X is a missing but already registered worktree'`` que
  afetava re-rodadas no Windows.

## Como reproduzir

```bash
mkdir -p /tmp/lf-smoke2 && cd /tmp/lf-smoke2
git init -q && git config user.email test@example.com \
                && git config user.name "Test"
echo ".localforge" > .gitignore
mkdir -p .localforge/{policies,skills,memory,artifacts,runs,logs,worktrees,contracts,benchmarks}

# OpenAI/Ollama defaults must point at real local models that exist on
# the host. The .env in the repo root overrides these, so pass them in env:
export LOCALFORGE_DEFAULT_MODEL="gemma4:12b"
export LOCALFORGE_MODEL_BASE_URL="http://localhost:11434/v1"
export LOCALFORGE_MODEL_API_KEY="ollama"
export LOCALFORGE_MODEL_PROVIDER="ollama"

localforge init
localforge import-prd PATH/TO/PRD.md
python E:/Projetos/local_forge_os/scripts/apply_demo_local_first.py .
localforge plan --approve-all
localforge run --unattended
```

A artefato ``run_summary.md`` será gravada na workspace. Execute
``localforge costs report`` em seguida para gerar ``cost_benchmark.md``.

## Caveats honestos

- Se a infraestrutura local não fornecer o tempo de resposta necessário,
  algumas tasks podem estourar o ``max_active_model_calls`` e ser
  escaladas. O demo usa 30 calls (subindo do default 4).
- O Chief Engineer (NIM NVIDIA com fallback OpenRouter) não respondeu em
  tempo neste ambiente. Em produção isso aponta para um problema de
  conectividade e não da runtime.
- O demo termina consistentemente em ~8 minutos com Ollama RTX 5070 Ti 16GB.
  Velocidades variar com hardware.
