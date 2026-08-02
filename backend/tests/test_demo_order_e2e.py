from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select
from test_agent_graph import _tool_call, create_ticket, runtime_with

from refund_agent.demo_orders import create_demo_order
from refund_agent.domain.enums import (
    ApprovalStatus,
    DemoOrderScenario,
    TicketStatus,
)
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import (
    ApprovalTask,
    ManualReviewTask,
    RefundRequest,
    Ticket,
    User,
)


def _create_order(scenario: DemoOrderScenario, *, other_customer: bool = False) -> str:
    with SessionLocal() as db:
        email = "other@example.com" if other_customer else "customer@example.com"
        customer = db.scalar(select(User).where(User.email == email))
        admin = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert customer is not None and admin is not None
        order, _ = create_demo_order(
            db,
            customer=customer,
            product_name=f"全链路商品 {scenario}",
            scenario=scenario,
            request_id=f"e2e-{scenario}-{uuid4()}",
            created_by=admin,
        )
        db.commit()
        return order.order_number


def _submit_call(order_number: str, call_id: str) -> AIMessage:
    return _tool_call(
        "SubmitRefundContext",
        {
            "order_number": order_number,
            "reason": "全链路测试退款",
            "requested_action": "REFUND",
        },
        call_id,
    )


def test_generated_auto_refund_order_completes() -> None:
    order_number = _create_order(DemoOrderScenario.AUTO_REFUND)
    ticket_id = create_ticket(f"退款 {order_number}")
    runtime_with(
        _submit_call(order_number, "demo-auto"),
        AIMessage(content="退款 399.00 元已发起。"),
    ).start(ticket_id)

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        assert ticket is not None and ticket.status == TicketStatus.COMPLETED
        assert refund is not None and refund.status == "SUCCEEDED"
        assert db.scalar(
            select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id)
        ) is None
        assert db.scalar(
            select(ManualReviewTask).where(ManualReviewTask.ticket_id == ticket_id)
        ) is None


@pytest.mark.parametrize(
    ("scenario", "reason_fragment"),
    [
        (DemoOrderScenario.AMOUNT_APPROVAL, "超过自动退款上限"),
        (DemoOrderScenario.RISK_APPROVAL, "可疑退款信号"),
    ],
)
def test_generated_approval_orders_pause_and_resume(
    scenario: DemoOrderScenario,
    reason_fragment: str,
) -> None:
    order_number = _create_order(scenario)
    ticket_id = create_ticket(f"退款 {order_number}")
    runtime = runtime_with(
        _submit_call(order_number, f"demo-{scenario}"),
        AIMessage(content="退款已发起。"),
    )
    paused = runtime.start(ticket_id)
    assert paused["__interrupt__"]

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id))
        assert ticket is not None and ticket.status == TicketStatus.WAITING_APPROVAL
        assert approval is not None
        assert any(reason_fragment in reason for reason in approval.risk_reasons)
        approval.status = ApprovalStatus.APPROVED
        approval.approved_amount = approval.suggested_amount
        approval.version += 1
        db.commit()
        approval_id = approval.id
        approval_version = approval.version

    runtime.resume(
        ticket_id,
        {"kind": "approval", "approval_id": approval_id, "version": approval_version},
    )
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        assert ticket is not None and ticket.status == TicketStatus.COMPLETED
        assert refund is not None and refund.status == "SUCCEEDED"


def test_generated_unknown_payment_order_creates_technical_review() -> None:
    order_number = _create_order(DemoOrderScenario.PAYMENT_UNKNOWN)
    ticket_id = create_ticket(f"退款 {order_number}")
    runtime_with(_submit_call(order_number, "demo-payment-unknown")).start(ticket_id)

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        review = db.scalar(
            select(ManualReviewTask).where(ManualReviewTask.ticket_id == ticket_id)
        )
        assert ticket is not None and ticket.status == TicketStatus.MANUAL_REVIEW
        assert refund is not None and refund.status == "UNKNOWN"
        assert review is not None and review.category == "PAYMENT_UNKNOWN"
        assert db.scalar(
            select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id)
        ) is None


def test_generated_order_owned_by_another_customer_is_safely_rejected() -> None:
    order_number = _create_order(DemoOrderScenario.AUTO_REFUND, other_customer=True)
    ticket_id = create_ticket(f"退款 {order_number}")
    runtime_with(_submit_call(order_number, "demo-other-owner")).start(ticket_id)

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.status == TicketStatus.REJECTED
        assert ticket.order_id is None
        assert db.scalar(
            select(RefundRequest).where(RefundRequest.ticket_id == ticket_id)
        ) is None
