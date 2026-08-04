from typing import Any

# Default workspace configuration template (config.yaml)
DEFAULT_CONFIG_TEMPLATE: dict[str, Any] = {
    "version": 1,
    "project": {
        "name": "{project_name}",
    },
    "git": {
        "default_branch": "{default_branch}",
        "remote_url": "{remote_url}",
    },
    "models": {
        "provider": "omniroute",
        "base_url": "http://localhost:20128/v1",
        "default_model": "auto/best-free",
        "fallback_models": [
            "auto/coding:free",
        ],
    },
}

# Conservative default policy configuration template (policies/default.yaml)
DEFAULT_POLICY_TEMPLATE: dict[str, Any] = {
    "version": 1,
    "policy": {
        "name": "unattended_conservative",
        "allowed_commands": [
            "git status",
            "git diff",
            "git rev-parse",
            "git show-ref",
            "git branch",
            "git worktree",
            "git add",
            "git commit",
            "git reset",
            "git clean",
            "pytest",
            "python -m pytest",
            "ruff check",
            "mypy",
        ],
        "blocked_commands": [
            "rm -rf",
            "git push --force",
            "git merge main",
        ],
        "protected_paths": [
            ".env",
        ],
        "max_repair_attempts": 3,
        "max_files_touched": 10,
    },
}
