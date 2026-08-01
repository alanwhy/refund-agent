from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from refund_agent.api.dependencies import DbSession, require_roles
from refund_agent.api.schemas import ApprovalDecisionRequest, ApprovalView
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import (
    ApprovalDecision,
    ApprovalStatus,
    TicketStatus,
    UserRole,
)
from refund_agent.models import ApprovalTask, Message, Order, Ticket, User
from refund_agent.worker.tasks import run_workflow

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
Approver = Annotated[
    User,
    Depends(require_roles(UserRole.APPROVER, UserRole.ADMIN)),
]


def _view(db: DbSession, approval: ApprovalTask) -> ApprovalView:
    ticket = db.get(Ticket, approval.ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    customer = db.get(User, ticket.customer_id)
    return ApprovalView(
        id=approval.id,
        ticket_id=approval.ticket_id,
        status=approval.status,
        version=approval.version,
        risk_reasons=approval.risk_reasons or [],
        suggested_amount=approval.suggested_amount,
        approved_amount=approval.approved_amount,
        assigned_to=approval.assigned_to,
        order_number=order.order_number if order else None,
        product_name=order.product_name if order else None,
        customer_name=customer.display_name if customer else "未知客户",
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


@router.get("", response_model=list[ApprovalView])
def list_approvals(db: DbSession, user: Approver) -> list[ApprovalView]:
    statement = select(ApprovalTask).order_by(ApprovalTask.created_at.desc())
    if user.role == UserRole.APPROVER:
        statement = statement.where(
            (ApprovalTask.assigned_to.is_(None)) | (ApprovalTask.assigned_to == user.id)
        )
    return [_view(db, approval) for approval in db.scalars(statement)]


@router.get("/{approval_id}", response_model=ApprovalView)
def approval_detail(
    approval_id: str,
    db: DbSession,
    user: Approver,
) -> ApprovalView:
    approval = db.get(ApprovalTask, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if user.role == UserRole.APPROVER and approval.assigned_to not in {None, user.id}:
        raise HTTPException(status_code=404, detail="Approval not found")
    return _view(db, approval)


@router.post("/{approval_id}/decision", response_model=ApprovalView)
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    db: DbSession,
    user: Approver,
) -> ApprovalView:
    approval = db.get(ApprovalTask, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status not in {ApprovalStatus.PENDING, ApprovalStatus.ESCALATED}:
        raise HTTPException(status_code=409, detail="Approval is already decided")
    if user.role == UserRole.APPROVER and approval.assigned_to not in {None, user.id}:
        raise HTTPException(status_code=404, detail="Approval not found")
    try:
        decision = ApprovalDecision(payload.decision)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported decision") from exc
    if decision == ApprovalDecision.TRANSFER:
        if not payload.transfer_to:
            raise HTTPException(status_code=422, detail="transfer_to is required")
        target = db.get(User, payload.transfer_to)
        if target is None or target.role != UserRole.APPROVER:
            raise HTTPException(status_code=422, detail="Invalid transfer target")
        new_status = ApprovalStatus.PENDING
        assigned_to = target.id
        approved_amount = None
    elif decision == ApprovalDecision.REJECT:
        new_status = ApprovalStatus.REJECTED
        assigned_to = approval.assigned_to or user.id
        approved_amount = None
    else:
        new_status = ApprovalStatus.APPROVED
        assigned_to = approval.assigned_to or user.id
        approved_amount = payload.approved_amount or approval.suggested_amount
        if Decimal(approved_amount) > Decimal(approval.suggested_amount):
            raise HTTPException(status_code=422, detail="Approved amount exceeds refundable amount")
        if Decimal(approved_amount) <= 0:
            raise HTTPException(status_code=422, detail="Approved amount must be positive")

    values: dict[str, Any] = {
        "status": new_status,
        "assigned_to": assigned_to,
        "approved_amount": approved_amount,
        "comment": payload.comment,
        "version": payload.version + 1,
    }
    if decision != ApprovalDecision.TRANSFER:
        values.update({"decided_by": user.id, "decided_at": datetime.now(UTC)})
    result = db.execute(
        update(ApprovalTask)
        .where(ApprovalTask.id == approval_id, ApprovalTask.version == payload.version)
        .values(**values)
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Approval was changed by another user")
    ticket = db.get(Ticket, approval.ticket_id)
    if ticket is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Ticket not found")
    if decision == ApprovalDecision.REJECT:
        ticket.status = TicketStatus.REJECTED
        ticket.current_step = "approval_rejected"
        db.add(
            Message(
                conversation_id=ticket.conversation_id,
                sender="ASSISTANT",
                content="退款申请未获批准。如需进一步帮助，请联系人工客服。",
                dedup_key=f"{ticket.id}:terminal:{TicketStatus.REJECTED}",
            )
        )
    elif decision == ApprovalDecision.TRANSFER:
        ticket.current_step = "approval_transferred"
    else:
        ticket.approved_amount = approved_amount
        ticket.status = TicketStatus.RUNNING
        ticket.current_step = "approval_approved"
    append_audit(
        db,
        action=f"approval.{decision.value.lower()}",
        entity_type="approval",
        entity_id=approval.id,
        ticket_id=ticket.id,
        actor_id=user.id,
        details={"approved_amount": str(approved_amount) if approved_amount else None},
    )
    db.commit()
    db.refresh(approval)
    if decision != ApprovalDecision.TRANSFER:
        run_workflow.delay(
            ticket.id,
            "resume",
            {"kind": "approval", "approval_id": approval.id, "version": approval.version},
        )
    return _view(db, approval)
