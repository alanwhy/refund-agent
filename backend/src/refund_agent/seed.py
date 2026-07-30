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
    if db.scalar(select(User.id).limit(1)):
        return

    customer = User(
        email="customer@example.com",
        password_hash=hash_password(DEMO_PASSWORD),
        role=UserRole.CUSTOMER,
        display_name="林晓",
    )
    other_customer = User(
        email="other@example.com",
        password_hash=hash_password(DEMO_PASSWORD),
        role=UserRole.CUSTOMER,
        display_name="其他客户",
    )
    approver = User(
        email="approver@example.com",
        password_hash=hash_password(DEMO_PASSWORD),
        role=UserRole.APPROVER,
        display_name="审批专员",
    )
    admin = User(
        email="admin@example.com",
        password_hash=hash_password(DEMO_PASSWORD),
        role=UserRole.ADMIN,
        display_name="系统管理员",
    )
    db.add_all([customer, other_customer, approver, admin])
    db.flush()

    delivered_at = datetime.now(UTC) - timedelta(days=2)
    db.add_all(
        [
            Order(
                order_number="ORD-399",
                customer_id=customer.id,
                product_name="云感步行鞋",
                amount=Decimal("399.00"),
                delivered_at=delivered_at,
            ),
            Order(
                order_number="ORD-699",
                customer_id=customer.id,
                product_name="轻量旅行箱",
                amount=Decimal("699.00"),
                delivered_at=delivered_at,
            ),
            Order(
                order_number="ORD-199-FRAUD",
                customer_id=customer.id,
                product_name="无线耳机",
                amount=Decimal("199.00"),
                delivered_at=delivered_at,
                fraud_flag=True,
            ),
            Order(
                order_number="ORD-299-UNKNOWN",
                customer_id=customer.id,
                product_name="桌面阅读灯",
                amount=Decimal("299.00"),
                delivered_at=delivered_at,
                payment_behavior="unknown",
            ),
            Order(
                order_number="ORD-500-OTHER",
                customer_id=other_customer.id,
                product_name="他人订单商品",
                amount=Decimal("500.00"),
                delivered_at=delivered_at,
            ),
        ]
    )

    policy = (
        "普通商品自签收之日起七天内，在商品完好且订单未退款的情况下可以申请无理由退货。"
        "退款金额以订单实际支付金额为准。超过五百元或命中风险规则的退款需要人工审批。"
    )
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
