from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import false, select

from refund_agent.api.dependencies import CurrentUser, DbSession
from refund_agent.api.schemas import OrderView
from refund_agent.domain.enums import UserRole
from refund_agent.models import (
    ApprovalTask,
    ManualReviewTask,
    Order,
    RefundRequest,
    Ticket,
    User,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _scoped_orders(user: CurrentUser):  # type: ignore[no-untyped-def]
    statement = select(Order)
    if user.role == UserRole.CUSTOMER:
        return statement.where(Order.customer_id == user.id)
    if user.role == UserRole.APPROVER:
        visible_order_ids = (
            select(Ticket.order_id)
            .join(ApprovalTask, ApprovalTask.ticket_id == Ticket.id)
            .where(
                (ApprovalTask.assigned_to.is_(None))
                | (ApprovalTask.assigned_to == user.id)
            )
        )
        return statement.where(Order.id.in_(visible_order_ids))
    if user.role == UserRole.ADMIN:
        return statement
    return statement.where(false())


def _related_ticket(db: DbSession, order: Order, user: CurrentUser) -> Ticket | None:
    statement = (
        select(Ticket)
        .where(Ticket.order_id == order.id)
        .order_by(Ticket.created_at.desc())
    )
    if user.role == UserRole.APPROVER:
        statement = statement.join(
            ApprovalTask, ApprovalTask.ticket_id == Ticket.id
        ).where(
            (ApprovalTask.assigned_to.is_(None))
            | (ApprovalTask.assigned_to == user.id)
        )
    return db.scalar(statement.limit(1))


def _lifecycle_status(db: DbSession, order: Order, ticket: Ticket | None) -> str:
    if ticket is None:
        return order.status
    refund = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket.id))
    if refund is not None and refund.status == "SUCCEEDED":
        return "REFUNDED"
    if ticket.status == "MANUAL_REVIEW":
        return "MANUAL_REVIEW"
    if ticket.status == "WAITING_APPROVAL":
        return "WAITING_APPROVAL"
    if ticket.status in {"CREATED", "RUNNING", "WAITING_USER"}:
        return "AFTER_SALES_PROCESSING"
    if ticket.status == "REJECTED":
        return "REFUND_REJECTED"
    if ticket.status == "FAILED" or (refund is not None and refund.status == "FAILED"):
        return "AFTER_SALES_FAILED"
    return order.status


def build_order_view(db: DbSession, order: Order, user: User) -> OrderView:
    ticket = _related_ticket(db, order, user)
    approval = (
        db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id))
        if ticket
        else None
    )
    manual_review = (
        db.scalar(select(ManualReviewTask).where(ManualReviewTask.ticket_id == ticket.id))
        if ticket and user.role == UserRole.ADMIN
        else None
    )
    customer = db.get(User, order.customer_id) if user.role == UserRole.ADMIN else None
    internal = user.role in {UserRole.APPROVER, UserRole.ADMIN}
    return OrderView(
        id=order.id,
        order_number=order.order_number,
        product_name=order.product_name,
        amount=order.amount,
        status=order.status,
        lifecycle_status=_lifecycle_status(db, order, ticket),
        delivered_at=order.delivered_at,
        customer_id=order.customer_id if user.role == UserRole.ADMIN else None,
        customer_name=customer.display_name if customer else None,
        customer_email=customer.email if customer else None,
        ticket_id=ticket.id if ticket else None,
        ticket_status=ticket.status if ticket else None,
        approval_id=approval.id if approval else None,
        approval_status=approval.status if approval else None,
        approval_assigned_to=approval.assigned_to if approval else None,
        risk_reasons=(ticket.risk_reasons or []) if ticket and internal else None,
        manual_review_id=manual_review.id if manual_review else None,
        manual_review_category=manual_review.category if manual_review else None,
    )


@router.get("", response_model=list[OrderView])
def list_orders(
    db: DbSession,
    user: CurrentUser,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[OrderView]:
    statement = _scoped_orders(user)
    if status:
        statement = statement.where(Order.status == status)
    statement = statement.order_by(Order.delivered_at.desc()).limit(limit)
    return [build_order_view(db, order, user) for order in db.scalars(statement)]


@router.get("/{order_id}", response_model=OrderView)
def order_detail(order_id: str, db: DbSession, user: CurrentUser) -> OrderView:
    order = db.scalar(_scoped_orders(user).where(Order.id == order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return build_order_view(db, order, user)
