"""
Stripe billing models for metered subscription billing.

This module contains SQLModel definitions for Stripe subscription and meter event tracking,
following the existing patterns from usage_tracking.py.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import JSON, Column, Integer, String, DateTime, Boolean, Text
from sqlmodel import Field, SQLModel


class StripeSubscriptionStatus(str, Enum):
    """
    Stripe subscription status enumeration.

    Matches Stripe API subscription statuses:
    https://stripe.com/docs/api/subscriptions/object
    """
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


class StripeMeterEventStatus(str, Enum):
    """
    Stripe meter event status enumeration.

    Tracks the lifecycle of meter events sent to Stripe.
    """
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StripeSubscription(SQLModel, table=True):
    """
    Stripe subscription tracking model.

    Tracks subscription status and billing period information for tenant subscriptions.
    """

    __tablename__ = "stripe_subscriptions"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")

    # Stripe identifiers
    stripe_subscription_id: str = Field(
        unique=True,
        index=True,
        description="Unique Stripe subscription ID"
    )
    stripe_customer_id: str = Field(description="Stripe customer ID")

    # Subscription status - using enum for type safety
    status: StripeSubscriptionStatus = Field(
        index=True,
        description="Subscription status (active, canceled, past_due, etc.)"
    )

    # Billing period
    current_period_start: Optional[datetime] = Field(description="Current period start timestamp")
    current_period_end: Optional[datetime] = Field(description="Current period end timestamp")

    # Cancellation
    cancel_at_period_end: bool = Field(
        default=False,
        description="Whether subscription will cancel at period end"
    )

    # Tier information
    tier: Optional[str] = Field(description="Subscription tier/plan")

    # Audit trail
    created_by: Optional[str] = Field(description="User who created the record")
    updated_by: Optional[str] = Field(description="User who last updated the record")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class StripeMeterEvent(SQLModel, table=True):
    """
    Stripe meter event tracking model.

    Tracks metered usage events sent to Stripe for billing.
    """

    __tablename__ = "stripe_meter_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")

    # Event details
    event_name: str = Field(description="Name/type of the meter event")
    quantity: int = Field(description="Quantity to record in Stripe")

    # Batch processing
    batch_id: Optional[str] = Field(description="Batch ID for grouped events")

    # Idempotency
    idempotency_key: str = Field(
        unique=True,
        description="Unique idempotency key to prevent duplicate events"
    )

    # Stripe response
    stripe_response: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Stripe API response data"
    )

    # Status - using enum for type safety
    status: StripeMeterEventStatus = Field(
        index=True,
        description="Event status (pending, succeeded, failed)"
    )
    error_message: Optional[str] = Field(
        sa_column=Text,
        description="Error message if event failed"
    )

    # Audit trail
    created_by: Optional[str] = Field(description="User who created the record")
    updated_by: Optional[str] = Field(description="User who last updated the record")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    retried_at: Optional[datetime] = Field(description="Last retry timestamp")
    retry_count: int = Field(default=0, description="Number of retry attempts")

    class Config:
        use_enum_values = True


# Database operations (can be expanded later)
async def create_stripe_subscription(
    session,
    tenant_id: str,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    status: str,
    current_period_start: Optional[datetime] = None,
    current_period_end: Optional[datetime] = None,
    cancel_at_period_end: bool = False,
    tier: Optional[str] = None
) -> StripeSubscription:
    """
    Create a Stripe subscription record.

    Args:
        session: Database session
        tenant_id: Tenant identifier
        stripe_subscription_id: Stripe subscription ID
        stripe_customer_id: Stripe customer ID
        status: Subscription status
        current_period_start: Current billing period start
        current_period_end: Current billing period end
        cancel_at_period_end: Whether to cancel at period end
        tier: Subscription tier

    Returns:
        Created StripeSubscription instance
    """
    subscription = StripeSubscription(
        tenant_id=tenant_id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        status=status,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
        tier=tier
    )

    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)

    return subscription


async def create_stripe_meter_event(
    session,
    tenant_id: str,
    event_name: str,
    quantity: int,
    idempotency_key: str,
    batch_id: Optional[str] = None,
    stripe_response: Optional[Dict[str, Any]] = None,
    status: str = "pending"
) -> StripeMeterEvent:
    """
    Create a Stripe meter event record.

    Args:
        session: Database session
        tenant_id: Tenant identifier
        event_name: Name/type of meter event
        quantity: Quantity to record
        idempotency_key: Unique idempotency key
        batch_id: Optional batch ID
        stripe_response: Optional Stripe API response
        status: Event status

    Returns:
        Created StripeMeterEvent instance
    """
    event = StripeMeterEvent(
        tenant_id=tenant_id,
        event_name=event_name,
        quantity=quantity,
        batch_id=batch_id,
        idempotency_key=idempotency_key,
        stripe_response=stripe_response,
        status=status
    )

    session.add(event)
    await session.commit()
    await session.refresh(event)

    return event
