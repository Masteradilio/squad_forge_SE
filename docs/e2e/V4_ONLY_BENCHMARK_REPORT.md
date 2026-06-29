# LocalForge OS - V4-Only Empirical Benchmark Report

## 1. Executive Summary

Este relatório documenta a execução empírica real de ponta a ponta do **LocalForge V4 Candidate** (API-led AI Engineering Squad) no workspace isolado `sprintboard-v4`.

O benchmark foi executado de forma física e real para produzir o produto **SprintBoard Lite** de acordo com os requisitos em [docs/PRD_SPRINTBOARD_LITE.md](file:///E:\Projetos\local_forge_os/docs/PRD_SPRINTBOARD_LITE.md), sem simulações ou dados pré-fabricados.

### Status do Benchmark
> [!IMPORTANT]
> **STATUS: REJECTED**
>
> A execução empírica real do LocalForge V4 foi finalizada com classificação **REJECTED** de acordo com as validações de pré-flight e os resultados persistidos no banco de runtime.

---

## 2. Blockers Detectados (Pré-flight Checklist)

Os seguintes impedimentos técnicos reais foram validados pelo pré-flight:

1. **V4 API-led routing did not execute any Chief Engineer/OpenRouter call; benchmark did not exercise the intended V4 architecture.**


---

## 3. Métricas Reais do Workspace V4 (Extraídas do SQLite)

Métricas de execução extraídas diretamente da base de dados `.localforge/localforge.db` após a rodada da pipeline:

| Metric | Variant: V4 Candidate | Detail / Evidence |
| :--- | :---: | :--- |
| **Run ID** | f"V4-Run-1" | ID de execução real do controle do LocalForge |
| **SQLite DB Path** | `benchmarks/workspaces/sprintboard-v4/.localforge/localforge.db` | Banco SQLite físico do runtime |
| **Tasks Planned** | 5 | Escopo completo do PRD |
| **Tasks Imported** | 0 | Sucesso na importação real |
| **Task Runs Executed** | 35 | Quantidade de iterações de tarefas tentadas |
| **PR_READY Count** | 0 | Tarefas prontas para pull request |
| **FAILED_SAFE Count** | 5 | Falhas seguras capturadas de forma robusta |
| **Actual API Cost (USD)** | $0.0000 | Custos reais de chamadas aos modelos |
| **Actual Model Calls Logged** | 0 | Quantidade de chamadas aos modelos registradas |
| **OpenRouter Chief Calls Logged** | 0 | Deve ser maior que zero para validar a V4 API-led |
| **Local Calls Logged** | 0 | Evidencia a parte local/economy da arquitetura |
| **API-led Routing Contracts** | {} | Tarefas complexas para Chief; tarefas simples para local |
| **Artifacts Generated** | 0 | Artefatos gravados no disco pelo pipeline |

---

## 4. Distribuição de Estados das Tarefas

Abaixo consta a distribuição real de status das 5 tarefas após a rodada:
- **BACKLOG**: 0
- **READY**: 0
- **CLAIMED**: 0
- **PLANNING**: 0
- **IMPLEMENTING**: 0
- **TESTING**: 0
- **PR_READY**: 0
- **FAILED_SAFE**: 5

---

## 5. Evidência de Saída do Terminal e Logs da CLI

### Resultados do Pré-flight
- **docker_or_dev**: PASSED - Docker active: False, Dev mode (local sandbox) config: True
- **llm_installed**: PASSED - Chosen model for execution: 'gemma4:12b'. Ollama installed models: ['gemma4:12b', 'granite4.1:8b', 'nemotron-3-nano:4b']
- **task_count_match**: PASSED - Tasks imported: 5, Expected count: 5
- **chief_engineer_configured**: PASSED - OPENROUTER_MODEL configured: True, OPENROUTER_API_KEY configured: True

### Logs de Execução / Erros da CLI
```text
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
Task LF-PRD-001 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')\nfatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-001 localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1')
fatal: 'localforge/lf-prd-001-gest-o-de-itens-de-trabalho-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-001'
Task LF-PRD-002 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')\nfatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-002 localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1')
fatal: 'localforge/lf-prd-002-m-quina-de-estados-determin-st-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-002'
Task LF-PRD-003 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')\nfatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-003 localforge/lf-prd-003-filtros-e-exporta-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-003-filtros-e-exporta-o-run-1')
fatal: 'localforge/lf-prd-003-filtros-e-exporta-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-003'
Task LF-PRD-004 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')\nfatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-004 localforge/lf-prd-004-frontend-view-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-004-frontend-view-run-1')
fatal: 'localforge/lf-prd-004-frontend-view-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-004'
Task LF-PRD-005 failed during runner setup: GitAdapterError("Git command 'git worktree add E:\\Projetos\\local_forge_os\\benchmarks\\workspaces\\sprintboard-v4\\.localforge\\worktrees\\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.\nStdout: \nStderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')\nfatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'")
Traceback (most recent call last):
  File "E:\Projetos\local_forge_os\backend\localforge\services\scheduler.py", line 367, in _process_iteration
    runner_context = await asyncio.wait_for(
                     ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Adilio\AppData\Local\Programs\Python\Python311\Lib\asyncio\tasks.py", line 489, in wait_for
    return fut.result()
           ^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\services\runners.py", line 48, in setup
    worktree_path, branch_name = await manager.setup_worktree(task.id)
                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\manager.py", line 95, in setup_worktree
    await git.create_worktree(
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 122, in create_worktree
    await self._execute_git(args, use_task_context=False)
  File "E:\Projetos\local_forge_os\backend\localforge\gitops\adapter.py", line 54, in _execute_git
    raise GitAdapterError(
localforge.gitops.adapter.GitAdapterError: Git command 'git worktree add E:\Projetos\local_forge_os\benchmarks\workspaces\sprintboard-v4\.localforge\worktrees\lf-prd-005 localforge/lf-prd-005-engenharia-e-valida-o-run-1' failed with code 128.
Stdout: 
Stderr: Preparing worktree (checking out 'localforge/lf-prd-005-engenharia-e-valida-o-run-1')
fatal: 'localforge/lf-prd-005-engenharia-e-valida-o-run-1' is already used by worktree at 'E:/Projetos/local_forge_os/benchmarks/workspaces/sprintboard-v3/.localforge/worktrees/lf-prd-005'
```

---

## 6. Conclusão e Próximos Passos

> [!IMPORTANT]
> **CLASSIFICACAO: REJECTED**
> The V4-only run proves the API-led/economy-first architecture only when at least one `openrouter` call is recorded in `model_call_ledger` and costs are consolidated in the report. Otherwise the result remains **REJECTED** or **BLOCKED**, even if the CLI exits with code 0.
