import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubPRAdapter:
    enabled: bool = False
    token: str | None = None

    @classmethod
    def from_environment(cls) -> "GitHubPRAdapter":
        enabled = os.getenv("LOCALFORGE_ENABLE_GITHUB_PR", "").lower() in {"1", "true", "yes"}
        token = os.getenv("LOCALFORGE_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        return cls(enabled=enabled and bool(token), token=token)

    def create_pr(self, *, title: str, body: str, branch: str) -> str | None:
        if not self.enabled:
            return None
        # Remote PR creation is intentionally deferred until a configured CLI/API
        # transport exists. Returning None keeps the local PR artifact as source of truth.
        return None
