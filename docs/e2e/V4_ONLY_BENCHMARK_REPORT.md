# LocalForge OS - V4-Only Empirical Benchmark Report

> Historical evidence notice (2026-07-12): this report records a prior V4 run. It is not
> reproducible from the current checkout because the disposable `sprintboard-v4` workspace
> is absent. The legacy script also used simulated Docker/Ollama preflight responses and
> persisted no routing-contract summary. The original V4 result below is retained for audit
> history, but a fresh run must satisfy `MASTER_BACKLOG_V5.md` before it can support current
> quality or savings claims.

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V4 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v4`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///E:\Projetos\local_forge_os/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: ACCEPTED**
>
> A execução empírica real do LocalForge V4 foi finalizada com classificação **ACCEPTED** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

Nenhum blocker detectado no pré-flight.

---

## 3. Métricas Reais do Workspace V4 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V4 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V4-Run-1" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v4/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | 5 | Escopo completo do PRD |
| **Tasks Imported** | 5 | Sucesso na importação real |
| **Task Runs Executed** | 6 | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | 5 | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | 0 | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | $0.0214 | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | 6 | Quantidade de chamadas aos modelos registradas |
| **NVIDIA Chief Calls Logged** | 0 | Provider primário para validar a V4 API-led |
| **OpenRouter Fallback Calls Logged** | 5 | Fallback pago quando NVIDIA não responde |
| **Paid Chief Calls Logged** | 5 | Deve ser maior que zero para validar a V4 API-led |
| **Local Calls Logged** | 1 | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | 97 | Artefatos gravados no disco pelo pipeline |

---

## 4. Distribuição de Estados das Tarefas

Abaixo consta a distribuição real de status das 5 tarefas após a rodada:
- **BACKLOG**: 0
- **READY**: 0
- **CLAIMED**: 0
- **PLANNING**: 0
- **IMPLEMENTING**: 0
- **TESTING**: 0
- **PR_READY**: 5
- **FAILED_SAFE**: 0

---

## 5. Evidência de Saída do Terminal e Logs da CLI

### Resultados do Pré-flight
- **docker_or_dev**: PASSED - Docker active: False, Dev mode (local sandbox) config: True
- **llm_installed**: PASSED - Chosen model for execution: 'gemma4:12b'. Ollama installed models: ['gemma4:12b', 'granite4.1:8b', 'nemotron-3-nano:4b']
- **task_count_match**: PASSED - Tasks imported: 5, Expected count: 5
- **chief_engineer_configured**: PASSED - provider=nvidia, model configured: True, api key configured: True, fallback=openrouter

### Logs de Execução / Erros da CLI
```text
Scrum Master Orchestrator Started parsing PRD:
E:\Projetos\local_forge_os\docs\PRD_SPRINTBOARD_LITE.md
PRD import complete
  Document hash:
b61b00d412c4ef04ac322356534b5eca5e3b41a1a3c989c02d7cc7792ab7504a
  Changed: True
  Epics: 2
  Tasks: 5
Tasks mapped to roles based on complexity.
Approved all planning/backlog tasks: 5 tasks marked as READY.
Handing over to Execution Pipeline...
Starting Run 1 in unattended mode...
Run 1 status changed: PENDING
[Economy Bundler] Previewing API call: reason=SEMANTIC_REPAIR_PLAN, estimated_input_tokens=212
[Economy Bundler] Previewing API call: reason=SEMANTIC_REPAIR_PLAN, estimated_input_tokens=228
Run 1 status changed: RUNNING
[Economy Bundler] Previewing API call: reason=SEMANTIC_REPAIR_PLAN, estimated_input_tokens=207
[Economy Bundler] Previewing API call: reason=SEMANTIC_REPAIR_PLAN, estimated_input_tokens=200
[Economy Bundler] Previewing API call: reason=SEMANTIC_REPAIR_PLAN, estimated_input_tokens=407
Run 1 status changed: COMPLETED

Run finished with status: COMPLETED
Summary: Execution Summary:
- PRs Ready/Done: 5
- Blocked Tasks: 0
- Failed-Safe Tasks: 0
- Safety Blocks: 0

Recommended Next Steps:
- Execution completed cleanly. Ready to merge PRs!
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: ACCEPTED**
> The V4-only run proves the API-led/economy-first architecture only when at least one paid Chief Engineer call (`nvidia` primary or `openrouter` fallback) is recorded in `model_call_ledger` and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
