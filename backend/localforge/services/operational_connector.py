"""Provider-neutral repository connector boundary for operational loops."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Page:
    items: list[object]
    next_cursor: str | None = None


@dataclass(frozen=True)
class IssueRecord:
    external_id: str
    number: int
    title: str
    body: str
    labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PullRequestRecord:
    external_id: str
    number: int
    title: str
    head_sha: str
    mergeable: bool | None = None
    has_conflicts: bool = False


@dataclass(frozen=True)
class ReviewThreadRecord:
    external_id: str
    pr_number: int
    commit_sha: str
    file_path: str
    line_number: int
    body: str
    resolved: bool = False


@dataclass(frozen=True)
class CheckRunRecord:
    external_id: str
    build_id: str
    commit_sha: str
    name: str
    conclusion: str
    failed_test: str | None = None
    log_excerpt: str = ""
    is_flaky: bool = False


@dataclass(frozen=True)
class DraftPullRequest:
    external_id: str
    number: int
    url: str
    title: str
    idempotency_key: str
    draft: bool = True


class OperationalRepositoryConnector(Protocol):
    """Least-capability connector contract consumed by operational loops."""

    def list_issues(self, cursor: str | None = None) -> Page: ...

    def list_pull_requests(self, cursor: str | None = None) -> Page: ...

    def list_review_threads(self, cursor: str | None = None) -> Page: ...

    def list_check_runs(self, cursor: str | None = None) -> Page: ...

    def create_draft_pr(
        self,
        *,
        title: str,
        branch: str,
        body: str,
        idempotency_key: str,
    ) -> DraftPullRequest: ...


class LocalRepositoryConnector:
    """Deterministic local connector for controlled tests and dry runs."""

    def __init__(
        self,
        *,
        issues: list[IssueRecord] | None = None,
        pull_requests: list[PullRequestRecord] | None = None,
        review_threads: list[ReviewThreadRecord] | None = None,
        check_runs: list[CheckRunRecord] | None = None,
        page_size: int = 50,
    ) -> None:
        self.issues = issues or []
        self.pull_requests = pull_requests or []
        self.review_threads = review_threads or []
        self.check_runs = check_runs or []
        self.page_size = page_size
        self.created_draft_prs: dict[str, DraftPullRequest] = {}

    def list_issues(self, cursor: str | None = None) -> Page:
        return self._page(self.issues, cursor)

    def list_pull_requests(self, cursor: str | None = None) -> Page:
        return self._page(self.pull_requests, cursor)

    def list_review_threads(self, cursor: str | None = None) -> Page:
        return self._page(self.review_threads, cursor)

    def list_check_runs(self, cursor: str | None = None) -> Page:
        return self._page(self.check_runs, cursor)

    def create_draft_pr(
        self,
        *,
        title: str,
        branch: str,
        body: str,
        idempotency_key: str,
    ) -> DraftPullRequest:
        existing = self.created_draft_prs.get(idempotency_key)
        if existing is not None:
            return existing
        number = len(self.created_draft_prs) + 1
        draft_pr = DraftPullRequest(
            external_id=f"local-pr-{number}",
            number=number,
            url=f"local://pull/{number}",
            title=title,
            idempotency_key=idempotency_key,
        )
        self.created_draft_prs[idempotency_key] = draft_pr
        return draft_pr

    def _page(self, items: Sequence[object], cursor: str | None) -> Page:
        start = int(cursor or "0")
        end = start + max(self.page_size, 1)
        next_cursor = str(end) if end < len(items) else None
        return Page(items=list(items[start:end]), next_cursor=next_cursor)


def fetch_all_pages(
    fetch_page: Callable[[str | None], Page],
    *,
    max_pages: int = 20,
) -> list[object]:
    """Read paginated connector results with a bounded loop."""
    cursor: str | None = None
    all_items: list[object] = []
    for _ in range(max_pages):
        page = fetch_page(cursor)
        all_items.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return all_items
    raise RuntimeError("Connector pagination exceeded max_pages.")


def sanitize_external_text(value: str) -> str:
    """Treat external provider text as untrusted data before model/context use."""
    return (
        value.replace("SYSTEM OVERRIDE", "[external text removed]")
        .replace("Ignore previous instructions", "[external text removed]")
        .replace("elevate autonomy", "[external text removed]")
    )
