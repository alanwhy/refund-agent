from sqlalchemy import select
from sqlalchemy.orm import Session

from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import ManualReviewCategory, TicketStatus
from refund_agent.models import ManualReviewTask, Message, Ticket

CUSTOMER_MESSAGE = "当前申请暂时无法自动完成，已转交售后专员处理。"

TECHNICAL_SUMMARIES: dict[ManualReviewCategory, str] = {
    ManualReviewCategory.MODEL_FAILURE: "智能助手服务异常，需要人工继续处理。",
    ManualReviewCategory.PAYMENT_UNKNOWN: "支付结果未知，需要核对支付渠道结果。",
    ManualReviewCategory.DATA_INCONSISTENCY: "工单数据状态不完整，需要人工核查。",
    ManualReviewCategory.SECURITY_REJECTION: "智能助手调用未通过安全校验，需要人工核查。",
}


def ensure_manual_review(
    db: Session,
    *,
    ticket: Ticket,
    category: ManualReviewCategory,
    run_id: str,
    node_name: str,
) -> ManualReviewTask:
    task = db.scalar(select(ManualReviewTask).where(ManualReviewTask.ticket_id == ticket.id))
    if task is None:
        task = ManualReviewTask(
            ticket_id=ticket.id,
            category=category,
            submitted_order_number=ticket.submitted_order_number,
            technical_summary=TECHNICAL_SUMMARIES[category],
        )
        db.add(task)
        db.flush()

    ticket.status = TicketStatus.MANUAL_REVIEW
    ticket.current_step = "manual_review"
    ticket.waiting_for = None
    ticket.current_question = None

    message_key = f"{ticket.id}:manual-review"
    if db.scalar(select(Message).where(Message.dedup_key == message_key)) is None:
        db.add(
            Message(
                conversation_id=ticket.conversation_id,
                sender="ASSISTANT",
                content=CUSTOMER_MESSAGE,
                dedup_key=message_key,
            )
        )
    append_audit(
        db,
        action="manual_review.created",
        entity_type="manual_review",
        entity_id=task.id,
        ticket_id=ticket.id,
        details={"category": category},
        event_key=f"{ticket.id}:manual-review:created",
        run_id=run_id,
        node_name=node_name,
    )
    return task
