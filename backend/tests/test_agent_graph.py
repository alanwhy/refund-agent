import json
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select
from support.scripted_model import ScriptedModel

from refund_agent.agent.graph import build_refund_graph
from refund_agent.agent.runtime import AgentRuntime
from refund_agent.domain.enums import ApprovalStatus, TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import (
    ApprovalTask,
    AuditEvent,
    Conversation,
    Message,
    RefundRequest,
    Ticket,
    User,
)


def _tool_call(name: str, args: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def create_ticket(content: str) -> str:
    with SessionLocal() as db:
        customer = db.scalar(select(User).where(User.email == "customer@example.com"))
        assert customer is not None
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        db.flush()
        ticket = Ticket(customer_id=customer.id, conversation_id=conversation.id)
        db.add_all(
            [
                Message(conversation_id=conversation.id, sender="USER", content=content),
                ticket,
            ]
        )
        db.commit()
        return ticket.id


def runtime_with(*responses: AIMessage) -> AgentRuntime:
    model = ScriptedModel(responses=list(responses))
    return AgentRuntime(graph=build_refund_graph(model, checkpointer=InMemorySaver()))


def test_agent_chooses_read_tools_then_completes_refund() -> None:
    ticket_id = create_ticket("我想退货，订单号 ORD-399，原因是不合适")
    runtime = runtime_with(
        _tool_call("get_order", {"order_number": "ORD-399"}, "order-1"),
        _tool_call("search_policy", {"query": "七天无理由退款"}, "policy-1"),
        _tool_call(
            "SubmitRefundContext",
            {"order_number": "ORD-399", "reason": "商品不合适", "requested_action": "REFUND"},
            "submit-1",
        ),
        AIMessage(content="退款 399.00 元已发起，请留意到账通知。"),
    )

    result = runtime.start(ticket_id)

    assert result["order_snapshot"]["order_number"] == "ORD-399"
    assert result["policy_evidence"]
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        tool_events = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.ticket_id == ticket_id,
                    AuditEvent.action == "tool.completed",
                )
            )
        )
        assert ticket is not None
        assert ticket.status == TicketStatus.COMPLETED
        assert ticket.approved_amount == Decimal("399.00")
        assert refund is not None
        assert len(tool_events) == 2


def test_agent_interrupts_for_user_input_and_resumes_same_thread() -> None:
    ticket_id = create_ticket("我想退款")
    model = ScriptedModel(
        responses=[
            _tool_call(
                "RequestUserInput",
                {
                    "question": "请提供订单号和退款原因。",
                    "missing_fields": ["order_number"],
                },
                "ask-1",
            ),
            _tool_call(
                "SubmitRefundContext",
                {
                    "order_number": "ORD-399",
                    "reason": "商品不合适",
                    "requested_action": "REFUND",
                },
                "submit-2",
            ),
            AIMessage(content="退款 399.00 元已发起，请留意到账通知。"),
        ]
    )
    runtime = AgentRuntime(graph=build_refund_graph(model, checkpointer=InMemorySaver()))

    paused = runtime.start(ticket_id)
    assert paused["__interrupt__"]
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.status == TicketStatus.WAITING_USER

    resumed = runtime.resume(
        ticket_id,
        {"kind": "user_input", "message": "订单号 ORD-399，商品不合适"},
    )
    assert resumed["order_number"] == "ORD-399"
    second_call = model.captured_messages[1]
    request = next(
        message
        for message in second_call
        if isinstance(message, AIMessage)
        and any(call["id"] == "ask-1" for call in message.tool_calls)
    )
    request_index = second_call.index(request)
    assert isinstance(second_call[request_index + 1], ToolMessage)
    tool_result = second_call[request_index + 1]
    assert tool_result.tool_call_id == "ask-1"
    assert tool_result.name == "RequestUserInput"
    assert json.loads(str(tool_result.content)) == {
        "answered_fields": ["order_number"],
        "status": "user_input_received",
    }
    assert isinstance(second_call[request_index + 2], HumanMessage)
    assert second_call[request_index + 2].content == "订单号 ORD-399，商品不合适"
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.status == TicketStatus.COMPLETED


def test_high_value_refund_interrupts_and_resumes_after_approval() -> None:
    ticket_id = create_ticket("我想退款 ORD-699，原因是不合适")
    runtime = runtime_with(
        _tool_call(
            "SubmitRefundContext",
            {"order_number": "ORD-699", "reason": "商品不合适", "requested_action": "REFUND"},
            "submit-3",
        ),
        AIMessage(content="退款 699.00 元已发起，请留意到账通知。"),
    )

    paused = runtime.start(ticket_id)
    assert paused["__interrupt__"]
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id))
        assert ticket is not None
        assert ticket.status == TicketStatus.WAITING_APPROVAL
        assert approval is not None
        approval.status = ApprovalStatus.APPROVED
        approval.approved_amount = approval.suggested_amount
        approval.version += 1
        db.commit()
        approval_id = approval.id

    runtime.resume(
        ticket_id,
        {"kind": "approval", "approval_id": approval_id, "version": 2},
    )
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refunds = list(
            db.scalars(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        )
        approvals = list(
            db.scalars(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket_id))
        )
        approval_messages = list(
            db.scalars(
                select(Message).where(
                    Message.conversation_id == ticket.conversation_id,
                    Message.dedup_key == f"{ticket_id}:approval-requested",
                )
            )
        )
        assert ticket is not None
        assert ticket.status == TicketStatus.COMPLETED
        assert len(refunds) == 1
        assert len(approvals) == 1
        assert len(approval_messages) == 1


def test_unknown_payment_is_never_retried() -> None:
    ticket_id = create_ticket("我想退款 ORD-299-UNKNOWN，灯坏了")
    runtime = runtime_with(
        _tool_call(
            "SubmitRefundContext",
            {
                "order_number": "ORD-299-UNKNOWN",
                "reason": "商品损坏",
                "requested_action": "REFUND",
            },
            "submit-4",
        ),
        AIMessage(content="退款状态需要人工核查。"),
    )
    runtime.start(ticket_id)

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket_id))
        assert ticket is not None
        assert ticket.status == TicketStatus.MANUAL_REVIEW
        assert refund is not None
        assert refund.status == "UNKNOWN"
