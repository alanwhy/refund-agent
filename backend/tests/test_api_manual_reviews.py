from fastapi.testclient import TestClient
from sqlalchemy import select
from test_agent_graph import create_ticket

from refund_agent.api.app import app
from refund_agent.domain.enums import ManualReviewCategory
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.manual_review.service import ensure_manual_review
from refund_agent.models import ApprovalTask, ManualReviewTask, RefundRequest, Ticket


def _headers(client: TestClient, email: str) -> dict[str, str]:
    login = client.post(
        "/api/auth/login", json={"email": email, "password": "Demo123!"}
    ).json()
    return {"Authorization": f"Bearer {login['access_token']}"}


def _task() -> str:
    ticket_id = create_ticket("异常处理接口测试")
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        task = ensure_manual_review(
            db,
            ticket=ticket,
            category=ManualReviewCategory.MODEL_FAILURE,
            run_id="api-manual-review-test",
            node_name="test",
        )
        db.commit()
        return task.id


def test_customer_cannot_read_manual_reviews() -> None:
    with TestClient(app) as client:
        headers = _headers(client, "customer@example.com")
        assert client.get("/api/manual-review-tasks", headers=headers).status_code == 403


def test_reviewer_can_claim_and_resolve_without_refund_side_effects() -> None:
    task_id = _task()
    with TestClient(app) as client:
        headers = _headers(client, "approver@example.com")
        detail = client.get(f"/api/manual-review-tasks/{task_id}", headers=headers)
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["category"] == "MODEL_FAILURE"
        assert "Prompt" not in payload

        claimed = client.post(
            f"/api/manual-review-tasks/{task_id}/assign",
            headers=headers,
            json={"version": payload["version"]},
        )
        assert claimed.status_code == 200
        claimed_payload = claimed.json()
        assert claimed_payload["version"] == payload["version"] + 1
        assert claimed_payload["assigned_to"]

        conflict = client.post(
            f"/api/manual-review-tasks/{task_id}/resolution",
            headers=headers,
            json={
                "version": payload["version"],
                "status": "RESOLVED",
                "resolution_note": "旧版本不应成功",
            },
        )
        assert conflict.status_code == 409

        resolved = client.post(
            f"/api/manual-review-tasks/{task_id}/resolution",
            headers=headers,
            json={
                "version": claimed_payload["version"],
                "status": "RESOLVED",
                "resolution_note": "已确认模型异常，人工答复客户。",
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "RESOLVED"

        repeated = client.post(
            f"/api/manual-review-tasks/{task_id}/resolution",
            headers=headers,
            json={
                "version": resolved.json()["version"],
                "status": "UNRESOLVABLE",
                "resolution_note": "不应再次处理",
            },
        )
        assert repeated.status_code == 409

    with SessionLocal() as db:
        task = db.get(ManualReviewTask, task_id)
        assert task is not None
        assert db.scalar(
            select(ApprovalTask).where(ApprovalTask.ticket_id == task.ticket_id)
        ) is None
        assert db.scalar(
            select(RefundRequest).where(RefundRequest.ticket_id == task.ticket_id)
        ) is None


def test_resolution_note_validation() -> None:
    task_id = _task()
    with TestClient(app) as client:
        headers = _headers(client, "approver@example.com")
        response = client.post(
            f"/api/manual-review-tasks/{task_id}/resolution",
            headers=headers,
            json={"version": 1, "status": "RESOLVED", "resolution_note": ""},
        )
        assert response.status_code == 422
