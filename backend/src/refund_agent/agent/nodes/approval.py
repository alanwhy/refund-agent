from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select

from refund_agent.agent.state import RefundAgentState
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import ApprovalStatus, TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import ApprovalTask, Message, Ticket


def approval_interrupt(state: RefundAgentState) -> dict[str, Any]:
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket is None or not state.get("amount_cap"):
            raise ValueError("Incomplete approval state")
        approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id))
        if approval is None:
            approval = ApprovalTask(
                ticket_id=ticket.id,
                risk_reasons=state.get("risk_reasons", []),
                suggested_amount=Decimal(state["amount_cap"]),
                expires_at=datetime.now(UTC) + timedelta(minutes=30),
            )
            db.add(approval)
            db.flush()
        ticket.status = TicketStatus.WAITING_APPROVAL
        ticket.current_step = "waiting_approval"
        ticket.waiting_for = "APPROVAL"
        question_key = f"{ticket.id}:approval-requested"
        if db.scalar(select(Message).where(Message.dedup_key == question_key)) is None:
            db.add(
                Message(
                    conversation_id=ticket.conversation_id,
                    sender="ASSISTANT",
                    content="退款申请已核验，当前需要人工审批。审批完成后会自动继续处理。",
                    dedup_key=question_key,
                )
            )
        append_audit(
            db,
            action="workflow.interrupted",
            entity_type="approval",
            entity_id=approval.id,
            ticket_id=ticket.id,
            details={"kind": "approval", "risk_reasons": state.get("risk_reasons", [])},
            event_key=f"{ticket.id}:refund-v2:approval-interrupted",
            run_id=state["run_id"],
            node_name="approval_interrupt",
        )
        db.commit()
        approval_id = approval.id

    resumed = interrupt(
        {
            "kind": "approval",
            "ticket_id": state["ticket_id"],
            "approval_id": approval_id,
            "amount_cap": state["amount_cap"],
            "risk_reasons": state.get("risk_reasons", []),
        }
    )
    if not isinstance(resumed, dict):
        raise ValueError("Invalid approval resume payload")
    with SessionLocal() as db:
        approval = db.get(ApprovalTask, approval_id)
        ticket = db.get(Ticket, state["ticket_id"])
        if approval is None or ticket is None:
            raise ValueError("Approval not found")
        if resumed.get("approval_id") != approval.id:
            raise PermissionError("Approval resume payload does not match checkpoint")
        if resumed.get("version") != approval.version:
            raise PermissionError("Approval resume version does not match database state")
        if approval.status == ApprovalStatus.APPROVED:
            if approval.approved_amount is None:
                raise ValueError("Approved amount is missing")
            if Decimal(approval.approved_amount) > Decimal(state["amount_cap"]):
                raise ValueError("Approved amount exceeds deterministic cap")
            ticket.status = TicketStatus.RUNNING
            ticket.current_step = "approval_approved"
            ticket.waiting_for = None
            ticket.approved_amount = approval.approved_amount
            route = "execute_refund"
        elif approval.status == ApprovalStatus.REJECTED:
            ticket.status = TicketStatus.REJECTED
            ticket.current_step = "approval_rejected"
            ticket.waiting_for = None
            route = "respond"
        else:
            raise ValueError("Approval is not in a resumable state")
        append_audit(
            db,
            action="workflow.resumed",
            entity_type="approval",
            entity_id=approval.id,
            ticket_id=ticket.id,
            details={"kind": "approval", "status": approval.status},
            event_key=f"{ticket.id}:refund-v2:approval-resumed:{approval.version}",
            run_id=state["run_id"],
            node_name="approval_interrupt",
        )
        db.commit()
    return {"approval_id": approval_id, "route": route, "waiting_for": None}


def route_after_approval(state: RefundAgentState) -> str:
    return state.get("route", "manual")
