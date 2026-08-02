from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from refund_agent.api.app import app
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import Order, User


def _headers(client: TestClient, email: str) -> dict[str, str]:
    payload = client.post(
        "/api/auth/login", json={"email": email, "password": "Demo123!"}
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_only_admin_can_list_demo_customers() -> None:
    with TestClient(app) as client:
        admin_headers = _headers(client, "admin@example.com")
        response = client.get("/api/demo/customers", headers=admin_headers)
        assert response.status_code == 200
        assert {item["email"] for item in response.json()} >= {
            "customer@example.com",
            "other@example.com",
        }
        assert set(response.json()[0]) == {"id", "display_name", "email"}

        for email in ("customer@example.com", "approver@example.com"):
            assert client.get(
                "/api/demo/customers", headers=_headers(client, email)
            ).status_code == 403


@pytest.mark.parametrize(
    "scenario",
    ["AUTO_REFUND", "AMOUNT_APPROVAL", "RISK_APPROVAL", "PAYMENT_UNKNOWN"],
)
def test_admin_creates_demo_order_and_replay_is_idempotent(scenario: str) -> None:
    request_id = f"api-{scenario}-{uuid4()}"
    with SessionLocal() as db:
        customer = db.scalar(select(User).where(User.email == "customer@example.com"))
        assert customer is not None
        customer_id = customer.id

    with TestClient(app) as client:
        headers = _headers(client, "admin@example.com")
        body = {
            "customer_id": customer_id,
            "product_name": f"接口测试商品 {scenario}",
            "scenario": scenario,
            "request_id": request_id,
        }
        created = client.post("/api/demo/orders", headers=headers, json=body)
        assert created.status_code == 201
        payload = created.json()
        assert payload["replayed"] is False
        assert payload["order"]["customer_email"] == "customer@example.com"
        assert payload["order"]["order_number"].startswith("ORD-DEMO-")

        replay = client.post("/api/demo/orders", headers=headers, json=body)
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
        assert replay.json()["order"]["id"] == payload["order"]["id"]

        customer_orders = client.get(
            "/api/orders", headers=_headers(client, "customer@example.com")
        ).json()
        assert payload["order"]["id"] in {item["id"] for item in customer_orders}


def test_demo_order_rejects_non_admin_invalid_customer_and_internal_fields() -> None:
    with SessionLocal() as db:
        customer = db.scalar(select(User).where(User.email == "customer@example.com"))
        admin = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert customer is not None and admin is not None
        customer_id = customer.id
        admin_id = admin.id

    valid = {
        "customer_id": customer_id,
        "product_name": "安全测试商品",
        "scenario": "AUTO_REFUND",
        "request_id": f"api-security-{uuid4()}",
    }
    with TestClient(app) as client:
        assert client.post(
            "/api/demo/orders",
            headers=_headers(client, "customer@example.com"),
            json=valid,
        ).status_code == 403

        admin_headers = _headers(client, "admin@example.com")
        assert client.post(
            "/api/demo/orders",
            headers=admin_headers,
            json={**valid, "customer_id": admin_id},
        ).status_code == 422
        assert client.post(
            "/api/demo/orders",
            headers=admin_headers,
            json={**valid, "amount": "1.00"},
        ).status_code == 422

    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.product_name == "安全测试商品")) is None
