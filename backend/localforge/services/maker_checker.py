import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import AutonomyEnforcementResult, VerificationStatus
from localforge.storage.orm import MakerCheckerVerificationORM

logger = logging.getLogger(__name__)


class MakerCheckerService:
    """Service layer enforcing independent Maker/Checker verification and preventing self-approval."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_verification(
        self,
        project_id: int,
        task_run_id: int,
        maker_agent_id: str,
        checker_agent_id: str,
    ) -> domain.MakerCheckerVerification:
        """Initialize a new MakerCheckerVerification request."""
        # Validation: Maker and Checker cannot be the same agent/context ID
        if maker_agent_id == checker_agent_id:
            raise ValueError(
                f"Self-verification rejected: maker_agent_id ({maker_agent_id}) cannot be equal to checker_agent_id."
            )

        verification = domain.MakerCheckerVerification(
            project_id=project_id,
            task_run_id=task_run_id,
            maker_agent_id=maker_agent_id,
            checker_agent_id=checker_agent_id,
            status=VerificationStatus.PENDING,
        )
        orm_obj = MakerCheckerVerificationORM.from_domain(verification)
        self.session.add(orm_obj)
        await self.session.flush()
        return orm_obj.to_domain()

    async def submit_verification_result(
        self,
        verification_id: int,
        checker_agent_id: str,
        approved: bool,
        deterministic_passed: bool,
        tests_executed: list[str],
        not_checked: list[str],
        feedback: str | None = None,
    ) -> tuple[domain.MakerCheckerVerification, AutonomyEnforcementResult, str]:
        """Submit the verification decision from the independent Checker.

        Returns:
            (verification, enforcement_result, reason)
        """
        stmt = select(MakerCheckerVerificationORM).where(
            MakerCheckerVerificationORM.id == verification_id
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"MakerCheckerVerification with ID {verification_id} not found.")

        # Prevent spoofing: checker submitting result must match assigned checker_agent_id
        if orm_obj.checker_agent_id != checker_agent_id:
            reason = f"Role spoofing rejected: submitting agent '{checker_agent_id}' does not match assigned checker '{orm_obj.checker_agent_id}'."
            logger.warning(reason)
            return orm_obj.to_domain(), AutonomyEnforcementResult.DENIED_ROLE_SPOOFING, reason

        # Prevent self-approval
        if orm_obj.maker_agent_id == checker_agent_id:
            reason = f"Self-verification rejected: maker and checker share identical ID '{checker_agent_id}'."
            logger.warning(reason)
            return orm_obj.to_domain(), AutonomyEnforcementResult.DENIED_SELF_VERIFICATION, reason

        # Deterministic checks must pass
        if approved and not deterministic_passed:
            reason = "Verification rejected: deterministic tests/checks must pass before approval."
            logger.warning(reason)
            orm_obj.status = VerificationStatus.REJECTED.value
            orm_obj.checker_feedback = reason
            await self.session.flush()
            return orm_obj.to_domain(), AutonomyEnforcementResult.DENIED_AUTONOMY_EXCEEDED, reason

        orm_obj.deterministic_passed = deterministic_passed
        orm_obj.tests_executed_json = tests_executed
        orm_obj.not_checked_json = not_checked
        orm_obj.checker_feedback = feedback

        if approved:
            orm_obj.status = VerificationStatus.APPROVED.value
            reason = "Task verification APPROVED by independent checker."
        else:
            orm_obj.status = VerificationStatus.REJECTED.value
            reason = f"Task verification REJECTED by checker: {feedback}"

        await self.session.flush()
        return orm_obj.to_domain(), AutonomyEnforcementResult.ALLOWED, reason

    async def get_verification_for_task_run(
        self, task_run_id: int
    ) -> domain.MakerCheckerVerification | None:
        """Get the latest verification record for a task run."""
        stmt = (
            select(MakerCheckerVerificationORM)
            .where(MakerCheckerVerificationORM.task_run_id == task_run_id)
            .order_by(MakerCheckerVerificationORM.created_at.desc())
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        return orm_obj.to_domain() if orm_obj else None

    async def verify_pr_ready_eligibility(self, task_run_id: int) -> tuple[bool, str]:
        """Check if a task run has a valid, APPROVED independent verification required for PR_READY."""
        ver = await self.get_verification_for_task_run(task_run_id)
        if not ver:
            return False, f"Missing Maker/Checker verification record for task_run {task_run_id}."

        if ver.status != VerificationStatus.APPROVED:
            return False, f"Task verification status is '{ver.status.value}', expected APPROVED."

        if not ver.deterministic_passed:
            return False, "Deterministic checks did not pass for this task verification."

        return True, "Task run has valid independent verification."
