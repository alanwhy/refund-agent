import json
from datetime import UTC, datetime
from typing import Annotated, Any

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field
from sqlalchemy import func, select

from refund_agent.adapters.knowledge import search_knowledge
from refund_agent.adapters.logistics import MockLogisticsGateway
from refund_agent.agent.schemas import (
    LogisticsToolResult,
    OrderToolResult,
    PolicyCitation,
    PolicyToolResult,
    RefundHistoryToolResult,
)
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import Order, RefundRequest, Ticket


def _customer_id(state: dict[str, Any]) -> str:
    customer_id = state.get("customer_id")
    if not isinstance(customer_id, str) or not customer_id:
        raise PermissionError("Trusted customer context is missing")
    return customer_id


@tool
def get_order(
    order_number: Annotated[str, Field(pattern=r"^ORD-[A-Za-z0-9-]+$", max_length=50)],
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Get the current customer's order facts by order number."""
    with SessionLocal() as db:
        order = db.scalar(
            select(Order).where(
                Order.order_number == order_number.upper(),
                Order.customer_id == _customer_id(state),
            )
        )
        if order is None:
            return OrderToolResult(found=False, order_number=order_number.upper()).model_dump_json()
        return OrderToolResult(
            found=True,
            order_number=order.order_number,
            product_name=order.product_name,
            amount=order.amount,
            status=order.status,
            delivered_at=order.delivered_at.isoformat(),
            product_tags=order.product_tags,
        ).model_dump_json()


@tool
def get_logistics(
    order_number: Annotated[str, Field(pattern=r"^ORD-[A-Za-z0-9-]+$", max_length=50)],
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Get delivery facts for the current customer's order."""
    with SessionLocal() as db:
        order = db.scalar(
            select(Order).where(
                Order.order_number == order_number.upper(),
                Order.customer_id == _customer_id(state),
            )
        )
        if order is None:
            return LogisticsToolResult(
                found=False, order_number=order_number.upper()
            ).model_dump_json()
        snapshot = MockLogisticsGateway().lookup(order)
        return LogisticsToolResult(
            found=True,
            order_number=snapshot.order_number,
            status=snapshot.status,
            delivered_at=snapshot.delivered_at.isoformat(),
        ).model_dump_json()


@tool
def search_policy(
    query: Annotated[str, Field(min_length=2, max_length=200)],
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Search effective refund policy documents and return cited excerpts."""
    _customer_id(state)
    safe_query = query.strip()[:200]
    with SessionLocal() as db:
        documents = search_knowledge(db, safe_query, limit=3)
        result = PolicyToolResult(
            citations=[
                PolicyCitation(
                    document_id=document.id,
                    title=document.title,
                    version=document.version,
                    excerpt=document.body[:240],
                )
                for document in documents
            ]
        )
        return result.model_dump_json()


@tool
def get_refund_history(
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Get aggregate refund history for the current customer."""
    with SessionLocal() as db:
        customer_id = _customer_id(state)
        base = select(func.count(RefundRequest.id)).join(
            Ticket, Ticket.id == RefundRequest.ticket_id
        ).where(Ticket.customer_id == customer_id)
        total = db.scalar(base) or 0
        succeeded = db.scalar(base.where(RefundRequest.status == "SUCCEEDED")) or 0
        unknown = db.scalar(base.where(RefundRequest.status == "UNKNOWN")) or 0
        return RefundHistoryToolResult(
            total_requests=total,
            successful_requests=succeeded,
            unknown_requests=unknown,
        ).model_dump_json()


READ_TOOLS: list[BaseTool] = [get_order, get_logistics, search_policy, get_refund_history]
READ_TOOL_NAMES = {item.name for item in READ_TOOLS}


def parse_tool_content(name: str, content: str) -> tuple[str, Any]:
    parsed = json.loads(content)
    if name == "get_order":
        return "order_snapshot", parsed
    if name == "get_logistics":
        return "logistics_snapshot", parsed
    if name == "search_policy":
        return "policy_evidence", parsed.get("citations", [])
    if name == "get_refund_history":
        return "refund_history", parsed
    raise ValueError(f"Unknown tool result: {name}")


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()
