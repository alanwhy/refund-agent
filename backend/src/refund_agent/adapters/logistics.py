from dataclasses import dataclass
from datetime import datetime

from refund_agent.models import Order


@dataclass(frozen=True)
class LogisticsSnapshot:
    order_number: str
    status: str
    delivered_at: datetime


class MockLogisticsGateway:
    def lookup(self, order: Order) -> LogisticsSnapshot:
        return LogisticsSnapshot(
            order_number=order.order_number,
            status="DELIVERED" if order.status == "DELIVERED" else order.status,
            delivered_at=order.delivered_at,
        )
