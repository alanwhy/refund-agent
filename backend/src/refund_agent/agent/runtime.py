from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from psycopg_pool import ConnectionPool
from sqlalchemy import select

from refund_agent.adapters.llm import build_chat_model
from refund_agent.agent.graph import build_refund_graph
from refund_agent.infrastructure.checkpoint import create_checkpoint_pool
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import Message, Ticket


@dataclass
class AgentRuntime:
    graph: Any
    pool: ConnectionPool | None = None

    @staticmethod
    def config(ticket_id: str) -> dict[str, Any]:
        return {
            "configurable": {
                "thread_id": ticket_id,
                "checkpoint_ns": "refund-v2",
            }
        }

    def start(self, ticket_id: str) -> dict[str, Any]:
        with SessionLocal() as db:
            ticket = db.get(Ticket, ticket_id)
            if ticket is None:
                raise ValueError("Ticket not found")
            message = db.scalar(
                select(Message)
                .where(Message.conversation_id == ticket.conversation_id, Message.sender == "USER")
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            if message is None:
                raise ValueError("Ticket has no user message")
            state = {
                "messages": [HumanMessage(content=message.content)],
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "run_id": str(uuid4()),
                "graph_version": "refund-v2",
                "agent_step_count": 0,
                "model_failure_count": 0,
                "tool_failure_count": 0,
            }
        return cast(dict[str, Any], self.graph.invoke(state, config=self.config(ticket_id)))

    def resume(self, ticket_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.graph.invoke(Command(resume=payload), config=self.config(ticket_id)),
        )

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()


def create_runtime(model: BaseChatModel | None = None) -> AgentRuntime:
    pool = create_checkpoint_pool()
    saver = PostgresSaver(pool)
    graph = build_refund_graph(model or build_chat_model(), checkpointer=saver)
    return AgentRuntime(graph=graph, pool=pool)


@lru_cache
def get_runtime() -> AgentRuntime:
    return create_runtime()
