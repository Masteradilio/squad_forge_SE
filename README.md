# LocalForge OS

LocalForge OS is a local-first autonomous software engineering operating system.

It is designed to transform a `PRD.md` and backlog into small, testable engineering tasks, run local AI agents, coordinate work through safe state machines, use local models through Ollama/OpenAI-compatible APIs, execute tests, perform bounded self-healing, and prepare Pull Requests for human review.

LocalForge OS must not depend on Codex, Antigravity, Claude, or cloud agents at runtime. Codex and Antigravity may be used only as development assistants while building the project.

## Current status

This repository is at project bootstrap stage.

The current source of truth is:

- `docs/LocalForge_OS_PRD.md`
- `docs/MASTER_BACKLOG.md`
- `CHANGELOG.md`
- `AGENTS.md`
- `GEMINI.md`

Implementation should follow `MASTER_BACKLOG.md` phase by phase.

## Core principles

- Local-first execution
- Clean-room reimplementation
- Safe unattended automation
- Human-reviewed Pull Requests
- No automatic merge to `main`
- No shell execution outside the Safety Kernel
- No Socratic gate behavior from implementation agents
- Data-Driven engineering decisions when details are missing

## Initial development setup

Recommended environment:

- Windows + Git Bash or WSL
- Python 3.12+
- Node.js LTS
- Git
- Docker Desktop, later phases
- Ollama, later phases

Create and activate a Python virtual environment:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Run initial checks:

```bash
python -m pytest backend/tests -q
ruff check .
mypy backend
```

## Development with Codex or Antigravity

Codex should read:

- `AGENTS.md`
- `.agents/skills/localforge-os/SKILL.md`

Gemini/Antigravity should read:

- `GEMINI.md`
- `.gemini/skills/localforge-os/SKILL.md`

Implementation agents must follow `MASTER_BACKLOG.md` and update `CHANGELOG.md` after every completed phase.

## License

MIT License. See `LICENSE`.
