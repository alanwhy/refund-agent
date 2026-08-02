from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, select, update

from refund_agent.api.dependencies import DbSession, require_roles
from refund_agent.api.schemas import (
    ManualReviewAssignRequest,
    ManualReviewResolutionRequest,
    ManualReviewView,
)
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import (
    ManualReviewCategory,
    ManualReviewStatus,
    UserRole,
)
from refund_agent.models import ManualReviewTask, Order, Ticket, User

router = APIRouter(prefix="/api/manual-review-tasks", tags=["manual-reviews"])
Reviewer = Annotated[
    User,
    Depends(require_roles(UserRole.APPROVER, UserRole.ADMIN)),
]


def _view(db: DbSession, task: ManualReviewTask) -> ManualReviewView:
    ticket = db.get(Ticket, task.ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    customer = db.get(User, ticket.customer_id)
    assigned = db.get(User, task.assigned_to) if task.assigned_to else None
    return ManualReviewView(
        id=task.id,
        ticket_id=ticket.id,
        status=task.status,
        category=task.category,
        version=task.version,
        submitted_order_number=task.submitted_order_number,
        technical_summary=task.technical_summary,
        assigned_to=task.assigned_to,
        assigned_name=assigned.display_name if assigned else None,
        resolution_note=task.resolution_note,
        resolved_by=task.resolved_by,
        customer_name=customer.display_name if customer else "未知客户",
        order_id=order.id if order else None,
        order_number=order.order_number if order else None,
        product_name=order.product_name if order else None,
        ticket_status=ticket.status,
        created_at=task.created_at,
        updated_at=task.updated_at,
        resolved_at=task.resolved_at,
    )


@router.get("", response_model=list[ManualReviewView])
def list_manual_reviews(
    db: DbSession,
    user: Reviewer,
    status: ManualReviewStatus | None = None,
    category: ManualReviewCategory | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ManualReviewView]:
    del user
    statement = select(ManualReviewTask)
    if status is not None:
        statement = statement.where(ManualReviewTask.status == status)
    if category is not None:
        statement = statement.where(ManualReviewTask.category == category)
    statement = statement.order_by(
        case((ManualReviewTask.status == ManualReviewStatus.PENDING, 0), else_=1),
        ManualReviewTask.created_at.desc(),
    ).limit(limit)
    return [_view(db, task) for task in db.scalars(statement)]


@router.get("/{task_id}", response_model=ManualReviewView)
def manual_review_detail(task_id: str, db: DbSession, user: Reviewer) -> ManualReviewView:
    del user
    task = db.get(ManualReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Manual review task not found")
    return _view(db, task)


@router.post("/{task_id}/assign", response_model=ManualReviewView)
def assign_manual_review(
    task_id: str,
    payload: ManualReviewAssignRequest,
    db: DbSession,
    user: Reviewer,
) -> ManualReviewView:
    task = db.get(ManualReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Manual review task not found")
    if task.status != ManualReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Manual review task is already closed")

    assignee_id = payload.assignee_id or user.id
    if user.role == UserRole.APPROVER and assignee_id != user.id:
        raise HTTPException(status_code=403, detail="Approvers can only claim tasks themselves")
    assignee = db.get(User, assignee_id)
    if assignee is None or assignee.role != UserRole.APPROVER or not assignee.active:
        raise HTTPException(status_code=422, detail="Invalid assignee")

    values: dict[str, Any] = {
        "assigned_to": assignee_id,
        "version": payload.version + 1,
        "updated_at": datetime.now(UTC),
    }
    result = db.execute(
        update(ManualReviewTask)
        .where(
            ManualReviewTask.id == task_id,
            ManualReviewTask.version == payload.version,
            ManualReviewTask.status == ManualReviewStatus.PENDING,
        )
        .values(**values)
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task was changed by another user")
    append_audit(
        db,
        action="manual_review.assigned",
        entity_type="manual_review",
        entity_id=task_id,
        ticket_id=task.ticket_id,
        actor_id=user.id,
        details={"assigned_to": assignee_id},
    )
    db.commit()
    refreshed = db.get(ManualReviewTask, task_id)
    assert refreshed is not None
    return _view(db, refreshed)


@router.post("/{task_id}/resolution", response_model=ManualReviewView)
def resolve_manual_review(
    task_id: str,
    payload: ManualReviewResolutionRequest,
    db: DbSession,
    user: Reviewer,
) -> ManualReviewView:
    task = db.get(ManualReviewTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Manual review task not found")
    try:
        new_status = ManualReviewStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported resolution status") from exc
    if new_status not in {
        ManualReviewStatus.RESOLVED,
        ManualReviewStatus.UNRESOLVABLE,
    }:
        raise HTTPException(status_code=422, detail="Unsupported resolution status")
    if task.status != ManualReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Manual review task is already closed")
    if user.role == UserRole.APPROVER and task.assigned_to not in {None, user.id}:
        raise HTTPException(status_code=404, detail="Manual review task not found")

    now = datetime.now(UTC)
    result = db.execute(
        update(ManualReviewTask)
        .where(
            ManualReviewTask.id == task_id,
            ManualReviewTask.version == payload.version,
            ManualReviewTask.status == ManualReviewStatus.PENDING,
        )
        .values(
            status=new_status,
            assigned_to=(
                task.assigned_to
                or (user.id if user.role == UserRole.APPROVER else None)
            ),
            resolution_note=payload.resolution_note.strip(),
            resolved_by=user.id,
            resolved_at=now,
            updated_at=now,
            version=payload.version + 1,
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Task was changed by another user")
    append_audit(
        db,
        action=f"manual_review.{new_status.value.lower()}",
        entity_type="manual_review",
        entity_id=task_id,
        ticket_id=task.ticket_id,
        actor_id=user.id,
        details={"resolution_note": payload.resolution_note.strip()},
    )
    db.commit()
    refreshed = db.get(ManualReviewTask, task_id)
    assert refreshed is not None
    return _view(db, refreshed)
