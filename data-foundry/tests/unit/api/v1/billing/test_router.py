"""
Test suite for Stripe Billing Webhook Router.

TDD Approach: Red-Green-Refactor
- These tests are written FIRST (Red phase)
- They will FAIL until implementation is complete
- This ensures 95%+ test coverage from the start

Security Critical: Webhook endpoint must verify signatures to prevent forgery.
All security scenarios must be tested.
"""

import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime

import pytest
from fastapi import status, HTTPException
from fastapi.responses import JSONResponse
from stripe import Event

from src.api.v1.billing.router import stripe_webhook
from src.services.stripe.signature_verification import InvalidSignatureError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def webhook_secret():
    """Valid webhook secret for testing."""
    return "whsec_test_secret_1234567890abcdef"


@pytest.fixture
def sample_stripe_event():
    """Sample Stripe event object."""
    event_dict = {
        "id": "evt_test_12345",
        "object": "event",
        "api_version": "2020-08-27",
        "created": 1234567890,
        "type": "customer.created",
        "data": {
            "object": {
                "id": "cus_test_123",
                "object": "customer",
                "email": "test@example.com",
                "name": "Test Customer"
            }
        }
    }
    # Create a mock Event object
    event = Mock(spec=Event)
    event.id = "evt_test_12345"
    event.type = "customer.created"
    event.data = event_dict["data"]
    event.to_dict.return_value = event_dict
    return event


@pytest.fixture
def sample_webhook_payload():
    """Sample webhook payload as bytes."""
    payload = {
        "id": "evt_test_12345",
        "object": "event",
        "api_version": "2020-08-27",
        "created": 1234567890,
        "type": "customer.created",
        "data": {
            "object": {
                "id": "cus_test_123",
                "object": "customer",
                "email": "test@example.com"
            }
        }
    }
    return json.dumps(payload).encode('utf-8')


@pytest.fixture
def mock_request(sample_webhook_payload):
    """Mock FastAPI request with webhook payload."""
    request = Mock()
    request.headers = {}
    request.body = AsyncMock(return_value=sample_webhook_payload)
    return request


@pytest.fixture
def mock_verifier(webhook_secret, sample_stripe_event):
    """Mock StripeWebhookVerifier."""
    verifier = Mock()
    verifier.verify.return_value = sample_stripe_event
    return verifier


# =============================================================================
# Test Cases: Happy Path
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_valid_signature_returns_200(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that valid webhook signature returns 200 OK.

    This is the happy path - Stripe sends webhook with valid signature.
    Endpoint should:
    1. Verify signature
    2. Route to handler
    3. Return 200 OK quickly (acknowledgment)
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_12345"
        mock_event.type = "customer.created"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                mock_route.return_value = None

                # Act
                response = await stripe_webhook(mock_request)

                # Assert
                assert response.status_code == status.HTTP_200_OK
                mock_verifier_instance.verify.assert_called_once()
                # route_event_to_handler is now called with event and event_handler
                assert mock_route.call_count == 1
                call_args = mock_route.call_args
                assert call_args[0][0] == mock_event  # First arg is the event


# =============================================================================
# Test Cases: Signature Verification (Security)
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that invalid webhook signature returns 401 Unauthorized.

    Security Critical: Prevents webhook forgery attacks.
    """
    # Arrange
    signature_header = "t=1234567890,v1=invalid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.side_effect = InvalidSignatureError(
            "Webhook signature verification failed"
        )
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(mock_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            mock_verifier_instance.verify.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_missing_signature_header_returns_400(
    mock_request,
    webhook_secret
):
    """
    Test that missing signature header returns 400 Bad Request.

    Edge case: Stripe-Signature header is completely missing.
    """
    # Arrange
    mock_request.headers = {}  # No signature header

    with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
        mock_get_secret.return_value = webhook_secret

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_webhook_empty_signature_returns_400(
    mock_request,
    webhook_secret
):
    """
    Test that empty signature header returns 400 Bad Request.

    Edge case: Stripe-Signature header exists but is empty/whitespace.
    """
    # Arrange
    mock_request.headers = {"stripe-signature": ""}

    with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
        mock_get_secret.return_value = webhook_secret

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_webhook_empty_payload_returns_400(
    mock_request,
    webhook_secret
):
    """
    Test that empty payload returns 400 Bad Request.

    Edge case: Request body is empty.
    """
    # Arrange
    mock_request.headers = {"stripe-signature": "t=1234567890,v1=signature"}
    mock_request.body.return_value = b""

    with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
        mock_get_secret.return_value = webhook_secret

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_webhook_missing_webhook_secret_raises_500(
    mock_request
):
    """
    Test that missing webhook secret raises 500.

    Configuration error: STRIPE_WEBHOOK_SECRET not set.
    """
    # Arrange
    mock_request.headers = {"stripe-signature": "t=1234567890,v1=signature"}

    with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
        # Simulate missing webhook secret
        mock_get_secret.side_effect = ValueError(
            "STRIPE_WEBHOOK_SECRET environment variable is not configured"
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await stripe_webhook(mock_request)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# Test Cases: Event Routing
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_routes_customer_created_event(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that customer.created event is routed correctly.

    Verifies event type routing logic.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_12345"
        mock_event.type = "customer.created"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                # Act
                await stripe_webhook(mock_request)

                # Assert
                # route_event_to_handler is now called with event and event_handler
                assert mock_route.call_count == 1
                called_event = mock_route.call_args[0][0]
                assert called_event.type == "customer.created"


@pytest.mark.asyncio
async def test_webhook_routes_invoice_paid_event(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that invoice.paid event is routed correctly.

    Verifies event type routing logic for invoice events.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_67890"
        mock_event.type = "invoice.paid"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                # Act
                await stripe_webhook(mock_request)

                # Assert
                # route_event_to_handler is now called with event and event_handler
                assert mock_route.call_count == 1
                called_event = mock_route.call_args[0][0]
                assert called_event.type == "invoice.paid"


@pytest.mark.asyncio
async def test_webhook_routes_subscription_deleted_event(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that customer.subscription.deleted event is routed correctly.

    Verifies event type routing logic for subscription events.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_subscription_deleted"
        mock_event.type = "customer.subscription.deleted"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                # Act
                await stripe_webhook(mock_request)

                # Assert
                # route_event_to_handler is now called with event and event_handler
                assert mock_route.call_count == 1
                called_event = mock_route.call_args[0][0]
                assert called_event.type == "customer.subscription.deleted"


# =============================================================================
# Test Cases: Error Handling
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_verification_error_raises_401(
    mock_request,
    webhook_secret
):
    """
    Test that InvalidSignatureError raises 401.

    Security: Verification failure should return 401, not 500.
    """
    # Arrange
    signature_header = "t=1234567890,v1=forged_signature"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.side_effect = InvalidSignatureError(
            "Webhook signature verification failed"
        )
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(mock_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_webhook_value_error_from_verifier_raises_401(
    mock_request,
    webhook_secret
):
    """
    Test that ValueError from verifier raises 401.

    Edge case: Stripe SDK raises ValueError for invalid parameters.
    """
    # Arrange
    signature_header = "t=1234567890,v1=malformed_signature"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.side_effect = ValueError(
            "Invalid signature format"
        )
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(mock_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_webhook_unexpected_error_during_verification_raises_500(
    mock_request,
    webhook_secret
):
    """
    Test that unexpected errors during verification raise 500.

    Safety net: Catch-all for unexpected exceptions during signature verification.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.side_effect = Exception("Unexpected error")
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(mock_request)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_webhook_handler_error_does_not_fail_webhook(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that handler errors don't cause webhook to fail.

    Best Practice: Even if handler fails, return 200 (event was verified).
    Stripe will not retry if we return 200.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_12345"
        mock_event.type = "customer.created"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                mock_route.side_effect = Exception("Unexpected error")

                # Act
                response = await stripe_webhook(mock_request)

                # Assert - Should still return 200 (best practice)
                # Even if handler fails, event was verified so we acknowledge
                assert response.status_code == status.HTTP_200_OK


# =============================================================================
# Test Cases: Performance and Best Practices
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_returns_quick_acknowledgment(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that webhook returns 200 quickly (acknowledgment pattern).

    Stripe Best Practice: Return 200 immediately, process asynchronously.
    This prevents Stripe from retrying the webhook.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_12345"
        mock_event.type = "customer.created"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                mock_route.return_value = None

                # Act
                response = await stripe_webhook(mock_request)

                # Assert
                # Should return 200 immediately
                assert response.status_code == status.HTTP_200_OK

                # Response should contain success message
                response_body = json.loads(response.body.decode())
                assert "received" in response_body.get("message", "").lower()


# =============================================================================
# Test Cases: Idempotency and Delivery
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_handles_duplicate_events(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that webhook handles duplicate event deliveries.

    Stripe may send same event multiple times (retries).
    Endpoint should handle gracefully.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_duplicate_123"  # Same event ID
        mock_event.type = "invoice.paid"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                mock_route.return_value = None

                # Act - First delivery
                response1 = await stripe_webhook(mock_request)

                # Act - Duplicate delivery (same event)
                response2 = await stripe_webhook(mock_request)

                # Assert
                assert response1.status_code == status.HTTP_200_OK
                assert response2.status_code == status.HTTP_200_OK
                assert mock_route.call_count == 2


# =============================================================================
# Test Cases: Response Format
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_returns_correct_response_format(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that webhook returns correct JSON response format.

    Verifies API contract / response schema.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_response_format"
        mock_event.type = "customer.created"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                # Act
                response = await stripe_webhook(mock_request)

                # Assert
                assert response.status_code == status.HTTP_200_OK
                assert response.headers["content-type"] == "application/json"

                response_body = json.loads(response.body.decode())
                assert "message" in response_body
                assert "event_id" in response_body
                assert response_body["event_id"] == "evt_test_response_format"


# =============================================================================
# Test Cases: Handler Integration (P4-003 Stub)
# =============================================================================

@pytest.mark.asyncio
async def test_webhook_routes_to_handler_stub(
    mock_request,
    sample_webhook_payload,
    webhook_secret
):
    """
    Test that webhook routes events to handler (P4-003 stub).

    Verifies integration point for P4-003 event handlers.
    """
    # Arrange
    signature_header = "t=1234567890,v1=valid_signature_hash"
    mock_request.headers = {"stripe-signature": signature_header}

    with patch('src.api.v1.billing.router.StripeWebhookVerifier') as MockVerifier:
        mock_event = Mock()
        mock_event.id = "evt_test_handler_integration"
        mock_event.type = "customer.subscription.updated"

        mock_verifier_instance = Mock()
        mock_verifier_instance.verify.return_value = mock_event
        MockVerifier.return_value = mock_verifier_instance

        with patch('src.api.v1.billing.router.get_webhook_secret') as mock_get_secret:
            mock_get_secret.return_value = webhook_secret

            with patch('src.api.v1.billing.router.route_event_to_handler') as mock_route:
                # Act
                await stripe_webhook(mock_request)

                # Assert
                # route_event_to_handler is now called with event and event_handler
                assert mock_route.call_count == 1
