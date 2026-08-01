from datetime import UTC, datetime, timedelta
from decimal import Decimal

import jieba
from sqlalchemy import select
from sqlalchemy.orm import Session

from refund_agent.domain.enums import UserRole
from refund_agent.models import KnowledgeDocument, Order, User
from refund_agent.security.passwords import hash_password

DEMO_PASSWORD = "Demo123!"


def seed_demo_data(db: Session) -> None:
    users: dict[str, User] = {}
    for email, role, display_name in (
        ("customer@example.com", UserRole.CUSTOMER, "林晓"),
        ("other@example.com", UserRole.CUSTOMER, "其他客户"),
        ("approver@example.com", UserRole.APPROVER, "审批专员"),
        ("admin@example.com", UserRole.ADMIN, "系统管理员"),
    ):
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(DEMO_PASSWORD),
                role=role,
                display_name=display_name,
            )
            db.add(user)
        users[email] = user
    db.flush()

    customer = users["customer@example.com"]
    other_customer = users["other@example.com"]
    delivered_at = datetime.now(UTC) - timedelta(days=2)
    order_specs = (
        ("ORD-399", customer.id, "云感步行鞋", "399.00", False, "success"),
        ("ORD-699", customer.id, "轻量旅行箱", "699.00", False, "success"),
        ("ORD-199-FRAUD", customer.id, "无线耳机", "199.00", True, "success"),
        ("ORD-299-UNKNOWN", customer.id, "桌面阅读灯", "299.00", False, "unknown"),
        ("ORD-500-OTHER", other_customer.id, "他人订单商品", "500.00", False, "success"),
    )
    for (
        order_number,
        customer_id,
        product_name,
        amount,
        fraud_flag,
        payment_behavior,
    ) in order_specs:
        order = db.scalar(select(Order).where(Order.order_number == order_number))
        if order is None:
            db.add(
                Order(
                    order_number=order_number,
                    customer_id=customer_id,
                    product_name=product_name,
                    amount=Decimal(amount),
                    delivered_at=delivered_at,
                    fraud_flag=fraud_flag,
                    payment_behavior=payment_behavior,
                )
            )

    policy = (
        "普通商品自签收之日起七天内，在商品完好且订单未退款的情况下可以申请无理由退货。"
        "退款金额以订单实际支付金额为准。超过五百元或命中风险规则的退款需要人工审批。"
    )
    existing_policy = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.title == "七天无理由退货政策",
            KnowledgeDocument.version == "2026.07",
        )
    )
    if existing_policy is None:
        db.add(
            KnowledgeDocument(
                title="七天无理由退货政策",
                body=policy,
                search_tokens=" ".join(jieba.cut(policy)),
                version="2026.07",
                effective_from=datetime.now(UTC) - timedelta(days=30),
            )
        )
    db.commit()
