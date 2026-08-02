from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from refund_agent.domain.enums import DemoOrderScenario


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


class ManualReviewView(BaseModel):
    id: str
    ticket_id: str
    status: str
    category: str
    version: int
    submitted_order_number: str | None
    technical_summary: str
    assigned_to: str | None
    assigned_name: str | None
    resolution_note: str | None
    resolved_by: str | None
    customer_name: str
    order_id: str | None
    order_number: str | None
    product_name: str | None
    ticket_status: str
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class ManualReviewAssignRequest(BaseModel):
    version: int = Field(ge=1)
    assignee_id: str | None = None


class ManualReviewResolutionRequest(BaseModel):
    version: int = Field(ge=1)
    status: str
    resolution_note: str = Field(min_length=1, max_length=2000)


class OrderView(BaseModel):
    id: str
    order_number: str
    product_name: str
    amount: Decimal
    status: str
    delivered_at: datetime
    customer_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    ticket_id: str | None = None
    ticket_status: str | None = None
    approval_id: str | None = None
    approval_status: str | None = None
    approval_assigned_to: str | None = None
    risk_reasons: list[str] | None = None
    manual_review_id: str | None = None
    manual_review_category: str | None = None


class DemoCustomerView(BaseModel):
    id: str
    display_name: str
    email: EmailStr


class DemoOrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    product_name: str = Field(min_length=2, max_length=100)
    scenario: DemoOrderScenario
    request_id: str = Field(min_length=8, max_length=100)

    @field_validator("product_name")
    @classmethod
    def normalize_product_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("product_name must contain at least 2 characters")
        return normalized


class DemoOrderCreateResponse(BaseModel):
    order: OrderView
    replayed: bool
