# LocalForge OS E2E Acceptance Plan

## Goal

Validate whether LocalForge OS can take a medium-scope PRD, route work across
local Ollama models by task complexity, run unattended, recover from ordinary
execution failures, and leave reviewable pull request artifacts instead of
requiring direct human intervention.

## Model Routing Under Test

| Complexity | Ollama model | Intended roles/tasks |
| --- | --- | --- |
| High | `gemma4:12b` | architecture, UI fidelity, financial algorithms, final review |
| Medium | `granite4.1:8b` | implementation, test planning, integration cleanup |
| Low | `nemotron-3-nano:4b` | simple documentation, mechanical setup, basic status summaries |

The E2E is only successful if execution evidence shows these model names are
visible in LocalForge role/task context or model configuration and the run uses
the configured local provider rather than a cloud fallback.

## Test Project

The disposable project is `samples/e2e-hp12c-platinum`. Its PRD is
`samples/e2e-hp12c-platinum/docs/PRD_HP12C_PLATINUM.md`.

The PRD asks LocalForge to build a desktop-style financial calculator inspired by
the HP 12C Platinum visual reference in `docs/e2e/hp12c-platinum-reference.png`.
For this internal E2E, the visual acceptance target is a faithful reference-style
layout, color system, screen, and button grid. The project must avoid claiming
official HP affiliation.

## E2E Scenarios

### Scenario 1 - Environment and Model Sanity

Commands:

```powershell
$env:PYTHONPATH="E:\Projetos\local_forge_os\backend"
.\.codex_venv\Scripts\python.exe -m pytest backend/tests -q
.\.codex_venv\Scripts\python.exe -m mypy backend
ollama list
```

Pass criteria:

- backend regression passes without warning summary;
- mypy passes;
- `gemma4:12b`, `granite4.1:8b`, and `nemotron-3-nano:4b` are available.

### Scenario 2 - PRD Import and Task Planning

Commands, from `samples/e2e-hp12c-platinum`:

```powershell
$env:PYTHONPATH="E:\Projetos\local_forge_os\backend"
$env:LOCALFORGE_DEFAULT_MODEL="granite4.1:8b"
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main init
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main import-prd docs\PRD_HP12C_PLATINUM.md --json
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main plan
```

Pass criteria:

- workspace initializes without touching the main LocalForge repository state;
- PRD import creates around 30 tasks;
- tasks have clear acceptance criteria;
- tasks remain in BACKLOG until explicit approval.

### Scenario 3 - Unattended Run and PR Artifact Generation

Commands, from `samples/e2e-hp12c-platinum`:

```powershell
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main plan --approve-all
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main run --unattended
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main status
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main prs
```

Pass criteria:

- run reaches `COMPLETED` without manual intervention;
- each accepted task reaches `PR_READY`, `DONE`, or an explained safe terminal
  state;
- generated artifacts include role evidence and PR artifacts;
- source files for the calculator exist in the disposable project;
- generated implementation has runnable tests or a deterministic validation
  command.

### Scenario 4 - Self-Healing and Safety Behavior

The run must demonstrate at least one recoverable failure or safety-relevant
decision through audit evidence. Acceptable evidence includes:

- a failed command followed by a repair artifact and later passing validation;
- a blocked unsafe command/file write with a clear safety decision;
- a task ending in `FAILED_SAFE` with a useful summary and no corrupted worktree.

Pass criteria:

- failure is visible in logs/audit;
- LocalForge does not silently hang;
- final state is either repaired or explicitly safe-failed.

### Scenario 5 - Review Surface

Commands:

```powershell
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main logs
E:\Projetos\local_forge_os\.codex_venv\Scripts\python.exe -m localforge.cli.main replay <run-id>
```

Pass criteria:

- logs explain task/risk/safety decisions;
- replay output exists for the final run;
- a human reviewer can identify what changed, what passed, what failed, and what
  PR artifacts to inspect.

## Rating Rubric

### Funciona bem

- All five scenarios pass.
- The run produces reviewable PR artifacts and actual calculator implementation
  files.
- Model routing evidence includes all three requested Ollama models.
- Any failure is either self-healed or cleanly safe-failed with actionable
  summary.

### Funciona com ressalvas

- Core import/planning/run/PR artifact flow works, but one or more expectations
  need manual interpretation, have weak evidence, or produce incomplete
  implementation.

### Não está pronto

- The run does not produce actual implementation files, does not use the local
  model path, cannot finish unattended, loses auditability, or fails without
  actionable recovery.

## Final Evidence to Record

- exact commands run;
- final command outputs;
- generated task count;
- final run id and status;
- final task status counts;
- PR artifact count and paths;
- model names observed in configuration/context/artifacts;
- implementation files generated in `samples/e2e-hp12c-platinum`;
- final rating and blockers.
