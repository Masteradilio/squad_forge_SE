"""Request-scoped tenant identity and fail-closed resource scoping.

The local installation keeps a backwards-compatible ``local`` tenant when no
tenant headers are supplied. Hosted/staging deployments must provide an
explicit tenant and user identity at the API boundary; services then reuse the
same context through ``AsyncSession.info``.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import HTTPException, Request


_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str = "local"
    user_id: str = "local-user"
    roles: frozenset[str] = frozenset({"owner"})


_current_context: ContextVar[TenantContext] = ContextVar(
    "localforge_tenant_context", default=TenantContext()
)


def normalize_tenant_id(value: str | None) -> str:
    tenant_id = (value or "local").strip().lower()
    if not _TENANT_RE.fullmatch(tenant_id):
        raise HTTPException(status_code=400, detail="Invalid tenant identifier")
    return tenant_id


def context_from_request(request: Request) -> TenantContext:
    environment = request.app.state.security_policy
    tenant_header = request.headers.get("x-tenant-id")
    user_id = (request.headers.get("x-user-id") or "local-user").strip()
    if not user_id or len(user_id) > 255:
        raise HTTPException(status_code=400, detail="Invalid user identifier")
    if environment.api_token and not tenant_header:
        raise HTTPException(status_code=400, detail="X-Tenant-ID is required")
    roles = frozenset(
        item.strip().lower()
        for item in (request.headers.get("x-tenant-roles") or "owner").split(",")
        if item.strip()
    )
    return TenantContext(
        tenant_id=normalize_tenant_id(tenant_header),
        user_id=user_id,
        roles=roles or frozenset({"member"}),
    )


def current_context() -> TenantContext:
    return _current_context.get()


def bind_context(context: TenantContext):
    return _current_context.set(context)


def reset_context(token: object) -> None:
    _current_context.reset(token)  # type: ignore[arg-type]


def session_tenant(session: object) -> str:
    info = getattr(session, "info", {})
    return str(info.get("tenant_id") or current_context().tenant_id)

