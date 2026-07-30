from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from refund_agent.adapters.knowledge import search_knowledge
from refund_agent.adapters.llm import get_llm_client
from refund_agent.adapters.payment import MockPaymentGateway
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import ApprovalStatus, RefundStatus, TicketIntent, TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import (
    ApprovalTask,
    Message,
    Order,
    RefundRequest,
    Ticket,
    WorkflowCheckpoint,
)
from refund_agent.rules.engine import evaluate_policy, evaluate_risk


class WorkflowState(TypedDict):
    ticket_id: str
    resume: bool
    route: NotRequired[str]


def _customer_message(db: Session, ticket: Ticket) -> Message:
    message = db.scalar(
        select(Message)
        .where(Message.conversation_id == ticket.conversation_id, Message.sender == "USER")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if message is None:
        raise ValueError("Ticket has no customer message")
    return message


def _reply(db: Session, ticket: Ticket, content: str) -> None:
    db.add(Message(conversation_id=ticket.conversation_id, sender="ASSISTANT", content=content))


class RefundWorkflow:
    def __init__(self) -> None:
        self.llm = get_llm_client()
        self.payment = MockPaymentGateway()
        self.graph = self._build()

    def _build(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("classify", self.classify)
        graph.add_node("load_order", self.load_order)
        graph.add_node("policy", self.policy)
        graph.add_node("risk", self.risk)
        graph.add_node("refund", self.refund)
        graph.add_node("notify", self.notify)
        graph.add_conditional_edges(
            START, lambda state: "refund" if state["resume"] else "classify"
        )
        graph.add_conditional_edges(
            "classify",
            lambda state: state["route"],
            {"continue": "load_order", "end": END},
        )
        graph.add_conditional_edges(
            "load_order",
            lambda state: state["route"],
            {"continue": "policy", "end": END},
        )
        graph.add_conditional_edges(
            "policy",
            lambda state: state["route"],
            {"continue": "risk", "end": END},
        )
        graph.add_conditional_edges(
            "risk",
            lambda state: state["route"],
            {"refund": "refund", "end": END},
        )
        graph.add_edge("refund", "notify")
        graph.add_edge("notify", END)
        return graph.compile()

    def run(self, ticket_id: str, *, resume: bool = False) -> None:
        self.graph.invoke({"ticket_id": ticket_id, "resume": resume})

    def classify(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None:
                raise ValueError("Ticket not found")
            ticket.status = TicketStatus.RUNNING
            ticket.current_step = "classifying"
            message = _customer_message(db, ticket)
            result = self.llm.classify(message.content)
            ticket.intent = result.intent
            ticket.intent_confidence = result.confidence
            append_audit(
                db,
                action="intent.classified",
                entity_type="ticket",
                entity_id=ticket.id,
                ticket_id=ticket.id,
                details={
                    "intent": result.intent,
                    "confidence": result.confidence,
                    "order_number": result.order_number,
                },
            )
            if result.intent != TicketIntent.REFUND:
                ticket.status = TicketStatus.MANUAL_REVIEW
                ticket.current_step = "manual_review"
                _reply(
                    db,
                    ticket,
                    "已识别到换货或异常售后需求，工单已转交人工专员继续处理。",
                )
                db.commit()
                return {**state, "route": "end"}
            if not result.order_number:
                ticket.status = TicketStatus.MANUAL_REVIEW
                ticket.current_step = "missing_order"
                _reply(db, ticket, "请提供订单号（例如 ORD-399），我会继续核验退款资格。")
                db.commit()
                return {**state, "route": "end"}
            order = db.scalar(select(Order).where(Order.order_number == result.order_number))
            if order is not None:
                ticket.order_id = order.id
            else:
                ticket.current_step = f"order_not_found:{result.order_number}"
            db.commit()
            return {**state, "route": "continue"}

    def load_order(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            order = db.get(Order, ticket.order_id) if ticket and ticket.order_id else None
            if ticket is None:
                raise ValueError("Ticket not found")
            ticket.current_step = "order_validation"
            if order is None or order.customer_id != ticket.customer_id:
                ticket.status = TicketStatus.REJECTED
                ticket.current_step = "order_rejected"
                _reply(db, ticket, "未找到可处理的订单。请确认订单号属于当前账号。")
                append_audit(
                    db,
                    action="order.access_rejected",
                    entity_type="ticket",
                    entity_id=ticket.id,
                    ticket_id=ticket.id,
                    details={"reason": "not_found_or_not_owned"},
                )
                db.commit()
                return {**state, "route": "end"}
            append_audit(
                db,
                action="order.validated",
                entity_type="order",
                entity_id=order.id,
                ticket_id=ticket.id,
                details={"order_number": order.order_number, "amount": str(order.amount)},
            )
            db.commit()
            return {**state, "route": "continue"}

    def policy(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None or ticket.order_id is None:
                raise ValueError("Ticket has no order")
            order = db.get(Order, ticket.order_id)
            if order is None:
                raise ValueError("Order not found")
            ticket.current_step = "policy_check"
            result = evaluate_policy(order)
            ticket.requested_amount = Decimal(order.amount)
            ticket.calculated_amount = result.amount
            ticket.rule_version = result.rule_version
            evidence = search_knowledge(db, "七天 无理由 退款")
            append_audit(
                db,
                action="policy.evaluated",
                entity_type="ticket",
                entity_id=ticket.id,
                ticket_id=ticket.id,
                details={
                    "eligible": result.eligible,
                    "amount": str(result.amount),
                    "reasons": result.reasons,
                    "rule_version": result.rule_version,
                    "knowledge_versions": [document.version for document in evidence],
                },
            )
            if not result.eligible:
                ticket.status = TicketStatus.REJECTED
                ticket.current_step = "policy_rejected"
                _reply(db, ticket, f"该订单暂不符合自动退款条件：{'；'.join(result.reasons)}。")
                db.commit()
                return {**state, "route": "end"}
            db.commit()
            return {**state, "route": "continue"}

    def risk(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None or ticket.order_id is None or ticket.calculated_amount is None:
                raise ValueError("Incomplete ticket for risk evaluation")
            order = db.get(Order, ticket.order_id)
            if order is None:
                raise ValueError("Order not found")
            ticket.current_step = "risk_check"
            result = evaluate_risk(
                order,
                Decimal(ticket.calculated_amount),
                ticket.intent_confidence or 0.0,
            )
            ticket.risk_level = result.level
            ticket.risk_reasons = result.reasons
            ticket.matched_rule_ids = result.rule_ids
            ticket.rule_version = result.rule_version
            append_audit(
                db,
                action="risk.evaluated",
                entity_type="ticket",
                entity_id=ticket.id,
                ticket_id=ticket.id,
                details={
                    "requires_approval": result.requires_approval,
                    "risk_level": result.level,
                    "rule_ids": result.rule_ids,
                    "reasons": result.reasons,
                    "rule_version": result.rule_version,
                },
            )
            if result.requires_approval:
                approval = db.scalar(
                    select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id)
                )
                if approval is None:
                    approval = ApprovalTask(
                        ticket_id=ticket.id,
                        risk_reasons=result.reasons,
                        suggested_amount=Decimal(ticket.calculated_amount),
                        expires_at=datetime.now(UTC) + timedelta(minutes=30),
                    )
                    db.add(approval)
                    db.flush()
                checkpoint = db.scalar(
                    select(WorkflowCheckpoint).where(WorkflowCheckpoint.ticket_id == ticket.id)
                )
                snapshot = {
                    "ticket_id": ticket.id,
                    "order_id": ticket.order_id,
                    "calculated_amount": str(ticket.calculated_amount),
                    "approval_id": approval.id,
                    "next_step": "refund",
                }
                if checkpoint is None:
                    checkpoint = WorkflowCheckpoint(
                        ticket_id=ticket.id,
                        step="waiting_approval",
                        state=snapshot,
                    )
                    db.add(checkpoint)
                else:
                    checkpoint.step = "waiting_approval"
                    checkpoint.state = snapshot
                ticket.status = TicketStatus.WAITING_APPROVAL
                ticket.current_step = "waiting_approval"
                _reply(db, ticket, "退款申请已核验，当前需要人工审批。审批完成后会自动继续处理。")
                append_audit(
                    db,
                    action="approval.requested",
                    entity_type="approval",
                    entity_id=approval.id,
                    ticket_id=ticket.id,
                    details={"reasons": result.reasons},
                )
                db.commit()
                return {**state, "route": "end"}
            db.commit()
            return {**state, "route": "refund"}

    def refund(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None or ticket.order_id is None or ticket.calculated_amount is None:
                raise ValueError("Incomplete ticket for refund")
            order = db.get(Order, ticket.order_id)
            if order is None or order.customer_id != ticket.customer_id:
                raise ValueError("Order ownership changed")
            approval = db.scalar(select(ApprovalTask).where(ApprovalTask.ticket_id == ticket.id))
            if ticket.risk_reasons and (
                approval is None or approval.status != ApprovalStatus.APPROVED
            ):
                raise PermissionError("Required approval is missing")
            amount = (
                Decimal(approval.approved_amount)
                if approval and approval.approved_amount is not None
                else Decimal(ticket.calculated_amount)
            )
            if amount > Decimal(ticket.calculated_amount):
                raise ValueError("Approved amount exceeds refundable amount")
            ticket.approved_amount = amount
            ticket.current_step = "refund_execution"
            key = f"{ticket.id}:refund"
            request = db.scalar(select(RefundRequest).where(RefundRequest.idempotency_key == key))
            if request is None:
                request = RefundRequest(
                    ticket_id=ticket.id,
                    idempotency_key=key,
                    amount=amount,
                    status=RefundStatus.PROCESSING,
                )
                db.add(request)
                db.flush()
            if request.status == RefundStatus.SUCCEEDED:
                ticket.status = TicketStatus.COMPLETED
                db.commit()
                return state
            if request.status == RefundStatus.UNKNOWN:
                ticket.status = TicketStatus.MANUAL_REVIEW
                db.commit()
                return state
            result = self.payment.refund(order, amount, key)
            request.status = result.status
            request.payment_reference = result.reference
            if result.status == RefundStatus.SUCCEEDED:
                ticket.status = TicketStatus.COMPLETED
                ticket.current_step = "completed"
            elif result.status == RefundStatus.UNKNOWN:
                ticket.status = TicketStatus.MANUAL_REVIEW
                ticket.current_step = "payment_unknown"
            else:
                ticket.status = TicketStatus.FAILED
                ticket.current_step = "payment_failed"
            append_audit(
                db,
                action="refund.executed",
                entity_type="refund",
                entity_id=request.id,
                ticket_id=ticket.id,
                details={
                    "amount": str(amount),
                    "status": result.status,
                    "payment_reference": result.reference,
                    "idempotency_key": key,
                },
            )
            db.commit()
            return state

    def notify(self, state: WorkflowState) -> WorkflowState:
        with SessionLocal() as db:
            ticket = db.get(Ticket, state["ticket_id"])
            if ticket is None:
                raise ValueError("Ticket not found")
            request = db.scalar(select(RefundRequest).where(RefundRequest.ticket_id == ticket.id))
            if ticket.status == TicketStatus.COMPLETED and request:
                _reply(
                    db,
                    ticket,
                    (
                        f"退款 ¥{request.amount:.2f} 已发起，预计 1–3 个工作日到账。"
                        "请在 7 天内寄回商品，退货地址：上海市浦东新区售后中心。"
                    ),
                )
            elif ticket.status == TicketStatus.MANUAL_REVIEW:
                _reply(
                    db,
                    ticket,
                    "支付结果暂时无法确认，已冻结重复操作并转交人工核查。",
                )
            elif ticket.status == TicketStatus.FAILED:
                _reply(db, ticket, "退款暂未成功，工单已保留，请由售后专员继续处理。")
            db.commit()
            return state
