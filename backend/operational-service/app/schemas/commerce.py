"""Pydantic schemas for commercial orders, checkout links, refunds, and signed payment events."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CommerceOrderCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mercadopago", "shopify", "stub"] = "mercadopago"
    external_order_id: str | None = Field(default=None, max_length=160)
    client_id: int | None = Field(default=None, ge=1)
    opportunity_id: int | None = Field(default=None, ge=1)
    conversation_id: int | None = Field(default=None, ge=1)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    expected_amount_minor: int = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommerceRefundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(gt=0)
    external_event_id: str | None = Field(default=None, min_length=3, max_length=160)
    reason: str = Field(default="customer_refund", max_length=240)


class CommercePaymentEventOut(BaseModel):
    id: int
    order_id: int
    provider: str
    external_event_id: str
    external_payment_id: str | None = None
    event_type: str
    currency: str
    amount_minor: int
    occurred_at: datetime
    recorded_at: datetime


class CommerceOrderOut(BaseModel):
    id: int
    provider: str
    external_order_id: str | None = None
    order_number: str
    client_id: int | None = None
    opportunity_id: int | None = None
    conversation_id: int | None = None
    currency: str
    expected_amount_minor: int
    confirmed_amount_minor: int
    refunded_amount_minor: int
    net_confirmed_minor: int
    status: str
    checkout_url: str | None = None
    discrepancy_reason: str | None = None
    metadata: dict[str, Any]
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
