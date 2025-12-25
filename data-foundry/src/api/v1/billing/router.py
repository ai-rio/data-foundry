"""
Stripe Billing API Router

Provides endpoints for:
- Webhook handling for Stripe events
- Customer management
- Subscription management
- Usage reporting
"""

from fastapi import APIRouter, Request, Response, HTTPException, Header
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
import logging
import json
from stripe import WebhookSignature

from src.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
) -> JSONResponse:
    """
    Handle Stripe webhook events.

    Processes events like:
    - invoice.payment_succeeded
    - invoice.payment_failed
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.upcoming

    Webhook secret is stored in settings.SECRET_MANAGER_KEY
    """
    webhook_secret = settings._secret_manager.get_secret("STRIPE_WEBHOOK_SECRET")

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    payload = await request.body()
    sig_header = stripe_signature

    if not sig_header:
        logger.warning("Webhook received without Stripe-Signature header")
        raise HTTPException(status_code=400, detail="No signature provided")

    try:
        # Verify webhook signature
        event = WebhookSignature.construct_event(
            payload,
            sig_header,
            webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Handle the event
    event_type = event["type"]
    event_data = event["data"]["object"]

    logger.info(f"Received Stripe webhook: {event_type}")

    try:
        if event_type == "invoice.payment_succeeded":
            await handle_payment_succeeded(event_data)
        elif event_type == "invoice.payment_failed":
            await handle_payment_failed(event_data)
        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(event_data)
        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(event_data)
        elif event_type == "invoice.upcoming":
            await handle_invoice_upcoming(event_data)
        else:
            logger.info(f"Unhandled event type: {event_type}")

        return JSONResponse(content={"status": "success", "event_type": event_type})

    except Exception as e:
        logger.error(f"Error processing webhook {event_type}: {e}")
        # Return 200 to avoid retrying for processed events
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=200
        )


async def handle_payment_succeeded(invoice: Dict[str, Any]):
    """Handle successful payment event."""
    customer_id = invoice.get("customer")
    amount_paid = invoice.get("amount_paid")
    currency = invoice.get("currency")

    logger.info(f"Payment succeeded for customer {customer_id}: {amount_paid} {currency}")

    # TODO: Update payment status in database
    # TODO: Send confirmation email to customer


async def handle_payment_failed(invoice: Dict[str, Any]):
    """Handle failed payment event."""
    customer_id = invoice.get("customer")
    amount_due = invoice.get("amount_due")
    attempt_count = invoice.get("attempt_count")

    logger.warning(
        f"Payment failed for customer {customer_id}. "
        f"Attempt: {attempt_count}, Amount: {amount_due}"
    )

    # TODO: Update payment status in database
    # TODO: Send payment failed notification to customer


async def handle_subscription_updated(subscription: Dict[str, Any]):
    """Handle subscription update event."""
    customer_id = subscription.get("customer")
    status = subscription.get("status")
    current_period_end = subscription.get("current_period_end")

    logger.info(
        f"Subscription updated for customer {customer_id}. "
        f"Status: {status}"
    )

    # TODO: Update subscription status in database


async def handle_subscription_deleted(subscription: Dict[str, Any]):
    """Handle subscription deletion/cancellation event."""
    customer_id = subscription.get("customer")

    logger.info(f"Subscription deleted for customer {customer_id}")

    # TODO: Update subscription status in database


async def handle_invoice_upcoming(invoice: Dict[str, Any]):
    """Handle upcoming invoice event (sent before payment is attempted)."""
    customer_id = invoice.get("customer")
    amount_due = invoice.get("amount_due")
    currency = invoice.get("currency")

    logger.info(
        f"Upcoming invoice for customer {customer_id}: {amount_due} {currency}"
    )

    # TODO: Send invoice preview email to customer


@router.get("/health")
async def billing_health() -> Dict[str, str]:
    """Health check endpoint for billing service."""
    return {"status": "healthy", "service": "billing"}
