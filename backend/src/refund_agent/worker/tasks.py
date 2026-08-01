from datetime import UTC, datetime

from redis import Redis
from sqlalchemy import select

from refund_agent.agent.runtime import get_runtime
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import ApprovalStatus, TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import ApprovalTask, Ticket
from refund_agent.worker.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="refund_agent.run_workflow", bind=True, max_retries=2
)
def run_workflow(  # type: ignore[no-untyped-def]
    self,
    ticket_id: str,
    operation: str = "start",
    payload: dict[str, object] | None = None,
) -> None:
    redis = Redis.from_url(celery_app.conf.broker_url)
    lock = redis.lock(f"ticket:{ticket_id}", timeout=120, blocking_timeout=2)
    if not lock.acquire(blocking=True):
        raise self.retry(countdown=2)
    try:
        runtime = get_runtime()
        if operation == "start":
            runtime.start(ticket_id)
        elif operation == "resume":
            runtime.resume(ticket_id, dict(payload or {}))
        else:
            raise ValueError(f"Unknown workflow operation: {operation}")
    finally:
        if lock.owned():
            lock.release()


@celery_app.task(name="refund_agent.escalate_expired_approvals")  # type: ignore[untyped-decorator]
def escalate_expired_approvals() -> int:
    count = 0
    with SessionLocal() as db:
        approvals = db.scalars(
            select(ApprovalTask).where(
                ApprovalTask.status == ApprovalStatus.PENDING,
                ApprovalTask.expires_at < datetime.now(UTC),
            )
        )
        for approval in approvals:
            approval.status = ApprovalStatus.ESCALATED
            ticket = db.get(Ticket, approval.ticket_id)
            if ticket:
                ticket.status = TicketStatus.WAITING_APPROVAL
                ticket.current_step = "approval_escalated"
            append_audit(
                db,
                action="approval.escalated",
                entity_type="approval",
                entity_id=approval.id,
                ticket_id=approval.ticket_id,
            )
            count += 1
        db.commit()
    return count
