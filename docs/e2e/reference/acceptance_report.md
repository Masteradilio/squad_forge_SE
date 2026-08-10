# ForgeOS Reference ForgeLedger PRD Benchmark

- Status: **ACCEPTED**
- README claims checked: **15/15 PASS**
- Workspace: benchmarks/workspaces/readme-trace-run-20260809T001429Z
- PRD: docs/PRD_REFERENCE_FORGEOS.md

## README claim versus observed evidence

| Claim | Evidence | Status |
| --- | --- | --- |
| OmniRoute-only live gateway and model evidence | route=nvidia/nvidia/nemotron-3-nano-30b-a3b; providers={'omniroute': 11} | **PASS** |
| PRD import, contracts, worktrees, tasks, and PR_READY | tasks={'PR_READY': 5}; runs={'COMPLETED': 1} | **PASS** |
| Lifetime goal, receipts, quota/frontier, and events | revision=73; receipts=6; events=67 | **PASS** |
| Generated product and canonical fixture acceptance | {"manifest_ok": true, "commands": [{"exit_code": 0, "command": ["pytest", "tests", "-q"]}, {"exit_code": 0, "command": ["pytest", "C:\\Users\\adili\\projetos_offline\\local_forge_os\\scripts\\fixtures\\reference_forgeos_create_acceptance.py", "C:\\Users\\adili\\projetos_offline\\local_forge_os\\scripts\\fixtures\\reference_forgeos_validation_acceptance.py", "C:\\Users\\adili\\projetos_offline\\local_forge_os\\scripts\\fixtures\\reference_forgeos_summary_acceptance.py", "C:\\Users\\adili\\projetos_offline\\local_forge_os\\scripts\\fixtures\\reference_forgeos_snapshot_acceptance.py", "-q"]}]} | **PASS** |
| Plan/diff/test/review/risk/PR artifact evidence | required=['DiffArtifact', 'PRArtifact', 'PlanArtifact', 'ReviewArtifact', 'RiskArtifact', 'TestArtifact']; observed={'DiffArtifact': 27, 'PRArtifact': 12, 'PlanArtifact': 6, 'RepairArtifact': 6, 'ReviewArtifact': 6, 'RiskArtifact': 6, 'RoleArtifact': 42, 'TestArtifact': 6} | **PASS** |
| Typed Predict/CodeAct-style Harness contract | code_act strategy and required context retained | **PASS** |
| Durable prompts, memory, refinement, snapshots | snapshots, refinement, persistence, and prompt protection | **PASS** |
| Bounded parent/child subagent lifecycle | durable parent-child lifecycle and terminal protection | **PASS** |
| Built-in and persisted custom skills | three workflow skills and a persisted custom manifest | **PASS** |
| Pre-execution safety hook boundary | pre-execution hook denied the tool before executor | **PASS** |
| Nested spans and lifecycle events | nested spans and ordered lifecycle events | **PASS** |
| Graphify, MemPalace, and sanitized rule synthesis | Graphify, MemPalace recall, and sanitized rule synthesis | **PASS** |
| Optional Context7 MCP surface | MCP parser and endpoint surface present; live service not required | **PASS** |
| Optional Redis cache/pub-sub/lock surface | optional cache, pub-sub, and lock interface present; server not required | **PASS** |
| Optional Helm/HPA deployment surface | optional chart and HPA template present | **PASS** |

## Control-plane evidence

- Goal status: **COMPLETED**
- Todos: **[('LF-PRD-001', 'PASSED'), ('LF-PRD-002', 'PASSED'), ('LF-PRD-003', 'PASSED'), ('LF-PRD-004', 'PASSED'), ('LF-PRD-005', 'PASSED')]**
- Receipts: **6**

This report is generated after the real ForgeOS run from SQLite, the
durable control-plane snapshot, independent product tests, canonical
fixtures, and bounded platform probes. It does not edit generated
product code or convert optional integration surfaces into live proof.
