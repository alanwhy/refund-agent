from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres import PostgresSaver
from support.scripted_model import ScriptedModel
from test_agent_graph import _tool_call, create_ticket

from refund_agent.agent.graph import build_refund_graph
from refund_agent.agent.runtime import AgentRuntime
from refund_agent.infrastructure.checkpoint import create_checkpoint_pool
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import Ticket


def test_postgres_checkpoint_survives_runtime_restart() -> None:
    ticket_id = create_ticket("我想退款")
    first_model = ScriptedModel(
        responses=[
            _tool_call(
                "RequestUserInput",
                {"question": "请提供订单号。", "missing_fields": ["order_number"]},
                "checkpoint-ask",
            )
        ]
    )
    first_pool = create_checkpoint_pool()
    first_runtime = AgentRuntime(
        graph=build_refund_graph(first_model, checkpointer=PostgresSaver(first_pool)),
        pool=first_pool,
    )
    paused = first_runtime.start(ticket_id)
    assert paused["__interrupt__"]
    first_runtime.close()

    second_model = ScriptedModel(
        responses=[
            _tool_call(
                "SubmitRefundContext",
                {
                    "order_number": "ORD-399",
                    "reason": "商品不合适",
                    "requested_action": "REFUND",
                },
                "checkpoint-submit",
            ),
            AIMessage(content="退款 399.00 元已发起，请留意到账通知。"),
        ]
    )
    second_pool = create_checkpoint_pool()
    second_runtime = AgentRuntime(
        graph=build_refund_graph(second_model, checkpointer=PostgresSaver(second_pool)),
        pool=second_pool,
    )
    second_runtime.resume(ticket_id, {"kind": "user_input", "message": "ORD-399，不合适"})
    second_runtime.close()

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        assert ticket.status == "COMPLETED"
