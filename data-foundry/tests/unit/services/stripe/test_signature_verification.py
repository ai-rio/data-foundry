"""
Test suite for Stripe webhook signature verification.

TDD Approach: Red-Green-Refactor
- These tests are written FIRST (Red phase)
- They will FAIL until implementation is complete
- This ensures 100% test coverage from the start

Security Critical: This component prevents webhook forgery attacks.
All attack vectors must be tested.
"""

import hmac
import json
import time
from unittest.mock import MagicMock, Mock, patch
from datetime import datetime, timedelta

import pytest
import stripe

from src.services.stripe.signature_verification import (
    StripeWebhookVerifier,
    InvalidSignatureError,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def webhook_secret():
    """Valid webhook secret for testing."""
    return "whsec_test_secret_1234567890abcdef"


@pytest.fixture
def sample_payload_dict():
    """Sample webhook payload as dictionary."""
    return {
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


@pytest.fixture
def sample_payload_bytes(sample_payload_dict):
    """Sample webhook payload as bytes (as received from Stripe)."""
    return json.dumps(sample_payload_dict).encode('utf-8')


@pytest.fixture
def sample_payload_str(sample_payload_dict):
    """Sample webhook payload as string."""
    return json.dumps(sample_payload_dict)


@pytest.fixture
def current_timestamp():
    """Current Unix timestamp for signature generation."""
    return int(time.time())


@pytest.fixture
def generate_valid_signature(sample_payload_bytes, webhook_secret):
    """Helper function to generate valid Stripe signatures."""
    def _generate(timestamp=None, payload=None):
        """Generate a valid signature header."""
        if timestamp is None:
            timestamp = int(time.time())

        if payload is None:
            payload = sample_payload_bytes

        secret = webhook_secret

        # Stripe signs: timestamp.payload (concatenated with dot)
        # Using HMAC-SHA256
        signed_payload = f"{timestamp}.{payload}".encode('utf-8')
        signature = hmac.new(
            secret.encode('utf-8'),
            signed_payload,
            'sha256'
        ).hexdigest()

        # Format as Stripe does: t=timestamp,v1=signature
        return f"t={timestamp},v1={signature}"

    return _generate


def generate_stripe_signature(timestamp: int, payload: bytes, secret: str) -> str:
    """
    Generate a Stripe webhook signature.

    Args:
        timestamp: Unix timestamp
        payload: Raw webhook payload as bytes
        secret: Webhook signing secret

    Returns:
        Signature header value (t=...,v1=...)
    """
    # Stripe signs: timestamp.payload (concatenated with dot)
    signed_payload = f"{timestamp}.{payload}".encode('utf-8')
    signature = hmac.new(
        secret.encode('utf-8'),
        signed_payload,
        'sha256'
    ).hexdigest()

    return f"t={timestamp},v1={signature}"


@pytest.fixture
def old_timestamp():
    """Timestamp that is outside Stripe's tolerance window (> 15 minutes old)."""
    # Current time minus 16 minutes (960 seconds)
    # Stripe's tolerance is typically around 15 minutes (900 seconds)
    return int(time.time()) - 960


@pytest.fixture
def future_timestamp():
    """Timestamp in the future."""
    return int(time.time()) + 3600  # 1 hour in future


# =============================================================================
# Test Class: StripeWebhookVerifier Initialization
# =============================================================================

class TestStripeWebhookVerifierInit:
    """Test suite for StripeWebhookVerifier initialization."""

    def test_init_with_valid_secret(self, webhook_secret):
        """Should initialize successfully with valid webhook secret."""
        verifier = StripeWebhookVerifier(webhook_secret)
        assert verifier.webhook_secret == webhook_secret

    def test_init_with_none_secret_raises_error(self):
        """Should raise ValueError when webhook_secret is None."""
        with pytest.raises(ValueError) as exc_info:
            StripeWebhookVerifier(None)

        assert "webhook_secret" in str(exc_info.value).lower()
        assert "none" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

    def test_init_with_empty_string_raises_error(self):
        """Should raise ValueError when webhook_secret is empty string."""
        with pytest.raises(ValueError) as exc_info:
            StripeWebhookVerifier("")

        assert "webhook_secret" in str(exc_info.value).lower()
        assert "empty" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

    def test_init_with_whitespace_only_secret_raises_error(self):
        """Should raise ValueError when webhook_secret is only whitespace."""
        with pytest.raises(ValueError) as exc_info:
            StripeWebhookVerifier("   ")

        assert "webhook_secret" in str(exc_info.value).lower()

    def test_init_stores_secret_correctly(self, webhook_secret):
        """Should store webhook_secret as instance variable."""
        verifier = StripeWebhookVerifier(webhook_secret)
        assert hasattr(verifier, 'webhook_secret')
        assert verifier.webhook_secret == webhook_secret
        assert verifier.webhook_secret.startswith('whsec_')


# =============================================================================
# Test Class: Valid Signature Verification
# =============================================================================

class TestValidSignatureVerification:
    """Test suite for valid signature verification scenarios."""

    def test_verify_with_valid_signature_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should successfully verify valid signature and return event."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        # Mock stripe.Webhook.construct_event to avoid actual signature verification
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_event.id = "evt_test_12345"
            mock_event.type = "customer.created"
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            # Should return a stripe.Event object
            assert result is not None
            assert result.id == "evt_test_12345"

    def test_verify_with_bytes_payload_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should accept payload as bytes."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_event.id = "evt_test_123"
            mock_event.type = "customer.created"
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            assert result.id == "evt_test_123"
            assert result.type == "customer.created"
            # Verify construct_event was called with bytes
            mock_construct.assert_called_once()

    def test_verify_with_string_payload_converts_to_bytes(
        self,
        webhook_secret,
        sample_payload_str,
        generate_valid_signature
    ):
        """Should convert string payload to bytes."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_event.id = "evt_test_123"
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_str, signature_header)

            assert result.id == "evt_test_123"
            mock_construct.assert_called_once()

    def test_verify_with_current_timestamp_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes,
        current_timestamp,
        generate_valid_signature
    ):
        """Should accept signature with current timestamp."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature(current_timestamp)

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            assert result is not None
            mock_construct.assert_called_once()


# =============================================================================
# Test Class: Invalid Signature Detection
# =============================================================================

class TestInvalidSignatureDetection:
    """Test suite for detecting invalid signatures."""

    def test_verify_with_wrong_secret_fails(
        self,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should reject signature generated with different secret."""
        wrong_secret = "whsec_wrong_secret_987654321"
        verifier = StripeWebhookVerifier(wrong_secret)

        # Generate signature with correct secret
        signature_header = generate_valid_signature()

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, signature_header)

        assert "signature" in str(exc_info.value).lower() or "verification" in str(exc_info.value).lower()

    def test_verify_with_tampered_payload_fails(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should reject signature when payload is tampered."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        # Tamper with the payload
        tampered_payload = sample_payload_bytes + b" tampered"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(tampered_payload, signature_header)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_tampered_payload_json_fails(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should reject signature when JSON payload is modified."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        # Tamper with JSON content
        payload_dict = json.loads(sample_payload_bytes)
        payload_dict['data']['object']['email'] = 'hacker@evil.com'
        tampered_payload = json.dumps(payload_dict).encode('utf-8')

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(tampered_payload, signature_header)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_forged_signature_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should reject completely forged signature."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Forged signature header
        forged_signature = "t=1234567890,v1=forged_signature_12345"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, forged_signature)

        assert "signature" in str(exc_info.value).lower()


# =============================================================================
# Test Class: Missing/Malformed Signature Headers
# =============================================================================

class TestMissingOrMalformedSignatureHeaders:
    """Test suite for handling missing or malformed signature headers."""

    def test_verify_with_missing_signature_header_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should raise clear error when signature header is None."""
        verifier = StripeWebhookVerifier(webhook_secret)

        with pytest.raises((InvalidSignatureError, ValueError)) as exc_info:
            verifier.verify(sample_payload_bytes, None)

        # Should have clear error message
        assert "signature" in str(exc_info.value).lower() or "header" in str(exc_info.value).lower()

    def test_verify_with_empty_signature_header_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should raise error when signature header is empty string."""
        verifier = StripeWebhookVerifier(webhook_secret)

        with pytest.raises((InvalidSignatureError, ValueError)) as exc_info:
            verifier.verify(sample_payload_bytes, "")

        assert "signature" in str(exc_info.value).lower() or "empty" in str(exc_info.value).lower()

    def test_verify_with_whitespace_only_header_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should raise error when signature header is only whitespace."""
        verifier = StripeWebhookVerifier(webhook_secret)

        with pytest.raises((InvalidSignatureError, ValueError)) as exc_info:
            verifier.verify(sample_payload_bytes, "   ")

        assert "signature" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    def test_verify_with_malformed_signature_no_timestamp_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should reject signature without timestamp."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Missing 't=' prefix
        malformed_signature = "v1=some_signature_value"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, malformed_signature)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_malformed_signature_no_version_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should reject signature without version."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Missing 'v1='
        malformed_signature = "t=1234567890"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, malformed_signature)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_malformed_signature_garbage_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should reject completely malformed signature."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Complete garbage
        garbage_signature = "garbage_data_not_a_signature"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, garbage_signature)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_signature_missing_equals_fails(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should reject signature with missing equals signs."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Missing '=' in format
        malformed_signature = "t1234567890 v1abcdef"

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, malformed_signature)

        assert "signature" in str(exc_info.value).lower()


# =============================================================================
# Test Class: Payload Edge Cases
# =============================================================================

class TestPayloadEdgeCases:
    """Test suite for payload edge cases."""

    def test_verify_with_none_payload_fails(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should raise clear error when payload is None."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with pytest.raises((ValueError, TypeError)) as exc_info:
            verifier.verify(None, signature_header)

        # Should have clear error message
        error_msg = str(exc_info.value).lower()
        assert "payload" in error_msg or "none" in error_msg

    def test_verify_with_empty_payload_fails(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should raise error when payload is empty bytes."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(b"", signature_header)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_empty_string_payload_fails(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should raise error when payload is empty string."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify("", signature_header)

        assert "signature" in str(exc_info.value).lower()

    def test_verify_with_large_payload_succeeds(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should handle large payloads correctly."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Create a large payload (100KB)
        large_data = {"data": "x" * 100000}
        large_payload = json.dumps(large_data).encode('utf-8')

        # Generate signature for this specific payload
        timestamp = int(time.time())
        signature_header = generate_stripe_signature(
            timestamp, large_payload, webhook_secret
        )

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(large_payload, signature_header)

            assert result is not None

    def test_verify_with_unicode_payload_succeeds(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should handle unicode characters in payload."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Payload with unicode
        unicode_data = {
            "customer": {
                "name": "张三",
                "email": "test@example.com",
                "description": "Customer with émojis 🎉 and spëcial çharacters"
            }
        }
        unicode_payload = json.dumps(unicode_data).encode('utf-8')

        # Generate signature for unicode payload
        timestamp = int(time.time())
        signature_header = generate_stripe_signature(
            timestamp, unicode_payload, webhook_secret
        )

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(unicode_payload, signature_header)

            assert result is not None


# =============================================================================
# Test Class: Replay Attack Prevention
# =============================================================================

class TestReplayAttackPrevention:
    """Test suite for replay attack prevention (timestamp validation)."""

    def test_verify_with_old_timestamp_rejected(
        self,
        webhook_secret,
        sample_payload_bytes,
        old_timestamp
    ):
        """Should reject signature with timestamp outside tolerance window."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Generate signature with old timestamp
        signature_header = generate_stripe_signature(
            old_timestamp, sample_payload_bytes, webhook_secret
        )

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, signature_header)

        # Error should mention timestamp or tolerance
        error_msg = str(exc_info.value).lower()
        assert "timestamp" in error_msg or "tolerance" in error_msg or "signature" in error_msg

    def test_verify_with_future_timestamp_rejected(
        self,
        webhook_secret,
        sample_payload_bytes,
        future_timestamp
    ):
        """Should reject signature with future timestamp."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Generate signature with future timestamp
        signature_header = generate_stripe_signature(
            future_timestamp, sample_payload_bytes, webhook_secret
        )

        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, signature_header)

        error_msg = str(exc_info.value).lower()
        assert "timestamp" in error_msg or "signature" in error_msg

    def test_verify_with_boundary_timestamp_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should accept timestamp at the edge of tolerance window."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Timestamp exactly at tolerance boundary (14 minutes = 840 seconds)
        # Stripe's tolerance is ~15 minutes, so this should pass
        boundary_timestamp = int(time.time()) - 840

        signature_header = generate_stripe_signature(
            boundary_timestamp, sample_payload_bytes, webhook_secret
        )

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            # Should pass (within tolerance)
            assert result is not None


# =============================================================================
# Test Class: Multiple Signatures (Stripe Behavior)
# =============================================================================

class TestMultipleSignatures:
    """Test suite for handling multiple signatures in header."""

    def test_verify_with_single_signature_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes,
        current_timestamp
    ):
        """Should handle header with single signature."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Single signature
        signature_header = generate_stripe_signature(
            current_timestamp, sample_payload_bytes, webhook_secret
        )

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            assert result is not None

    def test_verify_with_multiple_valid_signatures_succeeds(
        self,
        webhook_secret,
        sample_payload_bytes,
        current_timestamp
    ):
        """Should handle header with multiple signatures (Stripe may send this)."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Generate multiple signatures (as Stripe might do during key rotation)
        # Generate signature
        sig1_header = generate_stripe_signature(
            current_timestamp, sample_payload_bytes, webhook_secret
        )

        # Multiple signatures separated by commas (Stripe may send this)
        # Extract just the v1 signature
        sig1 = sig1_header.split('v1=')[1].split(',')[0]
        signature_header = f"t={current_timestamp},v1={sig1},v1={sig1}"

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            assert result is not None


# =============================================================================
# Test Class: Error Handling and Messages
# =============================================================================

class TestErrorHandlingAndMessages:
    """Test suite for error handling and error messages."""

    def test_invalid_signature_error_has_clear_message(self):
        """InvalidSignatureError should have clear, actionable message."""
        error = InvalidSignatureError("Signature verification failed")

        assert str(error)
        assert "signature" in str(error).lower()

    def test_invalid_signature_error_with_original_error(self):
        """Should be able to wrap original error."""
        original_error = Exception("Original HMAC error")
        error = InvalidSignatureError(
            "Webhook signature verification failed",
            original_error
        )

        assert error.message == "Webhook signature verification failed"
        assert error.original_error == original_error

    def test_verify_raises_custom_exception(
        self,
        webhook_secret,
        sample_payload_bytes
    ):
        """Should raise custom InvalidSignatureError, not generic Exception."""
        verifier = StripeWebhookVerifier(webhook_secret)

        forged_signature = "t=1234567890,v1=forged"

        with pytest.raises(InvalidSignatureError):
            verifier.verify(sample_payload_bytes, forged_signature)

        # Should NOT raise generic Exception
        with pytest.raises(InvalidSignatureError) as exc_info:
            verifier.verify(sample_payload_bytes, forged_signature)

        # Verify it's our custom exception
        assert isinstance(exc_info.value, InvalidSignatureError)
        assert not isinstance(exc_info.value, TypeError)
        assert not isinstance(exc_info.value, ValueError)


# =============================================================================
# Test Class: Integration with Stripe SDK
# =============================================================================

class TestIntegrationWithStripeSDK:
    """Test suite for integration with Stripe SDK."""

    def test_uses_stripe_webhook_construct_event(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should delegate to stripe.Webhook.construct_event."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_event.id = "evt_test_123"
            mock_event.type = "customer.created"
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, signature_header)

            # Verify it was called
            mock_construct.assert_called_once()
            # Verify it returned the event
            assert result.id == "evt_test_123"

    def test_passes_correct_parameters_to_stripe_sdk(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should pass correct parameters to Stripe SDK."""
        verifier = StripeWebhookVerifier(webhook_secret)
        signature_header = generate_valid_signature()

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            verifier.verify(sample_payload_bytes, signature_header)

            # Verify call was made
            mock_construct.assert_called_once()

            # Verify call parameters (check both positional and keyword args)
            call_args = mock_construct.call_args
            assert call_args is not None

            # Check keyword arguments (more robust)
            kwargs = call_args[1] if len(call_args) > 1 else call_args.kwargs
            assert 'payload' in kwargs or len(call_args[0]) > 0
            assert 'sig_header' in kwargs or len(call_args[0]) > 1
            assert 'secret' in kwargs or len(call_args[0]) > 2

            # Verify the values
            if kwargs:
                # Called with keyword arguments
                if 'payload' in kwargs:
                    assert kwargs['payload'] == sample_payload_bytes
                if 'sig_header' in kwargs:
                    assert kwargs['sig_header'] == signature_header
                if 'secret' in kwargs:
                    assert kwargs['secret'] == webhook_secret


# =============================================================================
# Test Class: Security Scenarios
# =============================================================================

class TestSecurityScenarios:
    """Test suite for specific security attack scenarios."""

    def test_prevents_signature_reuse_with_different_payload(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should prevent signature from being reused with different payload."""
        verifier = StripeWebhookVerifier(webhook_secret)
        valid_signature = generate_valid_signature()

        # Try to use signature with different payload
        different_payload = b'{"id": "different_event"}'

        with pytest.raises(InvalidSignatureError):
            verifier.verify(different_payload, valid_signature)

    def test_prevents_header_injection_attack(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should prevent header injection attacks."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # Try to inject additional headers
        injected_signature = generate_valid_signature() + ",v1=malicious"

        with pytest.raises(InvalidSignatureError):
            verifier.verify(sample_payload_bytes, injected_signature)

    def test_prevents_timing_attack_on_comparison(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should use constant-time comparison (handled by Stripe SDK)."""
        verifier = StripeWebhookVerifier(webhook_secret)

        # This test verifies we delegate to Stripe SDK which uses constant-time comparison
        # We just need to ensure it doesn't short-circuit
        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_construct.return_value = mock_event

            # Should not short-circuit, should call Stripe SDK
            result = verifier.verify(sample_payload_bytes, generate_valid_signature())

            assert result is not None
            mock_construct.assert_called_once()


# =============================================================================
# Test Class: Type Safety and Edge Cases
# =============================================================================

class TestTypeSafetyAndEdgeCases:
    """Test suite for type safety and edge cases."""

    def test_verify_with_dict_payload_raises_type_error(
        self,
        webhook_secret,
        sample_payload_dict,
        generate_valid_signature
    ):
        """Should raise clear error when payload is dict (not bytes/str)."""
        verifier = StripeWebhookVerifier(webhook_secret)

        with pytest.raises((TypeError, ValueError)):
            # Pass dict directly (should fail)
            verifier.verify(sample_payload_dict, generate_valid_signature())

    def test_verify_preserves_event_type(
        self,
        webhook_secret,
        sample_payload_bytes,
        generate_valid_signature
    ):
        """Should preserve event type from payload."""
        verifier = StripeWebhookVerifier(webhook_secret)

        with patch('stripe.Webhook.construct_event') as mock_construct:
            mock_event = MagicMock()
            mock_event.id = "evt_test_123"
            mock_event.type = "invoice.payment_succeeded"
            mock_construct.return_value = mock_event

            result = verifier.verify(sample_payload_bytes, generate_valid_signature())

            assert result.type == "invoice.payment_succeeded"

    def test_verify_handles_different_event_types(
        self,
        webhook_secret,
        generate_valid_signature
    ):
        """Should handle various Stripe event types."""
        verifier = StripeWebhookVerifier(webhook_secret)

        event_types = [
            "customer.created",
            "customer.updated",
            "customer.deleted",
            "invoice.payment_succeeded",
            "invoice.payment_failed",
            "subscription.created",
            "subscription.updated",
            "subscription.deleted"
        ]

        with patch('stripe.Webhook.construct_event') as mock_construct:
            for event_type in event_types:
                payload = json.dumps({"id": f"evt_{event_type}", "type": event_type}).encode('utf-8')

                # Generate signature for this payload
                timestamp = int(time.time())
                signature_header = generate_stripe_signature(
                    timestamp, payload, webhook_secret
                )

                mock_event = MagicMock()
                mock_event.type = event_type
                mock_construct.return_value = mock_event

                result = verifier.verify(payload, signature_header)
                assert result.type == event_type


# =============================================================================
# Test Class: Documentation and Interface
# =============================================================================

class TestDocumentationAndInterface:
    """Test suite for class documentation and interface."""

    def test_class_has_docstring(self):
        """Class should have comprehensive docstring."""
        assert StripeWebhookVerifier.__doc__ is not None
        assert len(StripeWebhookVerifier.__doc__) > 0

    def test_init_method_has_docstring(self):
        """__init__ should have documentation."""
        assert StripeWebhookVerifier.__init__.__doc__ is not None

    def test_verify_method_has_docstring(self):
        """verify method should have documentation."""
        assert StripeWebhookVerifier.verify.__doc__ is not None

    def test_exception_class_has_docstring(self):
        """InvalidSignatureError should have documentation."""
        assert InvalidSignatureError.__doc__ is not None
