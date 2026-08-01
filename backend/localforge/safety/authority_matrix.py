"""Agent Authority Matrix — Enforces strict tool and file path permissions across all 10 Squad Roles."""

from typing import List, Tuple


class AgentAuthorityMatrix:
    """Enforces role-based file access boundaries to prevent role cross-contamination."""

    ROLE_PERMISSIONS = {
        "Scrum Master": {
            "allowed": ["docs/PRD.md", "docs/MASTER_BACKLOG.md", "tasks/"],
            "forbidden": ["src/", "backend/", "tests/", "Dockerfile"],
        },
        "Chief Engineer": {
            "allowed": ["types/", "contracts/", "docs/ADR.md", "schema.prisma"],
            "forbidden": ["src/modules/", "tests/unit/"],
        },
        "Developer": {
            "allowed": ["src/modules/", "src/components/"],
            "forbidden": ["tests/", "types/", "Dockerfile", ".env"],
        },
        "Senior Developer": {
            "allowed": ["src/", "lib/", "components/", "public/"],
            "forbidden": ["tests/", "types/", "Dockerfile", ".env"],
        },
        "QA Engineer": {
            "allowed": ["tests/", "e2e/", "pytest.ini", "jest.config.js"],
            "forbidden": ["src/", "lib/", "components/"],
        },
        "Bug Fixer": {
            "allowed": ["traceback_lines_only"],
            "forbidden": ["docs/ADR.md", "package.json"],
        },
        "Reviewer": {
            "allowed": [],  # Read-only audit
            "forbidden": ["src/", "tests/", "docs/"],
        },
        "PR Writer": {
            "allowed": ["CHANGELOG.md", "PR_BODY.md", "docs/release_notes.md"],
            "forbidden": ["src/", "tests/"],
        },
        "Safety Auditor": {
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
    ) -> Tuple[bool, str]:
        """Validate if a Squad role is authorized to perform a write operation on a target file."""
        if not is_write:
            return (True, "Read-only action authorized.")

        permissions = self.ROLE_PERMISSIONS.get(role_name)
        if not permissions:
            return (True, f"Unrestricted role '{role_name}'.")

        # Check explicit forbidden paths
        for forbidden in permissions["forbidden"]:
            if forbidden != "traceback_lines_only" and forbidden in target_filepath:
                return (
                    False,
                    f"Agent Authority Violation: Role '{role_name}' is STRICTLY FORBIDDEN "
                    f"from modifying '{target_filepath}'. Violation prevented by ActionGateway.",
                )

        # Developer roles forbidden from touching test suites (prevents test bypassing)
        if role_name in ["Senior Developer", "Developer"] and ("tests/" in target_filepath or "test_" in target_filepath):
            return (
                False,
                f"Agent Authority Violation: Developer role '{role_name}' is BLOCKED from modifying "
                f"test suite '{target_filepath}' to prevent bypassing test assertions.",
            )

        return (True, f"Action authorized for role '{role_name}'.")
