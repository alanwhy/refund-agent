import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import DemoOrderScenario, UserRole
from refund_agent.models import DemoOrderCreation, Order, User


@dataclass(frozen=True)
class ScenarioSpec:
    fraud_flag: bool
    payment_behavior: str


SCENARIO_SPECS: dict[DemoOrderScenario, ScenarioSpec] = {
    DemoOrderScenario.AUTO_REFUND: ScenarioSpec(False, "success"),
    DemoOrderScenario.AMOUNT_APPROVAL: ScenarioSpec(False, "success"),
    DemoOrderScenario.RISK_APPROVAL: ScenarioSpec(True, "success"),
    DemoOrderScenario.PAYMENT_UNKNOWN: ScenarioSpec(False, "unknown"),
}


class DemoOrderNumberExhausted(RuntimeError):
    """Raised when a unique demo order number cannot be allocated."""


def generate_order_number() -> str:
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"ORD-DEMO-{datetime.now(UTC):%Y%m%d}-{suffix}"


def create_demo_order(
    db: Session,
    *,
    customer: User,
    product_name: str,
    amount: Decimal,
    scenario: DemoOrderScenario,
    request_id: str,
    created_by: User,
) -> tuple[Order, bool]:
    existing = db.scalar(
        select(DemoOrderCreation).where(DemoOrderCreation.request_id == request_id)
    )
    if existing is not None:
        order = db.get(Order, existing.order_id)
        if order is None:
            raise RuntimeError("Demo order idempotency record has no order")
        return order, True

    if customer.role != UserRole.CUSTOMER or not customer.active:
        raise ValueError("customer must be an active customer")
    if created_by.role != UserRole.ADMIN or not created_by.active:
        raise PermissionError("created_by must be an active administrator")

    order_number: str | None = None
    for _ in range(3):
        candidate = generate_order_number()
        if db.scalar(select(Order.id).where(Order.order_number == candidate)) is None:
            order_number = candidate
            break
    if order_number is None:
        raise DemoOrderNumberExhausted("Unable to allocate a unique demo order number")

    spec = SCENARIO_SPECS[scenario]
    order = Order(
        order_number=order_number,
        customer_id=customer.id,
        product_name=product_name,
        amount=amount,
        status="DELIVERED",
        delivered_at=datetime.now(UTC) - timedelta(days=2),
        product_tags=[],
        fraud_flag=spec.fraud_flag,
        payment_behavior=spec.payment_behavior,
    )
    db.add(order)
    db.flush()
    creation = DemoOrderCreation(
        request_id=request_id,
        order_id=order.id,
        created_by=created_by.id,
        scenario=scenario,
    )
    db.add(creation)
    append_audit(
        db,
        action="demo_order.created",
        entity_type="order",
        entity_id=order.id,
        actor_id=created_by.id,
        details={
            "customer_id": customer.id,
            "scenario": scenario,
            "amount": f"{amount:.2f}",
        },
        event_key=f"demo-order:{request_id}:created",
    )
    db.flush()
    return order, False
