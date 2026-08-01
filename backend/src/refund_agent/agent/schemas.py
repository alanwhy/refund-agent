from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RequestUserInput(BaseModel):
    """Pause the workflow and ask the customer for required information."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=300)
    missing_fields: list[Literal["order_number", "reason"]] = Field(min_length=1, max_length=2)


class SubmitRefundContext(BaseModel):
    """Submit collected refund facts for deterministic server validation."""

    model_config = ConfigDict(extra="forbid")

    order_number: str = Field(pattern=r"^ORD-[A-Z0-9-]+$", max_length=50)
    reason: str = Field(min_length=2, max_length=500)
    requested_action: Literal["REFUND"] = "REFUND"


class OrderToolResult(BaseModel):
    found: bool
    order_number: str
    product_name: str | None = None
    amount: Decimal | None = None
    status: str | None = None
    delivered_at: str | None = None
    product_tags: list[str] = Field(default_factory=list)


class LogisticsToolResult(BaseModel):
    found: bool
    order_number: str
    status: str | None = None
    delivered_at: str | None = None


class PolicyCitation(BaseModel):
    document_id: str
    title: str
    version: str
    excerpt: str


class PolicyToolResult(BaseModel):
    citations: list[PolicyCitation] = Field(default_factory=list)


class RefundHistoryToolResult(BaseModel):
    total_requests: int
    successful_requests: int
    unknown_requests: int
