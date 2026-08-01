from decimal import Decimal
from typing import Any

from refund_agent.adapters.knowledge import search_knowledge
from refund_agent.agent.state import RefundAgentState
from refund_agent.audit.service import append_audit
from refund_agent.domain.enums import TicketStatus
from refund_agent.infrastructure.database import SessionLocal
from refund_agent.models import Order, Ticket
from refund_agent.rules.engine import evaluate_policy, evaluate_risk


def policy_gate(state: RefundAgentState) -> dict[str, Any]:
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        order = db.get(Order, state.get("order_id")) if state.get("order_id") else None
        if ticket is None or order is None:
            raise ValueError("Incomplete ticket for policy evaluation")
        result = evaluate_policy(order)
        documents = search_knowledge(db, "七天 无理由 退款", limit=3)
        evidence = [
            {
                "document_id": item.id,
                "title": item.title,
                "version": item.version,
                "excerpt": item.body[:240],
            }
            for item in documents
        ]
        ticket.current_step = "policy_check"
        ticket.requested_amount = Decimal(order.amount)
        ticket.calculated_amount = result.amount
        ticket.rule_version = result.rule_version
        ticket.policy_evidence = evidence
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
                "knowledge_versions": [item.version for item in documents],
            },
            event_key=f"{ticket.id}:refund-v2:policy",
            run_id=state["run_id"],
            node_name="policy_gate",
        )
        if not result.eligible:
            ticket.status = TicketStatus.REJECTED
            ticket.current_step = "policy_rejected"
        db.commit()
    return {
        "eligibility": result.eligible,
        "amount_cap": str(result.amount),
        "policy_evidence": evidence,
    }


def route_after_policy(state: RefundAgentState) -> str:
    return "risk" if state.get("eligibility") else "respond"


def risk_gate(state: RefundAgentState) -> dict[str, Any]:
    with SessionLocal() as db:
        ticket = db.get(Ticket, state["ticket_id"])
        order = db.get(Order, state.get("order_id")) if state.get("order_id") else None
        if ticket is None or order is None or not state.get("amount_cap"):
            raise ValueError("Incomplete ticket for risk evaluation")
        result = evaluate_risk(order, Decimal(state["amount_cap"]), 0.99)
        ticket.current_step = "risk_check"
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
            event_key=f"{ticket.id}:refund-v2:risk",
            run_id=state["run_id"],
            node_name="risk_gate",
        )
        db.commit()
    return {
        "risk_level": result.level,
        "risk_reasons": result.reasons,
        "approval_required": result.requires_approval,
    }


def route_after_risk(state: RefundAgentState) -> str:
    return "approval" if state.get("approval_required") else "execute_refund"
