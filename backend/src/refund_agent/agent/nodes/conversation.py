import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import select

from refund_agent.adapters.llm import invoke_audited, read_prompt
from refund_agent.agent.schemas import RequestUserInput, SubmitRefundContext
from refund_agent.agent.state import RefundAgentState
from refund_agent.agent.tools import READ_TOOL_NAMES, parse_tool_content
from refund_agent.audit.service import append_audit
from refund_agent.config import get_settings
from refund_agent.domain.enums import (
    ManualReviewCategory,
    TicketIntent,
    TicketStatus,
)
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.manual_review.service import CUSTOMER_MESSAGE, ensure_manual_review
from refund_agent.models import Message, Order, RefundRequest, Ticket

MAX_TOOL_CALLS_PER_STEP = 4
MODEL_TOOL_NAMES = sorted(
    READ_TOOL_NAMES | {RequestUserInput.__name__, SubmitRefundContext.__name__}
)


def _last_ai_message(state: RefundAgentState) -> AIMessage:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, AIMessage):
            return message
    raise ValueError("Agent state has no AI message")


def _control_call(state: RefundAgentState, name: str) -> dict[str, Any]:
    message = _last_ai_message(state)
    for call in message.tool_calls:
        if call["name"] == name:
            return dict(call)
    raise ValueError(f"Missing control call: {name}")


def _control_args(state: RefundAgentState, name: str) -> dict[str, Any]:
    return dict(_control_call(state, name)["args"])


def _invalid_call_reason(calls: Sequence[Mapping[str, Any]]) -> str | None:
    if len(calls) > MAX_TOOL_CALLS_PER_STEP:
        return "TOO_MANY_TOOL_CALLS"
    names = {call["name"] for call in calls}
    control_names = {RequestUserInput.__name__, SubmitRefundContext.__name__}
    if not names.issubset(READ_TOOL_NAMES | control_names):
        return "UNKNOWN_TOOL"
    if names & control_names:
        if len(calls) != 1:
            return "MIXED_CONTROL_CALL"
        try:
            call = calls[0]
            schema = (
                RequestUserInput
                if call["name"] == RequestUserInput.__name__
                else SubmitRefundContext
            )
            schema.model_validate(call["args"])
        except (KeyError, TypeError, ValidationError):
            return "INVALID_CONTROL_ARGUMENTS"
    return None


def reason_and_route_node(
    model: Any,
) -> Callable[[RefundAgentState], dict[str, Any]]:
    def reason_and_route(state: RefundAgentState) -> dict[str, Any]:
        current_step = state.get("agent_step_count", 0)
        if current_step >= get_settings().agent_max_steps:
            return {"route": "manual", "last_error_code": "AGENT_STEP_LIMIT"}
        logical_step = current_step + 1
        with SessionLocal() as db:
            try:
                response = invoke_audited(
                    model,
                    [SystemMessage(content=read_prompt("refund_agent.md")), *state["messages"]],
                    db=db,
                    ticket_id=state["ticket_id"],
                    run_id=state["run_id"],
                    node_name="reason_and_route",
                    logical_step=logical_step,
                    tool_names=MODEL_TOOL_NAMES,
                )
            except Exception:
                db.commit()
                failures = state.get("model_failure_count", 0) + 1
                return {
                    "model_failure_count": failures,
                    "agent_step_count": logical_step,
                    "route": "manual",
                    "last_error_code": "MODEL_UNAVAILABLE",
                }
            if not isinstance(response, AIMessage):
                return {"route": "manual", "last_error_code": "INVALID_MODEL_MESSAGE"}
            invalid_reason = _invalid_call_reason(response.tool_calls)
            for call in response.tool_calls:
                append_audit(
                    db,
                    action="tool.requested",
                    entity_type="tool",
                    ticket_id=state["ticket_id"],
                    details={"tool": call["name"], "arguments": call["args"]},
                    event_key=(
                        f"{state['ticket_id']}:refund-v2:tool:{logical_step}:{call['id']}:requested"
                    ),
                    run_id=state["run_id"],
                    node_name="reason_and_route",
                )
            if invalid_reason:
                append_audit(
                    db,
                    action="security.tool_rejected",
                    entity_type="tool",
                    ticket_id=state["ticket_id"],
                    details={
                        "reason": invalid_reason,
                        "tool_names": [call["name"] for call in response.tool_calls],
                    },
                    event_key=(
                        f"{state['ticket_id']}:refund-v2:security:{logical_step}:{invalid_reason}"
                    ),
                    run_id=state["run_id"],
                    node_name="reason_and_route",
                )
            db.commit()
        return {
            "messages": [response],
            "agent_step_count": logical_step,
            "route": "manual" if invalid_reason else None,
            "last_error_code": invalid_reason,
        }

    return reason_and_route


def route_after_agent(state: RefundAgentState) -> str:
    if state.get("route") == "manual":
        return "manual"
    try:
        calls = _last_ai_message(state).tool_calls
    except ValueError:
        return "manual"
    if not calls:
        return "manual"
    names = {call["name"] for call in calls}
    if names.issubset(READ_TOOL_NAMES):
        return "tools"
    if names == {RequestUserInput.__name__} and len(calls) == 1:
        return "ask_user"
    if names == {SubmitRefundContext.__name__} and len(calls) == 1:
        return "validate_context"
    return "manual"


def collect_observations(state: RefundAgentState) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    tool_messages: list[ToolMessage] = []
    for message in reversed(state["messages"]):
        if isinstance(message, ToolMessage):
            tool_messages.append(message)
        elif isinstance(message, AIMessage):
            break
    with SessionLocal() as db:
        for message in reversed(tool_messages):
            try:
                key, value = parse_tool_content(message.name or "", str(message.content))
                updates[key] = value
                action = "tool.completed"
                details = {"tool": message.name, "result": value}
            except (ValueError, json.JSONDecodeError) as exc:
                action = "tool.failed"
                details = {"tool": message.name, "error_type": type(exc).__name__}
                updates["tool_failure_count"] = state.get("tool_failure_count", 0) + 1
            append_audit(
                db,
                action=action,
                entity_type="tool",
                ticket_id=state["ticket_id"],
                details=details,
                event_key=(
                    f"{state['ticket_id']}:refund-v2:tool:{state['agent_step_count']}:"
                    f"{message.tool_call_id}:{action}"
                ),
                run_id=state["run_id"],
                node_name="collect_observations",
            )
        db.commit()
    return updates


def ask_user(state: RefundAgentState) -> dict[str, Any]:
    control_call = _control_call(state, RequestUserInput.__name__)
    payload = RequestUserInput.model_validate(control_call["args"])
    dedup_key = f"{state['ticket_id']}:question:{state['agent_step_count']}"
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket is None:
            raise ValueError("Ticket not found")
        ticket.status = TicketStatus.WAITING_USER
        ticket.current_step = "waiting_user"
        ticket.waiting_for = "USER_INPUT"
        ticket.current_question = payload.question
        existing = db.scalar(select(Message).where(Message.dedup_key == dedup_key))
        if existing is None:
            db.add(
                Message(
                    conversation_id=ticket.conversation_id,
                    sender="ASSISTANT",
                    content=payload.question,
                    dedup_key=dedup_key,
                )
            )
        append_audit(
            db,
            action="workflow.interrupted",
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            details={"kind": "user_input", "missing_fields": payload.missing_fields},
            event_key=f"{ticket.id}:refund-v2:user-input:{state['agent_step_count']}",
            run_id=state["run_id"],
            node_name="ask_user",
        )
        db.commit()

    resumed = interrupt(
        {
            "kind": "user_input",
            "ticket_id": state["ticket_id"],
            "question": payload.question,
            "missing_fields": payload.missing_fields,
        }
    )
    if not isinstance(resumed, dict) or not isinstance(resumed.get("message"), str):
        raise ValueError("Invalid user input resume payload")
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket is None:
            raise ValueError("Ticket not found")
        ticket.status = TicketStatus.RUNNING
        ticket.current_step = "user_input_received"
        ticket.waiting_for = None
        ticket.current_question = None
        append_audit(
            db,
            action="workflow.resumed",
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            details={"kind": "user_input"},
            event_key=f"{ticket.id}:refund-v2:user-input-resumed:{state['agent_step_count']}",
            run_id=state["run_id"],
            node_name="ask_user",
        )
        db.commit()
    return {
        "messages": [
            ToolMessage(
                content=json.dumps(
                    {
                        "status": "user_input_received",
                        "answered_fields": payload.missing_fields,
                    },
                    ensure_ascii=False,
                ),
                name=RequestUserInput.__name__,
                tool_call_id=str(control_call["id"]),
            ),
            HumanMessage(content=resumed["message"]),
        ],
        "waiting_for": None,
        "current_question": None,
    }


def validate_context(state: RefundAgentState) -> dict[str, Any]:
    context = SubmitRefundContext.model_validate(_control_args(state, SubmitRefundContext.__name__))
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket is None:
            raise ValueError("Ticket not found")
        ticket.submitted_order_number = context.order_number
        order = db.scalar(
            select(Order).where(
                Order.order_number == context.order_number,
                Order.customer_id == state["customer_id"],
            )
        )
        if order is None:
            ticket.status = TicketStatus.REJECTED
            ticket.current_step = "order_rejected"
            append_audit(
                db,
                action="order.rejected",
                entity_type="order",
                ticket_id=ticket.id,
                details={
                    "submitted_order_number": context.order_number,
                    "reason": "ORDER_NOT_FOUND_OR_NOT_OWNED",
                },
                event_key=f"{ticket.id}:refund-v2:order-rejected",
                run_id=state["run_id"],
                node_name="validate_context",
            )
            db.commit()
            return {
                "route": "respond",
                "last_error_code": "ORDER_NOT_FOUND_OR_NOT_OWNED",
                "order_number": context.order_number,
                "reason": context.reason,
            }
        ticket.order_id = order.id
        ticket.intent = TicketIntent.REFUND
        ticket.intent_confidence = 0.99
        ticket.status = TicketStatus.RUNNING
        ticket.current_step = "order_validation"
        ticket.graph_version = "refund-v2"
        append_audit(
            db,
            action="order.validated",
            entity_type="order",
            entity_id=order.id,
            ticket_id=ticket.id,
            details={"order_number": order.order_number, "amount": str(order.amount)},
            event_key=f"{ticket.id}:refund-v2:order-validated",
            run_id=state["run_id"],
            node_name="validate_context",
        )
        db.commit()
    return {
        "order_number": context.order_number,
        "reason": context.reason,
        "order_id": order.id,
        "route": None,
    }


def response_node(
    model: BaseChatModel,
) -> Callable[[RefundAgentState], dict[str, Any]]:
    def respond(state: RefundAgentState) -> dict[str, Any]:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None:
                raise ValueError("Ticket not found")
            refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket.id))
            if ticket.status == TicketStatus.COMPLETED and refund is not None:
                fallback = (
                    f"退款 ¥{refund.amount:.2f} 已发起，预计 1–3 个工作日到账。"
                    "请在 7 天内寄回商品。"
                )
            elif ticket.status == TicketStatus.REJECTED:
                order_number = ticket.submitted_order_number or state.get("order_number")
                if state.get("last_error_code") == "ORDER_NOT_FOUND_OR_NOT_OWNED":
                    fallback = (
                        f"未找到订单 {order_number}，或该订单不属于当前账号。请核对订单号后重试。"
                    )
                else:
                    fallback = "该申请未通过退款校验。如有疑问，请联系人工客服。"
            elif ticket.status == TicketStatus.MANUAL_REVIEW:
                fallback = CUSTOMER_MESSAGE
            else:
                fallback = "退款申请已处理，请查看工单最新状态。"
            structured = {
                "status": ticket.status,
                "order_number": state.get("order_number"),
                "amount": str(refund.amount) if refund else None,
                "policy_evidence": ticket.policy_evidence,
                "risk_reasons": ticket.risk_reasons,
            }
            deterministic = (
                state.get("last_error_code") == "ORDER_NOT_FOUND_OR_NOT_OWNED"
                or ticket.status == TicketStatus.MANUAL_REVIEW
            )
            if deterministic:
                content = fallback
            else:
                try:
                    message = invoke_audited(
                        model,
                        [
                            SystemMessage(content=read_prompt("notification.md")),
                            HumanMessage(content=json.dumps(structured, ensure_ascii=False)),
                        ],
                        db=db,
                        ticket_id=ticket.id,
                        run_id=state["run_id"],
                        node_name="respond",
                        logical_step=state.get("agent_step_count", 0) + 1,
                    )
                    content = str(message.content).strip() or fallback
                    if refund and str(refund.amount) not in content:
                        content = fallback
                except Exception:
                    content = fallback
            dedup_key = (
                f"{ticket.id}:manual-review"
                if ticket.status == TicketStatus.MANUAL_REVIEW
                else f"{ticket.id}:terminal:{ticket.status}"
            )
            existing = db.scalar(select(Message).where(Message.dedup_key == dedup_key))
            if existing is None:
                db.add(
                    Message(
                        conversation_id=ticket.conversation_id,
                        sender="ASSISTANT",
                        content=content,
                        dedup_key=dedup_key,
                    )
                )
            ticket.waiting_for = None
            ticket.current_question = None
            db.commit()
        return {"messages": [AIMessage(content=content)]}

    return respond


def manual_review(state: RefundAgentState) -> dict[str, Any]:
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        if ticket is None:
            raise ValueError("Ticket not found")
        error_code = state.get("last_error_code")
        if error_code in {
            "UNKNOWN_TOOL",
            "TOO_MANY_TOOL_CALLS",
            "MIXED_CONTROL_CALL",
            "INVALID_CONTROL_ARGUMENTS",
        }:
            category = ManualReviewCategory.SECURITY_REJECTION
        elif error_code in {"MODEL_UNAVAILABLE", "INVALID_MODEL_MESSAGE", "AGENT_STEP_LIMIT"}:
            category = ManualReviewCategory.MODEL_FAILURE
        else:
            category = ManualReviewCategory.DATA_INCONSISTENCY
        ensure_manual_review(
            db,
            ticket=ticket,
            category=category,
            run_id=state["run_id"],
            node_name="manual_review",
        )
        append_audit(
            db,
            action="agent.manual_review",
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            details={"reason": state.get("last_error_code")},
            event_key=f"{ticket.id}:refund-v2:manual:{state.get('last_error_code')}",
            run_id=state["run_id"],
            node_name="manual_review",
        )
        db.commit()
    return {"messages": [AIMessage(content=CUSTOMER_MESSAGE)]}
