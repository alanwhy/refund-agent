from decimal import Decimal

from sqlalchemy import select

from refund_agent.domain.enums import ApprovalStatus, TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import (
    ApprovalTask,
    Conversation,
    Message,
    RefundRequest,
    Ticket,
    User,
    WorkflowCheckpoint,
)
from refund_agent.workflows.refund import RefundWorkflow


def create_ticket(order_number: str) -> str:
    with SessionLocal() as db:
        customer = db.scalar(select(User).where(User.email == "customer@example.com"))
        assert customer is not None
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        db.flush()
        ticket = Ticket(customer_id=customer.id, conversation_id=conversation.id)
        db.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    sender="USER",
                    content=f"我想退货，订单号 {order_number}",
                ),
                ticket,
            ]
        )
        db.commit()
        return ticket.id


def test_low_risk_refund_completes_once() -> None:
    ticket_id = create_ticket("ORD-399")
    workflow = RefundWorkflow()
    workflow.run(ticket_id)
    workflow.run(ticket_id)
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refunds = list(
            db.scalars(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        )
        assert ticket is not None
        assert ticket.status == TicketStatus.COMPLETED
        assert ticket.approved_amount == Decimal("399.00")
        assert len(refunds) == 1


def test_high_value_refund_pauses_and_resumes() -> None:
    ticket_id = create_ticket("ORD-699")
    workflow = RefundWorkflow()
    workflow.run(ticket_id)
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id))
        checkpoint = db.scalar(
            select(WorkflowCheckpoint).where(WorkflowCheckpoint.ticket_id == ticket_id)
        )
        assert ticket is not None
        assert ticket.status == TicketStatus.WAITING_APPROVAL
        assert approval is not None
        assert checkpoint is not None
        assert db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id)) is None
        approval.status = ApprovalStatus.APPROVED
        approval.approved_amount = approval.suggested_amount
        db.commit()
    workflow.run(ticket_id, resume=True)
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.status == TicketStatus.COMPLETED


def test_unknown_payment_never_auto_retries() -> None:
    ticket_id = create_ticket("ORD-299-UNKNOWN")
    workflow = RefundWorkflow()
    workflow.run(ticket_id)
    workflow.run(ticket_id)
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refunds = list(
            db.scalars(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        )
        assert ticket is not None
        assert ticket.status == TicketStatus.MANUAL_REVIEW
        assert len(refunds) == 1
        assert refunds[0].status == "UNKNOWN"
