from dataclasses import dataclass
from decimal import Decimal

from refund_agent.models import Order


@dataclass(frozen=True)
class PaymentResult:
    status: str
    reference: str | None


class MockPaymentGateway:
    def refund(self, order: Order, amount: Decimal, idempotency_key: str) -> PaymentResult:
        if order.payment_behavior == "unknown":
            return PaymentResult("UNKNOWN", None)
        if order.payment_behavior == "failed":
            return PaymentResult("FAILED", None)
        return PaymentResult("SUCCEEDED", f"PAY-{idempotency_key[-12:].upper()}")
