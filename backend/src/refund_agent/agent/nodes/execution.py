from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from refund_agent.adapters.payment import MockPaymentGateway
from refund_agent.agent.state import RefundAgentState
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import (
    ApprovalStatus,
    ManualReviewCategory,
    RefundStatus,
    TicketStatus,
)
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.manual_review.service import ensure_manual_review
from refund_agent.models import ApprovalTask, Order, RefundRequest, Ticket


def execute_refund_node(
    payment: MockPaymentGateway,
) -> Callable[[RefundAgentState], dict[str, Any]]:
    def execute_refund(state: RefundAgentState) -> dict[str, Any]:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            order = db.get(Order, state.get("order_id")) if state.get("order_id") else None
            if ticket is None or order is None or order.customer_id != state["customer_id"]:
                raise PermissionError("Order ownership validation failed")
            if ticket.calculated_amount is None:
                raise ValueError("Refund amount was not calculated")
            approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id))
            if state.get("approval_required"):
                if approval is None or approval.status != ApprovalStatus.APPROVED:
                    raise PermissionError("Required approval is missing")
                if approval.approved_amount is None:
                    raise ValueError("Approved amount is missing")
                amount = Decimal(approval.approved_amount)
            else:
                amount = Decimal(ticket.calculated_amount)
            if amount <= 0 or amount > Decimal(ticket.calculated_amount):
                raise ValueError("Refund amount exceeds deterministic cap")

            key = f"{ticket.id}:refund"
            request = db.scalar(select(RefundRequest).where(RefundRequest.idempotency_key == key))
            if request is None:
                request = RefundRequest(
                    ticket_id=ticket.id,
                    idempotency_key=key,
                    amount=amount,
                    status=RefundStatus.PROCESSING,
                )
                db.add(request)
                db.flush()
            if request.status == RefundStatus.SUCCEEDED:
                ticket.status = TicketStatus.COMPLETED
                ticket.current_step = "completed"
                db.commit()
                return {"refund_request_id": request.id}
            if request.status == RefundStatus.UNKNOWN:
                ensure_manual_review(
                    db,
                    ticket=ticket,
                    category=ManualReviewCategory.PAYMENT_UNKNOWN,
                    run_id=state["run_id"],
                    node_name="execute_refund",
                )
                db.commit()
                return {"refund_request_id": request.id}

            result = payment.refund(order, amount, key)
            request.status = result.status
            request.payment_reference = result.reference
            ticket.approved_amount = amount
            if result.status == RefundStatus.SUCCEEDED:
                ticket.status = TicketStatus.COMPLETED
                ticket.current_step = "completed"
            elif result.status == RefundStatus.UNKNOWN:
                ensure_manual_review(
                    db,
                    ticket=ticket,
                    category=ManualReviewCategory.PAYMENT_UNKNOWN,
                    run_id=state["run_id"],
                    node_name="execute_refund",
                )
            else:
                ticket.status = TicketStatus.FAILED
                ticket.current_step = "payment_failed"
            append_audit(
                db,
                action="refund.executed",
                entity_type="refund",
                entity_id=request.id,
                ticket_id=ticket.id,
                details={
                    "amount": str(amount),
                    "status": result.status,
                    "payment_reference": result.reference,
                    "idempotency_key": key,
                },
                event_key=f"{ticket.id}:refund-v2:refund-executed",
                run_id=state["run_id"],
                node_name="execute_refund",
            )
            db.commit()
            return {"refund_request_id": request.id}

    return execute_refund
