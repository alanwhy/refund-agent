from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    display_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class ChatRequest(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None
    ticket_id: str | None = None
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=8, max_length=100)


class ChatAccepted(BaseModel):
    ticket_id: str
    conversation_id: str
    status: str
    waiting_for: str | None = None
    status_url: str


class MessageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender: str
    content: str
    created_at: datetime


class TicketSummary(BaseModel):
    id: str
    status: str
    current_step: str
    waiting_for: str | None
    current_question: str | None
    intent: str | None
    order_number: str | None
    product_name: str | None
    calculated_amount: Decimal | None
    risk_level: str | None
    created_at: datetime


class TicketDetail(TicketSummary):
    conversation_id: str
    requested_amount: Decimal | None
    approved_amount: Decimal | None
    risk_reasons: list[str]
    matched_rule_ids: list[str]
    refund_status: str | None
    payment_reference: str | None
    approval_status: str | None
    policy_evidence: list[dict[str, object]]
    messages: list[MessageView]


class ApprovalView(BaseModel):
    id: str
    ticket_id: str
    status: str
    version: int
    risk_reasons: list[str]
    suggested_amount: Decimal
    approved_amount: Decimal | None
    assigned_to: str | None
    order_number: str | None
    product_name: str | None
    customer_name: str
    expires_at: datetime
    created_at: datetime


class ApprovalDecisionRequest(BaseModel):
    decision: str
    version: int
    approved_amount: Decimal | None = None
    comment: str | None = Field(default=None, max_length=1000)
    transfer_to: str | None = None


class AuditView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_id: str | None
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, object]
    trace_id: str
    created_at: datetime
