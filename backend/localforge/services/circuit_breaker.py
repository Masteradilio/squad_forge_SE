import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from localforge.models import domain
from localforge.models.enums import CircuitScope, CircuitState, ProgressSignal
from localforge.storage.orm import CircuitBreakerStateORM

logger = logging.getLogger(__name__)

DEFAULT_MAX_IDENTICAL_ERRORS = 3
DEFAULT_MAX_STAGNATION_COUNT = 3
DEFAULT_COOLDOWN_SECONDS = 300  # 5 minutes


class CircuitBreakerService:
    """Service layer managing persistent Circuit Breakers, progress detection, and kill controls."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_breaker(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
    ) -> domain.CircuitBreakerState:
        """Get or initialize a CircuitBreakerState record for a target."""
        scope_str = scope.value if isinstance(scope, CircuitScope) else str(scope)
        stmt = (
            select(CircuitBreakerStateORM)
            .where(CircuitBreakerStateORM.project_id == project_id)
            .where(CircuitBreakerStateORM.scope == scope_str)
            .where(CircuitBreakerStateORM.target_id == target_id)
        )
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()

        if not orm_obj:
            new_breaker = domain.CircuitBreakerState(
                project_id=project_id,
                scope=scope,
                target_id=target_id,
                state=CircuitState.CLOSED,
            )
            orm_obj = CircuitBreakerStateORM.from_domain(new_breaker)
            self.session.add(orm_obj)
            await self.session.flush()

        return orm_obj.to_domain()

    async def check_breaker(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
    ) -> tuple[bool, CircuitState, str | None]:
        """Check whether execution can proceed for a target given its circuit breaker state.

        Returns:
            (can_proceed: bool, current_state: CircuitState, reason: str | None)
        """
        breaker = await self.get_or_create_breaker(project_id, scope, target_id)
        now = datetime.now(UTC)

        # Check if in OPEN state
        if breaker.state == CircuitState.OPEN:
            cooldown_until = breaker.cooldown_until
            if cooldown_until and cooldown_until.tzinfo is None:
                cooldown_until = cooldown_until.replace(tzinfo=UTC)

            # Check cooldown expiration
            if cooldown_until and now >= cooldown_until:
                # Transition to HALF_OPEN / COOLDOWN
                breaker.state = CircuitState.HALF_OPEN
                breaker.reason = f"Cooldown period expired at {cooldown_until}. Entering HALF_OPEN."
                await self._update_breaker_domain(breaker)
                return True, CircuitState.HALF_OPEN, breaker.reason
            return False, CircuitState.OPEN, breaker.reason or "Circuit breaker is OPEN"


        elif breaker.state == CircuitState.ESCALATED:
            return False, CircuitState.ESCALATED, breaker.reason or "Circuit breaker is ESCALATED awaiting human review"

        return True, breaker.state, breaker.reason

    async def record_failure(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
        fingerprint: domain.FailureFingerprint,
        max_identical: int = DEFAULT_MAX_IDENTICAL_ERRORS,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> domain.CircuitBreakerState:
        """Record a failure event and open the breaker if thresholds are exceeded."""
        breaker = await self.get_or_create_breaker(project_id, scope, target_id)
        breaker.consecutive_failures += 1

        fp_hash = fingerprint.fingerprint_hash
        breaker.last_fingerprint = fp_hash

        # Update fingerprint histogram
        counts = dict(breaker.fingerprint_counts)
        counts[fp_hash] = counts.get(fp_hash, 0) + 1
        breaker.fingerprint_counts = counts

        evidence = dict(breaker.evidence_json)
        evidence["last_failure"] = {
            "error_type": fingerprint.error_type,
            "normalized_message": fingerprint.normalized_message,
            "hash": fp_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        breaker.evidence_json = evidence

        # Trip criteria: identical failure repeated max_identical times
        if counts[fp_hash] >= max_identical:
            now = datetime.now(UTC)
            breaker.state = CircuitState.OPEN
            breaker.opened_at = now
            breaker.cooldown_until = now + timedelta(seconds=cooldown_seconds)
            breaker.reason = (
                f"Tripped: identical failure '{fingerprint.error_type}' "
                f"(hash: {fp_hash}) repeated {counts[fp_hash]} times."
            )
            logger.warning(f"Circuit breaker TRIPPED for {scope}:{target_id}: {breaker.reason}")

        return await self._update_breaker_domain(breaker)

    async def record_progress_signal(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
        record: domain.AttemptProgressRecord,
        max_stagnation: int = DEFAULT_MAX_STAGNATION_COUNT,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    ) -> domain.CircuitBreakerState:
        """Record a progress signal (PROGRESS, STAGNATION, REGRESSION, REPEATED_FAILURE)."""
        breaker = await self.get_or_create_breaker(project_id, scope, target_id)

        if record.signal == ProgressSignal.PROGRESS:
            breaker.stagnation_count = 0
            if breaker.state == CircuitState.HALF_OPEN:
                breaker.state = CircuitState.CLOSED
                breaker.consecutive_failures = 0
                breaker.reason = "Recovered: progress detected during HALF_OPEN probe."
        elif record.signal == ProgressSignal.STAGNATION:
            breaker.stagnation_count += 1
            if breaker.stagnation_count >= max_stagnation:
                now = datetime.now(UTC)
                breaker.state = CircuitState.OPEN
                breaker.opened_at = now
                breaker.cooldown_until = now + timedelta(seconds=cooldown_seconds)
                breaker.reason = (
                    f"Tripped: no progress detected across {breaker.stagnation_count} consecutive attempts."
                )
                logger.warning(f"Circuit breaker TRIPPED (stagnation) for {scope}:{target_id}")

        elif record.signal == ProgressSignal.REGRESSION:
            now = datetime.now(UTC)
            breaker.state = CircuitState.OPEN
            breaker.opened_at = now
            breaker.cooldown_until = now + timedelta(seconds=cooldown_seconds)
            breaker.reason = "Tripped: test regression detected (previously passing tests failed)."
            logger.warning(f"Circuit breaker TRIPPED (regression) for {scope}:{target_id}")

        elif record.signal == ProgressSignal.REPEATED_FAILURE:
            breaker.consecutive_failures += 1
            now = datetime.now(UTC)
            breaker.state = CircuitState.OPEN
            breaker.opened_at = now
            breaker.cooldown_until = now + timedelta(seconds=cooldown_seconds)
            breaker.reason = "Tripped: exact repeated failure fingerprint detected."

        return await self._update_breaker_domain(breaker)

    async def reset_breaker(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
        actor_id: str = "user",
        reason: str = "Manual reset",
    ) -> domain.CircuitBreakerState:
        """Manually reset a circuit breaker to CLOSED state."""
        breaker = await self.get_or_create_breaker(project_id, scope, target_id)
        breaker.state = CircuitState.CLOSED
        breaker.consecutive_failures = 0
        breaker.stagnation_count = 0
        breaker.fingerprint_counts = {}
        breaker.last_fingerprint = None
        breaker.opened_at = None
        breaker.cooldown_until = None
        breaker.reason = f"Reset by {actor_id}: {reason}"
        logger.info(f"Circuit breaker RESET for {scope}:{target_id} by {actor_id}")
        return await self._update_breaker_domain(breaker)

    async def escalate_breaker(
        self,
        project_id: int,
        scope: CircuitScope,
        target_id: str,
        reason: str,
    ) -> domain.CircuitBreakerState:
        """Escalate a circuit breaker to ESCALATED state requiring human decision."""
        breaker = await self.get_or_create_breaker(project_id, scope, target_id)
        breaker.state = CircuitState.ESCALATED
        breaker.opened_at = datetime.now(UTC)
        breaker.reason = f"Escalated for human review: {reason}"
        logger.warning(f"Circuit breaker ESCALATED for {scope}:{target_id}: {reason}")
        return await self._update_breaker_domain(breaker)

    async def list_breakers_for_project(self, project_id: int) -> list[domain.CircuitBreakerState]:
        """List all circuit breakers for a project."""
        stmt = (
            select(CircuitBreakerStateORM)
            .where(CircuitBreakerStateORM.project_id == project_id)
            .order_by(CircuitBreakerStateORM.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return [orm.to_domain() for orm in result.scalars().all()]

    async def _update_breaker_domain(self, breaker: domain.CircuitBreakerState) -> domain.CircuitBreakerState:
        stmt = select(CircuitBreakerStateORM).where(CircuitBreakerStateORM.id == breaker.id)
        result = await self.session.execute(stmt)
        orm_obj = result.scalar_one_or_none()
        if not orm_obj:
            raise ValueError(f"CircuitBreakerState with ID {breaker.id} not found")

        orm_obj.state = breaker.state.value if isinstance(breaker.state, CircuitState) else str(breaker.state)
        orm_obj.consecutive_failures = breaker.consecutive_failures
        orm_obj.stagnation_count = breaker.stagnation_count
        orm_obj.fingerprint_counts_json = breaker.fingerprint_counts
        orm_obj.last_fingerprint = breaker.last_fingerprint
        orm_obj.opened_at = breaker.opened_at
        orm_obj.cooldown_until = breaker.cooldown_until
        orm_obj.reason = breaker.reason
        orm_obj.evidence_json = breaker.evidence_json
        await self.session.flush()
        return orm_obj.to_domain()
