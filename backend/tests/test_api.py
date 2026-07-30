from fastapi.testclient import TestClient

from refund_agent.api.app import app


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
