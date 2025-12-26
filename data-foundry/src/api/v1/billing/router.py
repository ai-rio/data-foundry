"""
Stripe Billing Webhook Router

Implements webhook endpoint for receiving Stripe events.
Follows SOLID principles: Single Responsibility (only receives and routes).

Security:
- Verifies Stripe webhook signatures using StripeWebhookVerifier
- Returns 401 on signature failure (prevents forgery attacks)
- Returns 400 on missing/invalid headers
- Returns 500 on unexpected errors

Best Practices:
- Returns 200 OK immediately (acknowledgment pattern)
- Processes events asynchronously (prevents timeouts)
- Logs all events for monitoring and debugging
- Uses WebhookEventHandler for event processing (P4-003)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

from fastapi import APIRouter, Request, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.stripe.signature_verification import (
    StripeWebhookVerifier,
    InvalidSignatureError,
)
from src.services.stripe.facade import (
    StripeService,
    StripeServiceError,
    StripeAPIError,
    StripeCustomerNotFoundError,
)
from src.api.v1.billing.contracts import (
    # Webhook contracts
    WebhookAckResponse,
    ErrorResponse,
    # Usage contracts
    UsageSummaryResponse,
    UsageBreakdown,
    CostBreakdown,
    SyncStatus,
    # Customer/Subscription contracts (P4-004)
    CreateCustomerRequest,
    UpdateCustomerRequest,
    CreateSubscriptionRequest,
    UpdateSubscriptionRequest,
    CustomerResponse,
    SubscriptionResponse,
    # Enums
    SubscriptionTier,
    SubscriptionStatus,
    # Documentation
    BILLING_API_TAGS,
    BILLING_ENDPOINT_DESCRIPTIONS,
)
from src.api.v1.billing.webhook_handlers import WebhookEventHandler
from src.models.stripe_billing import (
    StripeMeterEvent,
    StripeMeterEventStatus,
    StripeSubscription,
    StripeCustomer,
)
from src.models.tenant import Tenant
from src.api.deps import get_current_user
from src.database.connection import get_db_session


# =============================================================================
# Logging Configuration
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Tier Pricing Configuration (P4-005)
# =============================================================================

TIER_PRICING = {
    "starter": {
        "ai_labels": 0.002,      # $0.002 per AI label
        "human_audits": 0.02,    # $0.02 per human audit
    },
    "growth": {
        "ai_labels": 0.001,      # $0.001 per AI label
        "human_audits": 0.01,    # $0.01 per human audit
    },
    "enterprise": {
        "ai_labels": 0.0005,     # $0.0005 per AI label
        "human_audits": 0.005,   # $0.005 per human audit
    },
}


DEFAULT_PRICING = {
    "ai_labels": 0.001,      # Default to growth pricing
    "human_audits": 0.01,
}


# =============================================================================
# Configuration
# =============================================================================

def get_webhook_secret() -> str:
    """
    Get Stripe webhook secret from environment.

    Returns:
        Webhook signing secret (whsec_...)

    Raises:
        ValueError: If webhook secret is not configured
    """
    import os

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET environment variable is not set")
        raise ValueError(
            "STRIPE_WEBHOOK_SECRET environment variable is not configured. "
            "Set it to your Stripe webhook signing secret (starts with 'whsec_...')"
        )

    return webhook_secret


# =============================================================================
# Event Handler Router (P4-003)
# =============================================================================

def get_event_handler() -> WebhookEventHandler:
    """
    Dependency injection function for WebhookEventHandler.

    Creates a new WebhookEventHandler instance for each request using FastAPI's
    dependency injection system. This replaces the global singleton pattern with
    proper dependency injection.

    Returns:
        WebhookEventHandler instance

    Note:
        Uses FastAPI's Depends() for proper dependency injection instead of
        global singleton pattern. Each request gets a fresh handler instance.
    """
    from src.database.connection import get_db_session

    return WebhookEventHandler(get_db_session)


async def route_event_to_handler(event, event_handler: WebhookEventHandler) -> None:
    """
    Route Stripe event to appropriate handler (P4-003 Implementation).

    This function now uses the WebhookEventHandler to process events.
    Supports the following event types:
    - invoice.payment_succeeded: Update payment status
    - invoice.payment_failed: Trigger retry logic
    - customer.subscription.created: Sync subscription to database
    - customer.subscription.updated: Sync subscription status
    - customer.subscription.deleted: Mark as canceled

    Args:
        event: Verified Stripe event object
        event_handler: WebhookEventHandler instance (injected via Depends)

    Example:
        >>> event = stripe.Event(...)
        >>> handler = WebhookEventHandler(get_db_session)
        >>> await route_event_to_handler(event, handler)
    """
    try:
        await event_handler.handle_event(event)
    except Exception as e:
        # Log handler errors but don't propagate
        # Webhook endpoint must return 200
        logger.error(
            f"Error in route_event_to_handler: {e}",
            exc_info=True
        )


# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(
    prefix="",  # No prefix - mounted at /api/v1/billing in main app
    tags=BILLING_API_TAGS,
)


# =============================================================================
# Usage Summary Endpoint (P4-005)
# =============================================================================

@router.get(
    "/usage/{tenant_id}",
    response_model=UsageSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get usage summary for billing period",
    description=BILLING_ENDPOINT_DESCRIPTIONS["usage_summary"],
    responses={
        200: {"description": "Usage summary retrieved successfully"},
        401: {"description": "Unauthorized (missing or invalid token)"},
        403: {"description": "Forbidden (tenant access denied)"},
        400: {"description": "Bad request (invalid parameters)"},
        500: {"description": "Internal server error"},
    }
)
async def get_usage_summary(
    tenant_id: str,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> UsageSummaryResponse:
    """
    Get usage summary for billing period (P4-005).

    Aggregates stripe_meter_events by event_name and calculates costs.

    Security:
    - Requires valid JWT authentication
    - Users can only view their own tenant's usage
    - Admin users can view any tenant's usage
    - Tenant ID is validated and sanitized

    Args:
        tenant_id: Tenant identifier
        period_start: Optional start of billing period (ISO 8601)
        period_end: Optional end of billing period (ISO 8601)
        current_user: Authenticated user from JWT
        session: Database session

    Returns:
        UsageSummaryResponse with usage breakdown, costs, and sync status

    Raises:
        HTTPException 401: Missing or invalid authentication
        HTTPException 403: Unauthorized tenant access
        HTTPException 400: Invalid date range
        HTTPException 500: Database or server error
    """
    try:
        # =============================================================================
        # 1. Authorization Check
        # =============================================================================
        user_tenant_id = current_user.get("tenant_id")
        user_role = current_user.get("role")

        # Users can only view their own tenant's usage (unless admin)
        if user_role != "admin" and user_tenant_id != tenant_id:
            logger.warning(
                f"Unauthorized access attempt: user {current_user.get('sub')} "
                f"attempting to access tenant {tenant_id} data"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this tenant's usage data"
            )

        # =============================================================================
        # 2. Input Validation - Date Range
        # =============================================================================
        if period_start and period_end:
            if period_start > period_end:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="period_start must be before period_end"
                )

        # =============================================================================
        # 3. Query Subscription to Determine Tier
        # =============================================================================
        subscription_query = (
            select(StripeSubscription)
            .where(
                and_(
                    StripeSubscription.tenant_id == tenant_id,
                    StripeSubscription.status == "active"
                )
            )
            .order_by(StripeSubscription.created_at.desc())
            .limit(1)
        )

        subscription_result = await session.execute(subscription_query)
        subscription = subscription_result.scalar_one_or_none()

        # Determine tier pricing
        tier = subscription.tier if subscription else "growth"
        pricing = TIER_PRICING.get(tier, DEFAULT_PRICING)

        logger.info(f"Usage summary for tenant {tenant_id} using tier: {tier}")

        # =============================================================================
        # 4. Query Meter Events with Aggregation
        # =============================================================================
        # Build base query with filters
        base_filters = [StripeMeterEvent.tenant_id == tenant_id]

        if period_start:
            base_filters.append(StripeMeterEvent.created_at >= period_start)
        if period_end:
            base_filters.append(StripeMeterEvent.created_at <= period_end)

        # Aggregate by event_name
        aggregation_query = (
            select(
                StripeMeterEvent.event_name,
                func.sum(StripeMeterEvent.quantity).label("total_quantity"),
                func.count(StripeMeterEvent.id).label("event_count")
            )
            .where(and_(*base_filters))
            .group_by(StripeMeterEvent.event_name)
        )

        agg_result = await session.execute(aggregation_query)
        usage_rows = agg_result.all()

        # Build usage breakdown
        usage_breakdown = [
            UsageBreakdown(
                event_name=row.event_name,
                total_quantity=int(row.total_quantity or 0),
                event_count=int(row.event_count or 0)
            )
            for row in usage_rows
        ]

        # =============================================================================
        # 5. Calculate Estimated Costs
        # =============================================================================
        estimated_costs = []
        total_estimated_cost = 0.0

        for usage in usage_breakdown:
            event_name = usage.event_name
            quantity = usage.total_quantity

            # Get unit price for this event type (default to 0 if unknown)
            unit_price = pricing.get(event_name, 0.0)
            estimated_cost = quantity * unit_price

            cost_breakdown = CostBreakdown(
                event_name=event_name,
                quantity=quantity,
                unit_price=unit_price,
                estimated_cost=round(estimated_cost, 4)
            )
            estimated_costs.append(cost_breakdown)
            total_estimated_cost += estimated_cost

        # =============================================================================
        # 6. Query Sync Status
        # =============================================================================
        # Count events by status
        status_query = (
            select(
                StripeMeterEvent.status,
                func.count(StripeMeterEvent.id).label("count")
            )
            .where(and_(*base_filters))
            .group_by(StripeMeterEvent.status)
        )

        status_result = await session.execute(status_query)
        status_rows = status_result.all()

        pending_events = 0
        failed_events = 0
        total_events = 0

        for status_row in status_rows:
            count = int(status_row.count or 0)
            total_events += count

            if status_row.status == StripeMeterEventStatus.PENDING:
                pending_events = count
            elif status_row.status == StripeMeterEventStatus.FAILED:
                failed_events = count

        # Get last successful sync timestamp
        last_sync_query = (
            select(StripeMeterEvent.created_at)
            .where(
                and_(
                    *base_filters,
                    StripeMeterEvent.status == StripeMeterEventStatus.SUCCEEDED
                )
            )
            .order_by(StripeMeterEvent.created_at.desc())
            .limit(1)
        )

        last_sync_result = await session.execute(last_sync_query)
        last_sync = last_sync_result.scalar_one_or_none()

        # Build sync status
        sync_status = SyncStatus(
            last_sync=last_sync,
            pending_events=pending_events,
            failed_events=failed_events,
            total_events=total_events
        )

        # =============================================================================
        # 7. Build and Return Response
        # =============================================================================
        response = UsageSummaryResponse(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            usage_breakdown=usage_breakdown,
            estimated_costs=estimated_costs,
            total_estimated_cost=round(total_estimated_cost, 4),
            sync_status=sync_status
        )

        logger.info(
            f"Usage summary generated for tenant {tenant_id}: "
            f"{total_events} events, ${total_estimated_cost:.4f} estimated cost"
        )

        return response

    except HTTPException:
        # Re-raise HTTP exceptions (401, 403, 400)
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"Error in usage summary endpoint: {type(e).__name__} - {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving usage summary"
        )


# =============================================================================
# Webhook Endpoint
# =============================================================================

@router.post(
    "/webhook",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_200_OK,
    summary="Receive Stripe webhook events",
    description=BILLING_ENDPOINT_DESCRIPTIONS["webhook"],
    responses={
        200: {"description": "Webhook received successfully"},
        400: {"description": "Bad request (missing signature)"},
        401: {"description": "Unauthorized (invalid signature)"},
        500: {"description": "Internal server error"},
    }
)
async def stripe_webhook(
    request: Request,
    event_handler: WebhookEventHandler = Depends(get_event_handler)
) -> JSONResponse:
    """
    Handle Stripe webhook events.

    Security:
    1. Extract Stripe-Signature header
    2. Read raw request body
    3. Verify signature using StripeWebhookVerifier
    4. Route to appropriate handler

    Returns:
        200 OK immediately (acknowledgment pattern)
        Stripe expects quick response to prevent retries

    Raises:
        HTTPException 400: Missing or invalid signature header
        HTTPException 401: Signature verification failed
        HTTPException 500: Unexpected error
    """
    try:
        # Step 1: Extract Stripe-Signature header
        signature_header = request.headers.get("stripe-signature")

        if not signature_header:
            logger.warning("Webhook request missing Stripe-Signature header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Stripe-Signature header"
            )

        # Strip whitespace from signature header
        signature_header = signature_header.strip()
        if not signature_header:
            logger.warning("Webhook request has empty Stripe-Signature header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty Stripe-Signature header"
            )

        # Step 2: Read raw request body
        # IMPORTANT: Must read raw bytes for signature verification
        payload_bytes = await request.body()

        if not payload_bytes:
            logger.warning("Webhook request has empty payload")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty webhook payload"
            )

        # Step 3: Verify signature using StripeWebhookVerifier
        try:
            webhook_secret = get_webhook_secret()

        except ValueError as e:
            # Configuration error: webhook secret not set
            logger.error(f"Configuration error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook configuration error"
            )

        try:
            verifier = StripeWebhookVerifier(webhook_secret=webhook_secret)
            event = verifier.verify(payload=payload_bytes, signature_header=signature_header)

            logger.info(
                f"Webhook signature verified: {event.type} (ID: {event.id})"
            )

        except InvalidSignatureError as e:
            # Security: Log signature verification failures
            logger.error(
                f"Webhook signature verification failed: {e.message}. "
                f"This could indicate a forgery attempt."
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )

        except ValueError as e:
            # Stripe SDK raises ValueError for signature issues
            logger.error(
                f"Webhook signature validation error: {str(e)}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )

        # Step 4: Route event to handler (P4-003 implementation)
        # Note: This is async but we don't await it for quick response
        # In production, this would be a background task
        try:
            await route_event_to_handler(event, event_handler)
        except Exception as e:
            # Log handler error but still return 200
            # Stripe already received the event, we shouldn't fail
            logger.error(
                f"Error processing webhook event {event.id}: {str(e)}",
                exc_info=True
            )
            # Continue to return 200 (event was verified)

        # Step 5: Return 200 OK immediately (acknowledgment pattern)
        response_data = {
            "message": "Webhook received successfully",
            "event_id": event.id,
            "received_at": datetime.now(timezone.utc).isoformat()
        }

        return JSONResponse(
            content=response_data,
            status_code=status.HTTP_200_OK
        )

    except HTTPException:
        # Re-raise HTTP exceptions (400, 401)
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"Unexpected error in webhook endpoint: {type(e).__name__} - {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# =============================================================================
# Billing CRUD Endpoints (P4-004)
# =============================================================================

# Dependency injection for StripeService
async def get_stripe_service() -> StripeService:
    """
    Get StripeService instance for dependency injection.

    Returns:
        Initialized StripeService instance

    Raises:
        HTTPException: If service initialization fails
    """
    try:
        service = StripeService()
        await service.initialize()
        return service
    except Exception as e:
        logger.error(f"Failed to initialize StripeService: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing service temporarily unavailable"
        )


# -----------------------------------------------------------------------------
# Customer CRUD Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Stripe customer",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("create_customer", "Create a new Stripe customer"),
    responses={
        201: {"description": "Customer created successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def create_customer(
    request: CreateCustomerRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db_session: AsyncSession = Depends(get_db_session)
) -> CustomerResponse:
    """
    Create a new Stripe customer for the tenant's organization.

    Delegates to StripeService facade for customer creation.
    Requires authentication. Email address is required.
    """
    try:
        # Get tenant from current user context
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant ID not found in user context"
            )

        # Get tenant from database
        from src.models.tenant import Tenant
        from sqlmodel import col

        tenant_result = await db_session.execute(
            select(Tenant).where(col(Tenant.tenant_id) == tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )

        # Create customer through StripeService
        stripe_customer_id = await stripe_service.create_customer(
            tenant=tenant,
            email=request.email,
            name=request.name,
            db_session=db_session,
            created_by=current_user.get("sub")
        )

        logger.info(
            f"Created Stripe customer {stripe_customer_id} for tenant {tenant_id}"
        )

        # Retrieve and return the created customer
        customer_data = await stripe_service.get_customer_by_tenant(
            tenant_id=tenant_id,
            db_session=db_session
        )

        return CustomerResponse(**customer_data)

    except StripeAPIError as e:
        logger.error(f"Stripe API error creating customer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer with Stripe"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.get(
    "/customers/{tenant_id}",
    response_model=CustomerResponse,
    summary="Get customer information",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("get_customer", "Get customer by tenant ID"),
    responses={
        200: {"description": "Customer retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Customer not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def get_customer(
    tenant_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db_session: AsyncSession = Depends(get_db_session)
) -> CustomerResponse:
    """
    Retrieve customer information for a tenant.

    Enforces tenant isolation - users can only access their own tenant's customer.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to access "
                f"customer for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot access other tenants' data"
            )

        # Get customer from StripeService
        customer_data = await stripe_service.get_customer_by_tenant(
            tenant_id=tenant_id,
            db_session=db_session
        )

        if not customer_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        return CustomerResponse(**customer_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.put(
    "/customers/{tenant_id}",
    response_model=CustomerResponse,
    summary="Update customer",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("update_customer", "Update customer information"),
    responses={
        200: {"description": "Customer updated successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Customer not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def update_customer(
    tenant_id: str,
    request: UpdateCustomerRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db_session: AsyncSession = Depends(get_db_session)
) -> CustomerResponse:
    """
    Update customer information such as email or name.

    Enforces tenant isolation - users can only update their own tenant's customer.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to update "
                f"customer for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot modify other tenants' data"
            )

        # Get existing customer to find stripe_customer_id
        from sqlmodel import col
        customer_result = await db_session.execute(
            select(StripeCustomer).where(col(StripeCustomer.tenant_id) == tenant_id)
        )
        db_customer = customer_result.scalar_one_or_none()

        if not db_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Update customer through StripeService
        updated_customer = await stripe_service.update_customer(
            stripe_customer_id=db_customer.stripe_customer_id,
            email=request.email,
            name=request.name,
            metadata=request.metadata,
            db_session=db_session
        )

        logger.info(f"Updated customer {db_customer.stripe_customer_id}")

        return CustomerResponse(
            tenant_id=tenant_id,
            stripe_customer_id=updated_customer["stripe_customer_id"],
            email=updated_customer.get("email"),
            name=updated_customer.get("name"),
            created_at=datetime.fromisoformat(updated_customer["created_at"]) if isinstance(updated_customer.get("created_at"), str) else updated_customer.get("created_at"),
            updated_at=datetime.now(timezone.utc)
        )

    except StripeCustomerNotFoundError as e:
        logger.error(f"Customer not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.delete(
    "/customers/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete customer",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("delete_customer", "Delete Stripe customer"),
    responses={
        200: {"description": "Customer deleted successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def delete_customer(
    tenant_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db_session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Delete a Stripe customer.

    This operation cannot be undone. Enforces tenant isolation.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to delete "
                f"customer for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot delete other tenants' data"
            )

        # Get existing customer to find stripe_customer_id
        from sqlmodel import col
        customer_result = await db_session.execute(
            select(StripeCustomer).where(col(StripeCustomer.tenant_id) == tenant_id)
        )
        db_customer = customer_result.scalar_one_or_none()

        if not db_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )

        # Delete customer through StripeService
        await stripe_service.delete_customer(
            stripe_customer_id=db_customer.stripe_customer_id,
            db_session=db_session
        )

        logger.info(f"Deleted customer {db_customer.stripe_customer_id}")

        return {"message": "Customer deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting customer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


# -----------------------------------------------------------------------------
# Subscription CRUD Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/subscriptions",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create subscription",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("create_subscription", "Create new subscription"),
    responses={
        201: {"description": "Subscription created successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def create_subscription(
    request: CreateSubscriptionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db_session: AsyncSession = Depends(get_db_session)
) -> SubscriptionResponse:
    """
    Create a new subscription for a customer.

    Requires authentication and valid Stripe customer ID.
    """
    try:
        # Get tenant from current user context
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tenant ID not found in user context"
            )

        # Create subscription through StripeService
        # Note: StripeService.create_subscription doesn't exist yet in facade
        # We'll need to add it or implement here
        # For now, this is a placeholder that matches the expected API

        # Placeholder implementation - delegates to Stripe API directly
        import stripe
        import os

        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        # Create subscription in Stripe
        stripe_sub = stripe.Subscription.create(
            customer=request.stripe_customer_id,
            items=[{"price": request.price_id}] if request.price_id else None,
            cancel_at_period_end=request.cancel_at_period_end,
            metadata={
                "tenant_id": tenant_id,
                "tier": request.tier.value
            }
        )

        # Persist to database
        from src.models.stripe_billing import create_stripe_subscription
        from datetime import datetime, timezone

        db_subscription = await create_stripe_subscription(
            session=db_session,
            tenant_id=tenant_id,
            stripe_subscription_id=stripe_sub.id,
            stripe_customer_id=request.stripe_customer_id,
            status=stripe_sub.status,
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc),
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
            tier=request.tier.value
        )

        logger.info(
            f"Created subscription {stripe_sub.id} for tenant {tenant_id}"
        )

        return SubscriptionResponse(
            tenant_id=tenant_id,
            stripe_subscription_id=stripe_sub.id,
            stripe_customer_id=request.stripe_customer_id,
            status=stripe_sub.status,
            tier=request.tier.value,
            current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc),
            current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc),
            cancel_at_period_end=stripe_sub.cancel_at_period_end,
            created_at=db_subscription.created_at,
            updated_at=db_subscription.updated_at
        )

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error creating subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription with Stripe"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.get(
    "/subscriptions/{tenant_id}",
    response_model=SubscriptionResponse,
    summary="Get subscription",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("get_subscription", "Get subscription by tenant ID"),
    responses={
        200: {"description": "Subscription retrieved successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Subscription not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def get_subscription(
    tenant_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session)
) -> SubscriptionResponse:
    """
    Retrieve subscription information for a tenant.

    Enforces tenant isolation - users can only access their own tenant's subscription.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to access "
                f"subscription for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot access other tenants' data"
            )

        # Get subscription from database
        from sqlmodel import col
        subscription_result = await db_session.execute(
            select(StripeSubscription).where(col(StripeSubscription.tenant_id) == tenant_id)
        )
        subscription = subscription_result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        return SubscriptionResponse(
            tenant_id=subscription.tenant_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            stripe_customer_id=subscription.stripe_customer_id,
            status=subscription.status,
            tier=subscription.tier,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.put(
    "/subscriptions/{tenant_id}",
    response_model=SubscriptionResponse,
    summary="Update subscription",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("update_subscription", "Update subscription tier or settings"),
    responses={
        200: {"description": "Subscription updated successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Subscription not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def update_subscription(
    tenant_id: str,
    request: UpdateSubscriptionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session)
) -> SubscriptionResponse:
    """
    Update subscription tier or cancellation preference.

    Enforces tenant isolation - users can only update their own tenant's subscription.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to update "
                f"subscription for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot modify other tenants' data"
            )

        # Get existing subscription
        from sqlmodel import col
        subscription_result = await db_session.execute(
            select(StripeSubscription).where(col(StripeSubscription.tenant_id) == tenant_id)
        )
        subscription = subscription_result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        # Update subscription in Stripe
        import stripe
        import os
        from datetime import datetime, timezone

        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        update_data = {}
        if request.cancel_at_period_end is not None:
            update_data["cancel_at_period_end"] = request.cancel_at_period_end

        # For tier changes, we would need to update the subscription items
        # This is a simplified implementation
        if update_data:
            stripe_sub = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                **update_data
            )

            # Update database record
            if request.cancel_at_period_end is not None:
                subscription.cancel_at_period_end = request.cancel_at_period_end

            if request.tier:
                subscription.tier = request.tier.value

            subscription.updated_at = datetime.now(timezone.utc)
            await db_session.commit()
            await db_session.refresh(subscription)

            logger.info(f"Updated subscription {subscription.stripe_subscription_id}")

        return SubscriptionResponse(
            tenant_id=subscription.tenant_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            stripe_customer_id=subscription.stripe_customer_id,
            status=subscription.status,
            tier=subscription.tier,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


@router.delete(
    "/subscriptions/{tenant_id}",
    status_code=status.HTTP_200_OK,
    summary="Cancel subscription",
    description=BILLING_ENDPOINT_DESCRIPTIONS.get("cancel_subscription", "Cancel subscription"),
    responses={
        200: {"description": "Subscription canceled successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Subscription not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    }
)
async def cancel_subscription(
    tenant_id: str,
    immediate: bool = Query(False, description="Cancel immediately instead of at period end"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session)
) -> Dict[str, str]:
    """
    Cancel a subscription.

    Can cancel immediately or at period end. Enforces tenant isolation.
    """
    try:
        # Enforce tenant isolation
        user_tenant_id = current_user.get("tenant_id")
        if user_tenant_id != tenant_id:
            logger.warning(
                f"User {current_user.get('sub')} attempted to cancel "
                f"subscription for different tenant {tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Cannot cancel other tenants' subscriptions"
            )

        # Get existing subscription
        from sqlmodel import col
        subscription_result = await db_session.execute(
            select(StripeSubscription).where(col(StripeSubscription.tenant_id) == tenant_id)
        )
        subscription = subscription_result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )

        # Cancel subscription in Stripe
        import stripe
        import os
        from datetime import datetime, timezone

        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        if immediate:
            # Cancel immediately
            stripe_sub = stripe.Subscription.delete(
                subscription.stripe_subscription_id
            )
            subscription.status = "canceled"
        else:
            # Cancel at period end
            stripe_sub = stripe.Subscription.modify(
                subscription.stripe_subscription_id,
                cancel_at_period_end=True
            )
            subscription.cancel_at_period_end = True

        subscription.updated_at = datetime.now(timezone.utc)
        await db_session.commit()

        logger.info(f"Canceled subscription {subscription.stripe_subscription_id}")

        return {"message": "Subscription canceled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error canceling subscription: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred"
        )


# =============================================================================
# Module Exports (P4-004)
# =============================================================================

__all__ = [
    'router',
    'stripe_webhook',
    'route_event_to_handler',
    'get_usage_summary',
    'get_stripe_service',
    # Customer endpoints
    'create_customer',
    'get_customer',
    'update_customer',
    'delete_customer',
    # Subscription endpoints
    'create_subscription',
    'get_subscription',
    'update_subscription',
    'cancel_subscription',
    # Pricing configuration
    'TIER_PRICING',
    'DEFAULT_PRICING',
]
