from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from refund_agent.adapters.payment import MockPaymentGateway
from refund_agent.agent.nodes.approval import approval_interrupt, route_after_approval
from refund_agent.agent.nodes.conversation import (
    ask_user,
    collect_observations,
    manual_review,
    reason_and_route_node,
    response_node,
    route_after_agent,
    validate_context,
)
from refund_agent.agent.nodes.decisions import (
    policy_gate,
    risk_gate,
    route_after_policy,
    route_after_risk,
)
from refund_agent.agent.nodes.execution import execute_refund_node
from refund_agent.agent.schemas import RequestUserInput, SubmitRefundContext
from refund_agent.agent.state import RefundAgentState
from refund_agent.agent.tools import READ_TOOLS


def route_after_context(state: RefundAgentState) -> str:
    return "respond" if state.get("route") == "respond" else "policy"


def build_refund_graph(
    model: BaseChatModel,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    payment: MockPaymentGateway | None = None,
) -> Any:
    bound_model = model.bind_tools([*READ_TOOLS, RequestUserInput, SubmitRefundContext])
    builder = StateGraph(RefundAgentState)
    builder.add_node(  # type: ignore[call-overload]
        "reason_and_route", reason_and_route_node(bound_model)
    )
    builder.add_node("tools", ToolNode(READ_TOOLS))
    builder.add_node("collect_observations", collect_observations)
    builder.add_node("ask_user", ask_user)
    builder.add_node("validate_context", validate_context)
    builder.add_node("policy", policy_gate)
    builder.add_node("risk", risk_gate)
    builder.add_node("approval", approval_interrupt)
    builder.add_node(
        "execute_refund",
        execute_refund_node(payment or MockPaymentGateway()),  # type: ignore[arg-type]
    )
    builder.add_node("respond", response_node(model))  # type: ignore[arg-type]
    builder.add_node("manual", manual_review)

    builder.add_edge(START, "reason_and_route")
    builder.add_conditional_edges(
        "reason_and_route",
        route_after_agent,
        {
            "tools": "tools",
            "ask_user": "ask_user",
            "validate_context": "validate_context",
            "manual": "manual",
        },
    )
    builder.add_edge("tools", "collect_observations")
    builder.add_edge("collect_observations", "reason_and_route")
    builder.add_edge("ask_user", "reason_and_route")
    builder.add_conditional_edges(
        "validate_context", route_after_context, {"policy": "policy", "respond": "respond"}
    )
    builder.add_conditional_edges(
        "policy", route_after_policy, {"risk": "risk", "respond": "respond"}
    )
    builder.add_conditional_edges(
        "risk",
        route_after_risk,
        {"approval": "approval", "execute_refund": "execute_refund"},
    )
    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {"execute_refund": "execute_refund", "respond": "respond", "manual": "manual"},
    )
    builder.add_edge("execute_refund", "respond")
    builder.add_edge("respond", END)
    builder.add_edge("manual", END)
    return builder.compile(checkpointer=checkpointer)
