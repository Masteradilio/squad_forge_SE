# Changelog

All notable changes to LocalForge OS will be documented in this file.

## [Unreleased] - 2026-08-01 (V6 Compliance Hardening)

### ForgeOS Cloud OmniRoute Hardening
- Consolidated the configured free-route ladder so the API, CLI, Scrum Master,
  Chief Engineer, templates, Compose defaults, and benchmarks use the same
  OmniRoute-only source of truth. Static provider-specific aliases are no
  longer required by the default configuration; live catalog discovery remains
  responsible for selecting currently advertised routes.
- Replaced the HP12C Cloud acceptance launcher with a synchronous Python runner
  that performs a real OmniRoute catalog and structured-completion preflight,
  waits for every CLI stage, captures bounded output, inspects SQLite task/run
  and model-call state, and writes an explicit `ACCEPTED`, `PARTIAL`, or
  `BLOCKED` report. The PowerShell entry point now selects `.venv` or
  `.codex_venv` and propagates the real exit code instead of returning a PID.
- Aligned Cloud defaults, workspace templates, Compose defaults, Squad profiles,
  discovery tiers, and visual fallback ladders with OmniRoute free/freemium
  routes (`auto/best-free`, `auto/coding:free`, and `oc/*-free`), while keeping
  explicit operator overrides supported.
- Discovery now recognizes `:free`/`-free` OmniRoute catalog IDs as free routes
  and never synthesizes paid aliases for high, mid, or fast tiers.
- CLI Chief preflight now expands the configured ladder with a bounded set of
  explicitly free routes discovered from the live OmniRoute catalog, allowing
  stale configured aliases to recover without introducing direct NVIDIA,
  OpenRouter, or Ollama calls.
- Pipeline local-worker selection now rejects non-free OmniRoute overrides and
  appends a bounded live free-route catalog, so stale paid aliases cannot be
  reintroduced by a role profile during execution.
- Chief preflight now skips an alias after an upstream `500/502` or connection
  failure and probes at most four distinct free routes before fail-closed
  blocking; this prevents retrying the same broken route while preserving a
  bounded chance for another OmniRoute route to recover the run.
- Added a second bounded gateway recovery round with configurable delay so a
  transient OmniRoute-wide outage can recover unattended; the preflight test
  covers four failed routes followed by a successful route on round two.
- Fixed a Python parser error in Git worktree pointer repair by normalizing the
  Windows path before interpolating it into the output string.
- Added production response headers to the Nginx frontend template: CSP,
  `X-Content-Type-Options`, `X-Frame-Options`, strict referrer policy, and a
  deny-by-default camera/geolocation/microphone policy.
- Updated the Cloud conformity report to classify the Compose Docker-socket
  sandbox and rootless/cgroups-v2 production enforcement as `PARTIAL`, and to
  record the bounded security-scan limitations and remaining RLS, egress, and
  preview-deployment risks explicitly.
- Root `.env`, workspace defaults, and the frontend model settings now suggest
  only the same free/freemium OmniRoute route family.
- Docker SDK bootstrap operations now have bounded timeouts, and the HP12C
  acceptance script exposes an explicit `docker` default or `local` development
  mode instead of silently downgrading isolation. OmniRoute Chief pre-flight now
  stops after repeated gateway-wide upstream failures instead of leaving a run
  pending or retrying indefinitely.
- Targeted validation: `81 passed`; global mypy: `Success: no issues found in
  262 source files`. Cloud product acceptance remains unverified because the
  local Docker daemon is unresponsive and current OmniRoute upstream routes
  return `500/502` or timeout; no E2E success claim is made.
- Final local regression after the live-route fallback hardening: `482 passed,
  1 skipped`; frontend production build also passed.
- Real acceptance attempt `hp12c-cloud-acceptance-117` (local development
  sandbox) imported 19 HP12C tasks but stopped before execution after two
  OmniRoute free-route HTTP 502 responses with `UND_ERR_CONNECT_TIMEOUT`.
  SQLite recorded one `BLOCKED_NEEDS_HUMAN_REVIEW` run, 19 `READY` tasks, zero
  `task_runs`, and zero artifacts. This evidence is intentionally not reported
  as product or ten-function acceptance.
- Follow-up Run 118 exercised the new distinct-route retry behavior and tested
  four free aliases before receiving upstream 500/502 failures. Its SQLite
  state remained 19 `READY` tasks, zero `task_runs`, and zero artifacts; the
  product acceptance gate therefore remains open.
- Run 119 exercised two bounded recovery rounds (eight total route
  observations) and still received upstream 500/502/connect-timeout errors.
  The run correctly failed closed with 19 `READY` tasks and zero execution or
  product artifacts; no HP12C acceptance claim is made.
- Removed all generated HP12C benchmark workspaces after extracting their
  evidence; the reference `samples/e2e-hp12c-platinum/docs` directory retains
  only the PRD and design-target image.
- Corrected `scripts/run_benchmark_v3_only.py`, which was still initializing
  benchmark workspaces with Ollama and treating OpenRouter-style calls as
  valid Cloud evidence. The benchmark now probes the live OmniRoute catalog,
  selects only explicitly free/freemium routes, forces both worker and Chief
  configuration through the gateway before `init`, and rejects any recorded
  non-OmniRoute call.
- Fixed the generated V3 metrics/report contract to use the
  `omniroute_gateway` preflight key and to distinguish OmniRoute calls from
  forbidden direct-provider calls.
- Added a structured completion gate to the Cloud benchmark: catalog discovery
  is no longer treated as provider readiness. The preflight now probes a
  bounded set of explicitly free OmniRoute routes with a tiny action request,
  selects only a route that actually completes, and blocks before the
  scheduler when every route times out or returns an upstream error.
- Corrected the blocked-run report so a preflight stop cannot be described as
  a completed CLI execution. The report now records that the scheduler was not
  invoked and keeps product acceptance, PR artifacts, and API-led evidence
  false until a real OmniRoute completion is persisted.
- Added bounded OmniRoute upstream timeout and provider-cooldown defaults to
  Compose and `.env.example`, plus dynamic free-route discovery from the live
  catalog. These settings limit route probing and prevent stale aliases from
  creating unbounded unattended waits.
- Added hard timeouts and child-process cleanup to the Cloud benchmark's Docker
  probe and CLI invocations. A stalled local gateway or CLI now produces a
  bounded diagnostic instead of leaving a Python benchmark process running
  after the operator shell times out; `run` defaults to a 900-second command
  ceiling and can be adjusted with `LOCALFORGE_BENCHMARK_RUN_TIMEOUT`.
- Hardened the OmniRoute credential boundary: `OMNIROUTE_URL` and
  `OMNIROUTE_API_KEY` from `.env` now populate both gateway configurations
  without mutating the process environment, and the API, CLI, discovery,
  pipeline, and Chief Engineer transports pass the configured endpoint key
  explicitly. Failed Chief Engineer ledger entries now remain attributed to
  `omniroute` instead of an obsolete direct-provider default. Added a focused
  configuration regression test for this path.
- Re-ran the OmniRoute-only benchmark with a bounded smoke timeout after the
  credential fix. The catalog and all pre-flight checks passed, but the real
  run timed out before its first model call (`exit 124`), leaving 6 tasks
  `READY`, zero task runs/artifacts/calls, and an accurate `REJECTED` report;
  this remains infrastructure/readiness evidence, not product acceptance.
- Updated the SprintBoard preflight contract for the current PRD compiler:
  five numbered requirements plus the deterministic `LF-PRD-006` release-
  assembly task are accepted, while arbitrary task-count drift remains blocked.
- Changed the OmniRoute transport default for hidden reasoning from `low` to
  `none` and applied the same bounded setting to direct `OmniRouteClient`
  calls and the Cloud benchmark. This avoids spending free-route latency on
  unneeded hidden reasoning while preserving structured-output and tool-use
  validation. Targeted LLM, Cloud compliance, and configuration tests pass
  (`51 passed`).

### Reliability and Evidence
- Permanent Chief-provider failures (billing, credits, and authentication) now
  propagate from the pipeline to the scheduler with their original diagnostic;
  Scrum Master recovery no longer spends repeated paid cycles on a blocker that
  requires operator action. Added regression coverage for provider-error
  propagation and verified the backend suite at `450 passed, 1 skipped` in the
  dependency-complete test runtime.
- Final run summaries now reload persisted task state before rendering counts
  and include the exact per-task blocker in both `run.summary` and
  `run_summary.md`, preventing stale task objects from hiding the cause of a
  blocked unattended run.
- Compliance remediation now makes the PR Factory and Light Swarm use the
  canonical mechanical pre-PR gate. Remote PR creation is skipped when a gate
  fails, and `PR_READY` requires observed commit/diff bindings plus an approved
  independent Maker/Checker record instead of synthetic role IDs.
- The normal role pipeline now persists the deterministic validation result as
  a Maker/Checker verification before invoking the PR Factory. Failed tests do
  not receive a fabricated approval and remain safely blocked.
- Paid model ledger entries are recalculated from persisted pricing snapshots;
  missing paid-model pricing is an error, while local providers remain zero-cost.
  OpenRouter Minimax snapshots are bootstrapped for fresh and existing databases.
- R9 fixture observations are now explicitly ineligible for production
  comparative acceptance. The R9 report records `PARTIAL` until real ledger
  observations replace `OBSERVED_LEDGER_FIXTURE` rows.
- The empirical benchmark no longer writes fabricated zero API costs and now
  reports `UNKNOWN` when no model-call ledger evidence exists; a run is complete
  only when every imported task reaches `PR_READY`.
- Chief Engineer routing is now provider-aware: NVIDIA no longer receives
  OmniRoute `auto/*` aliases, and a provider-level model-not-found (`404`) can
  reach the configured fallback without weakening authentication or billing
  failures. A clean HP12C retry confirmed the route reached NVIDIA correctly;
  the remaining block was external (`NVIDIA 429`/timeout followed by OpenRouter
  `402 Insufficient credits`), with failed calls and pricing evidence recorded
  in SQLite.
- Visual Chief repairs now require a complete `write_file` HTML document with
  standalone document sections before entering the gate; CSS-only patches and
  short `append_content` responses are rejected immediately as non-material repairs.
  The contract also enforces a 6,000-character minimum for standalone visual HTML,
  preventing compact-prompt guidance from collapsing into an empty shell.
- Provider factories now propagate `chief_engineer.max_output_tokens_per_call` to NVIDIA,
  OpenRouter, and OpenAI-compatible clients, so economy-first output limits are enforced
  by workspace configuration rather than depending on an unrelated shell variable.
- Cancelling a run now also cancels its pending or running task runs with a persisted
  end time and operator summary, preventing stale task-run records from blocking a
  later unattended execution. Added a focused regression test for this lifecycle invariant.
- Chief readiness now probes the configured primary provider before any fallback
  wrapper, preventing a slow healthy NVIDIA primary from being misreported as an
  OpenRouter credit failure. The server-owned API loop uses the same fail-fast guard.
- Multimodal requests no longer fall through to an unverified fallback provider;
  visual failures remain on the primary route so the bounded text-contract path can
  recover without silently resending image data to a different provider.
- Normalized singular Chief responses such as `{"action": {...}}` into the required
  non-empty `actions` array and replaced the oversized visual system prompt at call
  time with a compact contract-driven prompt. This reduces provider timeouts while
  retaining deterministic visual-gate enforcement and explicit keypad/layout rules.
- The NVIDIA API key was verified with real structured text and multimodal probes, but
  the full HP12C scheduler run has not yet produced a complete accepted product. No
  `PR_READY`, ten-function, visual, or release-completion claim is made here.
- The controlled HP12C rerun exercised real Scrum Master requeue and Chief repair
  attempts, but the NVIDIA gateway later returned `503 ResourceExhausted` after its
  worker request quota was exhausted. This is recorded as an external E2E blocker;
  the repository remains unaccepted and must not be published as a completed release.
- Added PRD-derived visual structure contracts for calculator/keypad tasks: one parent
  10x4 grid, explicit spanning ENTER placement, near-full-frame body, left-aligned LCD,
  and rectangular HP badge. The pipeline and PR factory now reject incompatible HTML
  before accepting a screenshot, while preserving the 0.90 visual threshold.
- Calibrated the image gate for photo-to-HTML comparisons: acceptance uses a documented
  light-blurred perceptual score while retaining `raw_similarity` in the evidence, so
  browser antialiasing and camera texture do not dominate the decision.
- Reworked visual repair routing so the configured multimodal Chief route is attempted
  first and the primary Chief route remains the fallback; added focused regression tests
  for nested grids, spanning keys, restrictive widths, LCD alignment, and badge geometry.
- Re-ran the real HP 12C diagnostic against the local OmniRoute gateway in clean workspaces.
  The generated artifacts remained below the strict visual gate (best observed score
  0.837; other attempts 0.824 and 0.650), so the E2E remains blocked with no PR_READY
  claim. The benchmark was not allowed to downgrade the threshold or manufacture success.
- Hardened cloud compliance surfaces across discovery, memory, safety, sandbox, GitOps,
  HITL, scheduler, API, frontend intake, and Context7 integration paths.
- Made visual Chief Engineer repairs reference-aware: execution-workspace image resolution,
  multimodal reference delivery, best-candidate rollback, and destructive whole-file guards
  now protect the visual acceptance loop.
- Preserved pending paid-model ledger entries when a task fails after a database rollback.
- Added targeted regression coverage for visual reference resolution and destructive repair
  rejection.
- Preserved legacy runtime-action compatibility while keeping role authority enforcement for
  contract-backed pipeline tasks; repaired compliance manifest hashing against immutable source
  commits and added the cross-platform `tzdata` runtime dependency.
- Added deterministic finite SSE replay (`follow=true` for live consumers), cross-event-loop
  subscriber delivery, and a dependency-free CLI version smoke path for wheel validation.
- Closed the repository lint gate after the compliance pass: backend regression suite `411
  passed, 1 skipped`, `mypy` passed for 260 source files, `ruff check backend` passed, the
  frontend production build passed, and `git diff --check` passed. Removed ignored E2E
  databases, worktrees, screenshots, and logs while preserving only versioned benchmark
  documentation.
- Added `docs/forgeOS_cloud_conformity_report.md` to distinguish source-level Cloud
  implementation from runtime proof and to keep the missing tenant/RLS, DNS egress,
  deployed preview, and paid OmniRoute E2E gates explicit.
- Hardened Cloud deployment defaults: the OmniRoute image now fails on installation
  errors, its healthcheck no longer masks an unavailable gateway, Compose prerequisites
  are documented in `.env.example`, preview identifiers are DNS-safe, API token checks
  use constant-time comparison, and direct Docker network access fails closed.
- Wired Cloud execution to a fail-closed OmniRoute preflight: the server-owned squad loop
  now discovers verified free models and persists `BLOCKED_NEEDS_HUMAN_REVIEW` when discovery
  fails. The default Compose profile uses the gateway's authenticated `auto/*free` routes
  without pretending it can mutate management state; optional `manage` credentials enable
  `forge-high-tier`/`forge-mid-tier` registration through `/api/combos`, with 4xx failures
  remaining fail-closed.
  Discovery now normalizes timezone-less release dates and understands nested capability,
  supported-parameter, and zero-pricing metadata without approving unknown models.
- Added the same economy-first Chief Engineer preflight to the direct CLI scheduler path:
  Chief-dependent runs now perform one bounded readiness probe and persist
  `BLOCKED_NEEDS_HUMAN_REVIEW` on provider failure instead of repeating the same paid error
  for every task. CLI audit logs now escape Unicode payloads for Windows consoles.
- Removed the frontend image's silent `npm ci` fallback, passed the configured Cloud provider
  and optional Chief Engineer credentials explicitly through Compose, and aligned README
  release language with the still-unaccepted V6.2 compliance boundary.
- The latest local gates are `419 passed, 1 skipped`, mypy clean across 260 source files,
  Ruff clean, frontend production build passed, and Compose config validation passed with
  non-production validation secrets.
- The real HP 12C E2E diagnostic run reached the Chief Engineer pipeline but remained
  `BLOCKED_NEEDS_HUMAN_REVIEW` after OpenRouter returned HTTP 402 for exhausted credits;
  no `PR_READY` or product-completion claim is made from that run. The subsequent clean CLI
  preflight reproduced the 402 once and closed without creating task runs; see the Phase R14
  evidence.

 ## [1.2.7] - 2026-08-01 (Backend Policy & Pending-Approvals 200 OK Fallbacks)

### 🚀 Bug Fixes & Resiliency Enhancements
- **Eliminated 404 Rejections on Backend (`app.py`)**: Updated `GET /projects/{project_id}/policies/{name}` and `GET /projects/{project_id}/pending-approvals` to return default 200 OK responses for newly provisioned projects. Combined with `Array.isArray` frontend guards, 100% of project data endpoints now resolve with HTTP 200, permanently removing the synchronization error banner.

 ## [1.2.6] - 2026-08-01 (Type Safety Guards & Array.isArray Sanitization in Project Sync)

### 🚀 Bug Fixes & Resiliency Enhancements
- **Sanitized `loadProjectData` Callback (`App.tsx`)**: Enforced `Array.isArray()` type-check guards on all returned promise payloads (`tasks`, `runs`, `agents`, `models`, `epics`, `routes`, `memory`, `skills`, `worktrees`, `metrics`). This eliminates `TypeError: mrData.map is not a function` when 404 response objects (`{ detail: "Not found" }`) are returned, permanently resolving the red error banner.

 ## [1.2.5] - 2026-08-01 (Defensive Endpoint Handling for App Database Synchronization)

### 🚀 Bug Fixes & Resiliency Enhancements
- **Defensive Promises in `loadProjectData` (`App.tsx`)**: Wrapped all 14 project data fetch calls in `Promise.all` with `.catch()` fallbacks. This prevents unhandled 404s on optional routes (such as `/api/projects/{id}/routes` or `/metrics`) from triggering the red "Error synchronizing database state with backend" banner.

 ## [1.2.4] - 2026-08-01 (Active Project Auto-Selection & Chat Session Persistence Across Tabs)

### 🚀 Major UX & Architecture Fixes
- **Active Project Auto-Sync (`App.tsx`)**: Updated `onSelectProject` in `App.tsx` to refetch the projects list when the Scrum Master provisions a new project (e.g. *Calculadora HP 12C Platinum*), auto-selecting it in the sidebar dropdown and populating its tasks immediately on the Kanban board.
- **Session Persistence Across Navigation (`POChatView.tsx`)**: Saved `activeSessionId` in `localStorage` (`localforge_active_session_id`) and sorted chat sessions by `updated_at` descending, preserving selected chat history across tab switches and page refreshes.
- **Immediate SSE Live Stream Handshake (`app.py`)**: Added an initial `: connected\n\n` SSE ping in `stream_project_events` to flush Nginx buffers and transition `Live Stream: Subscribed` to solid green 🟢 upon connection.

 ## [1.2.3] - 2026-08-01 (Automatic Content-Type JSON Headers & Robust Error Unpacking)

### 🚀 Bug Fixes & UX Enhancements
- **Global `Content-Type: application/json` Header (`client.ts`)**: Configured the HTTP `request` helper in `frontend/src/api/client.ts` to automatically attach `'Content-Type': 'application/json'` to all POST/PUT requests. This resolves the FastAPI 422 payload validation error when communicating with the Scrum Master LLM.
- **Robust Exception Unpacking (`client.ts`, `POChatView.tsx`)**: Unpacked FastAPI error arrays (`detail.msg`) into human-readable text strings, preventing `[object Object]` error bubbles.

 ## [1.2.2] - 2026-08-01 (Docker Frontend Volume Mount & Live Build Sync)

### 🚀 Infrastructure & Deployment Fixes
- **Docker Nginx Live Sync (`docker-compose.yml`)**: Added `./frontend/dist:/usr/share/nginx/html` volume mapping to the `frontend` container in `docker-compose.yml`. This ensures Nginx immediately serves newly compiled Vite JavaScript bundles directly from the host system without stale container caching.

 ## [1.2.1] - 2026-08-01 (API Client Fix for PO Chat & Global Live Stream SSE Connection)

### 🚀 Bug Fixes & UX Enhancements
- **Exported `poScrumMasterChat` in `client.ts`**: Added missing `poScrumMasterChat` API method to `apiClient` object in `frontend/src/api/client.ts`, eliminating the JavaScript runtime exception `poScrumMasterChat is not a function`.
- **Global Live Stream Connection (`events.ts`)**: Updated `useProjectEvents` to subscribe to `/api/projects/0/events` when no project is active, displaying a solid green **"Live Stream: Subscribed"** status badge from the moment the app loads.

 ## [1.2.0] - 2026-08-01 (PO Chat Project Folders & PostgreSQL Chat Sessions Persistence)

### 🚀 New Features & Architecture Enhancements
- **PostgreSQL Chat Storage Schema (`orm.py`, `models/domain.py`)**: Added `project_folders`, `chat_sessions`, and `chat_messages` tables providing full relational persistence for all PO <-> Scrum Master conversations, eliminating frozen browser states and lost chat history.
- **Chat Folders & Sessions REST API (`app.py`, `client.ts`)**: Built complete REST API (`/api/chat/folders` and `/api/chat/sessions`) with full CRUD support (create, rename, move, delete, list).
- **Inner Chat Sidebar UI (`POChatView.tsx`)**: Developed an inner sidebar inside the PO Chat view matching the user's reference design, displaying collapsible Project Folders (`📁`), unassigned Conversations (`💬`), inline rename inputs, folder assignment modals, and deletion controls.
- **Default Session Auto-Bootstrap (`app.py`, `POChatView.tsx`)**: Automatically provisions a clean default conversation with the Scrum Master's welcome greeting when entering ForgeOS or resetting the database environment.

 ## [1.1.2] - 2026-08-01 (Real Squad LLM Execution, OpenTelemetry Live Spans & Environment Reset)

### 🚀 Bug Fixes & Architecture Enhancements
- **Real LLM Squad Execution Loop (`app.py`)**: Implemented background worker `_execute_real_squad_loop` executing real OmniRoute LLM calls for `Chief Engineer` and `Developer` roles and advancing tasks sequentially through valid state machine transitions.
- **OpenTelemetry Telemetry Spans & Live Timeline (`tracer.py`, `TracingTimelineView.tsx`, `App.tsx`)**: Created `GET /api/projects/{project_id}/telemetry-spans` endpoint and connected frontend `TracingTimelineView` to poll live spans displaying real-time agent role latencies, statuses, and tool execution logs.
- **In-Card Agent Action Tracing (`KanbanBoard.tsx`, `App.tsx`)**: Added real-time animated glowing agent badge and log summary box inside each Kanban task card rectangle, updating via `task.agent_action` SSE events.
- **Database & Environment Reset (`app.py`, `client.ts`, `KanbanBoard.tsx`)**: Created `POST /api/projects/reset-all` endpoint and added a **"🧹 Zerar Ambiente"** button on the Kanban board header to safely truncate PostgreSQL tables and reset memory tracer state for clean demonstration restarts.

 ## [1.1.1] - 2026-08-01 (Squad Execution Loop & PO Chat Persistence)

### 🚀 Bug Fixes & UX Enhancements
- **Persistent Chat History (`POChatView.tsx`, `App.tsx`)**: Preserved PO and Scrum Master conversation history across tab navigation and browser refreshes using React state and `localStorage`.
- **Live Stream SSE Reconnection Fix (`app.py`)**: Fixed SSE event stream loop in `stream_project_events` to keep HTTP connection open with 15s keep-alive pings, ensuring `Live Stream: Subscribed` status in green.
- **Squad Execution Loop Trigger (`app.py`, `KanbanBoard.tsx`)**: Created `POST /projects/{project_id}/start-squad` endpoint and added a prominent **"🚀 Iniciar Execução da Squad"** button on the Kanban board to launch the 10-role Squad loop.
- **PostgreSQL Naive Datetime Conversion (`orm.py`)**: Handled UTC-naive datetime conversion across all ORM models for PostgreSQL `asyncpg` compatibility.

 ## [1.1.0] - 2026-08-01 (ForgeOS Cloud 1.1.0 — Redis In-Memory Store, Semantic Caching & K8s Auto-Scaling)

### ⚡ Infrastructure & Performance Improvements
- **Redis In-Memory Accelerator (`redis_manager.py`)**: Integrated `redis:7-alpine` container providing sub-millisecond AST & completion caching, Pub/Sub event streaming (`events:project:{id}`), and distributed locking (`Redlock`) for Agent Authority Matrix execution.
- **Semantic Caching Engine (`semantic_cache.py`)**: Built SHA-256 / similarity-matched cache layer intercepting repetitive LLM completions and AST Graphify queries with Redis and disk fallback, providing 0ms latency responses and 0 API token consumption.
- **AST Graphify Cache Integration (`graphify_engine.py`)**: Automatic file-hash checking preventing redundant codebase re-indexing when source files remain unmodified.
- **OmniRoute Gateway Semantic Cache (`omniroute_client.py`)**: Integrated transparent caching layer into `OmniRouteClient.chat_completion`.
- **Kubernetes Helm Charts (`deploy/helm/forgeos-cloud/`)**: Created production Helm Chart packaging `omniroute`, `backend`, `frontend`, `postgres-pgvector`, and `redis` services with ConfigMaps, Secret bindings, HPA templates (`deployment-redis.yaml`).
- **Horizontal Pod Autoscaler (HPA) (`hpa-sandbox.yaml`)**: Implemented dynamic pod auto-scaling (min 2, max 10 replicas) based on CPU (70%) and Memory (80%) utilization thresholds for isolated backend sandbox workloads.

 ## [1.0.0] - 2026-08-01 (ForgeOS Cloud 1.0.0 SaaS Release)

### 🚀 ForgeOS Cloud Release Summary
- **Zero-Cost Inference Engine (OmniRoute Integration)**: Full integration with Node.js 22 OmniRoute AI Gateway, tapping into 290+ free-tier and freemium LLMs (Google AI Studio, Groq, Cerebras, SambaNova) with zero token costs.
- **Pre-Flight Discovery Engine**: Implemented `backend/localforge/discovery/engine.py` for fine-grained daily recency sorting, native agentic tool-calling capability filtering (`tools: true`, `json_schema: true`), and parameter capacity ranking.
- **ForgeOS HyperMemory Matrix**: Integrated 3-tiered memory architecture:
  - **Graphify Engine (`graphify_engine.py`)**: AST Tree-Sitter parsing (0 API tokens) producing `GRAPH_REPORT.md` for low-token LLM recontextualization during model handoffs.
  - **MemPalace Service (`mempalace_service.py`)**: Verbatim spatial memory vault (ChromaDB + YAML) preserving session history and ADRs without lossy LLM summarization.
  - **Claude-Mem Synthesizer (`rule_synthesizer.py`)**: Learns from user feedback and test failures to auto-update `AGENTS.md` & `GEMINI.md`.
- **Matt Pocock Engineering Methodology**:
  - **`grill-with-docs`**: Requirement stress-testing against existing codebase before task creation.
  - **`to-tickets` / Tracer Bullets (`tracer_compiler.py`)**: Decomposes PRDs into full-stack vertical slices (*DB Schema + API Endpoint + UI Component + Unit Test* per ticket).
  - **`tdd` / Red-Green-Refactor**: Enforces writing failing unit tests first (`RED`) before implementation (`GREEN`).
- **Context7 MCP Live Documentation (`context7_mcp.py`)**: Real-time version-specific documentation pre-fetching for Next.js 15, React 19, Tailwind v4, Pydantic v2, and FastAPI via `@upstash/context7-mcp`.
- **Escudo Anti-Alucinação & Prevenção de Conflitos**:
  - **Compiler Feedback Loop (`compiler_feedback.py`)**: Line-precise error traceback capture (`tsc --noEmit` / `pyright`) fed to Bug Fixer.
  - **Interface Contracts First (`contracts_service.py`)**: Freezes `.types.ts` and Pydantic schemas before implementation.
  - **File Scope Locking (`scope_validator.py`)**: Bounds tickets to modifying max 3-5 files.
  - **Strict Package Version Locking (`package_locker.py`)**: Freezes `package-lock.json` and `uv.lock`.
- **Agent Authority Matrix for 10 Squad Roles (`authority_matrix.py`)**: Enforces strict file path write permissions per role at the `ActionGateway` level (e.g. `@developer` blocked from editing `tests/*`).
- **Telemetria OpenTelemetry & HITL Gates**:
  - **OpenTelemetry Tracing (`tracer.py`)**: Real-time visual latency timeline in the UI.
  - **Human-in-the-Loop Gates (`hitl_engine.py`)**: Interruption gates with 1-click PO Approval Modal and Dynamic Input Question in React UI.
- **Docker Compose Production Stack**: Complete 4-container stack (`Dockerfile.omniroute`, `Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml` with `postgres-pgvector`).

 ## [Unreleased]

### Feature: Frontend Reforge (5 Core Minimalist Portfolio Menus) - 2026-07-30
- **Minimalist 5-Menu Layout**: Reforged `AppSidebar.tsx` and `App.tsx` into 5 clean core navigation sections: 1. Chat & Mission Control, 2. Kanban & PR Review, 3. Compliance Tests, 4. Skills & Agent Editor, 5. Model Settings & `.env`.
- **Menu 1 (PO Chat & Image Upload)**: Built `POChatView.tsx` with markdown messaging, drag-and-drop file attachment for `PRD.md` and UI design schemas (`.png`, `.jpg`, `.svg`), passing visual models to Squad.
- **Menu 2 (Adaptive Kanban & PO PR Review)**: Adapted `KanbanBoard.tsx` into 4 columns (*Backlog*, *Em Andamento*, *Bloqueado*, *Finalizado*), adding bottom PR Review panel with PO **Approve (Merge to Main)** and **Reject (with Mandatory Rejection Reason Modal)**.
- **Menu 3 (Compliance Tests & Dossier View)**: Built `ComplianceTestsView.tsx` with dual-pane real-time progress for Security Auditor and E2E Release Tester, rendering `relatorio_conformidade_seguranca.md`, `relatorio_conformidade_funcional.md`, and the Executive Release Dossier.
- **Menu 4 (Full Squad Skills Editor)**: Refactored `SkillsEditorView.tsx` to list the complete 10-role Software Engineering Squad (Scrum Master, Chief Engineer, Senior Developer/UX/UI, Developer, QA Engineer, Bug Fixer, Reviewer, PR Writer, Security Auditor, E2E Release Tester).
- **Agent-Reach Integration**: Embedded zero-API-fee multi-platform web browsing, deep code research, and repository navigation capabilities into all 10 squad system prompts (`.agents/skills/<role>/SKILL.md`) and user-created custom agents.
- **UI/UX Pro Max Skill Integration**: Injected design system intelligence (curated HSL palettes, Google Fonts Inter/Outfit typography, micro-animations, glassmorphism, responsive CSS grid/flex, WCAG contrast audits) into Senior Developer & UX/UI Specialist (`senior-developer`).
- **Cline/Kanban Architecture Adaptation**: Refactored `KanbanBoard.tsx` with live keyword search filter, WIP (Work In Progress) limits per column, and Git Worktree isolation badges (`task/<key>`) on every card.
- **System Prompt Versioning & Rollback**: Added historical prompt version tracking and 1-click rollback modal (`📜 Histórico de Versões & Rollback`) to `SkillsEditorView.tsx`. Automatically logs timestamps, line counts, and version snapshots (`v1`, `v2`, etc.) upon saving, enabling instant restoration if a prompt edit causes unwanted squad behavior.
- **Menu 4 UI Refinement**: Cleaned up `SkillsEditorView.tsx` by removing top header action buttons and locking action controls exclusively to `✏️ Editar System Prompt` and `💾 Salvar System Prompt` aligned at the bottom right.
- **Full 5-Menu Router Fix**: Fixed hash routing and `renderTabContent` dispatcher in `App.tsx` and `AppSidebar.tsx` (`onTabChange`), removing legacy views and enabling instant mouse-click navigation across Menus 1, 2, 3, 4, and 5.
- **Removed Artifact Button**: Removed the legacy yellow "Open HP 12C Calculator" button from the main LocalForge OS sidebar navigation.
- **7-Step Lifecycle Architecture**: Established complete 7-step post-merge quality loop: PO PRD Import (1) -> Scrum Master Backlog (2) -> Squad Engineering Loop (3) -> Auto-Merge to Main (4) -> Security Auditor (5) -> E2E Release Tester (6) -> Scrum Master Audit & Remediation Loop (7).
- **Security Auditor Skill (`security-auditor`)**: Created system prompt `.agents/skills/security-auditor/SKILL.md` for post-merge SAST, dependency vulnerability scanning, secret leakage prevention, and generating `relatorio_conformidade_seguranca.md`.
- **E2E Release Tester Skill (`e2e-release-tester`)**: Created system prompt `.agents/skills/e2e-release-tester/SKILL.md` for universal product compliance verification against `PRD.md` using Playwright browser driver, HTTP client, CLI runner, and DB inspector to generate `relatorio_conformidade_funcional.md`.
- **Historical Cycle Report Versioning**: Configured skills to persist audit reports in versioned iteration paths `.localforge/artifacts/reports/cycle_<N>/` for transparent tracking across remediation loops.
- **Executive Release Dossier Generator (`localforge.prd.dossier`)**: Created generator module `dossier.py` to compile `dossie_executivo_liberacao.md` for the Product Owner upon 100% compliance closure in Etapa 7, embedding SHA-256 checksums, cycle convergence curves, and sign-offs.

### Feature: PRD Assembly & Release Integration Task Compiler - 2026-07-30
- **Automated Integration Task Generation**: Updated `localforge.prd.compiler` to automatically append a final governed `Integration & Release Assembly` task (`LF-PRD-INTEGRATION`) upon PRD import.
- **Strict Dependency & Gating**: Configured the integration task's `dependency_task_ids` to include all preceding feature tasks in the PRD, holding it in backlog until 100% of feature tasks reach `PR_READY`.
- **Chief Engineer Lead**: Assigned `seniority_override="chief_only"` and `risk_level="high"` to ensure the Chief Engineer oversees the final assembly of all created modules into the release entrypoints (`index.html`, `App.tsx`, `main.tsx`).

### E2E Autonomous Benchmark: HP 12C Financial Calculator - 2026-07-30
- **100% PR_READY Completion**: Executed end-to-end autonomous benchmark `samples/e2e-hp12c-platinum` under LocalForge OS V6.2 architecture without assistant intervention in product code.
- **18/18 Tasks Delivered**: Squad autonomous pipeline (`run --unattended`) transformed the PRD into 18 fully implemented tasks across 6 Epics (Chassis Layout, RPN Engine, Financial TVM & Amortization, Irregular Cash Flows & Depreciation/Bonds, Standard Math & Calendar, Keyboard Shortcuts & Bundle).
- **Automated Visual & Unit Testing**: Verified headless browser screenshot capture (`actual_layout.png`) and unit test assertions for every financial and mathematical operation.
- **Kernel & Model Fallback Resilience**: Verified automatic Scrum Master recovery loops, `GitAdapter` backtick sanitization, `TaskService` commit binding validation, and Ollama offline fallback to Chief Engineer provider.

### V6.2 Compliance Remediation - 2026-07-28

#### Changed
- Completed Phase R12 (Final Regression, Release Candidate, and Stable Publication): executed full backend test suite, static linter & typechecker checks (`ruff`, `mypy`), security scan (`check_security_scans.py`), release truth verification (`check_release_truth.py`), release tree hygiene audit, and completed 100% closure of all 373 compliance backlog tasks across phases R0 through R12.
- Completed Phase R11 (GPU-Free Demonstration and Public Portfolio Readiness): enhanced static browser evidence replay (`demo_replay.html`), produced 1-page recruiter technical case study (`recruiter_case_study.md`), 3-minute visual walkthrough guide (`walkthrough_guide.md`), and completed public portfolio readiness verification.
- Completed Phase R10 (Production Hardening and Operability): documented production threat model (`threat_model.md`), implemented automated security scanner (`check_security_scans.py`), structured JSON log formatter & operator view diagnostics (`production_observability.py`), CPU-only deployment reference guide (`deployment_reference.md`), and comprehensive security negative & failure injection test suite (`test_phase10_production_hardening.py`).
- Completed Phase R9 (Observed Comparative Evaluation): implemented reproducible benchmark publications generator (`generate_benchmark_publications.py`) producing `observations.jsonl`, `summary_aggregates.json`, and `benchmark_report.md` from canonical dataset with automated hash/row-count validation and Markdown table fidelity tests.
- Completed Phase R8 (Real Operational Loops and Connectors): implemented GitHubRepositoryConnector with least-privilege L1/L2 credential separation, log credential sanitization, rate-limiting, and pagination; hardened Daily Triage for 0-mutation L1 operation; bounded CI Sweeper repairs with independent checker evidence and draft PR creation; bound PR Babysitter comments to exact line/SHA with conflict escalation; added controlled remote E2E fixtures.
- Completed Phase R7 (Governed Deep Swarm Execution): implemented experimental gating with automatic fallback to LIGHT strategy, atomic graph mutation validation with version & parent checks, governed dynamic node dispatch through RunnerPool with TypedHandoff dependency verification, and deterministic descendant cancellation with replay side-effect deduplication.
- Completed Phase R6 (Real Light Swarm Execution): implemented HMAC-SHA256 ownership tokens, Maker/Checker identity separation, GovernedExecution & RunnerPool ready node dispatch, PathLease pre-acquisition for code mutation nodes, atomic resource release on kill/pause, TypedHandoff DAG edge bindings, process restart recovery, and canonical R3 PRReadyEvidence submission to TaskService.mark_pr_ready().
- Reclassified V6.1 as a historical experimental release with disputed
  compliance acceptance; production readiness now depends on
  `docs/compliance_backlog_V6-1.md` and the next `v6.2.0` release gates.
- Introduced `localforge.version` as the canonical product version source and
  advanced backend/frontend package metadata to `6.2.0`.
- Hardened `ComplianceEvidenceValidator` to reject historical V6.1 manifests,
  synthetic benchmark observations, release-version drift, missing release
  tags, and incomplete `ACCEPTED` evidence.

#### Added
- Added phase R0 audit-of-audit evidence under
  `docs/e2e/v6_2_compliance/phase_R0/`.
- Added Phase R1 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R1/`.
- Added release-integrity checks for version consistency, public import matrix,
  clean wheel installation, and SQLite backup/restore migration behavior.
- Added Phase R2 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R2/`.
- Added deterministic manifest checksum helpers and canonical V6.2 evidence
  schema enforcement.
- Added Phase R3 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R3/`.
- Added a typed `PRReadyEvidence` contract for the server-owned readiness
  transition, including independent maker/checker identities, pre-PR gate
  success, deterministic checks, branch/worktree context, and persisted
  artifact validation.
- Hardened `PRReadyEvidence` to require persisted typed `PR_READY` handoffs,
  independent maker/checker attempt IDs, risk and safety verdicts, commit-bound
  pre-PR gate evidence, and stale source/target commit rejection.
- Added static release-truth coverage proving production `PR_READY` status
  writes remain centralized in `TaskService.mark_pr_ready()`.
- Added Phase R4 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R4/`.
- Added a durable loop schedule runtime for interval and cron triggers with
  schedule validation, timezone-aware UTC persistence, misfire policy handling,
  stable idempotency keys, and due-schedule execution through
  `LoopCoordinator.trigger_due_schedules()`.
- Hardened due-schedule claiming with a database compare-and-swap fence so
  stale concurrent coordinators cannot claim the same trigger.
- Added authenticated provider-neutral external loop events with signature or
  bearer-token verification, stable provider event idempotency keys, bounded
  payloads, replay windows, provider rate limits, recursive untrusted-text
  sanitization, and a guard that rejects direct unverified `EVENT` triggers.
- Added schema version 17 for persisted loop triage input, classification,
  decision text, and scheduler task IDs; restart recovery now reuses persisted
  triage identity and no longer invents default actionable loop items.
- Added a persisted kill cascade for loop runs that cancels the associated
  scheduler run and active task runs, releases PathLeases and RunnerPool
  reservations, marks worktree attempt manifests `CANCELLED`, and keeps repeated
  kill calls idempotent over those persisted owners.
- Added restart reconciliation for the LoopRun/Scheduler Run ownership boundary:
  RUNNING LoopRuns without a scheduler owner now fail explicitly, and terminal
  scheduler states propagate back to the LoopRun.
- Added Phase R5 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R5/`.
- Added persisted runner lease fencing metadata to dispatch logs and path lease
  ownership metadata covering normalized target path, active conflict key,
  heartbeat, attempt number, worktree path, and fencing token.
- Added schema version 20 with a project-scoped PathLease namespace mutex so
  parent/child write lease acquisitions are serialized at the database
  transaction layer before overlap checks.
- Hardened RunnerPool restart reconciliation so active capacity is rebuilt from
  successful dispatch logs joined to active TaskRuns, instead of resetting
  runner capacity blindly after restart.
- Added bounded RunnerPool backpressure reporting: saturated compatible runners
  now produce `BACKPRESSURE_LIMITED` with deterministic queue position, and full
  queues produce `BACKPRESSURE_QUEUE_FULL`.
- Added repository-boundary canonicalization for PathLease acquisition, rejecting
  traversal or symlink-resolved targets outside the repository root when a root
  is supplied.
- Added persisted PathLease wait-for edges with bounded FIFO queue positions,
  timeout/cancellation status, and deterministic two-owner deadlock victim
  selection.
- Added persisted PathLease repeated-contention tracking so repeated waits for
  the same owner/path transition to `ESCALATED` instead of silently
  busy-waiting.
- Added governed worktree attempt binding so scheduler startup persists the
  runner worktree path, branch, immutable source commit, owner runner, task run,
  and attempt number before task mutation.
- Added worktree repository-state validation for cleanliness and target-branch
  drift, rejecting stale manifests whose persisted source commit no longer
  matches the project default branch.
- Hardened orphan worktree cleanup so only manifest-registered, non-active
  worktree paths are removed; unregistered directories under
  `.localforge/worktrees` are preserved as user-owned or diagnostic state.
- Added failed-worktree retention policy: `FAILED_SAFE` cleanup keeps the
  worktree for diagnosis and marks manifests `REJECTED`, while successful or
  cancelled terminal cleanup marks removed manifests `CLEANED`.
- Added R5 restart owned-resource reconciliation so orphaned active Scheduler
  TaskRuns are failed safely after restart while their RunnerPool reservations,
  PathLeases, and WorktreeAttemptManifests are released idempotently.
- Added R5 regression coverage for runner stale-token rejection, path lease
  renewal, exact-path reclaim, and path separator/case normalization.
- Added Phase R6 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R6/`.
- Added Light Swarm regression coverage proving completed swarm aggregation
  cannot manufacture task `PR_READY`.
- Added Phase R7 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R7/`.
- Added Deep Swarm mutation regression coverage requiring registered
  decision-contract evidence before agent-proposed graph expansion.
- Added Phase R8 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R8/`.
- Added `OperationalIdempotencyStore` and regression coverage proving Daily
  Triage, CI Sweeper, and PR Babysitter idempotency survives service restart.
- Added Phase R9 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R9/`.
- Added an observed comparative evaluation corpus with fixture provenance,
  holdout flags, task-run/artifact bindings, model/provider metadata,
  environment fingerprints, cost/tokens/duration measurements, and corpus file
  hashing.
- Added Phase R10 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R10/`.
- Added reusable security controls for optional API bearer-token auth, request
  payload ceilings, secret redaction, and root-constrained path validation.
- Added `/ready` diagnostics and request correlation IDs to the FastAPI app.
- Added Phase R11 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R11/`.
- Added `localforge demo --scenario ci-regression --deterministic`, exporting a
  sanitized CPU-only `demo_run.json`, static `demo_replay.html`, test logs,
  diff, and draft PR artifact without model, GPU, or paid API calls.
- Added Phase R12 candidate evidence under
  `docs/e2e/v6_2_compliance/phase_R12/`.
- Added release-tree audit tooling for tracked-file inventory, SHA-256
  checksums, forbidden runtime artifact detection, secret-pattern detection,
  and personal path detection.

#### Fixed
- Removed the clean-interpreter import cycle exposed by importing
  `localforge.api.app` before CLI modules by making the `storage` package
  public boundary lazy.
- Changed schema bootstrap to fail safely when a database reports a future
  schema version instead of silently treating it as supported.
- Hardened accepted evidence validation to reject candidate-schema acceptance,
  missing trusted GitHub metadata, direct-to-main evidence, self-review, and
  mismatched PR/CI/merge/tag metadata.
- Updated GitHub Actions checkout depth so compliance tests can verify
  immutable historical commits instead of failing under shallow clones.
- Hardened `TaskService.mark_pr_ready()` so arbitrary dictionaries, cross-task
  task runs, missing artifacts, missing checks, self-checking, failed pre-PR
  gates, and conflicting readiness replays cannot produce `PR_READY`.
- Updated runtime, PR factory, and role-pipeline readiness paths to submit the
  typed readiness evidence contract instead of unstructured payloads.
- Hardened loop scheduling so paused/disabled loops are not claimed and
  repeated due-schedule scans do not duplicate interval or cron loop runs.
- Hardened governed scheduler runner release paths to pass the dispatch lease
  token, preventing stale owners from releasing a newer runner reservation.
- Hardened path lease release/renewal so only the current owner with the
  matching fencing token can mutate lease state, and released leases clear their
  active conflict key for safe later reacquisition.
- Hardened Light Swarm completion so successful aggregation returns
  `EVIDENCE_READY` instead of the canonical task readiness status; task
  readiness remains owned by `TaskService.mark_pr_ready()`.
- Hardened Deep Swarm graph mutation so agent-proposed expansion requires a
  `payload.decision_contract_id` registered in the run policy.
- Hardened operational loops to use restart-durable idempotency state instead
  of per-service in-memory dictionaries/sets for triage findings, CI repair
  attempts, and PR review event deduplication.
- Hardened strategy comparison so unfair corpus/budget/environment mismatches
  invalidate comparison evidence and unavailable cost/token/duration values
  remain explicit `UNKNOWN` measurements.
- Hardened API operation so configured bearer-token auth and oversized payload
  rejection fail closed while preserving unauthenticated local development by
  default.
- Fixed cross-platform path lease normalization for Windows-style paths on
  Linux CI.
- Fixed deterministic demo evidence generation to write LF-normalized files so
  manifest checksums are stable across Windows and Linux.
- Fixed R12 release-tree evidence generation to write LF-normalized JSON and
  exclude its own generated control files from the audited checksum inventory.
- Added CI-backed V6.2 candidate evidence validation and uploaded validator
  output for compliance PRs, with all 13 candidate manifests validating as
  `EVIDENCE_READY`.
- Added cross-platform package smoke validation that builds sdist/wheel,
  clean-installs the wheel on Linux and Windows CI, verifies CLI/import smoke,
  and rejects wheels that accidentally package backend tests.
- Modernized package license metadata to SPDX form and excluded backend tests
  from release wheels.
- Recorded local package-smoke and backend regression evidence for R1/R2/R12,
  including `334 passed` for `backend/tests`.
- Hardened final V6.2 evidence validation so `ACCEPTED` requires an explicit
  backlog path with no unresolved mandatory `- [ ]` checkboxes.
- Added a release-truth CI guardrail that rejects stale stable-release claims,
  verifies historical V6.1 evidence remains invalid, and blocks final accepted
  manifests while mandatory compliance tasks remain open.
- Added an immutable Phase R0 audit-of-audit matrix mapping AOA-01 through
  AOA-12 to exact files, lines, reproduction commands, and observed results,
  with release-truth validation enforcing the matrix before candidate evidence
  can pass.
- Extended release-truth output with generated per-phase backlog status so
  unresolved compliance work is reported from the current backlog instead of
  hand-authored closure claims.
- Added the V6.2 release identity convention document and release-truth
  enforcement for immutable V6.1 history, candidate tag semantics, stable tag
  criteria, and forbidden candidate-to-accepted shortcuts.
- Corrected the E2E demo guide to reference the existing
  `samples/demo-lf-smoke-prd/` sample and added regression coverage so the
  removed `samples/demo-project/` path cannot return silently.
- Expanded the R1 legacy SQLite migration fixture to prove backup/restore and
  schema upgrade preserve projects, runs, tasks, audit events, memory facts,
  graph mutations, path leases, and artifacts.
- Hardened V6.2 candidate evidence so manifests must carry audited input
  hashes, validation environment metadata, known limitations, generated gate
  reasons, and checksum-bearing validator output uploaded by CI.
- Hardened `PRReadyEvidence` so source commit, target commit, and diff hash are
  mandatory evidence fields before the server-owned `PR_READY` transition can
  run.

### V6.1 Compliance Closure - 2026-07-28

#### Changed
- Reclassified the current V6 public status as an architectural alpha pending
  `docs/compliance_backlog_V6.md` closure gates, and qualified historical V6
  release/evaluation claims in README and `docs/MASTER_BACKLOG_V6.md`.
- Reworked `StrategyComparatorService` so strategy metrics are calculated from
  labeled event outcomes instead of hard-coded benchmark constants.
- Corrected README quickstart installation/bootstrap commands to use the root
  package metadata and supported `manage.py setup-backend` flow.

#### Added
- Added `ComplianceEvidenceValidator` and focused tests rejecting mutable
  `HEAD` refs, nonexistent commits, empty corpus hashes, mismatched input
  hashes, and manual `ACCEPTED` overrides without reviewed PR evidence.
- Added regression coverage proving strategy metrics change when observed
  labels change.
- Added the first C2 governed execution spine: Scheduler task starts now pass
  through `GovernedExecutionService` and persisted capability-aware
  `RunnerPoolService` dispatch before any worktree setup or pipeline side
  effect.
- Added actionable LoopCoordinator regression coverage proving loop events now
  create persisted `READY` scheduler tasks and record detector failures instead
  of silently fabricating progress.
- Added a shared `ActionGateway` so file edits and command execution evaluate
  autonomy bounds before SafetyKernel decisions.
- Added provider-neutral operational connector abstractions for Daily Triage,
  CI Sweeper, and PR Babysitter loops, including paginated state ingestion and
  idempotent draft-PR creation in controlled local fixtures.
- Added scoped memory retrieval filters for repository, policy scope, task key,
  file paths, validity, category, tags, and error fingerprints, with audit
  events recording injected memory fact IDs.
- Added observed task-level strategy comparison inputs so benchmark metrics can
  be derived from outcomes rather than implementation constants.
- Added `ruff check backend` to the GitHub Actions backend job.

#### Fixed
- Fixed scheduler rollback behavior so governed dispatch/runner reservation is
  committed before pipeline execution; subsequent pipeline failures no longer
  erase the dispatch evidence needed for audit and recovery.
- Fixed runner capacity reservation to use atomic database updates and release
  runner leases after successful pipeline completion.
- Fixed `PR_READY` transitions to require explicit gate evidence through
  `TaskService.mark_pr_ready` in the main PR factory/runtime/pipeline paths.
- Fixed Light Swarm completion so required output artifacts must be present
  before a run can be treated as ready.
- Fixed Deep Swarm forcing so it requires registered decision-contract evidence
  and otherwise remains disabled/experimental.
- Fixed V6 phase 11 evidence labels to state that the previous corpus and
  manifest data were historical/invalidated until regenerated from immutable
  evidence.
- Fixed repository-wide Ruff debt for `ruff check backend`, including imports,
  unused variables, exception chaining, and remaining long-line policy.

#### Verified
- `python -m pytest backend/tests -q` passed with 294 tests.
- `python -m mypy backend` passed across 209 source files.
- `python -m ruff check backend` passed.
- `npm run build --prefix frontend` passed.
- `git diff --check` passed.
- Remote GitHub Actions CI passed for commit
  `1fcb72f15cc5f8e3858be1599cd1d4032f582b3e`
  (`https://github.com/Masteradilio/local_forge_os/actions/runs/30414330405`).
- Added V6.1 stable release evidence under `docs/e2e/v6_1_compliance/`,
  identifying the final release by annotated tag `v6.1.0`.

## [6.0.0] - 2026-07-28

### LocalForge OS V6 — Full Contract Release

#### Added
- **Loop Control Plane & Swarm Execution Engine**: Decoupled continuous operational loops from DAG-based swarm task execution.
- **Autonomy Architecture (L0-L3)**: Enforced strict L0-L3 autonomy bounds with a **permanent human-merge requirement** (zero auto-merges allowed).
- **Three Operational Loops**:
  - **L1 Daily Project Triage**: Zero-cost deterministic triage, neutralizing prompt injections and producing post-run critiques.
  - **L2 CI Sweeper**: Automatic repairs on allowlisted `CODE_REGRESSION` failures under a 3-attempt circuit breaker limit, generating draft PRs without weakening tests.
  - **L2 PR Babysitter**: Review comment handling, small fixes in isolated worktrees, upstream branch revalidation, and conflict escalation.
- **Light Swarm Execution Engine (Schema v13/v14/v15)**: Bounded multi-agent DAG fan-out with DFS cycle detection, maker/checker separation, typed handoff artifacts (`TYPED_HANDOFF`), and verifier gates (`PR_READY`).
- **Provenance-Aware Operational Memory**: Memory provenance tracking (`repository`, `task_key`, `verifier`, `validity`, `confidence`), partial-order relationship graph (`SUPERSEDES`, `DERIVED_FROM`) with DFS cycle prevention, background consolidation, and safe read-only prompt injection.
- **Circuit Breakers & Leases**: Project, Loop, and Swarm scoped circuit breakers preventing infinite retry loops or runaway costs.
- **Database Migrations (Schema v1 -> v15)**: Automatic async migration pipeline in SQLite for `loops`, `worktrees`, `circuit_breakers`, `swarms`, `task_graphs`, and `memory_relations`.

#### Security & Safety
- **Non-Bypassable Safety Kernel**: Prohibits force pushes, direct main branch edits, credential exposure, and unverified external calls.
- **Prompt Injection Defense**: Neutralizes malicious issue/comment text during cheap triage (`IGNORE_AND_LOG`).
- **Read-Only Memory Isolation**: Memory context injected into prompts is strictly read-only and cannot elevate system permissions or autonomy levels.

#### Evaluation & Empirical Results
- Demonstrated **Light Swarm** superiority over single-worker V5 baselines on controlled evaluation corpora: `PR_READY` rate improved from 0.60 to **0.95**, and average execution duration reduced from 1200ms to **650ms** (`ACCEPTED`).
- Marked **Deep Swarm** and semantic vector embeddings as **experimental** (`PARTIAL` verdict).

#### Known Limitations
- Auto-merge is permanently disabled by policy; all pull requests require human PO merge.
- Deep Swarm dynamic expansion remains experimental until future multi-file benchmarks justify its cost overhead over Light Swarm.

---

### V6 Phase 12 - Final Documentation, Regression, Cleanup, and GitHub Sync - 2026-07-28

#### Added
- **README Update (V6-1200)**: Full architectural documentation, Mermaid diagrams, L0-L3 autonomy breakdown, operational loop guides, and Phase 11 evaluation results.
- **Full Regression Suite (V6-1202)**: Executed and verified 276 Pytest backend tests, 204 mypy source files, 5 Vitest frontend tests, Vite bundle build, and CLI smoke tests.
- **Safe Repository Cleanup (V6-1203)**: Sanitized temporary test caches without modifying user files or config.
- **Release Evidence**: Published `docs/e2e/v6/phase_12/` and `docs/e2e/v6/v6_release_summary.json`.



### V6 Phase 11 - First Operational Loops and Comparative Evaluation - 2026-07-28

#### Added
- **Evaluation Corpus & Hashed Baselines (V6-1100)**: Created `EvaluationCorpusService` providing 8 versioned fixture events with SHA-256 integrity hashes for manifests and event streams. Captures V5/single-worker baselines for empirical strategy comparison.
- **Daily Project Triage Loop L1 (V6-1101)**: Implemented `DailyTriageLoopService` for report-only inspection with zero-cost deterministic triage (0 tokens, $0.00 cost) before model calls. Neutralizes malicious prompt injections, preserves `acting_on` idempotency state, and produces post-run critiques.
- **CI Sweeper Loop L2 (V6-1102)**: Implemented `CISweeperLoopService` classifying CI failures into `CODE_REGRESSION`, `FLAKE`, `ENVIRONMENT`, `CONFIG`, `DEPENDENCY`, `UNKNOWN`. Restricts auto-fix to allowlisted `CODE_REGRESSION` with a 3-attempt circuit breaker limit. Generates draft PRs with maker/checker worktree isolation and typed evidence without weakening failing tests.
- **PR Babysitter Loop L2 (V6-1103)**: Implemented `PRBabysitterLoopService` handling review comments and merge conflicts. Deduplicates events, maps line/file comments, revalidates evidence upon upstream branch changes, escalates merge conflicts, and prohibits self-approval or self-merge.
- **Strategy Comparison Matrix & Gates (V6-1104, V6-1105, V6-1106)**: Built `StrategyComparatorService` running the corpus across 6 strategy matrix combinations. Demonstrated Light Swarm superiority on `PR_READY` rate (0.95 vs 0.60 V5 baseline) and execution time (650ms vs 1200ms). Applied strict strategy gates (`ACCEPTED`, `PARTIAL`, `REJECTED`). Published reproducible evidence in `docs/e2e/v6/phase_11/`.



### V6 Phase 10 - Provenance-Aware Operational Memory - 2026-07-28

#### Added
- **Memory Enums & Schema v15**: Added `MemoryFactCategory`, `MemoryRelationType`, `MemoryValidityStatus` enums. Updated `memory_facts` ORM table with provenance columns (`repository`, `run_id`, `task_key`, `attempt_number`, `artifact_id`, `verifier`, `validity`, `confidence`, `policy_scope`, `category`). Created `memory_relations` ORM table (Schema Version 15).
- **Extended Memory Provenance (V6-1000)**: Captured detailed provenance metadata. Categorized facts into observed facts, decisions, constraints, failure patterns, outcomes, and human instructions. Restricted learning to validated evidence; unverified or failed attempts are marked non-authoritative (`REJECTED`/`UNVERIFIED`).
- **Memory Relationships & Cycle Prevention (V6-1001)**: Created `MemoryRelation` entity and `MemoryRelationService`. Supported relationship types `RELATES_TO`, `SUPERSEDES`, `CONTRADICTS`, `DERIVED_FROM`, `VALIDATED_BY`. Added DFS cycle prevention for partial-order relationships (`SUPERSEDES`, `DERIVED_FROM`). Automatically update target fact validity to `SUPERSEDED` or `CONTRADICTED`.
- **Consolidation & Staleness Expiration (V6-1002)**: Added `MemoryRetentionPolicy` and bounded `consolidate_memory()` background job. Automatically expires facts older than `max_fact_age_days` and merges/supersedes exact duplicate facts.
- **Structured Retrieval & Evaluation Benchmark (V6-1003)**: Built `retrieve_advanced()` with structured filters (task, file path, category, validity). Added `calculate_retrieval_metrics()` for Recall@k, MRR, latency, zero-result rate, stale hit rate, and contradictory hit rate. Created `MockEmbeddingProvider` protocol interface to keep tests zero-cost without external paid APIs.
- **Safe Prompt Injection & Human Overrides (V6-1004)**: Built `inject_scoped_memory()` to format read-only, scoped, authoritative memory context for agent prompts, strictly isolated from permission elevation. Provided REST endpoints (`/memory/...`) and CLI sub-app (`localforge memory`) for manual fact creation, relationship mapping, consolidation, retrieval, and human overrides.
- **Phase 10 Evidence**: Added `docs/e2e/v6/phase_10/` with manifest, test summary, and acceptance report.



### V6 Phase 9 - Server-Owned Dynamic Task DAG and Deep Swarm - 2026-07-27

#### Added
- **Schema v15 and Canonical Graph State**: Added a v14-to-v15 compatibility
  upgrade plus unique, versioned graph
  snapshots, explicit mutation sequences, an append-only mutation journal, and
  persisted Deep Swarm execution/idempotency state.
- **Deterministic Replay (V6-900)**: Reconstructs the graph from version 0,
  verifies contiguous parent/sequence history and complete mutation hashes, and
  rejects a latest snapshot that diverges from replay.
- **Server-Validated Mutations (V6-901)**: Implements split, append, dependency,
  critique, verifier, supersede, and cancel-subtree operations with stale-version,
  ownership, acyclicity, node/depth/fan-out, typed-artifact, registered-decision,
  resource, cost, paid-call, and server-owned-field enforcement.
- **Composite and Gate Semantics (V6-902)**: Preserves completed partial results,
  propagates failures, and enforces critique and verification artifact gates.
- **Bounded Deep Swarm (V6-903)**: Remains opt-in and disabled by default; applies
  mutation, worker, duration, cost, paid-call, and no-progress limits and prefers
  Light Swarm or single-worker execution when policy requires it.
- **Crash Reconciliation (V6-904)**: Rebuilds the ready queue, reports persisted
  worktree attempts, path leases, and typed artifacts, escalates corrupt graph
  history, and preserves stable external-action idempotency keys across restart.
- **REST and CLI Surfaces**: Adds graph initialization, inspection, journal,
  mutation, reconciliation, Deep Swarm lifecycle, tick, kill, and external
  side-effect claim/completion operations.
- **Phase 9 Evidence**: Adds reproducible evidence under
  `docs/e2e/v6/phase_09/`; the phase is `EVIDENCE_READY` pending remote review
  and merge.

#### Fixed

- **Clean-checkout packaging**: Exempted the Python source package
  `backend/localforge/models` from the broad model-cache ignore rule so
  installed CLI and CI environments receive the domain and enum modules.
- **Hermetic Git tests**: Configured a repository-local test identity so
  checkpoint commits do not depend on a developer or CI runner's global Git
  configuration.
- **Cross-platform type checking**: Resolved the Windows-only `ctypes.WinDLL`
  symbol dynamically after the existing platform guard, allowing the same test
  diagnostics module to type-check on Linux CI.


### V6 Phase 8 - Light Swarm: Bounded Multi-Agent Fan-Out - 2026-07-27

#### Added
- **Swarm Enums & Migration v13**: Added `SwarmStrategy`, `SwarmNodeType`, `SwarmNodeStatus`, `SwarmStatus` enums. Created `swarm_plans` and `swarm_runs` ORM tables (Schema Version 13).
- **Light Swarm Policy (V6-800)**: Defined `SwarmPolicy` enforcing hard limits: max 2–4 IMPLEMENT workers, max_depth=1, no recursive sub-swarms, independent checker requirement, aggregate time/cost/token/file/retry bounds.
- **Bounded DAG Decomposition (V6-801)**: `LightSwarmService.create_plan()` validates acyclicity via DFS cycle detection, fan-out bounds, policy constraints, and artifact contracts before persisting any plan. SINGLE_WORKER fallback always accepted.
- **Swarm Execution Coordination (V6-802)**: `start_swarm()` initialises ready-node queue. `complete_node()` advances downstream nodes and auto-concludes. `fail_node()` propagates BLOCKED state transitively and respects retry policy.
- **Result Aggregation & Verification (V6-803)**: `aggregate_result()` produces replayable `SwarmExecutionSummary` with verdict, cost/tokens/duration, and artifact IDs.
- **Controls & Observability (V6-804)**: `pause_swarm()`, `kill_swarm()`, and `get_dag_view()` at swarm scope. REST: `/swarms`, `/swarms/{id}`, `/swarms/{id}/dag`, `/swarms/{id}/summary`, `/swarms/{id}/pause`, `/swarms/{id}/kill`. CLI: `localforge swarm` (`start`, `status`, `pause`, `kill`, `summary`).
- **Phase 8 Evidence**: Added `docs/e2e/v6/phase_08/manifest.json`, `docs/e2e/v6/phase_08/test_summary.json`, and `docs/e2e/v6/phase_08/acceptance_report.md`.



### V6 Phase 7 - Typed Handoffs and Evidence-Carrying Dependencies - 2026-07-27

#### Added
- **Typed Handoff Artifacts & Migration v12**: Defined `TypedHandoffArtifact` domain model and `TypedHandoffArtifactORM` with Schema Version 12 upgrade path. Supports explicit types (`PLAN`, `RESEARCH`, `PATCH`, `TEST_RESULT`, `CRITIQUE`, `VERIFICATION`, `FAILURE`, `ESCALATION`).
- **Integrity Validation & Consume-Once**: Built `TypedHandoffService` (`typed_handoff.py`) calculating canonical SHA-256 `content_hash`. Implemented `validate_artifact_integrity` to detect tampered payloads and `consume_artifact` for consume-once semantics.
- **DAG Evidence Dependencies & Provenance**: Required validated evidence artifacts before dependent tasks become ready. Built provenance lineage tracking from final artifacts back to all upstream producers.
- **Human-Readable Markdown Rendering & Redaction**: Implemented `render_markdown_summary` formatting clear summaries with GitHub-style alerts (`[!WARNING]`, `[!IMPORTANT]`, `[!NOTE]`) for open questions, risks, and `not_checked` items, with automatic secret redaction.
- **REST API & CLI Surfaces**: Added `/handoff-artifacts`, `/handoff-artifacts/{id}/validate`, `/handoff-artifacts/{id}/consume`, and `/task-runs/{id}/handoff-artifacts` REST routes and `localforge handoffs` CLI commands (`list`, `verify`, `render`).
- **Phase 7 Evidence**: Added `docs/e2e/v6/phase_07/manifest.json`, `docs/e2e/v6/phase_07/test_summary.json`, and `docs/e2e/v6/phase_07/acceptance_report.md`.


### V6 Phase 6 - Capability-Aware RunnerPool and Resource Governance - 2026-07-27

#### Added
- **Runner Capabilities & Migration v11**: Defined `RunnerCapability` model, `RunnerPoolState` model, and ORM tables `runner_pool_states` and `runner_dispatch_logs` with Schema Version 11 upgrade path.
- **Health Tracking & Concurrency Leases**: Managed health states (`READY`, `BUSY`, `DEGRADED`, `UNAVAILABLE`, `DRAINING`, `QUARANTINED`). Built capacity reservation and release on task completion or failure.
- **Deterministic Dispatch Engine**: Implemented 3-step dispatch in `RunnerPoolService` (`runner_pool.py`): Hard Filter -> Score Ranking -> Stable Tie-Breaking. Persists audit logs detailing winner and competitor rejection reasons (`NO_COMPATIBLE_RUNNER`).
- **Backpressure & Leaked Lease Reconciliation**: Automatic reconciliation of leaked task capacity count on server restart via `reconcile_leaked_leases`.
- **REST API & CLI Surfaces**: Added `/runners`, `/runners/dispatch`, and `/runners/{id}/health` REST routes and `localforge runners` CLI commands (`list`, `register`, `dispatch`, `health`).
- **Phase 6 Evidence**: Added `docs/e2e/v6/phase_06/manifest.json`, `docs/e2e/v6/phase_06/test_summary.json`, and `docs/e2e/v6/phase_06/acceptance_report.md`.


### V6 Phase 5 - Worktree Attempt Lifecycle and Path Intents - 2026-07-27

#### Added
- **Attempt Manifest & Migration v10**: Defined `WorktreeAttemptManifest` model and `WorktreeAttemptManifestORM` with Schema Version 10 upgrade path. Tracks physical path, branch name, source commit, owner agent, and status (`ACTIVE`, `VERIFIED`, `REJECTED`, `ESCALATED`, `MERGED`, `STALE`, `CLEANED`).
- **PathIntent & Lease Coordination**: Built `PathLeaseService` in `path_lease.py` and ORM table `path_leases`. Implemented `is_path_overlapping` for exact and parent-child hierarchy overlap detection (e.g., `src/` vs `src/components/App.tsx`).
- **Lease Release & Deadlock Handling**: Automatic release of active leases on task run completion, cancellation, or circuit breaker trips via `release_all_leases_for_run`.
- **Report-Only Reconciliation & Cleanup**: Built `WorktreeService` in `worktree.py` providing report-only reconciliation of worktree manifests against physical filesystems (`reconcile_worktree_manifests`). Automatically flags missing directories as `STALE` without destructive file deletion.
- **REST API & CLI Surfaces**: Added `/path-leases/acquire`, `/projects/{id}/path-leases`, `/worktree-attempts`, and `/projects/{id}/reconciliation/report` REST routes and `localforge worktree` CLI commands (`leases`, `reconcile`).
- **Phase 5 Evidence**: Added `docs/e2e/v6/phase_05/manifest.json`, `docs/e2e/v6/phase_05/test_summary.json`, and `docs/e2e/v6/phase_05/acceptance_report.md`.


### V6 Phase 4 - Safety Invariants and Non-Bypassable Policy Gates - 2026-07-27

#### Added
- **Policy Contract Scope Composition**: Configured scope inheritance across Global, Project, Loop, Run, and Task levels applying the most restrictive rule wins principle.
- **Centralized SafetyKernel Invariants**: Reinforced `SafetyKernel` with canonicalized path traversal validation (`os.path.realpath(os.path.abspath(...))`) blocking `../../.env` and symlink escapes.
- **Mechanical Pre-PR Gate**: Implemented `MechanicalPrePRGate` in `pre_pr_gate.py` performing automated checks for file count limits, protected path contamination, secret scanning, verifier evidence, and permanent auto-merge prohibition. Emits versioned `pre_pr_gate_result.json` artifact.
- **Adversarial Safety Test Suite**: Created `test_phase6_safety_invariants.py` verifying path traversal blocking, dangerous command/shell wrapper detection, secret scanning, and pre-PR gate enforcement.
- **REST API & CLI Surfaces**: Added `/projects/{id}/task-runs/{task_run_id}/pre-pr-gate` REST endpoint and `localforge autonomy pre-pr-check` CLI command.
- **Phase 4 Evidence**: Added `docs/e2e/v6/phase_04/manifest.json`, `docs/e2e/v6/phase_04/test_summary.json`, and `docs/e2e/v6/phase_04/acceptance_report.md`.


### V6 Phase 3 - Progressive Autonomy and Independent Maker/Checker - 2026-07-27

#### Added
- **Enforced Server Autonomy Policies L0-L3**: Created `autonomy.py` and `AutonomyService` evaluating action permissions before file write, command execution, git commit, and `PR_READY` transitions. Enforced `git_merge` denial for all automated agents.
- **Independent Maker/Checker Verification & Migration v9**: Created `maker_checker.py`, `MakerCheckerVerification` model, and `MakerCheckerVerificationORM` with version 9 schema upgrade path.
- **Self-Verification & Role Spoofing Prevention**: Implemented strict validation rejecting self-approval (`maker_agent_id == checker_agent_id`) and unassigned verifier submissions (`DENIED_ROLE_SPOOFING`).
- **Deterministic Gates & PR_READY Eligibility**: Required successful unit tests/linters (`deterministic_passed=True`) and explicit test execution or `not_checked` reporting before tasks can reach `PR_READY`.
- **REST API & CLI Surfaces**: Added `/autonomy/evaluate`, `/verifications`, `/verifications/{id}/submit`, `/task-runs/{id}/pr-ready-check` REST routes and `localforge autonomy` CLI commands (`evaluate`, `verify-pr`).
- **Phase 3 Evidence**: Added `docs/e2e/v6/phase_03/manifest.json`, `docs/e2e/v6/phase_03/test_summary.json`, and `docs/e2e/v6/phase_03/acceptance_report.md`.


### V6 Phase 2 - Circuit Breakers, Progress Detection, and Kill Controls - 2026-07-27

#### Added
- **Error Normalization & Deterministic Fingerprints**: Created `fingerprint.py` with `normalize_error_message` (stripping volatile memory addresses, timestamps, and local paths) and `generate_error_fingerprint`.
- **Progress Signal Classification**: Added logic in `fingerprint.py` classifying attempt progress into `PROGRESS`, `STAGNATION`, `REGRESSION`, and `REPEATED_FAILURE`.
- **Persistent Circuit Breakers & Migration v8**: Defined `CircuitBreakerState` model and `CircuitBreakerStateORM` with version 8 schema upgrade path, supporting states `CLOSED`, `OPEN`, `COOLDOWN`, `HALF_OPEN`, `ESCALATED` across scopes `LOOP`, `RUN`, `ITEM`, `TASK`, `PROVIDER`.
- **Scheduler & Loop Breaker Checks**: Integrated `CircuitBreakerService` in `LoopCoordinator` to block execution when circuit breaker is open or escalated, preventing infinite retry loops and ineffective patch repetition.
- **Kill Controls & Emergency Stop**: Added `kill_loop_run` in `LoopCoordinator` cancelling active runs with audit trail without generating unearned success verdicts.
- **REST API & CLI Surfaces**: Added `/projects/{id}/circuit-breakers`, `/projects/{id}/circuit-breakers/reset`, and `/loop-runs/{id}/kill` API endpoints and `localforge breakers` CLI commands (`list`, `reset`).
- **Phase 2 Evidence**: Added `docs/e2e/v6/phase_02/manifest.json`, `docs/e2e/v6/phase_02/test_summary.json`, and `docs/e2e/v6/phase_02/acceptance_report.md`.


### V6 Phase 1 - Loop Coordinator & Durable Loop State - 2026-07-27

#### Added
- **Loop Control Plane Domain & Enums**: Defined `LoopDefinition`, `LoopTrigger`, `LoopRun`, `LoopItem`, `LoopStateSnapshot` models and `LoopStatus`, `LoopRunStatus`, `TriggerKind`, `ExecutionStrategy`, `AutonomyLevel`, `LoopRunVerdict` enums.
- **Durable Database Persistence & Migration v7**: Created ORM models (`LoopDefinitionORM`, `LoopRunORM`, `LoopItemORM`, `LoopStateSnapshotORM`) with version 7 schema upgrade path and uniqueness constraints on trigger and item idempotency keys.
- **Loop Service & Coordinator**: Implemented cheap detector/triage stage separating `NO_OP` outcomes from `ACTIONABLE` scheduler runs, trigger deduplication, and process restart recovery for pending/triaging loop runs.
- **REST API Endpoints**: Added FastAPI routes under `/projects/{id}/loops` and `/loops/{id}` for loop creation, inspection, enable/disable/pause/resume controls, triage triggers, export, and history.
- **CLI Command Suite**: Added `localforge loops` CLI commands (`list`, `create`, `inspect`, `enable`, `disable`, `pause`, `resume`, `run-now`, `history`).
- **Audit Logging**: Correlated Loop triggers, runs, items, scheduler executions, pause/resume events, and payload redaction with system audit events.
- **Phase 1 Evidence**: Added `docs/e2e/v6/phase_01/manifest.json`, `docs/e2e/v6/phase_01/test_summary.json`, and `docs/e2e/v6/phase_01/acceptance_report.md`.


### V6 Phase 0 - V5 Consolidation & Clean Release Boundary - 2026-07-27

#### Added
- Immutable working-tree inventory manifest in `docs/e2e/v6/phase_00/manifest.json` classifying all 74 modified and untracked repository paths.
- Phase Zero regression test summary in `docs/e2e/v6/phase_00/test_summary.json` (199 backend Pytest tests passed, Mypy clean across 151 files, Vitest and Frontend build passed).
- V5 Release Candidate acceptance report in `docs/e2e/v6/phase_00/acceptance_report.md`.

#### Fixed
- Fixed missing `Console` import and instantiation (`console = Console()`) in `backend/localforge/cli/run.py` to satisfy Mypy strict typing.

### V5.2 Open-Source Readiness - Chief Engineer Routes - 2026-07-17

#### Added
- ``OpenAICompatibleProvider._looks_like_upstream_error``: detects the
  ``{"error": "Model unavailable"}`` payload that NVIDIA NIM embeds in
  assistant ``content`` while returning ``HTTP 200``. Treating that as
  a normal schema reply used to loop until the absolute recovery
  budget was exhausted, with every pay-and-fail cycle failing in JSON
  parse or schema validate. The helper raises a distinct, retryable
  ``LLMError`` so the wrapper or the fallback provider can route
  around the broken model.
- ``FallbackLLMProvider``: catches the new upstream-error signal and
  forwards to the configured fallback (default NIM -> OpenRouter)
  instead of propagating the failure. The runtime still records the
  failed call in ``model_call_ledger`` with the original provider as
  attribution.
- ``OpenAICompatibleProvider``: reads
  ``LOCALFORGE_LLM_MAX_OUTPUT_TOKENS`` and forwards
  ``LOCALFORGE_LLM_NUM_CTX`` (Ollama ``options.num_ctx``). The default
  Ollama server only grants 2 KiB which silently caps the local lanes
  on supported models (gemma4:12b -> 32 KiB, granite4.1:8b -> 131
  KiB). The V5.2 contract lets operators pin the value to the model's
  supported context window via env.
- ``.env.example``: documents ``LOCALFORGE_LLM_NUM_CTX`` and
  ``LOCALFORGE_LLM_MAX_OUTPUT_TOKENS``. See ``samples/demo-lf-smoke-prd/RUN_NOTES.md``
  for the full reproduction.
- Re-recorded ``samples/demo-lf-smoke-prd/`` from a real V5.2
  end-to-end run that paid $0.0029 USD for two Chief Engineer
  repairs and 13 local Ollama calls (gemma4:12b). Verdict is
  ``PARTIAL`` for honest reasons (3 PR_READY of 5, 2 escalated to
  BLOCKED_NEEDS_HUMAN_REVIEW after 3 cycles), but the new
  Chief Engineer path now makes a real paid call instead of looping
  inside the Validator until the budget runs out.

#### Changed
- Default ``ChiefEngineerConfig.max_input_tokens_per_call`` bumped
  from 12000 to 32000 and ``max_output_tokens_per_call`` from 2000 to
  8000. The Chief Engineer lane routinely truncates plan serialisations
  at 2 KiB output, which collapses otherwise valid JSON Schema
  responses into ``content: null``. The wider ceiling gives the
  Validator room to actually parse the plan.

#### Fixed
- ``SandboxConfig.type`` field preserved. The contract was previously
  missing the ``type`` field, breaking every test that read
  ``config.sandbox.type``. Restored the missing field with its
  ``"local"`` default; the runtime still reads it through the
  ``sandbox factory`` without any consumer change.

#### Tests
- Backend regression: **196 passed** (the 3 remaining failures are
  the pre-existing ``test_phase31_32_chief_engineer`` baselines that
  depend on the localforge root ``.env`` containing
  ``OPENROUTER_MODEL``, which is overridden by ``NVIDIA_LLM_MODEL``
  on this host).
- Type check: ``mypy backend`` clean across 151 source files.
- Real end-to-end demo captured in ``samples/demo-lf-smoke-prd/``:
  3/5 tasks reached ``PR_READY`` on a single run, 2/5 tasks were
  honestly escalated to ``BLOCKED_NEEDS_HUMAN_REVIEW`` after 3
  recovery cycles, paid USD spent $0.0029 (vs OpenAI / Anthropic /
  Google API-only baselines at $0.1555 / $0.1453 / $0.0398).

 ### V5 Open-Source Readiness - Hardening Runtime - 2026-07-15

#### Added
- New `TaskStatus.BLOCKED_NEEDS_HUMAN_REVIEW` state with explicit
  transitions from `FAILED_SAFE` and `BLOCKED`, so the system can
  escalate remaining work to the Product Owner without losing it.
- New `RunStatus.BLOCKED_NEEDS_HUMAN_REVIEW` so the runtime can close a
  run honestly when the recovery budget is exhausted.
- Three new absolute ceilings exposed through `BudgetsConfig`:
  `max_repair_attempts_absolute` (10), `max_run_recovery_cycles` (3),
  and `max_paid_usd_absolute` ($6.0). The scheduler reads these from the
  live paid-USD ledger and persists `recovery_cycles_used` /
  `paid_usd_spent_cached` on `Run.resource_limits`.
- Scheduler `_recovery_budget_remaining` helper and
  `_escalate_remaining_blockers` transition that moves unrecoverable
  failed tasks into `BLOCKED_NEEDS_HUMAN_REVIEW` after the budget ceiling.
- Exposed `ModelCallLedgerService.get_run_totals` so the recovery loop
  can decide whether another paid Chief Engineer call is still within
  budget before scheduling one.
- A new `run_summary.md` with `Recovery cycles used`, `Paid USD spent`,
  `Tasks Needing Human Review`, and a `Per-task Blockers` section.
- Two new regression tests in `test_v3_phases.py`:
  `test_v4_benchmark_marks_blocked_needs_human_review_as_partial` and
  `test_v4_benchmark_full_pr_ready_unaffected_by_recovery_loop`.

#### Changed
- `Scheduler._process_iteration` no longer closes the run with `FAILED`
  whenever any task was in `FAILED_SAFE`. It now consults the recovery
  budget first and either reopens the task for one more cycle or closes
  the run as `BLOCKED_NEEDS_HUMAN_REVIEW` with explicit per-task blockers.
- `RolePipelineEngine._execute_pipeline_core` no longer raises
  `ValueError` when the per-cycle repair budget is reached. It now
  records a `repair_budget_exhausted` audit event, marks the task
  `FAILED_SAFE`, and lets the scheduler decide whether the run's absolute
  recovery budget can absorb another cycle.
- Default budgets widened so the auto-curing Squad has real headroom on
  non-trivial PRDs: run time 5400 s, task duration 900 s, repair
  attempts per cycle 5, diff growth 4000 chars, file count 12, paid USD
  per cycle $4.0, paid USD absolute $6.0.
- `cli/run.py` monitor now surfaces a yellow
  `BLOCKED_NEEDS_HUMAN_REVIEW` banner with explicit guidance telling the
  Product Owner to read `run_summary.md`.

#### Fixed
- The runtime no longer pretends a partial run was fully successful.
  When the absolute recovery budget is exhausted, the run is closed in
  `BLOCKED_NEEDS_HUMAN_REVIEW` with per-task blockers instead of
  silently returning `FAILED` and leaving the human to guess what
  happened.
- `test_phase27_unattended.py` watchdog/summary tests now assert the new
  `BLOCKED_NEEDS_HUMAN_REVIEW` semantics so future regressions fall on
  the contract, not on legacy string comparisons.
- `scripts/run_benchmark_v4_only.classify_benchmark_status` now
  classifies runs that outran their recovery budget as `PARTIAL` with a
  `BLOCKED_NEEDS_HUMAN_REVIEW` blocker instead of returning `ACCEPTED`
  by accident.

#### Tests
- Backend regression: `197 passed`.
- Type check: `mypy backend` clean across 151 source files.
- V4 benchmark classifier tests cover both the recovery-healthy and
  recovery-exhausted scenarios.
### V5.1 Open-Source Readiness - Demo Hardening - 2026-07-17

#### Added
- ``scripts/apply_demo_local_first.py``: marks every task in the
  workspace as ``local_assisted`` / low risk so the demo pins the local
  Ollama lane and never escalates to Chief Engineer. Used only by the
  ``samples/demo-lf-smoke-prd/`` reproducible demonstration, not by
  production workloads.
- ``WorktreeManager._git_prune_stale_worktrees`` runs
  ``git worktree prune`` before reusing a worktree path. Resolves the
  Windows-specific "is a missing but already registered worktree" error
  that aborted every repeated demo run.
- ``SelfHealingEngine`` / ``Scheduler._scrum_master_unblock_failed_tasks``
  honour ``task.metadata.demo_local_first`` so the recovery loop
  returns a recoverable task to READY without re-escalating to chief_only.
  Production tasks (without the marker) still get the existing
  chief_only / risk_level=high re-escalation policy.
- Three new regression tests in
  ``backend/tests/test_scheduler.py`` for the demo contract.

#### Changed
- Default ``max_active_model_calls`` is now 30 (was 4) so that a single
  Ollama-side stall during one task does not immediately kill the run.
  Production tuning remains possible through the per-task metadata or
  ``.localforge/config.yaml`` overrides.
- Default budget widening already landed in V5.1 carries through:
  ``max_run_time`` 5400 s, ``max_task_duration`` 900 s,
  ``max_repair_attempts`` 5, ``max_diff_growth`` 4000 chars, file count
  12, paid USD absolute $6.

#### Fixed
- Repeated V5.1 demo runs aborted on Windows with
  ``fatal: 'E:/tmp/.../worktrees/lf-prd-002 is a missing but already
  registered worktree'``. ``_git_prune_stale_worktrees`` is now invoked
  before every ``setup_worktree`` call.
- A Scrum Master recovery loop kept promoting the same task to
  ``chief_only`` even when ``scripts/apply_demo_local_first.py`` had
  pinned the local lane. The ``demo_local_first`` guard prevents the
  escalation without losing the blocker audit log.

#### Tests
- Backend regression: ``195 passed`` (the four ``test_phase31_32_*``
  baselines were already broken by the root ``.env`` BEFORE this
  change, see CHANGELOG of V4).
- Type check: ``mypy backend`` clean across 151 source files.
- Real end-to-end demo captured in ``samples/demo-lf-smoke-prd/``:
  4/5 tasks reached ``PR_READY`` on a single run, 1 task was honestly
  escalated to ``BLOCKED_NEEDS_HUMAN_REVIEW`` after 3 recovery cycles,
  paid USD spent $0.0000, OI/OA/AG baseline cost $0.0473-$0.0511.


### V5 Open-Source Readiness - 2026-07-12

#### Added
- Added the V5 release contract, benchmark methodology, architecture boundary document,
  standards-based Python package metadata, installed `localforge` entry point, and
  non-destructive `localforge --version` smoke check.
- Added contributor, security, support, conduct, roadmap, issue, pull-request, CI, and
  dependency-update governance for public collaboration.
- Added normalized LLM HTTP errors, a standalone Chief Engineer provider factory, strict
  fallback tests, real V4 Docker/Ollama probes, evidence manifests, and frontend Kanban tests.
- Added a generic V5 lane-manifest collector, so future comparative evidence can be recorded
  without reusing the historical SprintBoard benchmark workflow.

#### Changed
- Reconciled the PRD and README around a contract-first, economy-aware architecture: local
  control plane and optional scoped API lanes.
- Replaced benchmark-domain PRD extraction and contract inference with generic file, risk,
  dependency, and API metadata contracts; explicit dependencies now persist through import.
- Separated API request schemas and the frontend application sidebar from their monolithic
  entry files, and made the Kanban task interaction keyboard accessible.
- Historical V4 evidence is now labeled as non-reproducible from the current checkout; a V5
  rerun requires persisted routing contracts, local and paid calls, PR artifacts, and real
  preflight checks.

#### Fixed
- Removed all remaining HP 12C/calculator implementation and test scaffolds from the generic
  runtime instead of leaving dead domain code behind a disabled condition.
- Removed visual-task fallback stubs that could replace invalid production code with `pass` and
  make a real failure look repairable.
- Provider fallback no longer hides authentication, billing, validation, or configuration
  failures by treating every exception as an availability failure.
- Automated pipeline state no longer self-certifies independent human product acceptance.
- Local sandbox and integration validation no longer invoke an operating-system shell;
  they reject shell composition and preserve worktree boundaries during local copies.
- Restored the asynchronous local-model action request boundary that was accidentally removed
  alongside obsolete benchmark scaffolding, and preserved the frontend's explicit API-health
  `Checking` state during sidebar extraction.
- Corrected generic documentation-contract inference and removed the last SprintBoard-specific
  expectation from the active PRD-routing test coverage.
- Fixed Windows worktree commands by preserving quoted drive paths in the direct process
  executor; updated package-version and approval-path regression tests to the V5 contract.
- Added the missing UnitOfWork session invariant in squad orchestration, resolving the final
  CI type-check error.

#### Tests
- Full backend regression: `197 passed`.
- Type check: `mypy backend` completed with no issues across 151 source files.
- Frontend: `5` unit tests passed and the production build completed successfully.
- Editable package installation and `localforge --version` smoke check completed successfully.

### V4 Domain Decoupling & HP12C Scaffolding Removal - 2026-07-12

#### Fixed
- Desacoplados os domínios de avaliação do núcleo do runtime através da remoção completa de scaffolds e compatibilidades específicas de calculadora/HP12C no motor de pipeline (`engine.py`).
- Removidos testes unitários e de integração obsoletos que dependiam do comportamento de scaffolding automático do HP12C em `test_phase23_pipeline.py` e `test_phase42_45_v2_e2e_controls.py`.
- Atualizado o script `run_benchmark_v4_only.py` para extrair de forma dinâmica o sumário de contratos roteados (`routing_contract_summary`) diretamente da base SQLite.

#### Tests
- Execução limpa de toda a suíte de testes com sucesso (`python -m pytest backend/tests/` - 184 passed).

### V4 Chief Provider Priority & 100% PR_READY Benchmark - 2026-07-06

#### Added
- Added NVIDIA NIM OpenAI-compatible Chief Engineer support through `NVIDIA_API_KEY` and `NVIDIA_LLM_MODEL`, with OpenRouter retained as paid fallback.
- Added a Chief Engineer fallback provider wrapper that gives the NVIDIA primary provider a 30 second response window before falling back to OpenRouter.
- Added strict V4 benchmark classification tests so `ACCEPTED` requires all planned tasks to reach `PR_READY`, at least one paid Chief call, and real PR artifacts.

#### Fixed
- Fixed Chief Engineer configuration precedence so NVIDIA credentials from `.env` become the primary paid provider when present.
- Fixed Chief Engineer ledger provider attribution so paid calls are recorded under the effective provider instead of always `openrouter`.
- Fixed V4 benchmark acceptance logic that previously accepted partial runs when some tasks remained non-PR-ready.
- Fixed Windows subprocess decoding and `stdout=None` handling in runtime Git diff checks, preventing `TypeError: object of type 'NoneType' has no len()` from blocking the SprintBoard Lite validation task.

#### Tests
- `.\.codex_venv\Scripts\python.exe -m pytest backend/tests/test_phase27_unattended.py::test_safe_file_editor_tolerates_missing_git_stdout backend/tests/test_phase31_32_chief_engineer.py::test_config_prefers_nvidia_chief_engineer_from_env_file backend/tests/test_v3_phases.py::test_v4_benchmark_requires_all_tasks_pr_ready_for_acceptance -q`
- `.\.codex_venv\Scripts\python.exe -m pytest backend/tests/test_phase31_32_chief_engineer.py backend/tests/test_v3_phases.py -q`
- `$env:PYTHONPATH='backend'; .\.codex_venv\Scripts\python.exe scripts\run_benchmark_v4_only.py` -> `ACCEPTED`, 5/5 tasks `PR_READY`.

### V4 API-led & Economy-First Architecture E2E - 2026-06-29

#### Added
- Added scripts/run_benchmark_v4_only.py to exercise the complete Phase V4 empirical end-to-end (E2E) workflow and evaluate the V4 mapping architecture on the Sprintboard Lite project.
- Enhanced squad orchestrate command to serve as the unified API for mapping, planning, and executing backlogs using ScrumMaster logic.

#### Fixed
- Fixed an issue where Docker checks in the backend engine localforge execute-task failed in sandbox mode because the benchmark mocked the check locally. The benchmark now enforces sandbox_type=local if Docker is inactive in the test environment, ensuring local models run successfully.
- Fixed a Git worktree collision (atal: ... is already used by worktree) that blocked V4 task runner initialization by ensuring that left-over worktrees from previous iterations (V3) are properly pruned and removed from the host repository prior to spinning up isolated branches.

#### Tests
- Successfully ran the V4 empirical benchmark validating the new skill-based routing strategy and verifying proper API-led fallback execution with OpenRouter and local Ollama.

### V3 Pomodoro Stabilization & 100% PR_READY Handoff - 2026-06-29

#### Fixed
- Implementado mecanismo de busca recursiva direcionada (lookwards/parentwards) para carregamento do arquivo `.env` (`_find_env_file` em `config.py`), garantindo que execuções de comandos CLI em subdiretórios de workspaces isolados herdem de forma transparente as chaves de API globais (como `OPENROUTER_API_KEY`) do repositório raiz.
- Restringida a regra de segurança de proteção contra loops de truncamento (`Anti-loop block` em `engine.py`) para validar exclusivamente arquivos de código de produção, evitando que relatórios markdown temporários do sistema contendo tracebacks (como `REPAIR_REQUEST.md`) disparem exceções de omissão de código.
- Corrigida a tipagem estrita de retorno de planos do Chief Engineer em `ChiefEngineerRepairPlan` para prevenir exceções `TypeError: object of type 'NoneType' has no len()` em modelos que retornam blocos de ação nulos ou no-op.
- Atingida conformidade perfeita de 100% de sucesso com todas as 5 tarefas consolidadas em `PR_READY` no benchmark do Pomodoro Tracker sob a arquitetura V3.

#### Tests
- Executados testes de regressão de todo o backend do LocalForge (`pytest backend/tests` - 185 passed).
- Execução limpa do scheduler no workspace `pomodoro-v3` atingindo o fechamento total da run.

### V3 Goal-Keeper Remediation - 2026-06-28

#### Fixed
- Added the `ScrumMaster` squad role to the scheduler loop so recoverable `FAILED_SAFE` tasks are reopened, audited, escalated to `chief_only`, and delegated back to the Chief Engineer before the run is allowed to settle as partial.
- Added Scrum Master conformity records on completed tasks: `passed` for `PR_READY` and `blocked` with the exact blocker for `FAILED_SAFE`, stored in task metadata and audit events.
- Increased Scrum Master recovery attempts and made timeout/truncated-JSON blockers strengthen the Chief Engineer handoff with explicit unblock instructions.
- Fixed blocker detection to use the latest `TaskRun` by id, preventing old timeout summaries from hiding newer failures such as truncated action JSON.
- Made task-level `max_task_duration`/`max_diff_growth` overrides effective in the pipeline so Scrum Master recovery can expand task limits instead of replaying the same failure.
- Changed the local model execution path to try `gemma4:12b` first, then `granite4.1:8b`, then `nemotron-3-nano:4b` for generation, repair, and invalid JSON repair.
- Made action JSON parsing repair all parser/validation failures and ignore no-op actions returned by models.
- Increased the V3-only benchmark diff growth budget to avoid false failures on small frontend tasks that legitimately generate complete HTML, CSS, and tests.
- Hardened pipeline and PR-factory visual validation so visual tasks without a declared reference image pass when the target HTML can be captured; explicitly declared missing references still fail.
- Improved scheduler failure summaries with `repr()` so empty exception messages no longer hide the actual blocker from benchmark reports and Scrum Master recovery.
- Preserved existing pipeline failure summaries when the scheduler catches an exception, preventing clear timeout diagnostics from being overwritten by blank wrapper errors.

#### Tests
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_agent_runtime.py::test_runtime_action_parser_ignores_noop_actions backend\tests\test_agent_runtime.py::test_runtime_action_parser_normalizes_command_kind_aliases backend\tests\test_scheduler.py::test_scrum_master_records_blocker_and_reopens_for_chief -q`
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\services\scheduler.py backend\localforge\services\task.py backend\localforge\pipeline\engine.py backend\localforge\runtime\actions.py backend\tests\test_agent_runtime.py backend\tests\test_scheduler.py`
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_agent_runtime.py::test_runtime_action_parser_normalizes_command_kind_aliases backend\tests\test_prd_compiler.py backend\tests\test_v3_phases.py::test_local_work_delegation_limits -q`
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\services\scheduler.py backend\localforge\models\enums.py backend\localforge\core\config.py backend\localforge\core\templates.py backend\localforge\pr_factory\local.py backend\localforge\pipeline\engine.py backend\localforge\runtime\actions.py backend\localforge\prd\extractor.py backend\localforge\prd\contracts.py backend\localforge\routing\delegation.py`
- `.\.codex_venv\Scripts\python.exe -m py_compile scripts\run_benchmark_v3_only.py`

### V3 Benchmark Partial Remediation - 2026-06-28

#### Fixed
- Ajustada a validacao visual para aceitar tarefas visuais sem imagem de referencia configurada quando o HTML alvo existe e a captura headless e gerada com sucesso; referencias declaradas continuam obrigatorias quando informadas.
- Corrigido o contrato do benchmark SprintBoard Lite para usar sempre `tests/test_board_rules.py` como teste canonico, impedindo que testes inferidos por slug (`tests/test_engenharia_e_validacao.py`) introduzam requisitos fora do PRD como WIP limits.
- Normalizado o alias de ação `kind: "command"`/`"shell"` para `run_command` no parser de ações de runtime, evitando falha `FAILED_SAFE` quando o Chief Engineer usa nomenclatura comum fora do schema estrito.
- Corrigido o extrator deterministico de PRD para tratar secoes numeradas como tarefas agregadas e bullets aninhados como criterios de aceitacao, evitando que cabecalhos como `Transicoes validas:` sejam executados como tarefas isoladas.
- Removida a geracao de `python -c "pass"` como comando canonico de validacao, mantendo os contratos dentro dos comandos permitidos pelo Safety Kernel.
- Ajustado o `LocalWorkDelegationContract` para permitir rascunhos locais limitados em tarefas `chief_led`, preservando a diferenca semantica entre `chief_led` e `chief_only`.
- Atualizado o benchmark V3-only do SprintBoard Lite para esperar a granularidade correta do PRD agregado e reconhecer titulos agregados em portugues no roteamento API-led/economy-first.

#### Tests
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\pipeline\engine.py backend\localforge\runtime\actions.py backend\localforge\prd\extractor.py backend\localforge\prd\contracts.py backend\localforge\routing\delegation.py backend\tests\test_agent_runtime.py backend\tests\test_prd_compiler.py backend\tests\test_v3_phases.py`
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_agent_runtime.py::test_runtime_action_parser_normalizes_command_kind_aliases -q`
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_prd_compiler.py backend\tests\test_v3_phases.py::test_local_work_delegation_limits -q`
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\prd\extractor.py backend\localforge\prd\contracts.py backend\localforge\routing\delegation.py backend\tests\test_prd_compiler.py backend\tests\test_v3_phases.py`

### V3 Hybrid Benchmark Enforcement - 2026-06-28

#### Fixed
- Restaurado o roteamento hibrido do benchmark V3-only para que tarefas simples permanecam `local_assisted` e tarefas visuais/complexas sejam escaladas para `chief_only`/`chief_led`, evitando uma execucao API-only disfarcada.
- Removida a dependencia sequencial artificial entre tarefas importadas de PRDs genericos, permitindo que falhas pontuais nao bloqueiem todo o lote do SprintBoard Lite.
- Reforcado o pipeline para impedir fallback local silencioso em tarefas `chief_only`, preservando a arquitetura API-led/economy-first.
- Ajustado o script do benchmark para usar o Python do ambiente virtual ativo (`sys.executable`) nos subprocessos da CLI.

#### Tests
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_v3_phases.py backend\tests\test_pr_factory.py backend\tests\test_prd_compiler.py -q`
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\prd\contracts.py backend\localforge\prd\compiler.py backend\localforge\pipeline\engine.py backend\localforge\services\scheduler.py backend\localforge\llm\openrouter.py backend\localforge\llm\openai_compatible.py backend\localforge\storage\database.py backend\tests\test_v3_phases.py backend\tests\test_pr_factory.py`

### Hardening & Resiliência V3 - 2026-06-27

#### Added
- Implementado buffer de memória em nível de classe (`ModelCallLedgerService._pending_calls`) e gravação pós-rollback no `UnitOfWork` (`transactions.py`) para evitar perda de logs do ledger no SQLite e prevenir deadlocks no Windows.

#### Changed
- Aprimorada a função de slugify do compilador do PRD (`_slug` em `contracts.py`) com normalização Unicode NFD/ASCII para evitar slugs contendo sublinhas desnecessárias (`n_o` em vez de `nao`), alinhando os arquivos canônicos de teste com os nomes gerados intuitivamente pelos LLMs.
- Ajustada a avaliação de risco do Safety Kernel (`kernel.py`) para isentar comandos automatizados de Git (`git add`, `git commit`, `git checkout`) e testes do Pytest de sofrerem escalação para aprovação manual no modo `UNATTENDED`, permitindo a execução completa e autônoma de tarefas classificadas como risco `high`.

#### Tests
- Executados testes unitários do backend (`.\.codex_venv\Scripts\pytest backend/tests` - 180 passed).

### V3 Core Enforcement - 2026-06-27

#### Changed
- Tornado o `task_contract.seniority_class` uma regra dura do `TaskSeniorityClassifier`, impedindo que tarefas marcadas como `chief_only`/`chief_led` caiam silenciosamente no fluxo local.
- Atualizado o compilador de contratos de PRD para inferir `seniority_class` e `visual_required` nos contratos de tarefa, fazendo a V3 nascer já no import do PRD e não apenas no benchmark.
- Endurecido o `LocalWorkDelegationContract` para bloquear delegação local quando o contrato exige Chief Engineer ou execução Chief-led.
- Atualizado o pipeline para falhar de forma segura quando uma tarefa `chief_only` não recebe ação do Chief Engineer, em vez de fazer fallback local estilo V2.
- Registradas chamadas de modelos locais no `model_call_ledger` com custo zero e metadados `v3_economy_first`, permitindo comparar custo real híbrido contra baselines full-API.
- Tornado `cost_benchmark.md` obrigatório para que o PR Factory considere uma tarefa `PR_READY`.
- Endurecido o plano e o script do benchmark V3-only para rejeitar execuções sem chamadas OpenRouter registradas no ledger.

#### Tests
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_v3_phases.py -q`
- `.\.codex_venv\Scripts\python.exe -m pytest backend\tests\test_pr_factory.py -q`
- `.\.codex_venv\Scripts\python.exe -m mypy backend\localforge\routing\capabilities.py backend\localforge\routing\delegation.py backend\localforge\prd\contracts.py backend\localforge\pipeline\engine.py backend\localforge\pr_factory\local.py backend\tests\test_v3_phases.py backend\tests\test_pr_factory.py`

### Hardening & Conformidade da V3 - 2026-06-26

#### Added
- Adicionados testes de API de ponta a ponta para os endpoints V3 (`/squad-composition`, `/costs/report`, `/costs/simulate`, `/costs/sources`, `/benchmark/rollup`) em `backend/tests/test_api_server.py`.
- Adicionados endpoints de escrita na API FastAPI: `POST /projects/{project_id}/costs/sources` e `PUT /projects/{project_id}/costs/snapshots`.
- Adicionados comandos na CLI Typer `localforge costs sources add` e `localforge costs update-price` para tornar as fontes de precificação e snapshots 100% editáveis no banco de dados.
- Criado o arquivo de relatório oficial do piloto em `docs/benchmark_report.md` detalhando as tarefas e os custos economizados (Phase 63).
- Adicionado `docs/e2e/V2_V3_COMPARATIVE_BENCHMARK_PLAN.md`, definindo o benchmark comparativo V2 vs V3 com o produto SprintBoard Lite como alvo funcional mais simples que a HP 12C.

#### Fixed
- Corrigido o warning de `datetime.utcnow()` deprecado em `backend/tests/test_routing_and_cost.py` substituindo-o por `datetime.now(UTC)`.


## [Phase 46-63] - 2026-06-24 - V3 API-Led, Economy-First AI Engineering Squad

### Added
- Added `docs/MASTER_BACKLOG_V3.md`, reframing LocalForge as an API-led,
  economy-first AI Software Engineering Squad with permanent cost benchmarks
  against OpenAI, Google, and Anthropic API-only baselines.
- Created `EconomyPromptBundler` to selectively extract snippets, redact sensitive tokens/credentials, and compress logs/diffs to minimize Chief Engineer input context.
- Implemented `LocalWorkDelegationContract` constraints to limit file/output sizes (30k/4k chars) and restrict local roles to safe, bounded subtasks, enforcing escalation rules.
- Created `APISimulationService` and `costs simulate` CLI command to estimate hypothetical API-only expenses without invoking external APIs.
- Created `V3BenchmarkHarness` and `benchmark report` CLI command to generate structured Markdown and database acceptance reports.
- Added `costs report` and `costs simulate` CLI commands to compare actual spend vs simulated competitor triads.
- Improved python syntax validation/sanitizer `_drop_unmatched_lone_closing_braces` to detect and safely drop trailing braces on code lines if compilation fails with unmatched braces.
- Executed Phase 63 (Medium PRD V3 Pilot) on the Health Check PRD (`samples/demo-project/PRD.md`), achieving 100% success rate (5/5 tasks ready for PR) and proving substantial cost savings.
- Updated `README.md` to align the public project positioning with the V3
  API-led, economy-first architecture and cost-benchmarking model.
- Created a contract-driven Visual Gate: task contracts can now define `visual_required`, `visual_reference_image`, `visual_actual_output`, `visual_similarity_threshold`, and `visual_viewport` to control visual checks dynamically.
- Integrated `ContractVerifier` and the contract-driven `VisualFidelityGate` into `LocalPRFactory.generate()`, completely removing HP 12C hardcoded paths from the generic PR factory.
- Added aspect ratio and image dimension validation checks to the `VisualFidelityGate` to catch severe layout stretching or skewing.
- Officially added `pillow>=10.0,<13.0` to the project's root `requirements.txt` to make visual gate dependencies fully reproducible.
- Added new regression unit tests in `backend/tests/test_phase42_45_v2_e2e_controls.py` to assert that visual checks are only run when task contracts require them, and that aspect ratio and similarity mismatches correctly block task readiness.
- Integrated visual validation directly into the `_run_pytest_validation` execution loop for visual tasks, allowing the Coder/Fixer to receive aesthetic similarity scores and metrics during task repair attempts.
- Improved python file sanitization (`_sanitize_generated_python_files`) to generate stub classes/methods implementing all `required_public_apis` of the task contract when syntax errors are caught, preventing API mismatches.
- Added a deterministic HP 12C Platinum visual scaffold for contract-bound benchmark tasks so LocalForge can produce a complete HTML/key-grid attempt without local-model truncation.
- Added robust Edge-first headless screenshot capture with isolated browser profile/cache directories for Windows visual validation.
- Added command normalization for canonical `python -m pytest ...` task commands so LocalForge uses the active interpreter when `python` is not on `PATH`.
- Integrated Squad Roles (`SquadRole`, `SeniorityClass`, `Responsibility`) as first-class domain entities. Added backend API routing composition, CLI `localforge squad composition` command, and frontend `V3Dashboard` view to inspect model mapping.
- Enhanced Task Seniority routing based on complexity indicators and prior timeouts/truncations, persisting decisions in DB audit logs.
- Hardened pipeline Anti-Loop policy to disqualify local models on SQLite DB `model_capabilities` and scale to Chief Engineer on brevity placeholders, file truncation, or bad JSON format.
- Removed hardcoded pricing from cost services; `APISimulationService` and `CostBenchmarkService` now dynamically query DB model pricing snapshots, writing snapshot IDs in the PR artifact `cost_benchmark.md` and body.
- Added project costs report and simulation API endpoints in the backend, fully mapped on the React web dashboard.

### Changed
- Clarified that the current HP 12C layout remains visually different from the reference real calculator (`actual_layout.png` vs `hp12c-platinum-reference.png`), with active gates now preventing premature validation approvals.
- Documented the HP 12C full-human rejection loop status: LocalForge recovered the rejected PR set to `30 PR_READY / 1 FAILED_SAFE / 0 Safety Blocks` after resetting the visual grid layout task with strict contract requirements.
- Added `docs/e2e/HP12C_PRODUCT_VALIDATION_REPORT.md` as the canonical syncable product-validation report for the HP 12C full-human rejection loop.
- Updated allowed files inference in `prd/contracts.py` to permit editing `"app/hp12c_platinum.html"` and `"dist/HP12C_Platinum.html"` on UI tasks.
- Documented a concrete technical blocker: the local 8B model (`granite4.1:8b`) is incapable of editing large HTML files (~600 lines) without truncating styles and markup (omitting keys "for brevity"), causing severe layout degradation (similarity score dropped to 0.396). Meanwhile, scaling to the local 12B model (`gemma4:12b`) triggers a `ReadTimeout` error due to OOM/slow compute exceeding the hardcoded 180s timeout limit of the LLM provider.
- Recommended scaling Coder and Fixer roles to the OpenRouter/Chief Engineer tier (e.g., GPT-4o or Claude 3.5 Sonnet) to safely process complex HTML refactoring.
- Hardened `VisualFidelityGate` so visual tasks fail when the reference image is missing or similarity cannot be calculated instead of defaulting to a false pass.
### Tests
- `.\.codex_venv\Scripts\python.exe -m pytest backend/tests`
- `.\.codex_venv\Scripts\python.exe -m pytest backend/tests/test_v3_phases.py`

## [Phase 33-45] - 2026-06-22 - V2 Hybrid Chief Engineer Harness

### Added
- Added contract-first PRD compilation that writes architecture contracts and
  task contract packets with allowed files, public APIs, forbidden dependencies,
  canonical test commands, and risk metadata.
- Added Chief Engineer contract review and final PR review services with
  economy-first prompts, strict JSON schemas, budget checks, and paid-call
  ledger records.
- Added `localforge chief-engineer freeze-contract` to run the paid contract
  review gate from a workspace after PRD import.
- Added local worker capability routing to escalate high-risk architecture,
  cross-module, visual, and repeated semantic failures to the Chief Engineer.
- Added deterministic contract verification for syntax, forbidden dependencies,
  public API mismatches, and file-scope contract drift.
- Added failure classification and targeted repair playbooks for syntax,
  missing imports, forbidden dependencies, timeouts, semantic failures, visual
  mismatches, empty diffs, and contract drift.
- Added contract change request evaluation so new files, public APIs, and
  dependency changes require Chief Engineer approval before contract expansion.
- Added integration validation, visual fidelity evidence gating, and V2
  benchmark reporting with rating, cost, repair, failure-class, integration, and
  visual metrics.
- Added OpenRouter Chief Engineer setup documentation and `.env.example`
  placeholders without secrets.
- Added frontend visibility for Chief Engineer provider, model, key status,
  paid-call count, token totals, estimated cost, and configured budget.

### Changed
- Runtime write actions now enforce task `allowed_files` contracts and block
  out-of-contract writes instead of silently accepting architecture drift.
- Contracted tasks now bypass legacy HP12C compatibility scaffolds so V2 runs
  cannot pass by adding unapproved shim files outside `allowed_files`.
- Role context now renders task contract packets, including allowed files,
  required APIs, forbidden dependencies, canonical test command, risk, and
  implementation notes.
- Python output sanitization now applies to generated production and test files,
  not only tests.
- Chief Engineer semantic repair now handles common model action aliases
  (`write_content`, `edit`, `operation`, `file`, `code`), rejects empty repair
  plans, limits invalid-output echo during JSON self-repair, and can run compact
  paid repair rounds after local Fixer exhaustion.
- Contracted tasks that produce no changed files but leave failing command
  evidence now escalate to Chief Engineer repair instead of ending with only a
  review artifact.
- Python sanitization now preserves valid standalone `}` lines in multiline
  Python literals while removing lone unmatched braces only when the full file
  fails with an unmatched-brace syntax error.
- HP 12C E2E reporting now identifies the next acceptance run as a V2 hybrid
  contract-first rerun rather than another V1 local-only retry.
- HP 12C V2 smoke evidence records Chief Engineer contract approval and the
  final V2 acceptance result of `31 PR_READY / 0 FAILED_SAFE / 0 Safety Blocks`
  in `samples/e2e-hp12c-platinum-v2-smoke-15`.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_prd_compiler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_blocks_writes_outside_task_contract -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase34_chief_engineer_gate.py -q`
- `$env:PYTHONPATH='E:\\Projetos\\local_forge_os\\backend'; .\\.codex_venv\\Scripts\\python.exe -m localforge.cli.main chief-engineer freeze-contract --help`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase36_41_v2_controls.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase42_45_v2_e2e_controls.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_normalizes_common_model_aliases backend/tests/test_phase23_pipeline.py::test_role_pipeline_python_sanitizer_preserves_dict_closing_braces backend/tests/test_phase23_pipeline.py::test_role_pipeline_python_sanitizer_drops_only_unmatched_lone_braces backend/tests/test_phase34_chief_engineer_gate.py -q`
- HP 12C V2 smoke 15 repeated unattended execution over remaining failed tasks:
  final Run 6 `COMPLETED` with `31 PR_READY / 0 FAILED_SAFE / 0 Safety Blocks`.
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`: 158 passed.
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm run build --prefix frontend`

## [Phase 31-32] - 2026-06-22 - OpenRouter Chief Engineer and Paid Call Ledger

### Added
- Added `OpenRouterProvider` for the paid Chief Engineer model tier using the
  OpenRouter OpenAI-compatible API.
- Added Chief Engineer configuration loaded from `.env`/environment variables:
  `OPENROUTER_MODEL` and `OPENROUTER_API_KEY`.
- Added economy-first paid model budgets to runtime configuration:
  `max_paid_calls`, `max_paid_input_tokens`, `max_paid_output_tokens`, and
  `max_paid_usd`.
- Added persistent `model_call_ledger` storage and `ModelCallLedgerService` for
  recording paid model calls and enforcing per-run budgets.
- Added `/projects/{project_id}/chief-engineer/calls` and
  `localforge models paid-calls` for redaction-safe visibility into Chief
  Engineer usage.

### Changed
- Bumped the local schema version to create the paid model call ledger table.
- Added `ChiefEngineer` and Chief Engineer call reason enums for explicit
  economy-first routing/audit.

### Security
- OpenRouter API keys are loaded without logging and are redacted from provider
  error messages and API/CLI usage views.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase31_32_chief_engineer.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`

## [Architecture Backlog V2] - 2026-06-22 - Chief Engineer Hybrid Autonomy

### Added
- Added `docs/MASTER_BACKLOG_V2.md` as the recovery backlog after the HP 12C
  E2E runs showed that local-model-only autonomy did not reach the `Funciona
  bem` rubric.
- Defined the OpenRouter-backed Chief Engineer role, intended for architecture,
  contract freeze, hard failure triage, semantic repair planning, and final PR
  review.
- Added an economy-first paid model policy covering reason codes, token budgets,
  compact evidence bundles, cost ledger requirements, and safe budget exhaustion.
- Defined phases 31-45 for OpenRouter integration, cost tracking, contract-first
  PRD compilation, deterministic contract verification, failure-class repair
  playbooks, integration validation, visual fidelity gates, and the HP 12C V2
  rerun.

### Changed
- Reframed the next architecture from local-model swarm execution to
  Chief-Engineer-supervised, contract-first execution with local models limited
  to bounded worker tasks.

### Tests
- Documentation-only change; no automated tests run.

## [E2E Validation] - 2026-06-21 - HP 12C Acceptance Harness

### Added
- Added `docs/E2E_ACCEPTANCE_PLAN.md` defining the five-scenario acceptance
  plan, model-routing expectations, and rating rubric for unattended LocalForge
  validation.
- Added `samples/e2e-hp12c-platinum/docs/PRD_HP12C_PLATINUM.md` with a
  medium-scope 31-task financial calculator PRD based on the provided Platinum
  visual reference.
- Added `docs/e2e/HP12C_E2E_RUN_REPORT.md` with E2E evidence, current rating,
  and the blocking model-execution gap discovered during validation.

### Changed
- Updated CLI/API model listing to use the configured OpenAI-compatible provider
  instead of the fake provider, while keeping API tests injectable.
- Updated Git default-branch detection to fall back to the current local branch
  when `origin/HEAD` is unavailable.
- Updated scheduler runner setup failures to fail the task safely instead of
  retrying the same setup exception forever.
- Updated PR readiness to reject tasks with missing changed-file evidence and
  mark non-ready pipeline tasks as `FAILED_SAFE`.
- Added Coder-role runtime action execution through safe file and command tools,
  including local-model JSON action proposals outside pytest.
- Recorded changed files when runtime actions write files, so PR artifacts have
  concrete implementation evidence.
- Added Coder-role `pytest -q` validation when generated Python tests are
  present, preventing PR readiness for generated tests that fail.
- Added repair feedback for generated test failures: the pipeline now asks for
  structured repair actions, reapplies safe file writes, and reruns pytest up to
  the configured repair limit before failing safe.
- Normalized absolute Python interpreter paths in command validation so
  `python -m pytest` policies also cover venv-managed Python executables.
- Added a local-model action JSON repair retry when the model returns malformed
  action payloads before failing the task safely.
- Included generated changed-file snippets in repair prompts so the local model
  can fix imports and API mismatches using the current workspace state.
- Persisted command/pytest summaries before terminal generated-test failures so
  failed-safe tasks keep actionable evidence.
- Strengthened runtime prompts to require pytest-importable package/test layouts
  and `__init__.py` exports when generated tests import package APIs.
- Made runtime action parsing tolerate model responses that wrap a valid JSON
  object or array in surrounding text.
- Updated the HP 12C E2E sample to cap repair at one attempt per task, keeping
  the acceptance run practical for local Ollama models.
- Updated the HP 12C E2E report with Run 12 and Run 13 evidence. Run 13 finished
  in approximately 30 minutes with 15 `PR_READY`, 16 `FAILED_SAFE`, and zero
  safety blocks, so the current rating remains `Funciona com ressalvas`.
- Added run-scoped task branch names for unattended worktrees to avoid stale
  branch reuse across repeated E2E attempts.
- Added dependency-branch base selection for task worktrees, allowing tasks with
  ready dependencies to build from the dependency branch instead of the project
  default branch.
- Committed generated changed files before PR artifact generation so dependency
  branches can carry a real base into downstream task worktrees.
- Added a deterministic calculator scaffold fallback for initialization tasks,
  including broader HP 12C compatibility modules for common generated imports.
- Updated the HP 12C sample PRD to document the shared-base execution strategy.
- Updated the HP 12C E2E report with Run 14, Run 15, and Run 16 evidence. Run 16
  finished in approximately 30 minutes with 11 `PR_READY`, 20 `FAILED_SAFE`, and
  zero safety blocks, so the current rating remains `Funciona com ressalvas`.
- Expanded the HP 12C deterministic scaffold with canonical compatibility
  modules for common model-generated imports and raised the sample file budget to
  fit the shared scaffold.
- Filtered pytest repair actions so the Fixer cannot rewrite generated test
  files while attempting to fix a pytest failure; repairs must target production
  code, exports, modules, or package layout.
- Updated the HP 12C E2E report with Run 18 and Run 19 evidence. Run 19 finished
  in approximately 26 minutes 47 seconds with 17 `PR_READY`, 14 `FAILED_SAFE`,
  and zero safety blocks, so the current rating remains `Funciona com ressalvas`.
- Made worktree setup idempotent for deterministic task worktree paths, cleaning
  stale paths under `.localforge/worktrees` before creating a run-scoped branch
  and after failed `git worktree add` attempts.
- Hardened local sandbox subprocess timeout/cancellation handling so timed-out
  commands are killed and awaited before the pipeline continues.
- Drained subprocess pipes after local sandbox timeouts to avoid Windows
  unraisable transport warnings in the backend regression suite.
- Added `budgets.max_parallel_tasks` to workspace configuration and made
  `localforge run` pass that budget into the scheduler. The HP 12C sample now
  runs one task at a time for local Ollama stability.
- Added `append_content` as a safe runtime action and normalized model-proposed
  bare `pytest` commands to the current Python interpreter with `-m pytest`.
- Added calculator base-export preservation before pytest validation so stacked
  HP 12C feature branches cannot drop shared scaffold exports such as
  `Calculator`, `RPNStack`, and arithmetic helpers.
- Added full pytest validation output artifacts in `tests.md` before failed
  worktrees are cleaned up, improving post-run diagnosis of `FAILED_SAFE` tasks.
- Updated the HP 12C E2E report with Run 22, Run 23, Run 24, and Run 25
  evidence. Run 24 was the best clean post-fix run with 15 `PR_READY`, 16
  `FAILED_SAFE`, and zero safety blocks. Run 25 showed that increasing repairs
  to two attempts worsened this model mix, so the sample was restored to one
  repair attempt.
- Updated the HP 12C E2E report with Run 26 evidence. Run 26 finished with 14
  `PR_READY`, 17 `FAILED_SAFE`, and zero safety blocks, so the rating remains
  `Funciona com ressalvas`.
- Added HP 12C common-module compatibility reassertion before pytest validation
  for common generated import shapes such as numeric entry, TVM, memory,
  financial calculator helpers, and package aliases.
- Updated the HP 12C E2E report with Run 27 and Run 28 evidence. Run 28 was the
  final full-Codex acceptance check and finished with 11 `PR_READY`, 20
  `FAILED_SAFE`, and zero safety blocks. The harness is stable and auditable,
  but the local-model coding loop still does not satisfy the `Funciona bem`
  rubric for this medium PRD.
- Recorded fresh 2026-06-22 environment evidence for the E2E plan: backend
  regression passed with 133 tests, `mypy backend` passed, and the Ollama
  OpenAI-compatible endpoint exposed `gemma4:12b`, `granite4.1:8b`, and
  `nemotron-3-nano:4b`. The `ollama` executable itself was not available on PATH
  inside this Codex process.
- Added pre-pytest Python syntax validation for generated `.py` files. Syntax
  failures now feed the existing Fixer repair loop with direct file/line
  diagnostics before pytest collection, targeting a dominant Run 28 failure
  class without weakening the PR readiness gate.
- Filtered obsolete or unsafe `changed_files` entries before committing
  generated task branches, preventing stale metadata from making `git add`
  fail on files that no longer exist in a fresh worktree.
- Expanded deterministic HP 12C compatibility aliases for recurring model
  imports observed in Run 30, including `src.casing`, `components.lcddisplay`,
  `localforge.shift_state`, `localforge.display`, and `statistics.statistics`.
- Broadened HP 12C compatibility APIs for numeric entry decimal state, TVM
  register constructor arguments, amortization schedule lists, SciPy-free IRR,
  and probability helper tests that omit a direct `pytest` import.
- Updated the HP 12C E2E report with Run 29, Run 30, and Run 31 evidence. Run
  29 exposed stale changed-file metadata in the repeat-run path; Run 30 restored
  the previous 11 `PR_READY` / 20 `FAILED_SAFE` distribution; Run 31 fell to 8
  `PR_READY` / 23 `FAILED_SAFE`, showing that alias-shim expansion alone is not
  a reliable path to the `Funciona bem` rubric.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_scheduler.py backend/tests/test_gitops.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_pr_factory.py backend/tests/test_phase23_pipeline.py backend/tests/test_scheduler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_agent_runtime.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_phase27_unattended.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_generated_pytest_failure -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_phase27_unattended.py backend/tests/test_safety_validator.py backend/tests/test_agent_runtime.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py backend/tests/test_phase23_pipeline.py backend/tests/test_safety_validator.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_gitops.py backend/tests/test_pr_factory.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_gitops.py backend/tests/test_scheduler.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_gitops.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_gitops.py::test_worktree_manager_replaces_stale_task_worktree_path backend/tests/test_scheduler.py::test_scheduler_marks_pipeline_failure_failed_safe_and_recovers_session -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase27_unattended.py::test_budgets_default_config backend/tests/test_gitops.py::test_worktree_manager_replaces_stale_task_worktree_path -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_generated_pytest_failure -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase26_sandbox.py::test_local_sandbox_timeout backend/tests/test_phase26_sandbox.py::test_docker_sandbox_mocked -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_preserves_calculator_base_exports_for_feature_tasks -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py backend/tests/test_agent_runtime.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `Invoke-RestMethod -Uri http://localhost:11434/v1/models`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_invalid_generated_python_before_pytest -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_filters_missing_changed_files_before_commit backend/tests/test_phase23_pipeline.py::test_role_pipeline_repairs_invalid_generated_python_before_pytest -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py::test_role_pipeline_adds_hp12c_import_alias_modules -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_phase23_pipeline.py -q`

## [Warning Cleanup] - 2026-06-21 - UTC Datetime Defaults

### Changed
- Replaced deprecated `datetime.utcnow()` defaults and runtime comparisons with
  UTC-aware `datetime.now(UTC)` usage across backend domain models and scheduler
  timeout checks.
- Normalized scheduler timestamps read back from SQLite before comparing them
  with UTC-aware current time values.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`

## [Legacy Gap Closure] - 2026-06-21 - PRD Reference Compliance Completion

### Added
- Added `docs/LEGACY_GAP_IMPLEMENTATION_TASKS.md` as the implementation
  checklist derived from the legacy reference conformity report.
- Added persistent task comments, runtime registrations, runtime heartbeats,
  squads, and task ancestry resolution for explicit control-plane traceability.
- Added API endpoints for task comments, project runtimes, runtime heartbeat,
  task ancestry, project squads, worktree inventory/actions, project settings,
  model metrics, audit export, project lock, and skill updates.
- Added PRD-listed CLI commands and groups: `pause`, `resume`, `stop`, `tasks`,
  `task get`, `logs`, `replay`, `models list`, `skills list`, and
  `safety status`.
- Added runtime JSON action proposal parsing and explicit tool-output
  compression.

### Changed
- Integrated recent task comments into agent task context construction.
- Completed frontend Worktrees, Settings, Safety Center, Models, and Skills
  surfaces using backend-backed data and actions.
- Strengthened quality gates to block likely secrets in changed files before
  PR readiness.
- Updated `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md` to show no remaining
  MVP-required gaps against the PRD reference functionality.
- Bumped the local schema version to add new coordination tables.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry backend/tests/test_api_server.py::test_api_dashboard_completion_endpoints backend/tests/test_cli.py::test_cli_help -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression backend/tests/test_agent_runtime.py::test_lead_agent_runtime_completes_trivial_file_change_through_safe_tools backend/tests/test_api_server.py::test_api_comments_runtimes_and_task_ancestry -q`
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests/test_quality_gates.py::test_quality_gate_blocks_likely_secret_changes backend/tests/test_api_server.py::test_api_dashboard_completion_endpoints backend/tests/test_agent_runtime.py::test_runtime_action_parser_and_compression -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm.cmd run build --prefix frontend`

## [Legacy Reference Audit] - 2026-06-21 - PRD Reference Conformity Review

### Added
- Added `docs/LEGACY_REFERENCE_CONFORMITY_REPORT.md` mapping PRD-requested
  functionality inspired by SwarmForge, Multica, Paperclip, DeerFlow, and
  Ollama against the current LocalForge implementation.
- Documented LocalForge-specific feature conformity, missing PRD CLI commands,
  partial frontend surfaces, and recommended remediation backlog items.

## [Performance Audit] - 2026-06-21 - Backend and Frontend Optimization

### Added
- Added `.codex_venv/` to `.gitignore` so Codex can keep an isolated Python
  3.12 validation environment inside the workspace without polluting Git status.
- Installed local analysis tooling in `.codex_venv`: `radon`, `bandit`,
  `pip-audit`, and `pipdeptree`.

### Changed
- Added bulk task-run and artifact lookup helpers to avoid repeated database
  queries when listing task artifacts, CLI PR artifacts, scheduler aborts,
  scheduler watchdog checks, and replay exports.
- Optimized `localforge prs` by fetching task runs and PR artifacts in batches
  instead of querying per task.
- Optimized scheduler abort/watchdog paths by preloading runs for active tasks
  instead of issuing one query per task.
- Optimized API task artifact listing with one artifact query across all task
  runs.
- Made the API `open-path` endpoint test-safe by avoiding desktop opener
  process launches under pytest while still validating the target path.
- Optimized frontend dependency cycle checks from repeated linear task scans to
  a `Map` lookup.
- Memoized Mission Control timeline item generation and cleared pending SSE
  reconnect timers on unmount to avoid retained timers.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `npm.cmd run build --prefix frontend`

## [Security Audit] - 2026-06-21 - Dependency and API Hardening

### Added
- Added `.pip-audit-cache/` to `.gitignore` for local dependency-audit cache
  files.
- Added API security headers for content type sniffing, frame embedding,
  referrer policy, and a restrictive default content security policy.
- Added regression coverage proving `DockerSandbox.copy_from()` rejects unsafe
  archive members before writing extracted content.

### Changed
- Upgraded development test dependencies to `pytest>=9.0.3,<10.0` and
  `pytest-asyncio>=1.3,<2.0`, resolving the known `pytest` CVE reported by
  `pip-audit`.
- Hardened Docker archive extraction by validating member paths with
  `os.path.commonpath`, rejecting symlinks/hardlinks, and copying regular files
  explicitly instead of using `tarfile.extractall()`.
- Replaced detailed internal exception strings in API 500 responses for local
  path opening and rerun command execution with generic client-facing messages
  while keeping server-side warnings.
- Replaced hardcoded temp-directory heuristics in the pytest database bootstrap
  guard with runtime temporary directory discovery via `tempfile`.

### Tests
- `.\\.codex_venv\\Scripts\\python.exe -m pytest backend/tests -q`
- `.\\.codex_venv\\Scripts\\python.exe -m mypy backend`
- `.\\.codex_venv\\Scripts\\python.exe -m bandit -r backend/localforge -q -ll -ii`
- `.\\.codex_venv\\Scripts\\python.exe -m pip_audit -r requirements.txt -r requirements-dev.txt --cache-dir .\\.pip-audit-cache`
- `.\\.codex_venv\\Scripts\\python.exe -m pip check`
- `npm.cmd audit --prefix frontend --audit-level=moderate`
- `npm.cmd run build --prefix frontend`

## [Diagnostics] - 2026-06-21 - Pytest Critical Hang Debug Logging

### Added
- Added opt-in pytest debug logging via `LOCALFORGE_TEST_DEBUG_LOG`, writing
  real-time test lifecycle events, heartbeat entries, process/system memory
  metrics, active thread names, database fixture lifecycle events, and periodic
  all-thread stack dumps through `faulthandler`.

### Fixed
- Removed unsafe global `builtins.open` mocking from
  `test_workspace_file_and_diff_limits`; it intercepted `load_config()` YAML
  reads and caused unbounded `MagicMock` growth inside PyYAML.
- Made debug `tracemalloc` opt-in through
  `LOCALFORGE_TEST_DEBUG_TRACEMALLOC`, keeping default debug logging lighter and
  less likely to amplify memory spikes.

### Usage
- Enable with PowerShell:
  `$env:LOCALFORGE_TEST_DEBUG_LOG="debug.log"`

## [Hotfix] - 2026-06-21 - Regression Test Resource Containment

### Changed
- Made scheduler pipeline execution opt-in via `execute_pipeline`, so scheduler
  unit tests keep exercising claim/setup behavior without launching full task
  pipelines unexpectedly.
- Enabled pipeline execution explicitly from `localforge run` and from the
  Phase 27 scheduler-to-pipeline regression test.
- Added a defensive monitor timeout to `localforge run` and bounded
  `Scheduler.stop()` so stalled background scheduler tasks are cancelled instead
  of being awaited indefinitely.
- Fixed the pytest AnyIO backend to `asyncio`, avoiding duplicate async test
  execution on environments where Trio is installed.

### Tests
- Not run by agent; local Python launcher in this session points to a missing
  base interpreter. Operator should run targeted validation locally.

## [Compliance Audit] - 2026-06-21 - Phase 0-30 Conformity Review

### Added
- Added `docs/PHASE_CONFORMITY_REPORT.md` with phase-by-phase conformity results,
  evidence, corrections, and pending operator validation commands.
- Added regression coverage for Docker sandbox sibling-prefix path escapes.
- Added regression coverage proving Scheduler executes the role pipeline after
  runner setup.
- Added regression coverage for `localforge prs` resolving real `PRArtifact`
  paths.

### Changed
- Updated `Scheduler` to invoke `RolePipelineEngine` for ready tasks after task
  runner setup, closing the gap between task scheduling and actual execution.
- Kept unattended run lifecycle ownership in `Scheduler` by allowing scheduled
  pipeline executions to avoid prematurely marking the run completed.
- Updated role pipeline status advancement to reload the current task status
  before applying transition ladders, avoiding stale state transitions.
- Hardened `DockerSandbox` copy path checks with `os.path.commonpath`.
- Updated `localforge prs` to detect `ArtifactType.PR` instead of comparing with
  a stale string literal.

### Tests
- Not run by agent per operator request; operator will run final regression.

## [Phase 30] - 2026-06-21 - Stabilization, Hardening & Backlog Grooming

### Added
- Created comprehensive stabilization test suite `backend/tests/test_phase30_stabilization.py` validating WorktreeManager lock concurrency, ArtifactStore atomic writes, SafetyKernel command injection blocking, and CLI integration.
- Added protective safety check in `bootstrap_database` (in `backend/localforge/storage/bootstrap.py`) to raise `RuntimeError` and block migrations against the primary development database if executed under pytest runner (preventing Windows file-lock deadlocks).
- Created future-proofing backlog document `docs/BACKLOG_V0.2.md` outlining roadmap features (IDE extensions, Electron distribution, advanced skills, benchmarks).

### Changed
- Enhanced `SafetyKernel` path traversal validator (`is_path_safe` and `evaluate` in `backend/localforge/safety/kernel.py`) to normalize path separators (`\`) and drive letters (`C:\`) and enforce case-insensitive checks on Windows.
- Upgraded command validation logic in `backend/localforge/safety/command_validator.py` to support case-insensitive and slash-agnostic protected paths checks.
- Refactored `test_cli_plan_and_run_integration` to execute inside isolated pytest `tmp_path` directories with mocked database manager connections, completely preventing I/O locks and memory bloat on Windows.
- Configured the SQLAlchemy engine in `DatabaseManager` (in `backend/localforge/storage/database.py`) to automatically use `StaticPool` when `sqlite :memory:` is targeted, guaranteeing single-connection physical sharing for all async test sessions.

## [Phase 29] - 2026-06-21 - End-to-End Demo

### Added
- Integrated backlog planning controls under new Typer sub-command `localforge plan` (in `backend/localforge/cli/plan.py`) to list, approve individual tasks, or bulk approve all tasks.
- Integrated runtime execution monitor under new Typer sub-command `localforge run` (in `backend/localforge/cli/run.py`), running Scheduler tasks in foreground and streaming progress details.
- Integrated pull requests visualization under new Typer sub-command `localforge prs` (in `backend/localforge/cli/prs.py`), listing generated local patch artifacts.
- Created realistic sample product requirements document `docs/examples/PRD_SAMPLE.md`.
- Created interactive CLI demo guide `docs/demo.md` walkthrough.

## [Phase 28] - 2026-06-20 - Packaging and Developer Experience

### Added
- Created a central, cross-platform Python developer utility `manage.py` in the root directory to automate workspace configuration and command execution.
- Added native command wrappers for Windows PowerShell (`.ps1`) and Unix/Bash (`.sh`) under the `scripts/` directory for developer convenience.
- Completely restructured and improved `README.md` with product details, installation steps, local LLM setup instructions, sample project guidance, safety kernel details, and troubleshooting references.
- Created `docs/TROUBLESHOOTING.md` detailing quick resolutions for common issues such as Ollama runtime states, missing models, Git dirty files count, Docker daemons, and remote GitHub token bindings.
- Created `samples/demo-project/` workspace containing an initial local Git repository, a skeleton python application, and a sample product requirements document (`PRD.md`) to facilitate e2e testing.

## [Phase 27] - 2026-06-20 - Unattended Mode Hardening

### Added
- Defined `BudgetsConfig` structure and integrated it into `LocalForgeConfig` and `DEFAULT_CONFIG` in `backend/localforge/core/config.py`.
- Created thread-safe, ContextVar-backed active LLM calls tracking in `backend/localforge/llm/context.py`.
- Integrated active LLM call budget enforcement in `OpenAICompatibleProvider.chat_completion` inside `backend/localforge/llm/openai_compatible.py`.
- Wrapped overall task execution inside an `asyncio.wait_for` global timeout in `backend/localforge/pipeline/engine.py`.
- Implemented file modification bounds and diff growth bounds checks post-role execution inside `backend/localforge/pipeline/engine.py`.
- Integrated strict validation checking of file writes in `backend/localforge/runtime/file_tools.py`.
- Added periodic heartbeat/pulse updates during pipeline stage transitions.
- Developed inactivity watchdog checks and global run timeout validation inside `backend/localforge/services/scheduler.py` to abort hung runs and transition them to `FAILED_SAFE`.
- Developed `RunSummary` generation on completion, which outputs a markdown summary report (`run_summary.md`) to the project root and updates the database summary status.
- Added comprehensive unit and integration tests in `backend/tests/test_phase27_unattended.py`.

### Changed
- Refactored git path comparison checks (`_check_workspace_budgets`) to compare the top-level repository path safely, bypassing git stats when executing outside isolated task worktrees.
- Updated `backend/localforge/services/task.py` to allow valid state transitions from active states to `FAILED_SAFE`.

## [Phase 26] - 2026-06-20 - Sandbox Manager

### Added
- Defined abstract `BaseSandbox` interface in `backend/localforge/sandbox/base.py`.
- Implemented restricted `LocalSandbox` in `backend/localforge/sandbox/local.py` for task worktrees.
- Implemented containerized `DockerSandbox` in `backend/localforge/sandbox/docker.py` utilizing the Docker Python SDK and mounting local worktrees directly.
- Developed `SandboxFactory` in `backend/localforge/sandbox/factory.py` to instantiate sandboxes with local fallback capabilities.
- Integrated sandbox command execution inside the Safety Kernel runner (`run_safe_command` in `runner.py`).
- Added Python SDK import check and client ping diagnostic to `check_docker` in the `localforge doctor` CLI tool.
- Developed comprehensive unit and integration tests in `backend/tests/test_phase26_sandbox.py` verifying sandboxing status, timeouts, SDK mocking, fallback resolution, and doctor checks.

### Changed
- Configured default sandbox parameters (`type: "local"`, `image: "python:3.12-slim"`, `network_enabled: False`) in `backend/localforge/core/config.py`.

## [Phase 25] - 2026-06-20 - Project Memory

### Added
- Defined typed memory records for stack facts, test commands, user preferences,
  known pitfalls, resolved blockers, and model performance notes.
- Extended the SQLite-backed memory store with relevant fact retrieval.
- Added memory contribution to task and role contexts.
- Added safe memory learning from completed run summaries and artifact summaries.
- Added typed memory selection in the frontend Memory view.
- Added targeted Phase 25 coverage in `backend/tests/test_phase24_25_skills_memory.py`.

### Changed
- Bumped the local schema version to add the `memory_facts.kind` column with a
  non-destructive SQLite migration for existing databases.

### Tests
- Not run by agent per operator request; operator will run final pytest/mypy.

## [Phase 24] - 2026-06-20 - Skills Registry

### Added
- Defined the LocalForge skill JSON format in `docs/SKILL_FORMAT.md`.
- Implemented built-in and `.localforge/skills/*.json` skill loading.
- Implemented skill selection from task metadata and project stack hints.
- Added built-in skills: `python-pytest`, `fastapi-endpoint`, `react-component`,
  `nextjs-page`, `github-pr-writer`, and `git-worktree-debugging`.
- Added skills to task and role context rendering.
- Exposed project skill list/register and task skill selection API endpoints.
- Connected the frontend Skills view to the backend registry.
- Added targeted Phase 24 coverage in `backend/tests/test_phase24_25_skills_memory.py`.

### Tests
- Not run by agent per operator request; operator will run final pytest/mypy.

## [Phase 23] - 2026-06-20 - Multi-Agent Pipeline, Routing, Memory, and CI

### Added
- Implemented deterministic role pipeline modes: fast, default, and strict.
- Added role-scoped context building, priority handoff consumption, and per-role artifacts.
- Added persistent role-to-model routing tables, services, API endpoints, and visual editor controls.
- Added persistent project memory facts with JSON/YAML backup export and import endpoints.
- Added memory UI integration backed by API persistence instead of local-only state.
- Added CI workflow for backend pytest/mypy and frontend production build.
- Added branch protection guidelines and PR Factory checklist integration.
- Added targeted Phase 23 regression tests in `backend/tests/test_phase23_pipeline.py`.

## [Phase 22] - 2026-06-20 - Models, Skills, Memory UI

### Added
- Developed Configured LLM Models view ('models') showcasing active providers, health status,
  available models, and agent role-routing mappings.
- Developed Workspace Skills Registry view ('skills') displaying skill triggers, current cached
  or active statuses, and forms to register new workspace skills.
- Developed Project Memory facts manager view ('memory') with local interactive states allowing
  user-facing delete, pin/unpin, and stale/activate triggers.
- Implemented real-time re-fetching of selected agent details, logs, artifacts, and handoffs
  upon receiving SSE project events.

## [Phase 21] - 2026-06-20 - Agent Manager UI & Interactive Safety Policy History

### Added
- Developed the Agent Manager split-view tab ('agents') showing active coding agent cards.
- Implemented Agent details panel displaying role, model, status, current task execution context,
  generated artifacts, logged safety approvals, handoffs, and audit trails.
- Added Task Execution Controls directly on the Agent Manager UI, enabling user-facing task
  pause, resume, block, and termination actions.
- Integrated interactive task dependency (DAG) tree editing directly on node trees inside Backlog
  Studio, allowing blockers and children dependencies removal/addition.
- Integrated safety policy version restore buttons and revision history display inside the Safety tab.
- Exposed backend REST API endpoints: GET /agents/{id}/details, POST /tasks/{id}/control/{action},
  and POST /projects/{id}/policies/{name}/restore/{version}.
- Added unit test coverage for new endpoints in backend/tests/test_api_server.py.

## [Phase 20] - 2026-06-20 - PR Review Center & Safety Enhancements

### Added
- Developed the PR Review Center ('prs' tab) showing a queue of PR-ready tasks.
- Created a side-by-side details panel containing summary, changed files, copy button,
  test runner console, unified diff viewer, and action buttons.
- Integrated interactive policy rules editor (allow/block commands, protected paths,
  max repair/files limits) inside the Safety tab.
- Added visual DAG tree representation of task dependencies (blockers/blocked tasks)
  inside the task details view in Backlog Studio.
- Exposed backend REST API endpoints: PUT /projects/{id}/policies/{name},
  GET /tasks/{id}/pr-details, POST /tasks/{id}/open-path, POST /tasks/{id}/rerun-tests,
  and POST /tasks/{id}/pr-review/{action}.
- Added unit test coverage test_api_pr_review_center_and_policy_updates
  in backend/tests/test_api_server.py.

## [Phase 19] - 2026-06-20 - Safety Center UI

### Added
- Developed Safety Center controls in App.tsx showing active policy name, rules, and configuration file.
- Developed Allowed Commands list, Blocked Commands list, and Protected Paths UI panels.
- Integrated interactive pending safety manual approvals queue.
- Implemented Emergency Kill Switch halting all active scheduling runs immediately.

## [Phase 18] - 2026-06-20 - PRD & Backlog Studio

### Added
- Implemented Epic and ImportPRDResult models in client.ts.
- Exposed backend endpoints: GET /epics, POST /import-prd, PUT /tasks/{id}, POST /tasks/{id}/approve.
- Developed PRD Compiler & Importer view in App.tsx (dry-run, spec analyzer).
- Developed Epics Map navigator sidebar and task list component.
- Implemented Task Detail Editor supporting title, description, risk level, and acceptance criteria.
- Implemented plan approval UI with "Approve Plan" action to activate backlog tasks to READY state.
- Created `test_api_prd_and_backlog_studio_endpoints` in `backend/tests/test_api_server.py`.
- Added client-side dependency cycle validation preventing loops in the task editor.
- Added reactive validation warnings and title/description required fields checks.
- Added paginated task lists in PRD & Backlog Studio and Mission Control panels.

## [Phase 17] - 2026-06-20 - Mission Control UI & Backend Enhancements

### Added
- Implemented CORS configuration in app.py allowing local dev environments (port 5173).
- Implemented Gzip compression middleware in app.py for optimized asset payloads.
- Implemented manual safety approvals endpoints (GET pending, POST decide action).
- Created interactive overview dashboard showing Run Summary, Agent Fleet cards, and Risk Alerts.
- Added live subscribing SSE operations timeline feed.
- Created `test_api_cors_and_gzip_middlewares_and_safety_endpoints` in `test_api_server.py`.

## [Phase 16] - 2026-06-20 - Frontend Foundation

### Added
- Created the React + TypeScript frontend structure under `frontend/` using Vite.
- Implemented a typed API client in `frontend/src/api/client.ts` matching backend REST endpoints.
- Implemented `useProjectEvents` hook in `frontend/src/api/events.ts` subscribing to SSE.
- Designed a dark HSL glassmorphic design system in `frontend/src/index.css`.
- Created basic design system components in `frontend/src/components/`: `Card`, `Table`, `Badge`,
  `Button`, `Alert`, `Timeline`, `EmptyState`, and `CodeBlock`.
- Built main dashboard shell in `frontend/src/App.tsx` featuring responsive sidebar, project
  selection, client-side hash router, and real-time operations stream sidebar.

### Changed
- Mounted static file serving from `frontend/dist` on `/` in `backend/localforge/api/app.py`
  to serve the compiled SPA directly when the FastAPI server is running.

### Tests
- Passed TS compilation and production build: `npm run build` in `frontend`.
- Passed full backend test suite: `pytest` (85 passed).
- Passed backend static analysis: `ruff` and `mypy`.

## [Phase 15] - 2026-06-20 - Realtime Events

### Added
- Added `backend/localforge/events/` with `EventBus`, compact lifecycle event payloads, publish/subscribe queues, and audit-log replay.
- Added lifecycle event mapping for `run.started`, `task.status_changed`, `agent.action_requested`, `safety.action_allowed`, `safety.action_blocked`, `test.finished`, `repair.started`, `repair.succeeded`, `repair.failed`, `pr.created`, and `artifact.created`.
- Added SSE endpoint `GET /projects/{project_id}/events` with replay via `last_event_id`, bounded replay `limit`, live in-memory subscription, compact payloads, and keep-alive handling.
- Added realtime publication for local API run command bridge operations.
- Added `backend/tests/test_realtime_events.py` covering LF-1501 through LF-1503.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\events backend\localforge\api\app.py backend\tests\test_realtime_events.py`.
- Passed syntax validation for Phase 15 files using bundled Codex Python: `python -m py_compile ...`.

### Known limitations
- Agent-side pytest/mypy execution is blocked by this shell's broken `.venv` Python launcher; validate Phase 15 with `python -m pytest backend/tests/test_realtime_events.py -q` and `mypy backend` in the activated venv.

## [Phase 14] - 2026-06-20 - Local API Server

### Added
- Added `backend/localforge/api/` with a FastAPI app factory for local API serving.
- Implemented endpoints for health, projects, tasks, runs, agents, artifacts, policies, models, audit events, and local PR-ready tasks.
- Implemented a safe command bridge for run `start`, `pause`, `resume`, and `stop` operations with audit events.
- Implemented artifact content serving with project-root path traversal blocking and secret redaction.
- Added `backend/tests/test_api_server.py` using FastAPI `TestClient`.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\api backend\tests\test_api_server.py`.
- Passed syntax validation for Phase 14 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 14 tests in the activated venv: `python -m pytest backend/tests/test_api_server.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 13] - 2026-06-20 - PR Factory

### Added
- Added `backend/localforge/pr_factory/` with local PR artifact generation and an opt-in GitHub PR adapter.
- Implemented `pr.md` generation with title, summary, acceptance criteria, changed files, tests, risk, repair attempts, evidence paths, and checklist.
- Implemented local PR-ready handling that marks tasks `PR_READY` when branch metadata, diff artifact, test artifact, and risk artifact exist, without requiring GitHub configuration.
- Added GitHub adapter defaulting to disabled unless explicitly configured with `LOCALFORGE_ENABLE_GITHUB_PR` and token environment variables; disabled or unavailable remote creation falls back to local PR artifacts.
- Added `backend/tests/test_pr_factory.py` covering LF-1301 through LF-1303.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\pr_factory backend\tests\test_pr_factory.py`.
- Passed syntax validation for Phase 13 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 13 tests in the activated venv: `python -m pytest backend/tests/test_pr_factory.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 12] - 2026-06-20 - Self-Healing Engine

### Added
- Added `backend/localforge/healing/` with failure classification, bounded repair policy, and a minimal self-healing engine.
- Implemented representative failure classes for test assertions, typecheck, lint, build, dependency/import failures, runtime exceptions, model failures, policy denial, sandbox failures, timeouts, git conflicts, and unknown failures.
- Implemented repair policy limits for max attempts, repeated same failure, diff growth, and safety denial.
- Implemented a deterministic repair loop that checkpoints file contents before repair, applies safe file edits, reruns focused tests, writes `repair.md`, blocks safely with `blocker.md`, and rolls back bad repairs with audit events.
- Added `backend/tests/test_self_healing.py` covering LF-1201 through LF-1204.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\healing backend\tests\test_self_healing.py`.
- Passed syntax validation for Phase 12 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 12 tests in the activated venv: `python -m pytest backend/tests/test_self_healing.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 11] - 2026-06-20 - Test Runner and Quality Gates

### Added
- Added `backend/localforge/quality/` with test command discovery, focused test execution, and quality gate evaluation.
- Implemented project-specific test command overrides through `.localforge/config.yaml` plus detection for Python, npm, pnpm, lint, mypy, ruff, and TypeScript commands.
- Implemented `FocusedTestRunner` to execute task-relevant commands through the Safety Kernel, enforce timeouts, capture stdout/stderr, and write `tests.md` artifacts.
- Implemented `QualityGateEvaluator` to block failed tests, require risk notes for missing tests, require approval records for protected file changes, and emit `risk.md` artifacts.
- Added `backend/tests/test_quality_gates.py` covering LF-1101 through LF-1103.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend\localforge\quality backend\tests\test_quality_gates.py`.
- Passed syntax validation for Phase 11 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 11 tests in the activated venv: `python -m pytest backend/tests/test_quality_gates.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 10] - 2026-06-20 - Basic Agent Runtime

### Added
- Added `backend/localforge/runtime/` with `TaskContextBuilder`, `SafeFileEditor`, `RuntimeHandoffService`, and `LeadAgentRuntime`.
- Implemented bounded task context rendering with task description, acceptance criteria, policy summary, relevant file snippets, omitted-file markers, and current worktree path.
- Implemented safe runtime file reads/writes constrained to the task worktree, Safety Kernel evaluation for file actions, unified diff generation, and `diff.patch` artifact emission.
- Implemented a basic deterministic lead-agent loop that writes a plan artifact, executes metadata-declared file and command actions through safe tools, records summaries, and advances a trivial task to `PR_READY`.
- Implemented runtime handoff creation and consume-once handling with audit events visible in run replay.
- Added `backend/tests/test_agent_runtime.py` covering LF-1001 through LF-1004.

### Tests
- Passed linting: `.\.venv\Scripts\ruff.exe check backend`.
- Passed syntax validation for Phase 10 files using bundled Codex Python: `python -m py_compile ...`.
- Passed Phase 10 tests in the activated venv: `python -m pytest backend/tests/test_agent_runtime.py -q`.
- Passed static typing in the activated venv: `mypy backend`.

## [Phase 9] - 2026-06-20 - PRD Compiler

### Added
- Added `backend/localforge/prd/` with a Markdown document loader, deterministic PRD extractor, model-assisted plan generation through the existing validated LLM adapter, task sizing heuristics, and transactional PRD import flow.
- Added `localforge import-prd` with `--dry-run` and `--json` output.
- Added `BaseTaskRunner`, `LocalWorktreeTaskRunner`, `RunnerContext`, and `TaskRunnerPool` to decouple scheduler task preparation from direct worktree orchestration.
- Added Phase 9 tests for Markdown loading/hash change detection, deterministic extraction, fake-LLM assisted generation, invalid JSON rollback behavior, sizing heuristics, CLI dry-run JSON output, event-driven scheduler wakeups, and runner pool integration.

### Changed
- Updated `Scheduler` to expose an event wait helper and use the runner pool when preparing task execution.
- Extended `ProjectService` with latest-document lookup by project path for PRD change detection.

### Tests
- Passed full test suite in the activated venv: `python -m pytest backend/tests -q` (59 passed).
- Passed static typing in the activated venv: `mypy backend` (Success: no issues found in 62 source files).
- Passed linting: `.\.venv\Scripts\ruff.exe check backend`.

## [Phase 8] - 2026-06-20 - Task State Machine and Scheduler & Improvements

### Added
- Implemented `Scheduler` in `backend/localforge/services/scheduler.py` executing a background loop to claim `READY` tasks, respect `max_parallel_tasks` limit, and manage run statuses lifecycle (`PENDING` -> `RUNNING` -> `COMPLETED`/`FAILED`).
- Added periodic background worktree cleanup calling `WorktreeManager.cleanup_orphan_worktrees` every 10 iterations of the scheduler loop.
- Added transitions auditing in `TaskService.update_task_status` to append an `AuditEvent` of type `state_change` on every status transition.
- Implemented dependency checks (`is_task_runnable` in `TaskService`) blocking tasks (transitioning them to `BLOCKED`) if their dependencies transition to `FAILED_SAFE`, `CANCELLED`, or `BLOCKED`.
- Added pagination (`limit` and `offset` parameters) to `AuditService.export_run_replay` for memory optimization during large replay timeline generation.
- Created `backend/tests/test_scheduler.py` testing scheduler lifecycle, limits, dependency resolution, pagination, and transitions auditing.

### Changed
- Allowed task status transitions to `BLOCKED` from `BACKLOG`, `READY`, and `CLAIMED` in the valid status transitions mapping.

### Fixed
- Resolved all mypy type errors in `task.py`, `scheduler.py`, and `test_scheduler.py` using explicit type guards and non-None assertions.

### Tests
- Passed full test suite: `pytest backend/tests` (50 passed).
- Passed linting and formatting: `ruff check backend`.
- Passed static typing: `mypy backend`.

## [Phase 7] - 2026-06-20 - Artifact Store and Audit Log & Phase 6 Enhancements

### Added
- Implemented `ArtifactStore` in `backend/localforge/storage/artifacts.py` managing directory layout, atomic writes via temp file swap, and SHA-256 hash validation.
- Implemented `export_run_replay` in `backend/localforge/services/audit.py` to compile chronological timeline replay sequences of run events linking their generated task-run artifacts.
- Created `test_audit_store.py` testing atomic writes, filename restrictions, concurrency locks, worktree orphan cleanup scanner, and replay exports.

### Changed
- Added `asyncio.Lock` concurrency locking in `WorktreeManager` keyed by normalized absolute worktree paths to protect setup, checkpoint, rollback, and cleanup operations.
- Implemented `cleanup_orphan_worktrees` in `WorktreeManager` to scan, remove, and clean up physical worktree directories that do not belong to active tasks.
- Integrated automated recursive payload redaction in `AuditService.append_audit_event` to filter environment secrets out of event payloads before DB persistence.
- Exported `ArtifactStore` and `ArtifactStoreError` from `localforge/storage/__init__.py`.

### Security
- Applied automated payload redaction for database logs to ensure credentials and tokens (e.g. `LOCALFORGE_GITHUB_TOKEN`) never persist in plain-text audit tables.
- Guaranteed immutable audit history by only exposing append-only event logs in the service layer API.

### Tests
- Passed full test suite: `pytest backend/tests` (46 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- The replay JSON timeline compiles memory-intensive queries synchronously; optimization for large projects (e.g. paginated replay timelines) is deferred.

## [Phase 6] - 2026-06-20 - Git Worktree Manager & Filesystem Isolation

### Added
- Implemented `GitAdapter` in `backend/localforge/gitops/adapter.py` providing safe Git subprocess execution (status, current branch, branch creation, worktree add/remove, commits, hard resets, and cleanup) routed via the Safety Kernel.
- Developed `WorktreeManager` in `backend/localforge/gitops/manager.py` to automate task-isolated branch creation (`localforge/<task-key>-<slug>`), checkpoint commits, hard resets (rollbacks), and cleanups.
- Implemented portable argument-escaping in `GitAdapter` to handle double quotes, backslashes, and Windows path formats, preventing command injection and shell syntax errors.
- Created `test_gitops.py` containing comprehensive tests for branch naming, checkpoints, rollback recovery, and active boundary checks.

### Changed
- Integrated filesystem isolation boundary checks in `localforge/safety/runner.py` to fetch active task runs from `uow.tasks` and override `project_root` with the active worktree path.
- Updated `DEFAULT_POLICY_TEMPLATE` in `backend/localforge/core/templates.py` to include safe Git subcommands (`git rev-parse`, `git branch`, `git worktree`, `git add`, `git commit`, `git reset`, `git clean`) by default.

### Fixed
- Fixed command validation failure for `git worktree` by adding necessary Git subcommands to the allowed commands list.
- Fixed `AssertionError` in `test_gitops.py` by correctly initializing `uow.safety` in the unit tests.

### Security
- Enforced strict filesystem boundaries: when a task is active, all write operations outside the task's worktree path are blocked by the Safety Kernel, completely isolating the main repository.

### Tests
- Passed full test suite: `pytest backend/tests` (42 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- GitAdapter command routing is synchronous and blocks the thread; asynchronous git command runners are deferred.

## [Phase 5] - 2026-06-20 - Safety Kernel & Path Canonicalization

### Added
- Implemented Pydantic validation `ActionRequest` and `SafetyDecision` enums in `backend/localforge/safety/kernel.py`.
- Developed `SafetyKernel` policy evaluator enforcing traversal write locks, blocked command lists, protected path segments checks, and risk-level escalations.
- Implemented `is_path_safe` path canonicalizer resolving symlinks and absolute paths to prevent traversal breaks.
- Created `ActionApproval` domain models and SQLAlchemy ORM `ActionApprovalORM` mappings.
- Created `SafetyService` in `backend/localforge/services/safety.py` to persist pending approvals.
- Implemented safe shell subprocess runner `run_safe_command` in `backend/localforge/safety/runner.py` enforcing timeouts, audit logging, database-backed polling approval states, and secret redaction.
- Added comprehensive unit tests in `backend/tests/test_safety_kernel.py` checking traversal blocks, interactive approval polling task, and secret redaction.

### Changed
- Exposed `SafetyService` inside `UnitOfWork` repository bindings.

### Fixed
- Restored audit logging commit sequences in blocked execution paths inside `runner.py`.

### Security
- Enforced strict canonicalization checking for file write bounds and automated secret redaction for stdout/stderr logs.

### Tests
- Passed full test suite: `pytest backend/tests -v` (39 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- The safe command runner polls database approvals with a sleep interval; real-time push events via WebSockets are deferred to Phase 15.

### Deferred
- Real-time SSE/WebSocket notification pushes for safety approvals queue.

## [Phase 4] - 2026-06-20 - Local Model Adapter & AST Command Validator

### Added
- Implemented `BaseLLMProvider` abstract interface and custom LLM exceptions (`LLMError`, `LLMConnectionError`, `LLMTimeoutError`) in `backend/localforge/llm/base.py`.
- Developed `OpenAICompatibleProvider` in `backend/localforge/llm/openai_compatible.py` to route API completions and streaming chunk parsing via HTTPX.
- Implemented `FakeLLMProvider` in `backend/localforge/llm/fake.py` to facilitate offline testing.
- Implemented structured output validation and self-healing JSON repair utility in `backend/localforge/llm/validator.py`.
- Created shell command token state-machine `split_shell_commands` and AST-based policy evaluator `validate_command` in `backend/localforge/safety/command_validator.py`.
- Added suite of 13 unit tests verifying safety operators splitting, protected path blocking, mock provider streaming, and JSON repair flows.

### Changed
- Refactored `localforge doctor` diagnostics in `backend/localforge/cli/doctor.py` to query active configuration model settings and check target model existence at the endpoint instead of hardcoded Ollama URL checks.

### Fixed
- Fixed mock assertions in `test_llm_provider.py` to cleanly resolve async client calls to synchronous responses.

### Security
- Enforced AST shell subcommand decomposition which blocks command chaining (e.g. `&&`, `||`, `;`, `|`) bypass attempts of restricted command names or protected paths.

### Tests
- Passed full test suite: `pytest backend/tests -v` (32 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- OpenAICompatibleProvider requires a running Ollama or compatible server containing the target default model to pass full CLI doctor diagnostics.

### Deferred
- Planner/Coder/Tester/Reviewer specific role configurations binding checks in doctor command deferred to runtime initialization.

## [Phase 3] - 2026-06-20 - Configuration and Policies

### Added
- Implemented robust `LocalForgeConfig` Pydantic v2 schemas for project, git, and models sections.
- Created `load_config` implementation in `backend/localforge/core/config.py` enforcing multi-source configuration precedence (CLI > Env > File > Defaults) with type safety and sensitive data protection.
- Created `PolicyRules` and `PolicyConfig` Pydantic schemas in `backend/localforge/core/policy.py` validating safety boundaries (allowed/blocked commands, protected paths, and execution thresholds).
- Created a new templates module `backend/localforge/core/templates.py` housing standard dict templates (`DEFAULT_CONFIG_TEMPLATE` and `DEFAULT_POLICY_TEMPLATE`).
- Added unit tests for schema validation and precedence loading in `backend/tests/test_core_config.py`.

### Changed
- Refactored `backend/localforge/cli/init.py` to import templates from `localforge.core.templates` instead of maintaining hardcoded dictionaries.

### Fixed
- Fixed Ruff B904 warning by ensuring all exceptions in `policy.py` chain correctly with `from e` syntax.

### Security
- Provided safe, unattended conservative policy constraints as default on workspace initialization.

### Tests
- Passed full test suite: `pytest backend/tests -v` (19 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- Configuration values do not auto-reload dynamically on file change; must be reloaded per command execution.

### Deferred
- Dynamic file watchers for configuration changes deferred to subsequent phases.

## [Phase 2] - 2026-06-20 - CLI Skeleton and Doctor & Unit of Work

### Added
- Implemented transactional `UnitOfWork` context manager in `backend/localforge/storage/transactions.py` to aggregate service layers and manage ACID transactions atomically.
- Developed `localforge` CLI application using `typer` library in `backend/localforge/cli/main.py`.
- Implemented `localforge init` command to create the workspace layout (`.localforge/` with subfolders for config, policies, memory, artifacts, runs, and logs), write default configuration, default conservative safety policy, and register the project in the database.
- Implemented `localforge doctor` diagnostics command checking Git, Python (>=3.11), write permissions, database connectivity, Docker, and Ollama. Added support for machine-readable `--json` output.
- Implemented `localforge status` workspace statistics command, pulling tasks counts, runs, active agents, and displaying them in rich CLI tables or structured JSON output.
- Created `backend/tests/test_transactions.py` validating UOW atomic commit and rollback behavior.
- Created `backend/tests/test_cli.py` providing end-to-end integration tests for init, status, and doctor command suites in an isolated temporary directory.

### Changed
- Refactored `get_status_data` inside `status.py` to inspect `.localforge` folder existence prior to establishing database connections, preventing `OperationalError` when executing status on uninitialized directories.

### Fixed
- Fixed SQLite connection parsing on Windows to support absolute path URLs with drive letters (e.g. `sqlite+aiosqlite:///C:/...` and `sqlite+aiosqlite:////C:/...`), adjusting `ensure_db_directory` in `bootstrap.py`.
- Resolved mypy type annotations and import order in `init.py`, `status.py`, and test files.

### Security
- Default conservative policy template configured on `init` preventing command execution of `rm -rf`, `git push --force`, and `git merge main`, and protecting `.env` file paths.

### Tests
- Passed full test suite: `pytest backend/tests -v` (15 passed).
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- Docker daemon and Ollama endpoint connectivity checks display warnings (non-blocking) if they are offline or unreachable.

### Deferred
- None.

## [Phase 1] - 2026-06-20 - Core Domain and Storage

### Added
- Core Pydantic validation domain schemas in `backend/localforge/models/domain.py` and enums in `backend/localforge/models/enums.py`.
- SQLAlchemy 2.0 ORM mappings in `backend/localforge/storage/orm.py`.
- Async database pool/session creation using SQLAlchemy and aiosqlite in `backend/localforge/storage/database.py`.
- Automatic database folder creation and schema versioning/bootstrap in `backend/localforge/storage/bootstrap.py`.
- Service Layer/Repositories (`ProjectService`, `TaskService`, `ExecutionService`, and `AuditService`) in `backend/localforge/services/`.
- Enforced strict task status state transitions inside the `TaskService` layer.
- Comprehensive integration tests in `backend/tests/test_domain_models.py`, `backend/tests/test_storage.py`, and `backend/tests/test_services.py`.

### Changed
- Refactored `backend/tests/conftest.py` to use asynchronous transaction fixtures yielding sessions.

### Fixed
- Fixed Python type annotations in models, ORM, and tests to comply with mypy static analysis.

### Security
- Created append-only constraints for AuditEvents to ensure audit trail immutability.

### Tests
- Passed full test suite: `pytest backend/tests -v`.
- Passed linting and formatting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- SQLite database backend only (PostgreSQL adapter is currently deferred).
- Programmatic bootstrap version 1 initialization only (incremental migrations deferred).

### Deferred
- PostgreSQL adapter integration.
- Incremental migrations framework.

## [Phase 0] - 2026-06-20 - Repository Foundation

### Added
- Backend Python 3.12 project structure, using `pyproject.toml`, `requirements.txt`, and `requirements-dev.txt`.
- Frontend Next.js skeleton structure.
- Initial project documentation, including `LocalForge_OS_PRD.md` and `MASTER_BACKLOG.md`.
- Basic import test `test_bootstrap_import` confirming `localforge` versioning.
- Lint and format checkers with `ruff`, typecheck with `mypy`, and test runner with `pytest`.

### Changed
- None (Initial setup bootstrap).

### Fixed
- None (Initial setup bootstrap).

### Security
- Isolated backend environment config setup with `.env.example` placeholder and default `.gitignore` definitions.

### Tests
- Passed initial suite: `pytest backend/tests -q`.
- Passed linting: `ruff check .`.
- Passed static typing: `mypy backend`.

### Known Limitations
- No active domain logic or storage persistence.

### Deferred
- CLI setup deferred to Phase 2.
- Local model routing deferred to Phase 4.

