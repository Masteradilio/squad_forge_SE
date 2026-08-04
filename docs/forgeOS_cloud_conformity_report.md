# ForgeOS Cloud Conformity Report

**Audit date:** 2026-08-03  
**Reference plan:** `docs/plano_forgeOS_cloud.md`  
**Reference backlog:** `docs/backlog_forgeOS_cloud.md`  
**Verdict:** `IMPLEMENTATION_READY_FOR_TARGETED_VALIDATION`, not a production
release acceptance. The current runtime contract is OmniRoute-only with
free/freemium routes; no paid-provider fallback is part of this acceptance.

This report separates source-level implementation from runtime proof. The
historical Cloud backlog remains unchanged; its checkboxes are not treated as
evidence. A task is only `IMPLEMENTED` when the repository contains the
corresponding behavior and the relevant deterministic tests pass. External
service, Docker, and product claims remain `UNVERIFIED` until exercised in a
clean environment.

## Phase 1: Containers

| Task | Status | Evidence / limitation |
| --- | --- | --- |
| 1.1 OmniRoute image | IMPLEMENTED | `Dockerfile.omniroute` installs the gateway and now fails the image build if installation fails. |
| 1.2 Backend image | IMPLEMENTED | `Dockerfile.backend` installs the Cloud extra, Playwright, and runs as a non-root user. |
| 1.3 Frontend image | IMPLEMENTED | `Dockerfile.frontend` builds with `npm ci` and serves through Nginx. |
| 1.4 Compose stack | IMPLEMENTED | Compose defines OmniRoute, Postgres/pgvector, Redis, backend, and frontend with health dependencies. |
| 1.5 Clean Docker startup | UNVERIFIED | `docker compose config` requires `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `LOCALFORGE_API_TOKEN`; a clean startup has not been claimed. |

## Phase 2: OmniRoute and routing

| Task | Status | Evidence / limitation |
| --- | --- | --- |
| 2.1 OpenAI-compatible client | IMPLEMENTED | `OmniRouteClient` supports models, chat completions, SSE normalization, semantic cache, and authenticated combo management. |
| 2.2 Model discovery | IMPLEMENTED | Cloud runs now fail closed unless `models.provider=omniroute`; the server-owned loop performs bounded discovery before starting the Scheduler. |
| 2.3 Agentic capability filtering | IMPLEMENTED | Tool, JSON, and free-tier capabilities are required before routing; verified OmniRoute `auto/*free` aliases use the gateway's declared tool contract plus the deployment's explicit JSON-output verification flag. |
| 2.4 Recency and size ranking | IMPLEMENTED | Release age and parameter size are deterministic sort inputs. |
| 2.5 Dynamic combos | PARTIAL | Authenticated deployments can register `forge-high-tier` and `forge-mid-tier` through OmniRoute's `/api/combos` management API; the default Compose profile is read-only and uses verified `auto/*free` aliases because the gateway's management API requires a separate `manage` credential. |
| 2.6 Squad skills | PARTIAL | Local skill contracts exist, but upstream parity with `mattpocock/skills` is not independently proven. |
| 2.7 Context7 | IMPLEMENTED | Connector and prefetch surface exist; live MCP availability remains runtime-dependent. |
| 2.8 Interface contracts first | IMPLEMENTED | Task contracts, authority checks, and Chief Engineer contract services are present. |
| 2.9 File scope locking | IMPLEMENTED | Contract scope and protected-path checks are enforced before task acceptance. |

## Phase 3: Persistence and memory

| Task | Status | Evidence / limitation |
| --- | --- | --- |
| 3.1 Postgres/pgvector | PARTIAL | Postgres/pgvector is provisioned by Compose; ChromaDB is not a required runtime dependency. |
| 3.2 Tenant isolation/RLS | NOT IMPLEMENTED | The current ORM/API is project-scoped and does not yet provide authenticated tenant context or PostgreSQL RLS policies. |
| 3.3 BYOK vault | PARTIAL | AES-GCM vault primitives exist, but a complete tenant-scoped BYOK API and UI flow is not proven. |
| 3.4 Graphify | IMPLEMENTED | Deterministic AST graph generation and cache surfaces exist. |
| 3.5 MemPalace | IMPLEMENTED | Memory facts, relations, provenance, and retrieval surfaces exist. |
| 3.6 Rule synthesizer | IMPLEMENTED | Sanitized rule synthesis and atomic persistence exist; automatic project instruction injection remains bounded by policy. |
| 3.7 Backlog compiler | IMPLEMENTED | PRD compiler creates typed tasks, dependencies, contracts, and evidence metadata. |

## Phase 4: Execution safety and operations

| Task | Status | Evidence / limitation |
| --- | --- | --- |
| 4.1 Ephemeral sandbox | PARTIAL | Docker and local sandbox implementations have path containment, but the Compose backend still receives the host Docker socket; a rootless socket proxy or isolated worker boundary is still required for production. |
| 4.2 Resource limits | PARTIAL | CPU, memory, PID, read-only root, and no-new-privilege controls are applied to child containers, but rootless/cgroups-v2 production enforcement is not independently proven. |
| 4.3 Egress allowlist | PARTIAL | The default is network-denied and both the factory and Docker sandbox reject unprovisioned network access; DNS-level allowlist enforcement is not implemented. |
| 4.4 Live preview proxy | PARTIAL | Preview URL/config metadata exists; no deployed Traefik route or authenticated preview service is proven. |
| 4.5 Secret scrubbing | IMPLEMENTED | Terminal and exported artifact paths redact common API keys, bearer tokens, and assignments. |
| 4.6 Compiler feedback | IMPLEMENTED | Compiler/test feedback is passed into bounded repair paths. |
| 4.7 Dependency locking | IMPLEMENTED | Frontend `package-lock.json` is tracked and `uv.lock` is generated by `localforge init` through the package locker; a clean-install proof remains a release validation task. |
| 4.8 OpenTelemetry | IMPLEMENTED | Tracer and API timeline surfaces exist. |
| 4.9 HITL gates | IMPLEMENTED | Durable approval and dynamic-input paths exist in backend and frontend. |
| 4.10 Authority matrix | IMPLEMENTED | Role aliases, path scopes, and action gateway enforcement are tested. |

## Phase 5: Product and release

| Task | Status | Evidence / limitation |
| --- | --- | --- |
| 5.1 Tenant auth and cloud upload | PARTIAL | API auth and PO attachment intake exist, but tenant isolation is still missing. |
| 5.2 Live preview UI | PARTIAL | Frontend exposes settings/preview metadata, but a deployed preview journey is not proven. |
| 5.3 BYOK UI | PARTIAL | Settings surfaces exist; end-to-end encrypted tenant-scoped storage is not proven. |
| 5.4 Tracing timeline | IMPLEMENTED | Backend spans and frontend timeline component exist. |
| 5.5 Dynamic PO input/HITL UI | IMPLEMENTED | HITL modal and chat flow exist with API integration. |
| 5.6 Docker/OmniRoute E2E | BLOCKED | OmniRoute discovery is healthy, but Docker's Windows named pipe is currently unresponsive and the tested free/freemium routes returned upstream HTTP 500/502 or connect timeouts. No product acceptance exists until a real free-route completion is recorded in SQLite. |
| 5.7 Executive release dossier | PARTIAL | Dossier/evidence services exist, but a release dossier cannot be accepted while mandatory E2E and tenant gates remain open. |

## Deterministic validation

The current repository passes the local engineering gates:

```text
Targeted OmniRoute/cloud hardening tests pass (`81 passed`), the full backend
suite passes (`482 passed, 1 skipped`), mypy passes for `262 source files`, the
frontend production build passes, and `git diff --check` is clean. The
clean-clone release run remains unverified.
```

These results prove repository consistency, not Cloud deployment or product
acceptance. `/v1/models` discovery was verified against the local OmniRoute
gateway; both Chief preflight and pipeline worker selection now append only a
bounded set of explicitly free/freemium aliases from that live catalog.
Direct completion probes nevertheless failed at the upstream gateway, while
the Docker SDK could not complete a bounded Windows named-pipe ping. No
successful HP12C product run or ten-function validation is claimed. The next
acceptance run requires a responsive Docker daemon or an explicitly selected
local development sandbox, plus at least one healthy free/freemium OmniRoute
route, followed by SQLite inspection and manual verification of the product.
The current preflight also permits two short, configurable recovery rounds
after a complete route-ladder outage; this change is covered by the targeted
preflight test but has not yet produced a successful live completion.

## Latest real acceptance attempt

The bounded local-sandbox attempts on 2026-08-03 used
`benchmarks/workspaces/hp12c-cloud-acceptance-117` and
`benchmarks/workspaces/hp12c-cloud-acceptance-118` through the real CLI path.
Both successfully imported the HP12C PRD and created 19 typed tasks. Run 117
stopped after two upstream failures. After the preflight retry hardening, Run
118 skipped failed aliases and tested four distinct free routes before
stopping because the OmniRoute free-route preflight still received upstream
HTTP 500/502 responses, including `UND_ERR_CONNECT_TIMEOUT`. The persisted
SQLite state for Run 118 is:

```text
projects: 1
tasks: 19 (all READY)
runs: 1 (`BLOCKED_NEEDS_HUMAN_REVIEW`)
task_runs: 0
artifacts: 0
```

This is a valid fail-closed runtime result, not product acceptance. It proves
that PRD import and backlog creation work in the Cloud path, while proving no
completion, repair, PR generation, or ten-function HP12C behavior until at
least one OmniRoute free/freemium route completes a bounded chat request.

## Security review and remediation

The bounded security review found and fixed two actionable code issues: the
benchmark harness now binds `project_id` as a SQL parameter, and the
deterministic HTML replay renders payload fields with DOM `textContent` instead
of `innerHTML`, with script-safe JSON encoding. The Nginx production template
now emits CSP, `X-Content-Type-Options`, `X-Frame-Options`, strict referrer
policy, and restrictive permissions policy headers. A Windows Git worktree
pointer repair syntax error was also fixed and covered by the Git tests.

The repository security scanner's backend pattern/secret modes still report
regex false positives for documentation strings, safe
`create_subprocess_exec` calls, redaction regexes, environment-variable names,
and the internal development Redis URL. Those matches were manually triaged;
the scanner's full dependency mode was not accepted as evidence because its
networked `npm audit` exceeded the bounded timeout. Frontend pattern and secret
scans returned no findings. Residual production risks remain the Docker socket
boundary, missing PostgreSQL RLS/tenant context, and incomplete allowlisted
egress/preview deployment; these are explicitly not release-accepted.
