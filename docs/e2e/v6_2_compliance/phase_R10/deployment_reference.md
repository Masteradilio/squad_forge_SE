# LocalForge OS — CPU-Only Production Deployment Reference (V61C-1004)

## 1. Overview & Hardware Requirements

This document provides the canonical operational guide for deploying LocalForge OS in a supervised CPU-only environment.

### Minimum Hardware Specification
- **CPU**: 4 vCPUs / 4 cores x86_64 or ARM64.
- **RAM**: 8 GB minimum (16 GB recommended for concurrent workers).
- **Disk**: 50 GB persistent SSD storage (for SQLite DB, logs, and isolated worktree caches).
- **GPU**: None required. Core availability and execution operate 100% GPU-free.

---

## 2. Configuration & Secrets Management

All configuration variables MUST be provided via environment variables or a `.env` file loaded at startup. Hardcoded credentials in source files are strictly forbidden.

```bash
# Core Server Configuration
LOCALFORGE_VERSION=6.2.0
LOCALFORGE_ENV=production
LOCALFORGE_PORT=8000
DATABASE_URL=sqlite+aiosqlite:///data/localforge.db

# Least-Privilege Repository Connector Tokens
GITHUB_L1_READ_TOKEN=ghp_example_read_only_token
GITHUB_L2_DRAFT_TOKEN=ghp_example_draft_pr_token

# Feature Flags
ENABLE_DEEP_SWARM=false
```

---

## 3. Operational Procedures

### 3.1 Startup & Health Check
```bash
# Start backend server
uvicorn localforge.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Check health endpoint
curl http://localhost:8000/api/v1/health
```

### 3.2 Backup & Persistence Procedure
```bash
# Create consistent SQLite snapshot using online backup
python -c "
import sqlite3
src = sqlite3.connect('data/localforge.db')
bck = sqlite3.connect('backups/localforge_backup_$(date +%Y%m%d_%H%M%S).db')
src.backup(bck)
bck.close()
src.close()
"
```

### 3.3 Graceful Shutdown & Rollback
1. Send `SIGTERM` to the uvicorn process.
2. The server finishes active transactions, releases `PathLease` locks, and flushes `RunnerPool` tasks.
3. In case of rollback: restore the backed-up SQLite file and restart the server with the previous wheel release.
