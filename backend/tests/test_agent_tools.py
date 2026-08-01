import json

from refund_agent.agent.tools import get_order, search_policy


def test_trusted_state_is_hidden_from_model_tool_schema() -> None:
    schema = get_order.tool_call_schema.model_json_schema()
    assert "state" not in schema["properties"]


def test_order_tool_hides_other_customer_order() -> None:
    assert get_order.func is not None
    result = json.loads(
        get_order.func(order_number="ORD-500-OTHER", state={"customer_id": "missing"})
    )
    assert result == {
        "found": False,
        "order_number": "ORD-500-OTHER",
        "product_name": None,
        "amount": None,
        "status": None,
        "delivered_at": None,
        "product_tags": [],
    }


def test_policy_tool_limits_and_returns_citations() -> None:
    assert search_policy.func is not None
    result = json.loads(
        search_policy.func(query="七天 无理由 退款", state={"customer_id": "customer"})
    )
    assert len(result["citations"]) <= 3
