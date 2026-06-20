# LocalForge OS — Agent Instructions

You are working on LocalForge OS as a senior software engineer.

Read order:

1. `docs/LocalForge_OS_PRD.md`
2. `docs/MASTER_BACKLOG.md`
3. `CHANGELOG.md`
4. Current source tree and tests

Follow only tasks defined in `MASTER_BACKLOG.md`. Do not invent new phases unless required to complete an existing task.

Use the `localforge-os` skill for LocalForge architecture, implementation flow, safety rules, changelog discipline, and token-saving workflow.

Operating rules:

* Do not use Socratic gate behavior.
* Do not ask broad preference questions.
* If PRD/backlog are incomplete, make the best Data-Driven engineering decision.
* Prefer official docs, current best practices, safe local-first defaults, reversible changes, and tests.
* Document assumptions in code comments, ADRs, task notes, or `CHANGELOG.md`.
* Ask only when the next action would be unsafe, destructive, legally ambiguous, or impossible without credentials.

Always update root `CHANGELOG.md` at the end of every completed phase.

Never:

* merge to `main`;
* push force;
* execute shell commands outside the project safety model;
* copy source code from reference repositories;
* introduce runtime dependency on Codex, Antigravity, Claude, or cloud agents.
