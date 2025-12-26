"""
Billing API Contracts Module

Defines Pydantic models for request/response validation in billing endpoints.
Following API contract first approach for type safety and documentation.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# =============================================================================
# Response Models
# =============================================================================

class WebhookAckResponse(BaseModel):
    """
    Webhook acknowledgment response.

    Stripe Best Practice: Return 200 OK immediately to acknowledge receipt.
    Actual event processing happens asynchronously.

    Attributes:
        message: Success message
        event_id: Stripe event ID for tracking
        received_at: Timestamp when webhook was received
    """

    message: str = Field(
        ...,
        description="Success message confirming webhook receipt",
        example="Webhook received successfully"
    )

    event_id: str = Field(
        ...,
        description="Stripe event ID for tracking and deduplication",
        example="evt_1234567890"
    )

    received_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when webhook was received"
    )


class ErrorResponse(BaseModel):
    """
    Standard error response for billing endpoints.

    Attributes:
        error: Error message
        detail: Detailed error description (optional)
        status: HTTP status code
    """

    error: str = Field(
        ...,
        description="Error type or category",
        example="Invalid signature"
    )

    detail: Optional[str] = Field(
        None,
        description="Detailed error description"
    )

    status: int = Field(
        ...,
        description="HTTP status code",
        example=401
    )


# =============================================================================
# Documentation
# =============================================================================

BILLING_API_TAGS = [
    {
        "name": "billing",
        "description": "Stripe billing and webhook endpoints"
    }
]

BILLING_ENDPOINT_DESCRIPTIONS = {
    "webhook": (
        "Receive and process Stripe webhook events. "
        "This endpoint verifies webhook signatures and routes events "
        "to appropriate handlers. Returns 200 immediately upon receipt."
    )
}


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    'WebhookAckResponse',
    'ErrorResponse',
    'BILLING_API_TAGS',
    'BILLING_ENDPOINT_DESCRIPTIONS',
]
