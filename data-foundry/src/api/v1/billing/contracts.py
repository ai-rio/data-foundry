"""
Billing API Contracts Module (P4-004)

Defines Pydantic models for request/response validation in billing endpoints.
Following API contract first approach for type safety and documentation.

This module provides contracts for:
- Customer CRUD operations (Create, Read, Update, Delete)
- Subscription CRUD operations (Create, Read, Update, Cancel)
- Usage summary endpoints
- Webhook handling
- Standard error responses

All contracts use Pydantic v2 for automatic validation and serialization.
Updated for P4-004: Migrated from @validator to @field_validator (Pydantic v2)
"""

from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class SubscriptionTier(str, Enum):
    """
    Subscription tier enumeration.

    Valid subscription tiers for the application.
    """

    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    """
    Subscription status enumeration.

    Matches Stripe subscription status values.
    """

    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


# =============================================================================
# Request Models - Customer
# =============================================================================

class CreateCustomerRequest(BaseModel):
    """
    Request model for creating a Stripe customer.

    Attributes:
        email: Customer email address (required)
        name: Customer name (optional, defaults to tenant name)
    """

    email: EmailStr = Field(
        ...,
        description="Customer email address for billing",
        example="billing@company.com"
    )

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="Customer or organization name",
        example="Acme Corporation"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name doesn't contain malicious content."""
        if v and len(v.strip()) == 0:
            raise ValueError('Name cannot be empty or whitespace only')
        return v.strip() if v else v


class UpdateCustomerRequest(BaseModel):
    """
    Request model for updating a Stripe customer.

    Attributes:
        email: New email address (optional)
        name: New name (optional)
        metadata: Optional metadata updates (optional)
    """

    email: Optional[EmailStr] = Field(
        None,
        description="Updated customer email address"
    )

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description="Updated customer name"
    )

    metadata: Optional[Dict[str, str]] = Field(
        None,
        description="Additional customer metadata"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name doesn't contain malicious content."""
        if v and len(v.strip()) == 0:
            raise ValueError('Name cannot be empty or whitespace only')
        return v.strip() if v else v


# =============================================================================
# Request Models - Subscription
# =============================================================================

class CreateSubscriptionRequest(BaseModel):
    """
    Request model for creating a subscription.

    Attributes:
        stripe_customer_id: Stripe customer ID to subscribe (required)
        tier: Subscription tier (required)
        price_id: Stripe price ID for the tier (optional)
        cancel_at_period_end: Whether to cancel at period end (default False)
    """

    stripe_customer_id: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Stripe customer ID (cus_*)",
        example="cus_abc123"
    )

    tier: SubscriptionTier = Field(
        ...,
        description="Subscription tier to purchase"
    )

    price_id: Optional[str] = Field(
        None,
        min_length=7,
        max_length=500,
        description="Stripe price ID for the tier",
        example="price_abc123"
    )

    cancel_at_period_end: bool = Field(
        default=False,
        description="Whether subscription cancels at period end"
    )

    @field_validator('stripe_customer_id')
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        """Validate customer ID format."""
        if not v.startswith('cus_'):
            raise ValueError('Invalid Stripe customer ID format (must start with cus_)')
        return v

    @field_validator('price_id')
    @classmethod
    def validate_price_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate price ID format if provided."""
        if v and not v.startswith('price_'):
            raise ValueError('Invalid Stripe price ID format (must start with price_)')
        return v


class UpdateSubscriptionRequest(BaseModel):
    """
    Request model for updating a subscription.

    Attributes:
        tier: New subscription tier (optional)
        price_id: New price ID for tier change (optional)
        cancel_at_period_end: Whether to cancel at period end (optional)
    """

    tier: Optional[SubscriptionTier] = Field(
        None,
        description="New subscription tier for upgrade/downgrade"
    )

    price_id: Optional[str] = Field(
        None,
        min_length=7,
        max_length=500,
        description="New price ID for tier change"
    )

    cancel_at_period_end: Optional[bool] = Field(
        None,
        description="Update cancellation preference"
    )

    @field_validator('price_id')
    @classmethod
    def validate_price_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate price ID format if provided."""
        if v and not v.startswith('price_'):
            raise ValueError('Invalid Stripe price ID format (must start with price_)')
        return v


# =============================================================================
# Response Models - Customer
# =============================================================================

class CustomerResponse(BaseModel):
    """
    Response model for customer data.

    Attributes:
        tenant_id: Internal tenant identifier
        stripe_customer_id: Stripe customer ID (cus_*)
        email: Customer email address
        name: Customer name
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    tenant_id: str = Field(
        ...,
        description="Internal tenant identifier",
        example="tenant_abc123",
        min_length=1,
        max_length=255
    )

    stripe_customer_id: str = Field(
        ...,
        description="Stripe customer ID",
        example="cus_abc123"
    )

    email: Optional[str] = Field(
        None,
        description="Customer email address"
    )

    name: Optional[str] = Field(
        None,
        description="Customer name"
    )

    created_at: datetime = Field(
        ...,
        description="Customer creation timestamp"
    )

    updated_at: datetime = Field(
        ...,
        description="Last update timestamp"
    )


# =============================================================================
# Response Models - Subscription
# =============================================================================

class SubscriptionResponse(BaseModel):
    """
    Response model for subscription data.

    Attributes:
        tenant_id: Internal tenant identifier
        stripe_subscription_id: Stripe subscription ID (sub_*)
        stripe_customer_id: Associated Stripe customer ID
        status: Current subscription status
        tier: Subscription tier/plan
        current_period_start: Current billing period start
        current_period_end: Current billing period end
        cancel_at_period_end: Whether will cancel at period end
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    tenant_id: str = Field(
        ...,
        description="Internal tenant identifier",
        min_length=1,
        max_length=255
    )

    stripe_subscription_id: str = Field(
        ...,
        description="Stripe subscription ID",
        example="sub_abc123"
    )

    stripe_customer_id: str = Field(
        ...,
        description="Associated Stripe customer ID"
    )

    status: SubscriptionStatus = Field(
        ...,
        description="Current subscription status"
    )

    tier: Optional[str] = Field(
        None,
        description="Subscription tier/plan"
    )

    current_period_start: Optional[datetime] = Field(
        None,
        description="Current billing period start"
    )

    current_period_end: Optional[datetime] = Field(
        None,
        description="Current billing period end"
    )

    cancel_at_period_end: bool = Field(
        ...,
        description="Whether subscription will cancel at period end"
    )

    created_at: datetime = Field(
        ...,
        description="Subscription creation timestamp"
    )

    updated_at: datetime = Field(
        ...,
        description="Subscription update timestamp"
    )


# =============================================================================
# Response Models - Existing (Webhook, Usage, etc.)
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


class UsageBreakdown(BaseModel):
    """
    Usage breakdown by event type.

    Attributes:
        event_name: Type of meter event (e.g., "ai_labels", "human_audits")
        total_quantity: Total quantity consumed for this event type
        event_count: Number of individual events recorded
    """

    event_name: str = Field(
        ...,
        description="Event type name",
        example="ai_labels"
    )

    total_quantity: int = Field(
        ...,
        description="Total quantity consumed",
        example=1500,
        ge=0
    )

    event_count: int = Field(
        ...,
        description="Number of events recorded",
        example=10,
        ge=0
    )


class CostBreakdown(BaseModel):
    """
    Estimated cost breakdown by event type.

    Attributes:
        event_name: Type of meter event
        quantity: Total quantity consumed
        unit_price: Price per unit for this event type
        estimated_cost: Estimated cost (quantity * unit_price)
    """

    event_name: str = Field(
        ...,
        description="Event type name",
        example="ai_labels"
    )

    quantity: int = Field(
        ...,
        description="Total quantity consumed",
        example=1500,
        ge=0
    )

    unit_price: float = Field(
        ...,
        description="Price per unit in USD",
        example=0.001,
        ge=0
    )

    estimated_cost: float = Field(
        ...,
        description="Estimated total cost in USD",
        example=1.50,
        ge=0
    )


class SyncStatus(BaseModel):
    """
    Stripe sync status information.

    Attributes:
        last_sync: Timestamp of last successful sync
        pending_events: Number of events pending sync
        failed_events: Number of events that failed to sync
        total_events: Total number of events in the period
    """

    last_sync: Optional[datetime] = Field(
        None,
        description="Timestamp of last successful Stripe sync"
    )

    pending_events: int = Field(
        ...,
        description="Number of events pending synchronization",
        example=5,
        ge=0
    )

    failed_events: int = Field(
        ...,
        description="Number of events that failed to synchronize",
        example=2,
        ge=0
    )

    total_events: int = Field(
        ...,
        description="Total number of events in the period",
        example=100,
        ge=0
    )


class UsageSummaryResponse(BaseModel):
    """
    Usage summary response for billing period.

    Attributes:
        tenant_id: Tenant identifier
        period_start: Start of billing period
        period_end: End of billing period
        usage_breakdown: List of usage breakdowns by event type
        estimated_costs: List of cost breakdowns by event type
        total_estimated_cost: Total estimated cost across all event types
        sync_status: Stripe synchronization status
    """

    tenant_id: str = Field(
        ...,
        description="Tenant identifier",
        example="tenant_abc123",
        min_length=1,
        max_length=255
    )

    period_start: Optional[datetime] = Field(
        None,
        description="Start of billing period (ISO 8601)"
    )

    period_end: Optional[datetime] = Field(
        None,
        description="End of billing period (ISO 8601)"
    )

    usage_breakdown: List[UsageBreakdown] = Field(
        ...,
        description="Usage breakdown by event type"
    )

    estimated_costs: List[CostBreakdown] = Field(
        ...,
        description="Estimated cost breakdown by event type"
    )

    total_estimated_cost: float = Field(
        ...,
        description="Total estimated cost in USD",
        example=10.50,
        ge=0
    )

    sync_status: SyncStatus = Field(
        ...,
        description="Stripe synchronization status"
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
    ),
    "usage_summary": (
        "Get usage summary for a billing period. "
        "Aggregates stripe_meter_events by event_name and calculates "
        "estimated costs based on tier pricing. Returns usage breakdown, "
        "cost estimates, and Stripe sync status."
    ),
    "create_customer": (
        "Create a new Stripe customer for the tenant's organization. "
        "Requires authentication. Email address is required."
    ),
    "get_customer": (
        "Retrieve customer information for a tenant. "
        "Requires authentication and tenant access."
    ),
    "update_customer": (
        "Update customer information such as email or name. "
        "Requires authentication and tenant access."
    ),
    "delete_customer": (
        "Delete a Stripe customer. "
        "Requires authentication and tenant access. This operation cannot be undone."
    ),
    "create_subscription": (
        "Create a new subscription for a customer. "
        "Requires authentication and valid Stripe customer ID."
    ),
    "get_subscription": (
        "Retrieve subscription information for a tenant. "
        "Requires authentication and tenant access."
    ),
    "update_subscription": (
        "Update subscription tier or cancellation preference. "
        "Requires authentication and tenant access."
    ),
    "cancel_subscription": (
        "Cancel a subscription. "
        "Can cancel immediately or at period end. "
        "Requires authentication and tenant access."
    ),
}


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Request models
    'CreateCustomerRequest',
    'UpdateCustomerRequest',
    'CreateSubscriptionRequest',
    'UpdateSubscriptionRequest',
    # Response models
    'CustomerResponse',
    'SubscriptionResponse',
    'WebhookAckResponse',
    'ErrorResponse',
    'UsageBreakdown',
    'CostBreakdown',
    'SyncStatus',
    'UsageSummaryResponse',
    # Enums
    'SubscriptionTier',
    'SubscriptionStatus',
    # Documentation
    'BILLING_API_TAGS',
    'BILLING_ENDPOINT_DESCRIPTIONS',
]
