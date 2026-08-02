from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from refund_agent.demo_orders import DemoOrderNumberExhausted, create_demo_order
from refund_agent.domain.enums import DemoOrderScenario
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import (
    ApprovalTask,
    AuditEvent,
    DemoOrderCreation,
    ManualReviewTask,
    Order,
    RefundRequest,
    Ticket,
    User,
)


def _users(db):  # type: ignore[no-untyped-def]
    customer = db.scalar(select(User).where(User.email == "customer@example.com"))
    admin = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert customer is not None and admin is not None
    return customer, admin


@pytest.mark.parametrize(
    ("scenario", "amount", "fraud", "payment"),
    [
        (DemoOrderScenario.AUTO_REFUND, Decimal("399.00"), False, "success"),
        (DemoOrderScenario.AMOUNT_APPROVAL, Decimal("699.00"), False, "success"),
        (DemoOrderScenario.RISK_APPROVAL, Decimal("199.00"), True, "success"),
        (DemoOrderScenario.PAYMENT_UNKNOWN, Decimal("299.00"), False, "unknown"),
    ],
)
def test_demo_order_scenarios_are_deterministic(
    scenario: DemoOrderScenario,
    amount: Decimal,
    fraud: bool,
    payment: str,
) -> None:
    with SessionLocal() as db:
        customer, admin = _users(db)
        order, replayed = create_demo_order(
            db,
            customer=customer,
            product_name=f"场景商品 {scenario}",
            scenario=scenario,
            request_id=f"service-{scenario}-{uuid4()}",
            created_by=admin,
        )
        db.commit()
        assert replayed is False
        assert order.order_number.startswith("ORD-DEMO-")
        assert order.amount == amount
        assert order.fraud_flag is fraud
        assert order.payment_behavior == payment
        assert order.status == "DELIVERED"


def test_demo_order_creation_is_idempotent_and_has_no_refund_side_effects() -> None:
    request_id = f"service-idempotency-{uuid4()}"
    with SessionLocal() as db:
        customer, admin = _users(db)
        side_effect_counts_before = {
            model: db.scalar(select(func.count(model.id)))
            for model in (Ticket, ApprovalTask, ManualReviewTask, RefundRequest)
        }
        first, first_replayed = create_demo_order(
            db,
            customer=customer,
            product_name="首次商品",
            scenario=DemoOrderScenario.AUTO_REFUND,
            request_id=request_id,
            created_by=admin,
        )
        db.commit()
        first_id = first.id

    with SessionLocal() as db:
        customer, admin = _users(db)
        second, second_replayed = create_demo_order(
            db,
            customer=customer,
            product_name="不应覆盖的商品",
            scenario=DemoOrderScenario.PAYMENT_UNKNOWN,
            request_id=request_id,
            created_by=admin,
        )
        db.commit()
        assert first_replayed is False
        assert second_replayed is True
        assert second.id == first_id
        assert second.product_name == "首次商品"
        assert db.scalar(
            select(func.count(DemoOrderCreation.id)).where(
                DemoOrderCreation.request_id == request_id
            )
        ) == 1
        assert db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.action == "demo_order.created",
                AuditEvent.entity_id == first_id,
            )
        ) == 1
        assert db.scalar(select(func.count(Ticket.id)).where(Ticket.order_id == first_id)) == 0
        for model, count_before in side_effect_counts_before.items():
            assert db.scalar(select(func.count(model.id))) == count_before


def test_demo_order_number_retries_and_exhausts(monkeypatch: pytest.MonkeyPatch) -> None:
    with SessionLocal() as db:
        existing = db.scalar(select(Order).limit(1))
        customer, admin = _users(db)
        assert existing is not None
        monkeypatch.setattr(
            "refund_agent.demo_orders.service.generate_order_number",
            lambda: existing.order_number,
        )
        with pytest.raises(DemoOrderNumberExhausted):
            create_demo_order(
                db,
                customer=customer,
                product_name="冲突商品",
                scenario=DemoOrderScenario.AUTO_REFUND,
                request_id="service-number-conflict",
                created_by=admin,
            )
