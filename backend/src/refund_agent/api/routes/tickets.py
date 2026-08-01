from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select

from refund_agent.api.dependencies import CurrentUser, DbSession
from refund_agent.api.schemas import (
    ChatAccepted,
    ChatRequest,
    MessageView,
    TicketDetail,
    TicketSummary,
)
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import UserRole
from refund_agent.models import (
    ApprovalTask,
    Conversation,
    Message,
    Order,
    RefundRequest,
    Ticket,
)
from refund_agent.worker.tasks import run_workflow

router = APIRouter(prefix="/api", tags=["tickets"])


def _assert_ticket_access(ticket: Ticket, user: CurrentUser) -> None:
    if user.role == UserRole.CUSTOMER and ticket.customer_id != user.id:
        raise HTTPException(status_code=404, detail="Ticket not found")


@router.post("/chat/messages", response_model=ChatAccepted, status_code=202)
def send_message(
    payload: ChatRequest,
    response: Response,
    db: DbSession,
    user: CurrentUser,
) -> ChatAccepted:
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(status_code=403, detail="Only customers can start conversations")
    dedup_key = f"user:{user.id}:{payload.request_id}"
    existing_message = db.scalar(select(Message).where(Message.dedup_key == dedup_key))
    if existing_message is not None:
        ticket = db.scalar(
            select(Ticket).where(Ticket.conversation_id == existing_message.conversation_id)
        )
        if ticket is None or ticket.customer_id != user.id:
            raise HTTPException(status_code=409, detail="Duplicate request has no ticket")
        conversation = db.get(Conversation, ticket.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=409, detail="Duplicate request has no conversation")
    elif payload.ticket_id:
        ticket = db.scalar(select(Ticket).where(Ticket.id == payload.ticket_id).with_for_update())
        if ticket is None or ticket.customer_id != user.id:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket.status != "WAITING_USER":
            raise HTTPException(status_code=409, detail="Ticket is not waiting for user input")
        conversation = db.get(Conversation, ticket.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        db.add(
            Message(
                conversation_id=conversation.id,
                sender="USER",
                content=payload.content,
                dedup_key=dedup_key,
            )
        )
        ticket.status = "RUNNING"
        ticket.current_step = "user_input_submitted"
        db.commit()
        run_workflow.delay(
            ticket.id,
            "resume",
            {"kind": "user_input", "message": payload.content},
        )
    else:
        conversation = (
            db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
        )
        if conversation is not None and conversation.customer_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation is None:
            conversation = Conversation(customer_id=user.id)
            db.add(conversation)
            db.flush()
        message = Message(
            conversation_id=conversation.id,
            sender="USER",
            content=payload.content,
            dedup_key=dedup_key,
        )
        ticket = Ticket(customer_id=user.id, conversation_id=conversation.id)
        db.add_all([message, ticket])
        db.flush()
        append_audit(
            db,
            action="ticket.created",
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            actor_id=user.id,
            event_key=f"{ticket.id}:created",
        )
        db.commit()
        run_workflow.delay(ticket.id, "start", None)
    status_url = f"/api/tickets/{ticket.id}"
    response.headers["Location"] = status_url
    return ChatAccepted(
        ticket_id=ticket.id,
        conversation_id=conversation.id,
        status=ticket.status,
        waiting_for=ticket.waiting_for,
        status_url=status_url,
    )


def _summary(db: DbSession, ticket: Ticket) -> TicketSummary:
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    return TicketSummary(
        id=ticket.id,
        status=ticket.status,
        current_step=ticket.current_step,
        waiting_for=ticket.waiting_for,
        current_question=ticket.current_question,
        intent=ticket.intent,
        order_number=order.order_number if order else None,
        product_name=order.product_name if order else None,
        calculated_amount=ticket.calculated_amount,
        risk_level=ticket.risk_level,
        created_at=ticket.created_at,
    )


@router.get("/tickets", response_model=list[TicketSummary])
def list_tickets(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[TicketSummary]:
    statement = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit)
    if user.role == UserRole.CUSTOMER:
        statement = statement.where(Ticket.customer_id == user.id)
    return [_summary(db, ticket) for ticket in db.scalars(statement)]


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def ticket_detail(ticket_id: str, db: DbSession, user: CurrentUser) -> TicketDetail:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _assert_ticket_access(ticket, user)
    refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket.id))
    approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id))
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.created_at)
        )
    )
    return TicketDetail(
        **_summary(db, ticket).model_dump(),
        conversation_id=ticket.conversation_id,
        requested_amount=ticket.requested_amount,
        approved_amount=ticket.approved_amount,
        risk_reasons=ticket.risk_reasons or [],
        matched_rule_ids=ticket.matched_rule_ids or [],
        refund_status=refund.status if refund else None,
        payment_reference=refund.payment_reference if refund else None,
        approval_status=approval.status if approval else None,
        policy_evidence=ticket.policy_evidence or [],
        messages=[MessageView.model_validate(message) for message in messages],
    )
