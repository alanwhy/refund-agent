from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class RefundAgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    ticket_id: str
    customer_id: str
    run_id: str
    graph_version: str
    agent_step_count: int
    model_failure_count: int
    tool_failure_count: int
    order_number: str
    reason: str
    order_id: str
    order_snapshot: dict[str, Any]
    logistics_snapshot: dict[str, Any]
    policy_evidence: list[dict[str, Any]]
    refund_history: dict[str, Any]
    eligibility: bool
    amount_cap: str
    risk_level: str
    risk_reasons: list[str]
    approval_required: bool
    approval_id: str
    refund_request_id: str
    waiting_for: str | None
    current_question: str | None
    route: str
    last_error_code: str | None
