import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from refund_agent.config import get_settings
from refund_agent.models import Order


def _load(name: str) -> tuple[dict[str, Any], str]:
    settings = get_settings()
    path = settings.rules_dir / name
    if not path.exists():
        path = Path(__file__).resolve().parents[4] / "config" / "rules" / name
    content = path.read_bytes()
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid rule document: {name}")
    return data, hashlib.sha256(content).hexdigest()[:16]


@dataclass(frozen=True)
class PolicyResult:
    eligible: bool
    amount: Decimal
    reasons: list[str]
    rule_version: str


@dataclass(frozen=True)
class RiskResult:
    requires_approval: bool
    level: str
    reasons: list[str]
    rule_ids: list[str]
    rule_version: str


def evaluate_policy(order: Order) -> PolicyResult:
    rules, version = _load("refund_policy.yaml")
    reasons: list[str] = []
    allowed_statuses = set(rules["eligible_order_statuses"])
    if order.status not in allowed_statuses:
        reasons.append("订单状态不支持退货")
    delivered_at = order.delivered_at
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=UTC)
    age = datetime.now(UTC) - delivered_at
    if age.days >= int(rules["return_window_days"]):
        reasons.append("已超过七天退货时效")
    blocked_tags = set(rules["blocked_product_tags"])
    if blocked_tags.intersection(order.product_tags or []):
        reasons.append("该商品属于不可退类型")
    return PolicyResult(not reasons, Decimal(order.amount), reasons, version)


def evaluate_risk(order: Order, amount: Decimal, confidence: float) -> RiskResult:
    rules, version = _load("risk_rules.yaml")
    reasons: list[str] = []
    rule_ids: list[str] = []
    threshold = Decimal(str(rules["approval_threshold"]))
    if amount > threshold:
        rule_ids.append("AMOUNT_OVER_THRESHOLD")
        reasons.append(f"退款金额 ¥{amount:.2f} 超过自动退款上限 ¥{threshold:.2f}")
    if order.fraud_flag:
        rule_ids.append("FRAUD_FLAG")
        reasons.append("账户命中可疑退款信号")
    if confidence < float(rules["low_confidence_threshold"]):
        rule_ids.append("LOW_MODEL_CONFIDENCE")
        reasons.append("意图识别置信度不足")
    level = "HIGH" if rule_ids else "LOW"
    return RiskResult(bool(rule_ids), level, reasons, rule_ids, version)


def rule_snapshot() -> str:
    policy, policy_version = _load("refund_policy.yaml")
    risk, risk_version = _load("risk_rules.yaml")
    return json.dumps(
        {
            "policy": policy,
            "policy_version": policy_version,
            "risk": risk,
            "risk_version": risk_version,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
