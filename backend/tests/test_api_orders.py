from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_agent_graph import create_ticket

from refund_agent.api.app import app
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import ApprovalTask, Order, Ticket


def _headers(client: TestClient, email: str) -> dict[str, str]:
    login = client.post(
        "/api/auth/login", json={"email": email, "password": "Demo123!"}
    ).json()
    return {"Authorization": f"Bearer {login['access_token']}"}


def _approval_order() -> str:
    ticket_id = create_ticket("订单页面权限测试 ORD-699")
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        order = db.scalar(select(Order).where(Order.order_number == "ORD-699"))
        assert ticket is not None and order is not None
        ticket.order_id = order.id
        ticket.submitted_order_number = order.order_number
        ticket.status = "WAITING_APPROVAL"
        if db.scalar(
            select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id)
        ) is None:
            db.add(
                ApprovalTask(
                    ticket_id=ticket.id,
                    suggested_amount=Decimal("699.00"),
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
        db.commit()
        return order.id


def test_customer_only_sees_own_orders_and_safe_fields() -> None:
    with TestClient(app) as client:
        headers = _headers(client, "customer@example.com")
        response = client.get("/api/orders", headers=headers)
        assert response.status_code == 200
        orders = response.json()
        assert "ORD-500-OTHER" not in {item["order_number"] for item in orders}
        assert "ORD-399" in {item["order_number"] for item in orders}
        assert all(item["customer_id"] is None for item in orders)
        assert all(item["risk_reasons"] is None for item in orders)

        with SessionLocal() as db:
            other = db.scalar(
                select(Order).where(Order.order_number == "ORD-500-OTHER")
            )
            assert other is not None
            forbidden = client.get(f"/api/orders/{other.id}", headers=headers)
            assert forbidden.status_code == 404


def test_approver_only_sees_orders_with_visible_approval_tasks() -> None:
    visible_order_id = _approval_order()
    with TestClient(app) as client:
        headers = _headers(client, "approver@example.com")
        response = client.get("/api/orders", headers=headers)
        assert response.status_code == 200
        orders = response.json()
        assert visible_order_id in {item["id"] for item in orders}
        assert all(item["approval_status"] for item in orders)
        assert all(item["customer_name"] is None for item in orders)

        with SessionLocal() as db:
            ordinary = db.scalar(select(Order).where(Order.order_number == "ORD-399"))
            assert ordinary is not None
            hidden = client.get(f"/api/orders/{ordinary.id}", headers=headers)
            assert hidden.status_code == 404


def test_admin_sees_every_order_with_customer_summary() -> None:
    with TestClient(app) as client:
        headers = _headers(client, "admin@example.com")
        response = client.get("/api/orders", headers=headers)
        assert response.status_code == 200
        orders = response.json()
        assert {
            "ORD-399",
            "ORD-699",
            "ORD-199-FRAUD",
            "ORD-299-UNKNOWN",
            "ORD-500-OTHER",
        }.issubset({item["order_number"] for item in orders})
        assert all(item["customer_id"] for item in orders)
        assert all(item["customer_name"] for item in orders)
