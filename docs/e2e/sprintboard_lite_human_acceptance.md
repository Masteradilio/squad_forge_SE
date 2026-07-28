# SprintBoard Lite - Human Acceptance Report

This document records the human validation checks for the **SprintBoard Lite** benchmark.

## STATUS: HISTORICAL ACCEPTANCE — V5 RERUN REQUIRED

The checklist below records the prior V4 review. The referenced disposable workspace is not
present in the current checkout, and the stored routing summary is empty. It therefore does
not satisfy the current V5 reproducibility contract.

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

- **Workspace Path**: `benchmarks/workspaces/sprintboard-v4`
- **Total Task Runs**: 6 of 5 planned.
- **Total Artifacts**: 97 generated under `.localforge/artifacts/`.
- **Task Statuses**: {"PR_READY": 5}
- **Artifact Types**: {"DiffArtifact": 14, "PRArtifact": 12, "PlanArtifact": 6, "RepairArtifact": 6, "ReviewArtifact": 5, "RiskArtifact": 6, "RoleArtifact": 42, "TestArtifact": 6}
- **V4 Routing Contracts**: {}
- **Chief Engineer/NVIDIA Calls**: 0
- **Chief Engineer/OpenRouter Fallback Calls**: 5
- **Paid Chief Calls**: 5
- **Local Calls Logged**: 1
