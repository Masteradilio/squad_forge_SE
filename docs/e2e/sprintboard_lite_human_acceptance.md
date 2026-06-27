# SprintBoard Lite - Human Acceptance Report

This document records the human validation checks for the **SprintBoard Lite** benchmark.

## STATUS: PARTIAL

The product is accepted only when the benchmark reaches `ACCEPTED`. A `PARTIAL` result means LocalForge generated some PR artifacts but did not complete the product end-to-end.

### Acceptance Checklist

- `[ ]` **Create Tasks**: CRUD is present in the final deliverable.
- `[ ]` **Validation Rules**: title and state-machine validation pass in product tests.
- `[ ]` **Deterministic State Transitions**: legal/illegal transitions are enforced.
- `[ ]` **JSON Export**: board export works and includes active items.
- `[ ]` **Frontend UI**: Kanban UI is delivered as a runnable artifact.
- `[x]` **Evidence Exists**: runtime artifacts exist, but partial evidence is not human acceptance.

---

## Evidência de Execução Real (SQLite & FileSystem)

- **Workspace Path**: `benchmarks/workspaces/sprintboard-v3`
- **Total Task Runs**: 16 de 18 planejadas.
- **Total Artifacts**: 148 gerados em `.localforge/artifacts/`.
- **Status das Tarefas no Banco**: {"FAILED_SAFE": 11, "PR_READY": 5, "READY": 2}
- **Tipos de Artefatos no Banco**: {"DiffArtifact": 30, "PRArtifact": 10, "PlanArtifact": 13, "RepairArtifact": 7, "ReviewArtifact": 7, "RiskArtifact": 7, "RoleArtifact": 67, "TestArtifact": 7}
