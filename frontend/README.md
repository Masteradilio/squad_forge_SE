# LocalForge Web Control Plane

The React/Vite frontend displays projects, task contracts, runs, model routing, costs,
safety decisions, worktrees, and PR evidence from the local FastAPI server.

## Development

```bash
npm ci
npm run dev
```

The development server proxies `/api` to `http://127.0.0.1:8000`.

## Validation

```bash
npm test
npm run lint
npm run build
```

Feature components should keep API types in `src/api/client.ts`, expose testable pure logic
where practical, and preserve keyboard-accessible controls. Avoid adding benchmark-specific
UI behavior to generic components.
