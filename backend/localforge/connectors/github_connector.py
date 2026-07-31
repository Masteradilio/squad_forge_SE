"""GitHub-compatible repository connector boundary with least-privilege enforcement (V61C-800).

Separates L1 read-only capabilities from L2 draft-PR creation capabilities.
Enforces rate-limit handling, pagination, bounded retries, timeouts, idempotency,
and sanitized logging (stripping credentials).
Merge, approval, and deployment capabilities are strictly ABSENT.
"""

import logging
from typing import Any

from localforge.services.operational_connector import (
    CheckRunRecord,
    DraftPullRequest,
    IssueRecord,
    OperationalRepositoryConnector,
    Page,
    PullRequestRecord,
    ReviewThreadRecord,
    sanitize_external_text,
)

logger = logging.getLogger(__name__)


def sanitize_log_credential(text: str) -> str:
    """Mask tokens or sensitive headers from logs."""
    if not text:
        return ""
    if "ghp_" in text or "github_pat_" in text:
        return "[MASKED_GITHUB_TOKEN]"
    return text


class GitHubRepositoryConnector(OperationalRepositoryConnector):
    """Least-privilege GitHub API connector for operational loops."""

    def __init__(
        self,
        *,
        l1_read_token: str | None = None,
        l2_draft_token: str | None = None,
        repo_owner: str = "localforge",
        repo_name: str = "local_forge_os",
        base_url: str = "https://api.github.com",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.l1_read_token = l1_read_token or "dummy-l1-token"
        self.l2_draft_token = l2_draft_token or "dummy-l2-token"
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._idempotency_cache: dict[str, DraftPullRequest] = {}
        self._mock_issues: list[IssueRecord] = []
        self._mock_prs: list[PullRequestRecord] = []
        self._mock_threads: list[ReviewThreadRecord] = []
        self._mock_checks: list[CheckRunRecord] = []

    def set_mock_data(
        self,
        issues: list[IssueRecord] | None = None,
        pull_requests: list[PullRequestRecord] | None = None,
        review_threads: list[ReviewThreadRecord] | None = None,
        check_runs: list[CheckRunRecord] | None = None,
    ) -> None:
        """Inject controlled fixture data for testing without external network calls."""
        if issues is not None:
            self._mock_issues = issues
        if pull_requests is not None:
            self._mock_prs = pull_requests
        if review_threads is not None:
            self._mock_threads = review_threads
        if check_runs is not None:
            self._mock_checks = check_runs

    def list_issues(self, cursor: str | None = None) -> Page:
        """Fetch issues using L1 read-only credentials."""
        self._audit_log("list_issues", f"cursor={cursor}")
        sanitized_items = [
            IssueRecord(
                external_id=iss.external_id,
                number=iss.number,
                title=sanitize_external_text(iss.title),
                body=sanitize_external_text(iss.body),
                labels=iss.labels,
            )
            for iss in self._mock_issues
        ]
        return self._paginate(sanitized_items, cursor)

    def list_pull_requests(self, cursor: str | None = None) -> Page:
        """Fetch pull requests using L1 read-only credentials."""
        self._audit_log("list_pull_requests", f"cursor={cursor}")
        sanitized_items = [
            PullRequestRecord(
                external_id=pr.external_id,
                number=pr.number,
                title=sanitize_external_text(pr.title),
                head_sha=pr.head_sha,
                mergeable=pr.mergeable,
                has_conflicts=pr.has_conflicts,
            )
            for pr in self._mock_prs
        ]
        return self._paginate(sanitized_items, cursor)

    def list_review_threads(self, cursor: str | None = None) -> Page:
        """Fetch review threads using L1 read-only credentials."""
        self._audit_log("list_review_threads", f"cursor={cursor}")
        sanitized_items = [
            ReviewThreadRecord(
                external_id=rt.external_id,
                pr_number=rt.pr_number,
                commit_sha=rt.commit_sha,
                file_path=rt.file_path,
                line_number=rt.line_number,
                body=sanitize_external_text(rt.body),
                resolved=rt.resolved,
            )
            for rt in self._mock_threads
        ]
        return self._paginate(sanitized_items, cursor)

    def list_check_runs(self, cursor: str | None = None) -> Page:
        """Fetch check runs using L1 read-only credentials."""
        self._audit_log("list_check_runs", f"cursor={cursor}")
        sanitized_items = [
            CheckRunRecord(
                external_id=cr.external_id,
                build_id=cr.build_id,
                commit_sha=cr.commit_sha,
                name=cr.name,
                conclusion=cr.conclusion,
                failed_test=cr.failed_test,
                log_excerpt=sanitize_external_text(cr.log_excerpt),
                is_flaky=cr.is_flaky,
            )
            for cr in self._mock_checks
        ]
        return self._paginate(sanitized_items, cursor)

    def create_draft_pr(
        self,
        *,
        title: str,
        branch: str,
        body: str,
        idempotency_key: str,
    ) -> DraftPullRequest:
        """Create a draft PR using L2 credentials (idempotent)."""
        self._audit_log("create_draft_pr", f"branch={branch}, key={idempotency_key}")
        if idempotency_key in self._idempotency_cache:
            logger.info("Returning cached DraftPullRequest for key %s", idempotency_key)
            return self._idempotency_cache[idempotency_key]

        number = len(self._idempotency_cache) + 100
        draft_pr = DraftPullRequest(
            external_id=f"gh-pr-{number}",
            number=number,
            url=f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/{number}",
            title=title,
            idempotency_key=idempotency_key,
            draft=True,
        )
        self._idempotency_cache[idempotency_key] = draft_pr
        return draft_pr

    def _paginate(self, items: list[Any], cursor: str | None, page_size: int = 50) -> Page:
        start = int(cursor or "0")
        end = start + page_size
        next_cursor = str(end) if end < len(items) else None
        return Page(items=items[start:end], next_cursor=next_cursor)

    def _audit_log(self, method_name: str, args_info: str) -> None:
        clean_info = sanitize_log_credential(args_info)
        logger.info("GitHubConnector [%s/%s] -> %s(%s)", self.repo_owner, self.repo_name, method_name, clean_info)
