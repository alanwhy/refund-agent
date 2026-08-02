from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select

from refund_agent.api.dependencies import DbSession, require_roles
from refund_agent.api.routes.orders import build_order_view
from refund_agent.api.schemas import (
    DemoCustomerView,
    DemoOrderCreateRequest,
    DemoOrderCreateResponse,
)
from refund_agent.demo_orders import DemoOrderNumberExhausted, create_demo_order
from refund_agent.domain.enums import UserRole
from refund_agent.models import User

router = APIRouter(prefix="/api/demo", tags=["demo"])
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("/customers", response_model=list[DemoCustomerView])
def list_demo_customers(db: DbSession, user: Administrator) -> list[DemoCustomerView]:
    del user
    customers = db.scalars(
        select(User)
        .where(User.role == UserRole.CUSTOMER, User.active.is_(True))
        .order_by(User.display_name, User.email)
    )
    return [
        DemoCustomerView(id=item.id, display_name=item.display_name, email=item.email)
        for item in customers
    ]


@router.post(
    "/orders",
    response_model=DemoOrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: DemoOrderCreateRequest,
    response: Response,
    db: DbSession,
    user: Administrator,
) -> DemoOrderCreateResponse:
    customer = db.get(User, payload.customer_id)
    if customer is None or customer.role != UserRole.CUSTOMER or not customer.active:
        raise HTTPException(status_code=422, detail="请选择有效的客户账号")
    try:
        order, replayed = create_demo_order(
            db,
            customer=customer,
            product_name=payload.product_name,
            amount=payload.amount,
            scenario=payload.scenario,
            request_id=payload.request_id,
            created_by=user,
        )
    except DemoOrderNumberExhausted as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="暂时无法生成订单号，请稍后重试") from exc
    db.commit()
    if replayed:
        response.status_code = status.HTTP_200_OK
    return DemoOrderCreateResponse(
        order=build_order_view(db, order, user),
        replayed=replayed,
    )
