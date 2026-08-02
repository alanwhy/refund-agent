from sqlalchemy import func, select
from test_agent_graph import create_ticket

from refund_agent.domain.enums import ManualReviewCategory
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.manual_review.service import CUSTOMER_MESSAGE, ensure_manual_review
from refund_agent.models import AuditEvent, ManualReviewTask, Message, Ticket


def test_manual_review_creation_is_replay_safe() -> None:
    ticket_id = create_ticket("测试技术异常")
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        first = ensure_manual_review(
            db,
            ticket=ticket,
            category=ManualReviewCategory.MODEL_FAILURE,
            run_id="manual-review-test",
            node_name="test",
        )
        db.commit()
        first_id = first.id

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        second = ensure_manual_review(
            db,
            ticket=ticket,
            category=ManualReviewCategory.MODEL_FAILURE,
            run_id="manual-review-replay",
            node_name="test",
        )
        db.commit()

        assert second.id == first_id
        assert (
            db.scalar(
                select(func.count(ManualReviewTask.id)).where(
                    ManualReviewTask.ticket_id == ticket_id
                )
            )
            == 1
        )
        messages = list(
            db.scalars(
                select(Message).where(
                    Message.conversation_id == ticket.conversation_id,
                    Message.dedup_key == f"{ticket_id}:manual-review",
                )
            )
        )
        assert len(messages) == 1
        assert messages[0].content == CUSTOMER_MESSAGE
        assert (
            db.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.ticket_id == ticket_id,
                    AuditEvent.action == "manual_review.created",
                )
            )
            == 1
        )
