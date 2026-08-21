# Contributing to Squad Forge SE

Squad Forge SE welcomes focused changes that improve safe, auditable, and economical
software-engineering automation.

## Before opening a change

1. Read `docs/LocalForge_OS_PRD.md` and `docs/MASTER_BACKLOG_V5.md`.
2. Open or reference an issue for behavioral, architectural, or dependency changes.
3. Keep benchmark implementations outside `backend/localforge/`.
4. Never include credentials, generated worktrees, runtime databases, or private source.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
localforge doctor
```

The frontend is installed separately:

```bash
npm ci --prefix frontend
```

## Change contract

Each pull request should state:

- the problem and intended behavior;
- files and public APIs changed;
- targeted validation performed;
- safety, compatibility, and migration impact;
- benchmark evidence when making quality or cost claims.

Start with the smallest relevant test. Do not weaken gates, replace failing tests with
placeholders, or add domain-specific success paths to the generic runtime.

## Commit and review policy

- Use small, reviewable commits.
- Do not merge automatically to the default branch.
- Human review is required for security, sandbox, provider, policy, and migration changes.
- Generated code must meet the same review standard as human-written code.
