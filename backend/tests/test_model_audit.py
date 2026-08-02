from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select
from support.scripted_model import ScriptedModel
from test_agent_graph import create_ticket

from refund_agent.adapters.llm import invoke_audited
from refund_agent.api.app import app
from refund_agent.audit.service import append_audit, redact
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import AuditEvent


def _headers(client: TestClient, email: str) -> dict[str, str]:
    payload = client.post(
        "/api/auth/login", json={"email": email, "password": "Demo123!"}
    ).json()
    return {"Authorization": f"Bearer {payload['access_token']}"}


def test_recursive_audit_redaction_handles_keys_headers_and_json_strings() -> None:
    result = redact(
        {
            "apiKey": "gateway-secret",
            "nested": {"access_token": "jwt-value", "safe": 3},
            "messages": [
                "Authorization: Bearer abc.def.ghi",
                "key sk-abcdefgh12345678",
                '{"password":"hidden","order_number":"ORD-399"}',
            ],
            "usage": {"input_tokens": 12},
        }
    )

    assert result["apiKey"] == "[REDACTED]"
    assert result["nested"] == {"access_token": "[REDACTED]", "safe": 3}
    assert "abc.def.ghi" not in result["messages"][0]
    assert "sk-abcdefgh12345678" not in result["messages"][1]
    assert "hidden" not in result["messages"][2]
    assert "ORD-399" in result["messages"][2]
    assert result["usage"] == {"input_tokens": 12}


def test_model_audit_retains_structured_input_output_and_tool_calls() -> None:
    ticket_id = create_ticket("模型审计输入输出测试")
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="准备查询订单",
                tool_calls=[
                    {
                        "name": "get_order",
                        "args": {"order_number": "ORD-399", "api_key": "do-not-store"},
                        "id": "call-audit",
                    }
                ],
                usage_metadata={"input_tokens": 21, "output_tokens": 8, "total_tokens": 29},
            )
        ]
    )
    messages = [
        SystemMessage(content="系统提示"),
        HumanMessage(content="password=customer-secret 退款 ORD-399"),
        ToolMessage(
            content='{"api_key":"tool-secret","status":"DELIVERED"}',
            tool_call_id="previous-call",
        ),
    ]

    with SessionLocal() as db:
        response = invoke_audited(
            model,
            messages,
            db=db,
            ticket_id=ticket_id,
            run_id=str(uuid4()),
            node_name="audit_test",
            logical_step=1,
            tool_names=["get_order", "SubmitRefundContext"],
        )
        db.commit()
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.ticket_id == ticket_id,
                    AuditEvent.entity_type == "model",
                )
                .order_by(AuditEvent.created_at)
            )
        )

    assert response.content == "准备查询订单"
    requested = next(event for event in events if event.action == "model.requested")
    completed = next(event for event in events if event.action == "model.completed")
    assert requested.details["logical_step"] == 1
    assert requested.details["input"]["tools"] == ["get_order", "SubmitRefundContext"]
    serialized_messages = requested.details["input"]["messages"]
    assert [message["type"] for message in serialized_messages] == ["system", "human", "tool"]
    assert "customer-secret" not in serialized_messages[1]["content"]
    assert "tool-secret" not in serialized_messages[2]["content"]
    assert completed.details["output"]["content"] == "准备查询订单"
    assert completed.details["output"]["tool_calls"][0]["name"] == "get_order"
    assert completed.details["output"]["tool_calls"][0]["args"]["api_key"] == "[REDACTED]"
    assert completed.details["usage"]["total_tokens"] == 29


def test_audit_api_separates_model_and_business_events() -> None:
    marker = str(uuid4())
    with SessionLocal() as db:
        append_audit(
            db,
            action="model.requested",
            entity_type="model",
            entity_id=marker,
            details={"input": {"messages": []}},
        )
        append_audit(
            db,
            action="ticket.test_event",
            entity_type="ticket",
            entity_id=marker,
        )
        db.commit()

    with TestClient(app) as client:
        admin = _headers(client, "admin@example.com")
        model_events = client.get(
            "/api/audit-events?category=model&limit=500", headers=admin
        )
        business_events = client.get(
            "/api/audit-events?category=business&limit=500", headers=admin
        )
        assert model_events.status_code == 200
        assert business_events.status_code == 200
        assert all(event["entity_type"] == "model" for event in model_events.json())
        assert all(event["entity_type"] != "model" for event in business_events.json())
        assert client.get(
            "/api/audit-events?category=model",
            headers=_headers(client, "customer@example.com"),
        ).status_code == 403
