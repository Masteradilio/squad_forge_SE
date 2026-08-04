"""Agent Authority Matrix — Enforces strict tool and file path permissions across all 10 Squad Roles."""

import fnmatch
import os


class AgentAuthorityMatrix:
    """Enforces role-based file access boundaries to prevent role cross-contamination."""

    ROLE_PERMISSIONS = {
        "Scrum Master": {
            "allowed": ["docs/PRD.md", "docs/MASTER_BACKLOG.md", "tasks/"],
            "forbidden": ["src/", "backend/", "tests/", "Dockerfile"],
        },
            "Chief Engineer": {
                "allowed": ["*"],
                "forbidden": [".env", ".env.*", ".git/", ".localforge/"],
        },
        "Developer": {
            "allowed": ["src/", "app/", "frontend/", "backend/", "lib/", "components/"],
            "forbidden": ["tests/", "types/", "Dockerfile", ".env"],
        },
        "Senior Developer": {
            "allowed": ["src/", "app/", "frontend/", "backend/", "lib/", "components/", "public/"],
            "forbidden": ["tests/", "types/", "Dockerfile", ".env"],
        },
        "QA Engineer": {
            "allowed": ["tests/", "e2e/", "pytest.ini", "jest.config.js"],
            "forbidden": ["src/", "lib/", "components/"],
        },
        "Bug Fixer": {
            "allowed": ["src/", "frontend/", "backend/", "lib/", "components/"],
            "forbidden": ["tests/", ".env", ".git/", ".localforge/"],
        },
        "Reviewer": {
            "allowed": [],  # Read-only audit
            "forbidden": ["src/", "tests/", "docs/"],
        },
        "PR Writer": {
            "allowed": ["CHANGELOG.md", "PR_BODY.md", "docs/release_notes.md"],
            "forbidden": ["src/", "tests/"],
        },
        "Security Auditor": {
            "allowed": ["relatorio_conformidade_seguranca.md"],
            "forbidden": ["src/", "tests/"],
        },
        "E2E Release Tester": {
            "allowed": ["tests/e2e/", "relatorio_conformidade_funcional.md"],
            "forbidden": ["src/"],
        },
    }

    def validate_action_authority(
        self, role_name: str, target_filepath: str, is_write: bool = True
    ) -> tuple[bool, str]:
        """Validate if a Squad role is authorized to perform a write operation on a target file."""
        role_aliases = {
            "ChiefEngineer": "Chief Engineer",
            "SeniorDeveloper": "Senior Developer",
            "QAEngineer": "QA Engineer",
            "BugFixer": "Bug Fixer",
            "PRWriter": "PR Writer",
            "E2EReleaseTester": "E2E Release Tester",
        }
        role_name = role_aliases.get(role_name, role_name)
        if not is_write:
            return (True, "Read-only action authorized.")

        permissions = self.ROLE_PERMISSIONS.get(role_name)
        if role_name == "Safety Auditor":
            permissions = self.ROLE_PERMISSIONS.get("Security Auditor")
        if not permissions:
            return (False, f"Agent Authority Violation: unknown role '{role_name}' is denied.")

        normalized_target = os.path.normcase(target_filepath.replace("\\", "/")).replace("\\", "/").lstrip("./")

        def matches(pattern: str) -> bool:
            normalized_pattern = os.path.normcase(pattern.replace("\\", "/")).replace("\\", "/").lstrip("./")
            if normalized_pattern.endswith("/"):
                return normalized_target.startswith(normalized_pattern)
            return normalized_target == normalized_pattern or fnmatch.fnmatch(
                normalized_target, normalized_pattern
            )

        # Check explicit forbidden paths
        for forbidden in permissions["forbidden"]:
            if forbidden != "traceback_lines_only" and matches(forbidden):
                return (
                    False,
                    f"Agent Authority Violation: Role '{role_name}' is STRICTLY FORBIDDEN "
                    f"from modifying '{target_filepath}'. Violation prevented by ActionGateway.",
                )

        if not permissions["allowed"]:
            return (False, f"Agent Authority Violation: role '{role_name}' is read-only.")

        if not any(matches(allowed) for allowed in permissions["allowed"]):
            return (
                False,
                f"Agent Authority Violation: role '{role_name}' cannot modify '{target_filepath}'.",
            )

        # Developer roles remain forbidden from test suites even if a broad
        # allowed prefix is added later.
        if role_name in ["Senior Developer", "Developer"] and (
            normalized_target.startswith("tests/") or "/tests/" in normalized_target or "test_" in normalized_target
        ):
            return (
                False,
                f"Agent Authority Violation: Developer role '{role_name}' is BLOCKED from modifying "
                f"test suite '{target_filepath}' to prevent bypassing test assertions.",
            )

        return (True, f"Action authorized for role '{role_name}'.")
