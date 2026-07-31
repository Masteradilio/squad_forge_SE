import os

from localforge.models.enums import RunMode
from localforge.safety.runner import run_safe_command
from localforge.storage import UnitOfWork


class GitAdapterError(RuntimeError):
    """Raised when a Git command execution fails or returns a non-zero exit code."""

    pass


class GitAdapter:
    """Wrapper executing Git operations routed safely through the Safety Kernel runner."""

    def __init__(
        self,
        project_id: int,
        uow: UnitOfWork,
        run_id: int | None = None,
        task_id: int | None = None,
        run_mode: RunMode = RunMode.INTERACTIVE,
    ):
        self.project_id = project_id
        self.uow = uow
        self.run_id = run_id
        self.task_id = task_id
        self.run_mode = run_mode

    async def _execute_git(self, args: list[str], use_task_context: bool = True) -> str:
        """Helper routing the raw Git command list to the safety runner."""
        # Sanitize arguments portably using double quotes where necessary
        cmd_str = "git " + " ".join(
            f'"{a.replace(chr(34), chr(92) + chr(34))}"' if any(c in a for c in ' \t\n\v\f"') else a
            for a in args
        )

        # We can override the task ID (e.g. to None when adding worktrees from the main repository)
        effective_task_id = self.task_id if use_task_context else None

        code, out, err = await run_safe_command(
            project_id=self.project_id,
            command=cmd_str,
            uow=self.uow,
            run_id=self.run_id,
            task_id=effective_task_id,
            run_mode=self.run_mode,
        )

        if code != 0:
            raise GitAdapterError(
                f"Git command '{cmd_str}' failed with code {code}.\n"
                f"Stdout: {out.strip()}\nStderr: {err.strip()}"
            )
        return out

    async def status(self) -> str:
        """Execute git status in the active worktree context."""
        return await self._execute_git(["status"])

    async def current_branch(self) -> str:
        """Retrieve current active branch name."""
        out = await self._execute_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return out.strip()

    async def default_branch(self) -> str:
        """Find the remote origin HEAD branch or fall back to the current local branch."""
        try:
            out = await self._execute_git(["rev-parse", "--abbrev-ref", "origin/HEAD"])
            branch = out.strip()
            if branch.startswith("origin/"):
                return branch[7:]
            return branch
        except Exception:
            return await self.current_branch()

    async def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists locally or in refs/heads/."""
        try:
            # Check with rev-parse
            await self._execute_git(["show-ref", "--verify", f"refs/heads/{branch_name}"])
            return True
        except Exception:
            return False

    async def create_branch(self, branch_name: str) -> None:
        """Create a new local branch starting from HEAD."""
        await self._execute_git(["branch", branch_name])

    async def create_worktree(
        self, path: str, branch_name: str, base_branch: str | None = None
    ) -> None:
        """Create a new worktree directory mapping to branch.

        Must execute from the main repository context (overriding task_id to
        None).
        """
        # If path already exists, clean it up or allow git to handle it
        if os.path.exists(path):
            try:
                os.rmdir(path)
            except Exception:
                pass

        # Check if the branch exists
        exists = await self.branch_exists(branch_name)

        if exists:
            args = ["worktree", "add", path, branch_name]
        else:
            args = ["worktree", "add", "-b", branch_name, path]
            if base_branch:
                args.append(base_branch)

        # Run on the main repository root (overriding task_id to None so
        # safety kernel uses main project root)
        await self._execute_git(args, use_task_context=False)

    async def remove_worktree(self, path: str) -> None:
        """Remove a worktree registered directory from the main repository."""
        await self._execute_git(["worktree", "remove", path, "--force"], use_task_context=False)

    async def diff(self, base_ref: str | None = None) -> str:
        """Show unstaged/staged diff changes or compare against base ref."""
        args = ["diff"]
        if base_ref:
            args.append(base_ref)
        return await self._execute_git(args)

    async def commit(self, message: str) -> None:
        """Add all unstaged edits and commit changes into the active branch."""
        clean_msg = message.replace("`", "'")
        await self._execute_git(["add", "-A"])
        await self._execute_git(["commit", "-m", clean_msg, "--allow-empty"])

    async def commit_paths(self, paths: list[str], message: str) -> None:
        """Commit only selected relative paths in the active branch."""
        if not paths:
            return
        clean_msg = message.replace("`", "'")
        await self._execute_git(["add", "--", *paths])
        await self._execute_git(["commit", "-m", clean_msg, "--allow-empty"])

    async def reset_hard(self, ref: str) -> None:
        """Perform a hard reset to a specific git reference and clean directories."""
        await self._execute_git(["reset", "--hard", ref])
        await self._execute_git(["clean", "-fd"])

    async def current_commit_hash(self) -> str:
        """Get the hash of the current commit (HEAD)."""
        out = await self._execute_git(["rev-parse", "HEAD"])
        return out.strip()

    async def resolve_ref(self, ref: str, *, use_task_context: bool = True) -> str:
        """Resolve a Git ref to an immutable commit hash."""
        out = await self._execute_git(["rev-parse", ref], use_task_context=use_task_context)
        return out.strip()
