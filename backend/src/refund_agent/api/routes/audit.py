from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from refund_agent.api.dependencies import DbSession, require_roles
from refund_agent.api.schemas import AuditView
from refund_agent.domain.enums import UserRole
from refund_agent.models import AuditEvent

router = APIRouter(prefix="/api/audit-events", tags=["audit"])
Admin = Depends(require_roles(UserRole.ADMIN))


@router.get("", response_model=list[AuditView], dependencies=[Admin])
def list_audit_events(
    db: DbSession,
    ticket_id: str | None = None,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if ticket_id:
        statement = statement.where(AuditEvent.ticket_id == ticket_id)
    if action:
        statement = statement.where(AuditEvent.action == action)
    return list(db.scalars(statement))
