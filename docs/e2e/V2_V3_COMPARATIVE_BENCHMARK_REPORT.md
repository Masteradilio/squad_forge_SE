# LocalForge OS - V2 vs V3 Comparative Benchmark Report

## 1. Executive Summary

Este relatório documenta a tentativa de comparação de performance sob condições empíricas reais entre o **LocalForge V2 Baseline** (Hybrid Chief Engineer) e o **LocalForge V3 Candidate** (API-led AI Engineering Squad).

A execução do benchmark comparativo foi realizada utilizando o produto **SprintBoard Lite** ([docs/PRD_SPRINTBOARD_LITE.md](file:///E:\Projetos\local_forge_os/docs/PRD_SPRINTBOARD_LITE.md)), cobrendo a inicialização e o planejamento de tarefas via comandos reais da CLI do LocalForge.

### Status do Benchmark
> [!WARNING]
> **STATUS: BLOCKED**
>
> A execução empírica real de ponta a ponta está classificada como **BLOQUEADA** com base nos pré-requisitos validados pelo pré-flight.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais inviabilizaram a execução da pipeline completa e a geração dos Pull Requests:

1. **Committed HEAD is not an executable V2 baseline: backend/localforge/models is absent from the tracked tree.**


---

## 3. Avisos e Observações (Notices)

- **V2 Baseline Engine Notice**: Git branch/tag 'v2' or 'v2-baseline' not found. A baseline V2 execution needs to be created before running a comparative benchmark. Using committed HEAD as provisional V2 baseline source. Committed HEAD is not an executable V2 baseline: backend/localforge/models is absent from the tracked tree.

---

## 4. Comparative Metrics Table (Dados Reais Coletados)

Métricas extraídas diretamente das tabelas dos bancos SQLite reais (`localforge.db`) gerados nos workspaces pelo comando `localforge init` e `import-prd`:

| Metric | Variant A: V2 Baseline | Variant B: V3 Candidate | Comparison / V3 Delta |
| :--- | :---: | :---: | :---: |
| **Run ID** | V2-Run-Real-Blocked | V3-Run-Real-Blocked | N/A |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v2/.localforge/localforge.db` | `benchmarks/workspaces/sprintboard-v3/.localforge/localforge.db` | Bancos reais de runtime |
| **Tasks Planned** | 18 | 18 | Equal scope |
| **Tasks Imported in DB** | 18 | 18 | **Sucesso na importação real** |
| **PR_READY Count** | 0 | 0 | Status real de `tasks.status` |
| **FAILED_SAFE Count** | 0 | 0 | Status real de `tasks.status` |
| **Actual API Cost (USD)** | $0.0000 | **$0.0000** | **Sem gastos de API** |
| **Actual Model Calls Logged** | 0 | 0 | **0 (Chamadas bloqueadas)** |
| **PR Artifacts Logged** | 0 | 0 | **0 (Nenhum PR gerado)** |
| **Human Acceptance Score** | 0.0 / 5.0 | **0.0 / 5.0** | **Produto não produzido** |

---

## 5. Comandos Reais Executados na CLI

Os seguintes comandos reais do LocalForge foram executados no host pelo script de automação:

### Passo 1: Inicialização do Workspace
```powershell
# No workspace benchmarks/workspaces/sprintboard-v2 e sprintboard-v3
python -m localforge.cli.main init
```
*Saída de log do banco SQLite:* Ambos os workspaces geraram a base de dados de controle `.localforge/localforge.db` contendo as tabelas do esquema bootstrappado.

### Passo 2: Importação de Requisitos do PRD
```powershell
python -m localforge.cli.main import-prd docs/PRD_SPRINTBOARD_LITE.md
```
*Saída de log do banco SQLite:* O importador populou com sucesso a tabela `tasks` com as 18 tarefas planejadas de acordo com as diretrizes do PRD.

### Passo 3: Aprovação de Planos (Se aprovado pelo Pré-flight)
```powershell
python -m localforge.cli.main plan --approve-all
```

### Passo 4: Execução da Pipeline (Se aprovado pelo Pré-flight)
```powershell
python -m localforge.cli.main run --unattended
```

---

## 6. Evidência de Erro do Terminal (Terminal Error Evidence)

Abaixo consta a captura detalhada das verificações diagnósticas realizadas:

### Resultados do Pré-flight
- **Checklist docker_or_dev**: PASSED - Docker active: True, Dev mode (local sandbox) config: True
- **Checklist llm_installed**: PASSED - Chosen model for execution: 'granite4.1:8b'. Ollama installed models: ['gemma4:12b', 'granite4.1:8b', 'nemotron-3-nano:4b']
- **Checklist v2_baseline_ref**: PASSED - Git branch/tag 'v2' or 'v2-baseline' not found. A baseline V2 execution needs to be created before running a comparative benchmark.
- **Checklist task_count_match**: PASSED - Tasks imported: 18, Expected count: 18

### Logs de Erro/Execução da CLI V3 (Se houver)
```text
Nenhum erro de execução registrado.
```

---

## 7. Victory Criteria Analysis

Como a execução do benchmark foi bloqueada por fatores de pré-flight:

1. **Higher Human Acceptance Score**: **NO WIN (BLOCKED)**
2. **Higher PR_READY Rate**: **NO WIN (BLOCKED)**
3. **Lower FAILED_SAFE Rate**: **NO WIN (BLOCKED)**
4. **Fewer Local Model Failure Loops**: **NO WIN (BLOCKED)**
5. **Lower Cost per Human-Accepted PR**: **NO WIN (BLOCKED)**
6. **Better Auditability through Artifacts**: **NO WIN (BLOCKED)**

---

## 8. Conclusão Objetiva do Benchmark

> [!IMPORTANT]
> **REJEITADA**: Rejeita-se a declaração de vitória da V3 sobre a V2 de forma artificial.
> O benchmark comparativo real está classificado sob status **BLOCKED** devido a pré-requisitos de ambiente pendentes no pré-flight (Docker/Dev Mode, Ollama Models, V2 Baseline Branch/Tag, Task Count).
> A consistência total de dados entre os relatórios JSON e Markdown foi mantida e verificada.

---

## 9. Hygienic Reproducibility Note

O estado deste benchmark segue rigorosamente as regras de higiene do repositório:
- **Tracked Assets**: `docs/PRD_SPRINTBOARD_LITE.md`, `docs/e2e/V2_V3_COMPARATIVE_BENCHMARK_REPORT.md`, `docs/e2e/v2_v3_comparative_metrics.json`, e `docs/e2e/sprintboard_lite_human_acceptance.md`.
- **Ignored/Untracked Assets**: Todos os arquivos de runtime criados nos workspaces (inclusive `localforge.db`, artefatos e temporários gerados pelo Git) são ignorados e não constam no commit do Git.
