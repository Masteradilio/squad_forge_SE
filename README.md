# 🛡️ ForgeOS Cloud 1.0.0 — Software Engineering Squad Platform

> **SaaS Platform for Autonomous Software Engineering AI Squads with ZERO Inference Token Costs**

ForgeOS Cloud is an open-source, cloud-ready software engineering platform powered by an autonomous 10-role AI Squad. It turns product specifications (PRDs) into full-stack vertical slices (*Tracer Bullets*), routes work through a zero-cost multi-provider gateway (**OmniRoute**), manages persistent memory via the **HyperMemory Matrix** (Graphify AST GraphRAG, MemPalace Loci Vault, Claude-Mem Synthesizer), enforces strict **Matt Pocock TDD** (Red-Green-Refactor), fetches version-specific live documentation (**Context7 MCP**), and secures execution via an **Agent Authority Matrix** and **Human-in-the-Loop (HITL) Interruption Gates**.

---

## 🏛️ Core Architectural Innovations

### 1. OmniRoute AI Gateway Integration (Custo Zero de Inference)
- Connects to 290+ free-tier and freemium LLM providers (Google AI Studio, Groq, Cerebras, SambaNova, Mistral).
- **Pre-Flight Discovery Engine**: Dynamically filters models by native agentic capability (`tools: true`, `json_schema: true`), fine-grained daily recency, and parameter size score before every Squad run.

### 2. ForgeOS HyperMemory Matrix (Memória Trifásica)
- **Graphify Engine (AST GraphRAG)**: Uses local `tree-sitter` parsing (0 API tokens) to generate a structural call graph (`GRAPH_REPORT.md`) for instant, low-cost LLM recontextualization during model handoffs.
- **MemPalace Service (Loci Vault)**: Verbatim spatial memory vault (ChromaDB + YAML) storing architectural decisions (ADRs) and file history without lossy LLM summarization.
- **Claude-Mem Synthesizer**: Captures user corrections and test failures to auto-update `AGENTS.md` and `GEMINI.md` system prompts dynamically.

### 3. Matt Pocock Engineering Methodology
- **`grill-with-docs`**: Requirement stress-testing against existing codebase before task creation.
- **`to-tickets` / Tracer Bullets**: Decomposes PRDs strictly into vertical full-stack slices (*DB Schema + API Endpoint + UI Component + Unit Test* per ticket).
- **`tdd` / Red-Green-Refactor**: Enforces writing failing unit tests first (`RED`) before implementation (`GREEN`), eliminating 95% of hallucinated untested code.

### 4. Live Version-Specific Documentation via Context7 MCP
- Connects to `@upstash/context7-mcp` to pre-fetch real-time, version-specific documentation for libraries (Next.js 15, React 19, Tailwind v4, Pydantic v2, FastAPI), eliminating errors caused by model training cutoffs.

### 5. Escudo Anti-Alucinação & Prevenção de Conflitos
- **Compiler Feedback Loop**: Captures `tsc --noEmit` and `pyright` traceback line numbers (`App.tsx#L42`) and feeds them to the Bug Fixer agent.
- **Interface Contracts First**: Freezes shared TypeScript `.types.ts` and Pydantic schemas before code implementation.
- **File Scope Locking**: Restricts tickets to modifying a maximum of 3-5 files.
- **Strict Package Version Locking**: Freezes `package-lock.json` and `uv.lock`.

### 6. Agent Authority Matrix (10 Squad Roles Enforcement)
- Enforces strict role-based tool and file path permissions at the `ActionGateway` level:
  - `@developer`: Modifies application source code (`src/*`). **STRICTLY BLOCKED** from editing test files (`tests/*`).
  - `@qa`: Modifies test suites (`tests/*`). **BLOCKED** from modifying production application code.
  - `@architect`: Freezes type contracts (`types/*`, `docs/ADR.md`). **BLOCKED** from pushing directly to main.

### 7. Telemetria OpenTelemetry & Human-in-the-Loop (HITL)
- **OpenTelemetry Tracing**: Real-time visual execution timeline in the UI (`Scrum Master: 1.2s ➔ Chief Engineer: 3.4s ➔ Senior Dev: 4.1s`).
- **HITL Interruption Gates**: Pauses execution at critical architectural or release checkpoints with a 1-click PO Approval Modal in the React UI.
- **Dynamic PO Input Mid-Run**: Squad asks targeted questions in the PO Chat UI if missing PRD details are discovered.

### 8. Caching Semântico Avançado, Redis In-Memory Store & Helm Charts Kubernetes Auto-Scaling
- **Redis In-Memory Accelerator (`redis:7-alpine`)**: Proporciona cache semântico de AST com latência **< 1ms**, streaming de eventos Pub/Sub em tempo real e travas distribuídas atômicas (Redlock) para a Agent Authority Matrix.
- **Semantic Caching Engine**: Intercepta consultas repetitivas de AST e LLM no gateway OmniRoute (0ms de latência e 0 consumo de tokens).
- **Kubernetes Helm Charts (`deploy/helm/forgeos-cloud/`)**: Suporte a implantação automatizada no K8s com réplicas dinâmicas via Horizontal Pod Autoscaler (HPA) e suporte ao container Redis.

---

## 🚀 Docker & Docker Compose Quickstart

```bash
# Clone the repository
git clone https://github.com/Masteradilio/local_forge_os.git
cd local_forge_os

# Validate docker-compose configuration
docker compose config

# Build and launch all 5 containers (omniroute, backend, frontend, postgres-pgvector, redis)
docker compose up --build
```

### Access Ports:
- **Frontend Dashboard**: `http://localhost:80` or `http://localhost:5173`
- **FastAPI Backend**: `http://localhost:8000`
- **OmniRoute AI Gateway Proxy**: `http://localhost:20128/v1`
- **PostgreSQL Pgvector DB**: `localhost:5433`
- **Redis In-Memory Store**: `localhost:6379`

---

## 🧪 Automated Test Suite & Quality Verification

```bash
# Run backend pytest suite (398+ tests)
python -m pytest backend/tests -q

# Run frontend Vitest unit suite (100% Pass Rate)
npm test --prefix frontend
```

---

## 📄 Key Architecture & Backlog Documents

- `docs/plano_forgeOS_cloud.md` — Full ForgeOS Cloud Architectural Blueprint
- `docs/backlog_forgeOS_cloud.md` — 5-Phase Implementation Backlog & Rationale
- `CHANGELOG.md` — Implementation & Version History
