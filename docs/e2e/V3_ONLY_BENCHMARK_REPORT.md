# LocalForge OS - V3-Only Empirical Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V3 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v3`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///E:\Projetos\local_forge_os/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: ACCEPTED**
>
> A execução empírica real do LocalForge V3 foi finalizada com classificação **ACCEPTED** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

Nenhum blocker detectado no pré-flight.

---

## 3. Métricas Reais do Workspace V3 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V3 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V3-Run-1" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v3/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | 5 | Escopo completo do PRD |
| **Tasks Imported** | 5 | Sucesso na importação real |
| **Task Runs Executed** | 7 | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | 5 | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | 0 | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | $0.0307 | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | 16 | Quantidade de chamadas aos modelos registradas |
| **OpenRouter Chief Calls Logged** | 7 | Deve ser maior que zero para validar a V3 API-led |
| **Local Calls Logged** | 9 | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {"chief_only": 1, "chief_led": 4, "local_assisted": 0} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | 84 | Artefatos gravados no disco pelo pipeline |

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
- **docker_or_dev**: PASSED - Docker active: True, Dev mode (local sandbox) config: True
- **llm_installed**: PASSED - Chosen model for execution: 'gemma4:12b'. Ollama installed models: ['gemma4:12b', 'granite4.1:8b', 'nemotron-3-nano:4b']
- **task_count_match**: PASSED - Tasks imported: 5, Expected count: 5
- **chief_engineer_configured**: PASSED - OPENROUTER_MODEL configured: True, OPENROUTER_API_KEY configured: True

### Logs de Execução / Erros da CLI
```text
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Pipeline execution failed for task LF-PRD-001: Generated tests failed: [compressed output sha256=d2065f091290007e original_chars=997]

=================================== ERRORS ====================================
_________________ ERROR collecting tests/test_board_rules.py __________________
ImportError while importing test module 'E:\Projetos\local_forge_os\benchmarks\workspa
[...compressed...]
ROR tests/test_board_rules.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.09s

Task LF-PRD-001 failed during pipeline execution: ValueError("Generated tests failed: [compressed output sha256=d2065f091290007e original_chars=997]\n\r\n=================================== ERRORS ====================================\r\n_________________ ERROR collecting tests/test_board_rules.py __________________\r\nImportError while importing test module 'E:\\Projetos\\local_forge_os\\benchmarks\\workspa\n[...compressed...]\nROR tests/test_board_rules.py\r\n!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\r\n1 error in 0.09s\r\n")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 374, in _process_iteration
    await RolePipelineEngine(
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 158, in run_task
    raise e
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 128, in run_task
    result = await asyncio.wait_for(
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 221, in _execute_pipeline_core
    await self._execute_coder_actions(
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 730, in _execute_coder_actions
    raise ValueError(
ValueError: Generated tests failed: [compressed output sha256=d2065f091290007e original_chars=997]

=================================== ERRORS ====================================
_________________ ERROR collecting tests/test_board_rules.py __________________
ImportError while importing test module 'E:\Projetos\local_forge_os\benchmarks\workspa
[...compressed...]
ROR tests/test_board_rules.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.09s

Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Pipeline execution failed for task LF-PRD-001: Generated tests failed: [compressed output sha256=329f6904b01a1fcf original_chars=1752]
............F.....                                                       [100%]
================================== FAILURES ===================================
_____________________ test_cards_include_required_fields ______________________

    d
[...compressed...]
================
FAILED tests/test_board_rules.py::test_cards_include_required_fields - Assert...
1 failed, 17 passed in 0.06s

Task LF-PRD-001 failed during pipeline execution: ValueError('Generated tests failed: [compressed output sha256=329f6904b01a1fcf original_chars=1752]\n............F.....                                                       [100%]\r\n================================== FAILURES ===================================\r\n_____________________ test_cards_include_required_fields ______________________\r\n\r\n    d\n[...compressed...]\n================\r\nFAILED tests/test_board_rules.py::test_cards_include_required_fields - Assert...\r\n1 failed, 17 passed in 0.06s\r\n')
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 374, in _process_iteration
    await RolePipelineEngine(
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 158, in run_task
    raise e
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 128, in run_task
    result = await asyncio.wait_for(
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 221, in _execute_pipeline_core
    await self._execute_coder_actions(
  File "E:\Projetos\local_forge_os\backend\localforge\pipeline\engine.py", line 730, in _execute_coder_actions
    raise ValueError(
ValueError: Generated tests failed: [compressed output sha256=329f6904b01a1fcf original_chars=1752]
............F.....                                                       [100%]
================================== FAILURES ===================================
_____________________ test_cards_include_required_fields ______________________

    d
[...compressed...]
================
FAILED tests/test_board_rules.py::test_cards_include_required_fields - Assert...
1 failed, 17 passed in 0.06s

Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
Docker Python SDK is not installed. Falling back to local restricted sandbox.
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: ACCEPTED**
> The V3-only run proves the API-led/economy-first architecture only when at least one `openrouter` call is recorded in `model_call_ledger` and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
