from decimal import Decimal

from sqlalchemy import func, select
from test_agent_graph import create_ticket

from refund_agent.adapters.payment import MockPaymentGateway, PaymentResult
from refund_agent.agent.nodes.execution import execute_refund_node
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import AuditEvent, Order, RefundRequest, Ticket


class CountingPaymentGateway(MockPaymentGateway):
    def __init__(self) -> None:
        self.calls = 0

    def refund(self, order: Order, amount: Decimal, idempotency_key: str) -> PaymentResult:
        self.calls += 1
        return super().refund(order, amount, idempotency_key)


def test_refund_node_replay_does_not_repeat_payment_or_business_events() -> None:
    ticket_id = create_ticket("退款 ORD-399")
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        order = db.scalar(select(Order).where(Order.order_number == "ORD-399"))
        assert ticket is not None and order is not None
        ticket.order_id = order.id
        ticket.calculated_amount = Decimal("399.00")
        db.commit()
        order_id = order.id
        customer_id = ticket.customer_id

    gateway = CountingPaymentGateway()
    execute = execute_refund_node(gateway)
    state = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "order_id": order_id,
        "run_id": "replay-test-run",
        "approval_required": False,
    }

    first = execute(state)  # type: ignore[arg-type]
    second = execute(state)  # type: ignore[arg-type]

    assert first == second
    assert gateway.calls == 1
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count(RefundRequest.id)).where(RefundRequest.ticket_id == ticket_id)
        ) == 1
        assert db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.ticket_id == ticket_id,
                AuditEvent.action == "refund.executed",
            )
        ) == 1
