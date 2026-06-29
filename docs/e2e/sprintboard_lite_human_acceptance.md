# SprintBoard Lite - Human Acceptance Report

This document records the human validation checks for the **SprintBoard Lite** benchmark.

## STATUS: ACCEPTED

The product is accepted only when the benchmark reaches `ACCEPTED`. A `PARTIAL` result means LocalForge generated some PR artifacts but did not complete the product end-to-end.

### Acceptance Checklist

- `[x]` **Create Tasks**: CRUD is present in the final deliverable.
- `[x]` **Validation Rules**: title and state-machine validation pass in product tests.
- `[x]` **Deterministic State Transitions**: legal/illegal transitions are enforced.
- `[x]` **JSON Export**: board export works and includes active items.
- `[x]` **Frontend UI**: Kanban UI is delivered as a runnable artifact.
- `[x]` **Evidence Exists**: runtime artifacts exist, but partial evidence is not human acceptance.

---

## Real Execution Evidence (SQLite & FileSystem)

- **Workspace Path**: `benchmarks/workspaces/sprintboard-v3`
- **Total Task Runs**: 7 of 5 planned.
- **Total Artifacts**: 84 generated under `.localforge/artifacts/`.
- **Task Statuses**: {"PR_READY": 5}
- **Artifact Types**: {"DiffArtifact": 14, "PRArtifact": 10, "PlanArtifact": 5, "RepairArtifact": 5, "ReviewArtifact": 5, "RiskArtifact": 5, "RoleArtifact": 35, "TestArtifact": 5}
- **V3 Routing Contracts**: {"chief_only": 1, "chief_led": 4, "local_assisted": 0}
- **Chief Engineer/OpenRouter Calls**: 7
- **Local Calls Logged**: 9
