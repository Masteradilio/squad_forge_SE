# LocalForge OS - V3-Only Empirical Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V3 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v3`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///E:\Projetos\local_forge_os/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: BLOCKED**
>
> A execução empírica real do LocalForge V3 foi finalizada com classificação **BLOCKED** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

1. **Pre-flight 'omniroute_gateway' failed: GET http://127.0.0.1:20128/v1/models returned HTTP 0: timed out**
2. **Pre-flight 'omniroute_completion' failed: No explicit free route was advertised.**


---

## 3. Métricas Reais do Workspace V3 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V3 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V3-Run-0" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v3/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | 6 | 5 requisitos do PRD + assembly determinístico |
| **Tasks Imported** | 6 | Sucesso na importação real |
| **Task Runs Executed** | 0 | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | 0 | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | 0 | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | $0.0000 | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | 0 | Quantidade de chamadas aos modelos registradas |
| **Chief Calls Logged** | 0 | Deve ser maior que zero para validar a V3 API-led |
| **Local Calls Logged** | 0 | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {"chief_only": 1, "chief_led": 4, "local_assisted": 1} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | 0 | Artefatos gravados no disco pelo pipeline |

---

## 4. Distribuição de Estados das Tarefas

Abaixo consta a distribuição real de status das 6 tarefas após a rodada:
- **BACKLOG**: 6
- **READY**: 0
- **CLAIMED**: 0
- **PLANNING**: 0
- **IMPLEMENTING**: 0
- **TESTING**: 0
- **PR_READY**: 0
- **FAILED_SAFE**: 0

---

## 5. Evidência de Saída do Terminal e Logs da CLI

### Resultados do Pré-flight
- **docker_or_dev**: PASSED - Docker active: False, Dev mode (local sandbox) config: True
- **omniroute_gateway**: FAILED - GET http://127.0.0.1:20128/v1/models returned HTTP 0: timed out
- **omniroute_completion**: FAILED - No explicit free route was advertised.
- **task_count_match**: PASSED - Tasks imported: 6 = 5 PRD requirements + deterministic LF-PRD-006 release-assembly task
- **chief_engineer_configured**: PASSED - provider=omniroute, model configured: True, credentials/configuration ready: True

### Logs de Execução / Erros da CLI
```text
CLI run was not started because the OmniRoute completion pre-flight failed. The scheduler and task pipeline were intentionally not invoked.
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: BLOCKED**
> The V3-only run proves the OmniRoute-only API-led/economy-first architecture only when at least one `omniroute` call is recorded in `model_call_ledger`, no non-OmniRoute call is recorded, and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
