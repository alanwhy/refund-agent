from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_agent_graph import create_ticket

from refund_agent.api.app import app
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import ApprovalTask, Message, Order, Ticket


def test_health_and_login() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "Demo123!"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["role"] == "CUSTOMER"
        assert payload["access_token"]


def test_customer_cannot_access_admin_audit() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "Demo123!"},
        ).json()
        response = client.get(
            "/api/audit-events",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        assert response.status_code == 403


def test_chat_returns_accepted_resource_and_resumes_waiting_ticket(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dispatched: list[tuple[object, ...]] = []

    def capture(*args: object, **kwargs: object) -> None:
        del kwargs
        dispatched.append(args)

    monkeypatch.setattr("refund_agent.api.routes.tickets.run_workflow.delay", capture)
    request_prefix = str(uuid4())
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "customer@example.com", "password": "Demo123!"},
        ).json()
        headers = {"Authorization": f"Bearer {login['access_token']}"}
        created = client.post(
            "/api/chat/messages",
            headers=headers,
            json={"content": "我想退款", "request_id": f"{request_prefix}-start"},
        )
        assert created.status_code == 202
        payload = created.json()
        assert created.headers["location"] == payload["status_url"]
        assert dispatched[-1][1] == "start"

        with SessionLocal() as db:
            ticket = db.scalar(select(Ticket).where(Ticket.id == payload["ticket_id"]))
            assert ticket is not None
            ticket.status = "WAITING_USER"
            ticket.waiting_for = "USER_INPUT"
            ticket.current_question = "请提供订单号"
            db.commit()

        resumed = client.post(
            "/api/chat/messages",
            headers=headers,
            json={
                "ticket_id": payload["ticket_id"],
                "content": "订单号 ORD-399，商品不合适",
                "request_id": f"{request_prefix}-resume",
            },
        )
        assert resumed.status_code == 202
        assert dispatched[-1][1] == "resume"


def test_rejected_approval_resumes_graph_with_database_version(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    dispatched: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "refund_agent.api.routes.approvals.run_workflow.delay",
        lambda *args: dispatched.append(args),
    )
    ticket_id = create_ticket("退款 ORD-699")
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        order = db.scalar(select(Order).where(Order.order_number == "ORD-699"))
        assert ticket is not None and order is not None
        ticket.order_id = order.id
        ticket.status = "WAITING_APPROVAL"
        approval = ApprovalTask(
            ticket_id=ticket.id,
            suggested_amount=Decimal("699.00"),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(approval)
        db.commit()
        approval_id = approval.id

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "approver@example.com", "password": "Demo123!"},
        ).json()
        response = client.post(
            f"/api/approvals/{approval_id}/decision",
            headers={"Authorization": f"Bearer {login['access_token']}"},
            json={"decision": "REJECT", "version": 1, "comment": "不符合条件"},
        )

    assert response.status_code == 200
    assert dispatched == [
        (
            ticket_id,
            "resume",
            {"kind": "approval", "approval_id": approval_id, "version": 2},
        )
    ]
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        message = db.scalar(
            select(Message).where(
                Message.conversation_id == ticket.conversation_id,
                Message.dedup_key == f"{ticket_id}:terminal:REJECTED",
            )
        )
        assert ticket.status == "REJECTED"
        assert message is not None
