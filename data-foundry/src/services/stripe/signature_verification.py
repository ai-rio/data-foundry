"""
Stripe Webhook Signature Verification Module.

This module provides secure webhook signature verification for Stripe webhooks.
It prevents webhook forgery attacks, replay attacks, and payload tampering.

Security Critical: This is a core security component. All changes must:
1. Maintain 100% test coverage
2. Pass security audits (score ≥ 95)
3. Follow SOLID principles (single responsibility)
4. Use constant-time comparison for signatures

Dependencies:
    stripe: Stripe SDK for webhook signature verification
"""

import logging
from typing import Optional

import stripe


# =============================================================================
# Logging Configuration
# =============================================================================

logger = logging.getLogger(__name__)


# =============================================================================
# Custom Exceptions
# =============================================================================

class InvalidSignatureError(Exception):
    """
    Raised when webhook signature verification fails.

    This exception indicates that the webhook request could not be verified
    as coming from Stripe. Possible causes:
    - Signature was forged
    - Payload was tampered with
    - Replay attack (old timestamp)
    - Webhook secret mismatch
    - Malformed signature header

    Attributes:
        message: Human-readable error message
        original_error: The original exception from Stripe SDK (if any)
    """

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        """
        Initialize InvalidSignatureError.

        Args:
            message: Human-readable error message
            original_error: The original exception from Stripe SDK (if any)
        """
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.original_error:
            return f"{self.message} (caused by: {type(self.original_error).__name__})"
        return self.message


# =============================================================================
# Main Verification Class
# =============================================================================

class StripeWebhookVerifier:
    """
    Verifies Stripe webhook signatures to prevent forgery attacks.

    This class provides a single responsibility: verifying that webhook
    requests originated from Stripe and have not been tampered with.

    Security Features:
    - HMAC-SHA256 signature verification
    - Timestamp validation (prevents replay attacks)
    - Constant-time comparison (prevents timing attacks)
    - Payload tamper detection

    Usage:
        verifier = StripeWebhookVerifier(webhook_secret="whsec_...")
        event = verifier.verify(payload_bytes, signature_header)

    The verifier uses Stripe's official SDK for signature verification,
    ensuring compatibility with Stripe's security model.

    Attributes:
        webhook_secret: The webhook signing secret from Stripe dashboard
    """

    def __init__(self, webhook_secret: str):
        """
        Initialize the webhook verifier with a signing secret.

        Args:
            webhook_secret: Stripe webhook signing secret (starts with 'whsec_...')
                          This secret is obtained from the Stripe Dashboard:
                          Developers > Webhooks > Select webhook > Signing secret

        Raises:
            ValueError: If webhook_secret is None, empty, or only whitespace

        Security:
            The webhook secret must be kept secure. Never expose it in logs,
            error messages, or version control. Use environment variables.
        """
        # Validate webhook_secret parameter
        if webhook_secret is None:
            raise ValueError(
                "webhook_secret cannot be None. "
                "Provide a valid Stripe webhook signing secret (whsec_...)"
            )

        if not isinstance(webhook_secret, str):
            raise ValueError(
                f"webhook_secret must be a string, got {type(webhook_secret).__name__}"
            )

        # Strip and check for empty/whitespace
        webhook_secret = webhook_secret.strip()
        if not webhook_secret:
            raise ValueError(
                "webhook_secret cannot be empty or whitespace. "
                "Provide a valid Stripe webhook signing secret (whsec_...)"
            )

        # Validate format (should start with 'whsec_')
        if not webhook_secret.startswith('whsec_'):
            logger.warning(
                f"webhook_secret should start with 'whsec_', got: {webhook_secret[:10]}..."
            )

        # Store the webhook secret
        self.webhook_secret = webhook_secret
        logger.info("StripeWebhookVerifier initialized successfully")

    def verify(self, payload: bytes | str, signature_header: str) -> stripe.Event:
        """
        Verify webhook signature and return the event.

        This method performs the following security checks:
        1. Validates the signature format (timestamp, version, signature)
        2. Verifies HMAC-SHA256 signature using webhook secret
        3. Checks timestamp to prevent replay attacks (~15 minute tolerance)
        4. Ensures payload hasn't been tampered with

        Args:
            payload: Raw webhook payload as bytes or string.
                     This is the request body received from Stripe.
            signature_header: Value of the Stripe-Signature header.
                            Format: "t=timestamp,v1=signature[,v1=signature2]"

        Returns:
            stripe.Event: Verified event object from Stripe.
                        Contains event type, data, and metadata.

        Raises:
            InvalidSignatureError: If signature verification fails.
                                  Check the error message for specific cause.
            ValueError: If parameters are invalid (None, wrong type, etc.)

        Security:
            - Uses Stripe SDK's construct_event for verification
            - Constant-time comparison prevents timing attacks
            - Timestamp validation prevents replay attacks
            - HMAC verification prevents signature forgery

        Example:
            >>> verifier = StripeWebhookVerifier("whsec_...")
            >>> event = verifier.verify(request.body, request.headers['Stripe-Signature'])
            >>> print(event.type)  # 'customer.created'
        """
        # Validate payload parameter
        if payload is None:
            raise ValueError(
                "payload cannot be None. "
                "Provide the webhook payload as bytes or string."
            )

        # Validate signature_header parameter
        if signature_header is None:
            raise InvalidSignatureError(
                "signature_header cannot be None. "
                "Provide the Stripe-Signature header value."
            )

        if not isinstance(signature_header, str):
            raise ValueError(
                f"signature_header must be a string, got {type(signature_header).__name__}"
            )

        # Strip and validate signature_header
        signature_header = signature_header.strip()
        if not signature_header:
            raise InvalidSignatureError(
                "signature_header cannot be empty or whitespace. "
                "Provide a valid Stripe-Signature header value."
            )

        # Convert payload to bytes if necessary
        if isinstance(payload, str):
            payload_bytes = payload.encode('utf-8')
        elif isinstance(payload, bytes):
            payload_bytes = payload
        else:
            raise ValueError(
                f"payload must be bytes or string, got {type(payload).__name__}"
            )

        # Verify signature using Stripe SDK
        try:
            logger.debug("Verifying webhook signature...")

            # Use Stripe SDK's construct_event for verification
            # This handles:
            # - Signature format validation
            # - HMAC-SHA256 verification
            # - Timestamp validation (replay attack prevention)
            # - Constant-time comparison (timing attack prevention)
            event = stripe.Webhook.construct_event(
                payload=payload_bytes,
                sig_header=signature_header,
                secret=self.webhook_secret,
                tolerance=900  # 15 minutes in seconds (Stripe's default)
            )

            logger.info(
                f"Webhook signature verified successfully. "
                f"Event ID: {event.id}, Type: {event.type}"
            )

            return event

        except ValueError as e:
            # Stripe SDK raises ValueError for signature verification failures
            # This includes: invalid signature, tampered payload, old timestamp
            error_msg = "Webhook signature verification failed"
            logger.error(
                f"{error_msg}: {str(e)}. "
                f"This could indicate: forged signature, tampered payload, "
                f"replay attack, or incorrect webhook secret."
            )
            raise InvalidSignatureError(error_msg, original_error=e) from e

        except Exception as e:
            # Catch any other unexpected errors
            error_msg = "Unexpected error during webhook signature verification"
            logger.error(
                f"{error_msg}: {type(e).__name__} - {str(e)}",
                exc_info=True
            )
            raise InvalidSignatureError(error_msg, original_error=e) from e


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    'StripeWebhookVerifier',
    'InvalidSignatureError',
]
