from types import SimpleNamespace

import pytest

from refund_agent.api.routes.orders import _lifecycle_status


class FakeDb:
    def __init__(self, refund_status: str | None) -> None:
        self.refund_status = refund_status

    def scalar(self, statement):  # type: ignore[no-untyped-def]
        del statement
        return (
            SimpleNamespace(status=self.refund_status)
            if self.refund_status is not None
            else None
        )


@pytest.mark.parametrize(
    ("ticket_status", "refund_status", "expected"),
    [
        (None, None, "DELIVERED"),
        ("RUNNING", None, "AFTER_SALES_PROCESSING"),
        ("WAITING_USER", None, "AFTER_SALES_PROCESSING"),
        ("WAITING_APPROVAL", None, "WAITING_APPROVAL"),
        ("MANUAL_REVIEW", "UNKNOWN", "MANUAL_REVIEW"),
        ("REJECTED", None, "REFUND_REJECTED"),
        ("FAILED", None, "AFTER_SALES_FAILED"),
        ("COMPLETED", "FAILED", "AFTER_SALES_FAILED"),
        ("COMPLETED", "SUCCEEDED", "REFUNDED"),
    ],
)
def test_order_lifecycle_status_uses_latest_business_outcome(
    ticket_status: str | None,
    refund_status: str | None,
    expected: str,
) -> None:
    order = SimpleNamespace(status="DELIVERED")
    ticket = SimpleNamespace(id="ticket-1", status=ticket_status) if ticket_status else None

    assert _lifecycle_status(FakeDb(refund_status), order, ticket) == expected  # type: ignore[arg-type]
