from decimal import Decimal

from refund_agent.adapters.llm import FakeLLMClient
from refund_agent.audit.service import redact
from refund_agent.domain.enums import TicketIntent
from refund_agent.models import Order
from refund_agent.rules.engine import evaluate_risk


def test_fake_llm_extracts_refund_order() -> None:
    result = FakeLLMClient().classify("我要退款，订单 ORD-399")
    assert result.intent == TicketIntent.REFUND
    assert result.order_number == "ORD-399"
    assert result.confidence > 0.9


def test_amount_boundary_is_deterministic() -> None:
    order = Order(
        customer_id="customer",
        order_number="BOUNDARY",
        product_name="Boundary",
        amount=Decimal("500.00"),
        delivered_at=None,  # type: ignore[arg-type]
    )
    at_boundary = evaluate_risk(order, Decimal("500.00"), 0.99)
    over_boundary = evaluate_risk(order, Decimal("500.01"), 0.99)
    assert at_boundary.requires_approval is False
    assert over_boundary.requires_approval is True
    assert "AMOUNT_OVER_THRESHOLD" in over_boundary.rule_ids


def test_redaction_handles_nested_secrets() -> None:
    value = {
        "password": "plain",
        "nested": {"api_key": "secret", "message": "Bearer abc.def.ghi"},
    }
    assert redact(value) == {
        "password": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "message": "Bearer [REDACTED]"},
    }
