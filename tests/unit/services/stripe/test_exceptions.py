"""
Unit tests for Stripe service exception hierarchy.

Tests verify:
1. Exception hierarchy structure
2. Rich context attributes
3. to_dict() serialization
4. Exception inheritance chains
"""

import sys
from pathlib import Path
import importlib.util

# Direct import to avoid services/__init__.py import issues
exceptions_path = Path(__file__).parent.parent.parent.parent.parent / "data-foundry" / "src" / "services" / "stripe" / "exceptions.py"
spec = importlib.util.spec_from_file_location("exceptions", exceptions_path)
exceptions = importlib.util.module_from_spec(spec)
sys.modules["services.stripe.exceptions"] = exceptions
spec.loader.exec_module(exceptions)

import pytest

# Import from loaded module
StripeServiceError = exceptions.StripeServiceError
StripeInitializationError = exceptions.StripeInitializationError
StripeAPIError = exceptions.StripeAPIError
StripeRateLimitError = exceptions.StripeRateLimitError
StripeServerError = exceptions.StripeServerError
StripeCustomerError = exceptions.StripeCustomerError
StripeCustomerNotFoundError = exceptions.StripeCustomerNotFoundError
StripeCustomerExistsError = exceptions.StripeCustomerExistsError
StripeMeterError = exceptions.StripeMeterError
StripeMeterValidationError = exceptions.StripeMeterValidationError
StripeMeterQuotaError = exceptions.StripeMeterQuotaError
StripeIdempotencyError = exceptions.StripeIdempotencyError
StripeIdempotencyKeyTooLongError = exceptions.StripeIdempotencyKeyTooLongError
StripeBatchError = exceptions.StripeBatchError


# ============================================================================
# Base Exception Tests
# ============================================================================

class TestStripeServiceError:
    """Tests for StripeServiceError base exception."""

    def test_base_exception_creation(self):
        """Test creating base exception with message."""
        exc = StripeServiceError("Test error")
        assert exc.message == "Test error"
        assert str(exc) == "Test error"

    def test_base_exception_with_stripe_error(self):
        """Test base exception with underlying Stripe error."""
        stripe_error = Exception("Underlying Stripe error")
        exc = StripeServiceError("Test error", stripe_error=stripe_error)
        assert exc.stripe_error == stripe_error

    def test_base_exception_to_dict(self):
        """Test to_dict() serialization."""
        exc = StripeServiceError("Test error")
        result = exc.to_dict()
        assert result == {
            "error_type": "StripeServiceError",
            "message": "Test error",
        }

    def test_catch_as_base_exception(self):
        """Test all exceptions can be caught as StripeServiceError."""
        with pytest.raises(StripeServiceError):
            raise StripeCustomerNotFoundError("Not found")


# ============================================================================
# Initialization Error Tests
# ============================================================================

class TestStripeInitializationError:
    """Tests for StripeInitializationError."""

    def test_initialization_error_creation(self):
        """Test creating initialization error."""
        exc = StripeInitializationError("Failed to initialize")
        assert exc.message == "Failed to initialize"
        assert isinstance(exc, StripeServiceError)

    def test_initialization_error_to_dict(self):
        """Test serialization."""
        exc = StripeInitializationError("Invalid API key")
        result = exc.to_dict()
        assert result["error_type"] == "StripeInitializationError"
        assert result["message"] == "Invalid API key"


# ============================================================================
# API Error Tests
# ============================================================================

class TestStripeAPIError:
    """Tests for StripeAPIError."""

    def test_api_error_creation(self):
        """Test creating API error."""
        exc = StripeAPIError(
            "API call failed",
            stripe_error_type="InvalidRequestError",
            stripe_code="parameter_invalid"
        )
        assert exc.message == "API call failed"
        assert exc.stripe_error_type == "InvalidRequestError"
        assert exc.stripe_code == "parameter_invalid"
        assert exc.http_status is None
        assert exc.is_retryable is False

    def test_api_error_with_full_context(self):
        """Test API error with all context."""
        exc = StripeAPIError(
            "API call failed",
            stripe_error_type="APIError",
            stripe_code="api_error",
            http_status=500,
            is_retryable=True
        )
        assert exc.http_status == 500
        assert exc.is_retryable is True

    def test_api_error_to_dict(self):
        """Test serialization with context."""
        exc = StripeAPIError(
            "API failed",
            stripe_error_type="InvalidRequestError",
            stripe_code="param_invalid",
            http_status=400,
            is_retryable=False
        )
        result = exc.to_dict()
        assert result["error_type"] == "StripeAPIError"
        assert result["stripe_error_type"] == "InvalidRequestError"
        assert result["stripe_code"] == "param_invalid"
        assert result["http_status"] == 400
        assert result["is_retryable"] is False


class TestStripeRateLimitError:
    """Tests for StripeRateLimitError."""

    def test_rate_limit_error_creation(self):
        """Test creating rate limit error."""
        exc = StripeRateLimitError("Rate limit exceeded", retry_after=60)
        assert exc.message == "Rate limit exceeded"
        assert exc.retry_after == 60
        assert exc.http_status == 429
        assert exc.is_retryable is True

    def test_rate_limit_error_to_dict(self):
        """Test serialization."""
        exc = StripeRateLimitError("Too many requests", retry_after=120)
        result = exc.to_dict()
        assert result["error_type"] == "StripeRateLimitError"
        assert result["http_status"] == 429
        assert result["retry_after"] == 120
        assert result["is_retryable"] is True


class TestStripeServerError:
    """Tests for StripeServerError."""

    def test_server_error_creation(self):
        """Test creating server error."""
        exc = StripeServerError("Internal server error", http_status=502)
        assert exc.message == "Internal server error"
        assert exc.http_status == 502
        assert exc.is_retryable is True

    def test_server_error_default_status(self):
        """Test default HTTP status code."""
        exc = StripeServerError("Server error")
        assert exc.http_status == 500

    def test_server_error_to_dict(self):
        """Test serialization."""
        exc = StripeServerError("Gateway timeout", http_status=504)
        result = exc.to_dict()
        assert result["error_type"] == "StripeServerError"
        assert result["http_status"] == 504
        assert result["is_retryable"] is True


# ============================================================================
# Customer Error Tests
# ============================================================================

class TestStripeCustomerError:
    """Tests for StripeCustomerError."""

    def test_customer_error_creation(self):
        """Test creating customer error."""
        exc = StripeCustomerError(
            "Customer error",
            tenant_id="tenant_123",
            stripe_customer_id="cus_abc123"
        )
        assert exc.tenant_id == "tenant_123"
        assert exc.stripe_customer_id == "cus_abc123"

    def test_customer_error_to_dict(self):
        """Test serialization."""
        exc = StripeCustomerError(
            "Failed",
            tenant_id="tenant_456",
            stripe_customer_id="cus_xyz789"
        )
        result = exc.to_dict()
        assert result["tenant_id"] == "tenant_456"
        assert result["stripe_customer_id"] == "cus_xyz789"


class TestStripeCustomerNotFoundError:
    """Tests for StripeCustomerNotFoundError."""

    def test_not_found_error_creation(self):
        """Test creating not found error."""
        exc = StripeCustomerNotFoundError(
            "Customer not found",
            tenant_id="tenant_123",
            stripe_customer_id="cus_abc123"
        )
        assert exc.tenant_id == "tenant_123"
        assert isinstance(exc, StripeCustomerError)
        assert isinstance(exc, StripeServiceError)


class TestStripeCustomerExistsError:
    """Tests for StripeCustomerExistsError."""

    def test_exists_error_creation(self):
        """Test creating exists error."""
        exc = StripeCustomerExistsError(
            "Customer already exists",
            tenant_id="tenant_123"
        )
        assert exc.tenant_id == "tenant_123"
        assert isinstance(exc, StripeCustomerError)


# ============================================================================
# Meter Error Tests
# ============================================================================

class TestStripeMeterError:
    """Tests for StripeMeterError."""

    def test_meter_error_creation(self):
        """Test creating meter error."""
        exc = StripeMeterError(
            "Meter error",
            tenant_id="tenant_123",
            meter_event="ai_labels"
        )
        assert exc.tenant_id == "tenant_123"
        assert exc.meter_event == "ai_labels"

    def test_meter_error_to_dict(self):
        """Test serialization."""
        exc = StripeMeterError(
            "Failed",
            tenant_id="tenant_456",
            meter_event="human_audits"
        )
        result = exc.to_dict()
        assert result["tenant_id"] == "tenant_456"
        assert result["meter_event"] == "human_audits"


class TestStripeMeterValidationError:
    """Tests for StripeMeterValidationError."""

    def test_validation_error_creation(self):
        """Test creating validation error."""
        exc = StripeMeterValidationError(
            "Invalid meter event",
            meter_event="invalid_event",
            validation_errors=["Unknown event", "Invalid value"]
        )
        assert exc.meter_event == "invalid_event"
        assert exc.validation_errors == ["Unknown event", "Invalid value"]

    def test_validation_error_empty_list(self):
        """Test validation error with no validation errors."""
        exc = StripeMeterValidationError("Invalid")
        assert exc.validation_errors == []

    def test_validation_error_to_dict(self):
        """Test serialization."""
        exc = StripeMeterValidationError(
            "Validation failed",
            meter_event="test_event",
            validation_errors=["Error 1", "Error 2"]
        )
        result = exc.to_dict()
        assert result["meter_event"] == "test_event"
        assert result["validation_errors"] == ["Error 1", "Error 2"]


class TestStripeMeterQuotaError:
    """Tests for StripeMeterQuotaError."""

    def test_quota_error_creation(self):
        """Test creating quota error."""
        exc = StripeMeterQuotaError(
            "Quota exceeded",
            tenant_id="tenant_123",
            meter_event="ai_labels"
        )
        assert exc.meter_event == "ai_labels"
        assert isinstance(exc, StripeMeterError)


# ============================================================================
# Idempotency Error Tests
# ============================================================================

class TestStripeIdempotencyError:
    """Tests for StripeIdempotencyError."""

    def test_idempotency_error_creation(self):
        """Test creating idempotency error."""
        exc = StripeIdempotencyError(
            "Idempotency failed",
            idempotency_key="idemp_abc123"
        )
        assert exc.idempotency_key == "idemp_abc123"

    def test_idempotency_error_to_dict(self):
        """Test serialization."""
        exc = StripeIdempotencyError(
            "Failed",
            idempotency_key="idemp_xyz789"
        )
        result = exc.to_dict()
        assert result["idempotency_key"] == "idemp_xyz789"


class TestStripeIdempotencyKeyTooLongError:
    """Tests for StripeIdempotencyKeyTooLongError."""

    def test_key_too_long_error_creation(self):
        """Test creating key too long error."""
        exc = StripeIdempotencyKeyTooLongError(
            "Key too long",
            idempotency_key="x" * 300,
            key_length=300,
            max_length=255
        )
        assert exc.key_length == 300
        assert exc.max_length == 255

    def test_key_too_long_default_max_length(self):
        """Test default max length."""
        exc = StripeIdempotencyKeyTooLongError(
            "Key too long",
            key_length=300
        )
        assert exc.max_length == 255

    def test_key_too_long_to_dict(self):
        """Test serialization."""
        exc = StripeIdempotencyKeyTooLongError(
            "Too long",
            idempotency_key="x" * 300,
            key_length=300,
            max_length=255
        )
        result = exc.to_dict()
        assert result["key_length"] == 300
        assert result["max_length"] == 255


# ============================================================================
# Batch Error Tests
# ============================================================================

class TestStripeBatchError:
    """Tests for StripeBatchError."""

    def test_batch_error_creation(self):
        """Test creating batch error."""
        exc = StripeBatchError(
            "Batch failed",
            batch_id="batch_123",
            failed_count=5,
            total_count=10
        )
        assert exc.batch_id == "batch_123"
        assert exc.failed_count == 5
        assert exc.total_count == 10

    def test_batch_error_to_dict(self):
        """Test serialization."""
        exc = StripeBatchError(
            "Failed",
            batch_id="batch_456",
            failed_count=3,
            total_count=10
        )
        result = exc.to_dict()
        assert result["batch_id"] == "batch_456"
        assert result["failed_count"] == 3
        assert result["total_count"] == 10


# ============================================================================
# Inheritance Chain Tests
# ============================================================================

class TestExceptionInheritance:
    """Tests for exception inheritance chains."""

    def test_api_error_inheritance_chain(self):
        """Test API error inheritance."""
        assert issubclass(StripeAPIError, StripeServiceError)
        assert issubclass(StripeRateLimitError, StripeAPIError)
        assert issubclass(StripeRateLimitError, StripeServiceError)
        assert issubclass(StripeServerError, StripeAPIError)
        assert issubclass(StripeServerError, StripeServiceError)

    def test_customer_error_inheritance_chain(self):
        """Test customer error inheritance."""
        assert issubclass(StripeCustomerError, StripeServiceError)
        assert issubclass(StripeCustomerNotFoundError, StripeCustomerError)
        assert issubclass(StripeCustomerNotFoundError, StripeServiceError)
        assert issubclass(StripeCustomerExistsError, StripeCustomerError)
        assert issubclass(StripeCustomerExistsError, StripeServiceError)

    def test_meter_error_inheritance_chain(self):
        """Test meter error inheritance."""
        assert issubclass(StripeMeterError, StripeServiceError)
        assert issubclass(StripeMeterValidationError, StripeMeterError)
        assert issubclass(StripeMeterValidationError, StripeServiceError)
        assert issubclass(StripeMeterQuotaError, StripeMeterError)
        assert issubclass(StripeMeterQuotaError, StripeServiceError)

    def test_idempotency_error_inheritance_chain(self):
        """Test idempotency error inheritance."""
        assert issubclass(StripeIdempotencyError, StripeServiceError)
        assert issubclass(StripeIdempotencyKeyTooLongError, StripeIdempotencyError)
        assert issubclass(StripeIdempotencyKeyTooLongError, StripeServiceError)

    def test_batch_error_inheritance(self):
        """Test batch error inheritance."""
        assert issubclass(StripeBatchError, StripeServiceError)


# ============================================================================
# Exception Catching Tests
# ============================================================================

class TestExceptionCatching:
    """Tests for exception catching behavior."""

    def test_catch_customer_error_as_service_error(self):
        """Test catching customer error as service error."""
        with pytest.raises(StripeServiceError):
            raise StripeCustomerNotFoundError("Not found")

    def test_catch_api_error_as_service_error(self):
        """Test catching API error as service error."""
        with pytest.raises(StripeServiceError):
            raise StripeRateLimitError("Rate limited")

    def test_catch_specific_error_type(self):
        """Test catching specific error type."""
        with pytest.raises(StripeCustomerNotFoundError):
            raise StripeCustomerNotFoundError("Not found")

        with pytest.raises(StripeMeterValidationError):
            raise StripeMeterValidationError("Invalid")

    def test_no_catch_wrong_type(self):
        """Test not catching wrong exception type."""
        with pytest.raises(StripeMeterError):
            raise StripeMeterValidationError("Invalid")

        with pytest.raises(StripeAPIError):
            raise StripeRateLimitError("Rate limited")
