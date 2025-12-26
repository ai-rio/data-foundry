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
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse

from src.services.stripe.signature_verification import (
    StripeWebhookVerifier,
    InvalidSignatureError,
)
from src.api.v1.billing.contracts import (
    WebhookAckResponse,
    ErrorResponse,
    BILLING_API_TAGS,
    BILLING_ENDPOINT_DESCRIPTIONS,
)
from src.api.v1.billing.webhook_handlers import WebhookEventHandler


# =============================================================================
# Logging Configuration
# =============================================================================

logger = logging.getLogger(__name__)


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

# Global event handler instance (initialized lazily)
# In production, consider dependency injection
_event_handler: Optional[WebhookEventHandler] = None


def get_event_handler() -> WebhookEventHandler:
    """
    Get or create the WebhookEventHandler instance.

    Returns:
        WebhookEventHandler instance

    Note:
        Uses singleton pattern for efficiency. The handler is created
        on first call and reused for subsequent requests.
    """
    global _event_handler
    if _event_handler is None:
        # Import here to avoid circular imports and allow lazy initialization
        from src.database.connection import get_db_session

        # Use get_db_session as the session factory
        _event_handler = WebhookEventHandler(get_db_session)
        logger.info("WebhookEventHandler initialized")
    return _event_handler


async def route_event_to_handler(event) -> None:
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

    Example:
        >>> event = stripe.Event(...)
        >>> await route_event_to_handler(event)
    """
    try:
        handler = get_event_handler()
        await handler.handle_event(event)
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
    prefix="/billing",
    tags=BILLING_API_TAGS,
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
async def stripe_webhook(request: Request) -> JSONResponse:
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

        # Step 4: Route event to handler (P4-003 stub)
        # Note: This is async but we don't await it for quick response
        # In production, this would be a background task
        try:
            await route_event_to_handler(event)
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
# Module Exports
# =============================================================================

__all__ = [
    'router',
    'stripe_webhook',
    'route_event_to_handler',
]
