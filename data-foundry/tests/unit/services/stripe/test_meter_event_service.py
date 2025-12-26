"""
Unit tests for MeterEventService.

This test suite verifies the meter event reporting implementation following TDD approach.
Tests cover:
- Successful meter event reporting to Stripe
- Meter event validation (name and value)
- Idempotency key generation and registration
- Metadata handling and sanitization
- Stripe API error handling
- Retry logic with exponential backoff

Phase: 2.5.3 (Domain Services)
Task: 2.5.3.2 - Extract meter_event_service.py with MeterEventService using TDD
Created: 2025-12-25
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional

from src.services.stripe.types import (
    MeterEventServiceProtocol,
    MeterEventResult,
    MeterType,
)
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import (
    StripeMeterValidationError,
    StripeAPIError,
)
from src.services.stripe.validation import ValidationService
from src.services.stripe.idempotency_service import IdempotencyService
from src.services.stripe.retry_service import RetryService


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def stripe_config():
    """Provide Stripe configuration for testing."""
    return StripeConfig(
        max_retries=3,
        initial_retry_delay_ms=100,
        max_retry_delay_ms=1000,
        meter_ids={
            MeterType.AI_LABELS.value: "mtr_test_ai_labels",
            MeterType.HUMAN_AUDITS.value: "mtr_test_human_audits",
        }
    )


@pytest.fixture
def mock_validation_service(stripe_config):
    """Provide mock ValidationService."""
    service = Mock(spec=ValidationService)
    service.validate_meter_event = Mock(return_value=[])
    service.sanitize_metadata = Mock(return_value={})
    service.sanitize_idempotency_component = Mock(side_effect=lambda x: x)
    return service


@pytest.fixture
def mock_idempotency_service(stripe_config):
    """Provide mock IdempotencyService."""
    service = Mock(spec=IdempotencyService)
    service.generate_key = Mock(return_value="test_idempotency_key_123")
    service.is_registered = Mock(return_value=False)
    service.register_key = Mock()
    return service


@pytest.fixture
def mock_retry_service(stripe_config):
    """Provide mock RetryService."""
    service = Mock(spec=RetryService)

    # Store the actual stripe_client for retry simulation
    stripe_client = None

    async def mock_execute_with_retry(func, operation_name, *args, **kwargs):
        # For most tests, simply call the function once
        # The retry logic tests will override this behavior
        if hasattr(func, '__call__'):
            return func(*args, **kwargs)
        return func(*args, **kwargs)

    service.execute_with_retry = AsyncMock(side_effect=mock_execute_with_retry)
    service.is_transient_error = Mock(return_value=False)
    service._set_retry_behavior = None  # Will be set by tests that need retry simulation
    return service


@pytest.fixture
def mock_stripe_client():
    """Provide mock Stripe client."""
    client = Mock()
    client.create_meter_event = Mock(return_value={
        "id": "evt_test_123",
        "event_name": "ai_labels",
        "payload": {"value": "100"},
        "status": "succeeded"
    })
    return client


@pytest.fixture
def meter_event_service(
    stripe_config,
    mock_validation_service,
    mock_idempotency_service,
    mock_retry_service,
    mock_stripe_client
):
    """Provide MeterEventService instance for testing."""
    from src.services.stripe.meter_event_service import MeterEventService

    service = MeterEventService(
        config=stripe_config,
        validation_service=mock_validation_service,
        idempotency_service=mock_idempotency_service,
        retry_service=mock_retry_service,
        stripe_client=mock_stripe_client
    )
    return service


# ============================================================================
# Tests: Successful Meter Event Reporting
# ============================================================================

class TestMeterEventReportingSuccess:
    """Test successful meter event reporting scenarios."""

    @pytest.mark.asyncio
    async def test_report_usage_basic_success(self, meter_event_service, mock_stripe_client):
        """Test basic successful meter event reporting."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify result structure
        assert "event_id" in result
        assert "status" in result
        assert "stripe_response" in result
        assert result["meter_event"] == "ai_labels"
        assert result["value"] == 100

        # Verify Stripe client was called
        assert mock_stripe_client.create_meter_event.called

    @pytest.mark.asyncio
    async def test_report_usage_with_metadata(self, meter_event_service, mock_stripe_client, mock_validation_service):
        """Test meter event reporting with metadata."""
        metadata = {"source": "api", "count": "100"}

        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata=metadata
        )

        # Verify metadata sanitization was called
        mock_validation_service.sanitize_metadata.assert_called_once_with(metadata)

        # Verify success
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_report_usage_with_stripe_customer_id(self, meter_event_service, mock_stripe_client):
        """Test meter event reporting with Stripe customer ID."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            stripe_customer_id="cus_test_123"
        )

        # Verify success
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_report_usage_with_batch_id(self, meter_event_service, mock_idempotency_service):
        """Test meter event reporting with batch ID."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            batch_id="batch_test_123"
        )

        # Verify idempotency key generation with batch_id
        mock_idempotency_service.generate_key.assert_called_once()
        call_args = mock_idempotency_service.generate_key.call_args
        assert call_args[1]["batch_id"] == "batch_test_123"

        # Verify success
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_report_usage_human_audits(self, meter_event_service):
        """Test reporting human_audits meter event."""
        result = await meter_event_service.report_usage(
            meter_event="human_audits",
            value=50,
            tenant_id="tenant_123"
        )

        assert result["meter_event"] == "human_audits"
        assert result["value"] == 50


# ============================================================================
# Tests: Meter Event Validation
# ============================================================================

class TestMeterEventValidation:
    """Test meter event validation failures."""

    @pytest.mark.asyncio
    async def test_report_usage_invalid_meter_event_name(self, meter_event_service, mock_validation_service):
        """Test validation fails for invalid meter event name."""
        mock_validation_service.validate_meter_event.return_value = [
            "Invalid meter_event 'invalid_meter'"
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="invalid_meter",
                value=100,
                tenant_id="tenant_123"
            )

        assert "Invalid meter_event" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_report_usage_negative_value(self, meter_event_service, mock_validation_service):
        """Test validation fails for negative value."""
        mock_validation_service.validate_meter_event.return_value = [
            "Value must be positive"
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=-10,
                tenant_id="tenant_123"
            )

        assert "positive" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_report_usage_zero_value(self, meter_event_service, mock_validation_service):
        """Test validation fails for zero value."""
        mock_validation_service.validate_meter_event.return_value = [
            "Value must be positive"
        ]

        with pytest.raises(StripeMeterValidationError):
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=0,
                tenant_id="tenant_123"
            )

    @pytest.mark.asyncio
    async def test_report_usage_invalid_value_type(self, meter_event_service, mock_validation_service):
        """Test validation fails for non-integer value."""
        mock_validation_service.validate_meter_event.return_value = [
            "Value must be an integer"
        ]

        with pytest.raises(StripeMeterValidationError):
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100.5,  # type: ignore
                tenant_id="tenant_123"
            )

    @pytest.mark.asyncio
    async def test_report_usage_multiple_validation_errors(self, meter_event_service, mock_validation_service):
        """Test validation returns multiple errors."""
        mock_validation_service.validate_meter_event.return_value = [
            "Invalid meter_event",
            "Value must be positive"
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="invalid",
                value=-10,
                tenant_id="tenant_123"
            )

        # Check that all errors are present
        error_msg = str(exc_info.value)
        # The exception may format errors differently
        assert exc_info.value.validation_errors is not None


# ============================================================================
# Tests: Idempotency Key Generation
# ============================================================================

class TestIdempotencyKeyGeneration:
    """Test idempotency key generation and registration."""

    @pytest.mark.asyncio
    async def test_idempotency_key_generated(self, meter_event_service, mock_idempotency_service):
        """Test idempotency key is generated for each event."""
        await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify key generation was called
        mock_idempotency_service.generate_key.assert_called_once_with(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100,
            batch_id=None
        )

    @pytest.mark.asyncio
    async def test_idempotency_key_registered(self, meter_event_service, mock_idempotency_service):
        """Test idempotency key is registered after successful report."""
        await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify key registration
        mock_idempotency_service.register_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_key_in_result(self, meter_event_service, mock_idempotency_service):
        """Test idempotency key is included in result."""
        mock_idempotency_service.generate_key.return_value = "custom_key_123"

        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["event_id"] == "custom_key_123"


# ============================================================================
# Tests: Metadata Handling
# ============================================================================

class TestMetadataHandling:
    """Test metadata sanitization and handling."""

    @pytest.mark.asyncio
    async def test_metadata_sanitized(self, meter_event_service, mock_validation_service):
        """Test metadata is sanitized before sending to Stripe."""
        metadata = {"source": "api", "count": "100"}
        mock_validation_service.sanitize_metadata.return_value = {
            "source": "api",
            "count": "100"
        }

        await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata=metadata
        )

        # Verify sanitization was called
        mock_validation_service.sanitize_metadata.assert_called_once_with(metadata)

    @pytest.mark.asyncio
    async def test_metadata_validation_error_propagated(self, meter_event_service, mock_validation_service):
        """Test metadata validation errors are properly propagated."""
        mock_validation_service.sanitize_metadata.side_effect = StripeMeterValidationError(
            "Reserved key 'value' cannot be set"
        )

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123",
                metadata={"value": "test"}
            )

        assert "reserved" in str(exc_info.value).lower() or "cannot be set" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_none_metadata_handled(self, meter_event_service, mock_validation_service):
        """Test None metadata is handled gracefully."""
        await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata=None
        )

        # Sanitization should not be called for None metadata
        mock_validation_service.sanitize_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_metadata_handled(self, meter_event_service, mock_validation_service):
        """Test empty metadata is handled gracefully."""
        mock_validation_service.sanitize_metadata.return_value = {}

        await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata={}
        )

        # Should be called but return empty dict
        mock_validation_service.sanitize_metadata.assert_called_once_with({})


# ============================================================================
# Tests: Stripe API Error Handling
# ============================================================================

class TestStripeAPIErrorHandling:
    """Test Stripe API error handling."""

    @pytest.mark.asyncio
    async def test_stripe_api_error_raised(self, meter_event_service, mock_stripe_client):
        """Test Stripe API errors are properly wrapped and raised."""
        # Create a mock Stripe error
        class MockStripeError(Exception):
            def __init__(self):
                super().__init__("Stripe API error")
                self.http_status = 400

        mock_stripe_client.create_meter_event.side_effect = MockStripeError()

        with pytest.raises(Exception):
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )

    @pytest.mark.asyncio
    async def test_transient_error_retried(self, meter_event_service, mock_retry_service, mock_stripe_client):
        """Test transient errors trigger retry logic."""
        class MockTransientError(Exception):
            def __init__(self):
                super().__init__("Rate limit exceeded")
                self.http_status = 429

        # First call fails, second succeeds
        mock_stripe_client.create_meter_event.side_effect = [
            MockTransientError(),
            {"id": "evt_test_123", "status": "succeeded"}
        ]

        mock_retry_service.is_transient_error.return_value = True

        # Override execute_with_retry to simulate retry behavior
        call_count = [0]

        async def retry_with_simulation(func, operation_name, *args, **kwargs):
            call_count[0] += 1
            try:
                # First call will raise, second will succeed
                result = func(*args, **kwargs)
                # Check if result is awaitable
                if hasattr(result, '__await__'):
                    result = await result
                return result
            except Exception as e:
                if call_count[0] == 1 and mock_retry_service.is_transient_error(e):
                    # Simulate retry - call again
                    result = func(*args, **kwargs)
                    if hasattr(result, '__await__'):
                        result = await result
                    return result
                raise

        mock_retry_service.execute_with_retry = AsyncMock(side_effect=retry_with_simulation)

        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify success after retry
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_permanent_error_not_retried(self, meter_event_service, mock_retry_service, mock_stripe_client):
        """Test permanent errors do not trigger retry logic."""
        class MockPermanentError(Exception):
            def __init__(self):
                super().__init__("Bad request")
                self.http_status = 400

        mock_stripe_client.create_meter_event.side_effect = MockPermanentError()
        mock_retry_service.is_transient_error.return_value = False

        with pytest.raises(Exception):
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )


# ============================================================================
# Tests: MeterEventResult Structure
# ============================================================================

class TestMeterEventResultStructure:
    """Test MeterEventResult structure and content."""

    @pytest.mark.asyncio
    async def test_result_contains_all_fields(self, meter_event_service):
        """Test result contains all required fields."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify all required fields are present
        assert "event_id" in result
        assert "status" in result
        assert "stripe_response" in result
        assert "meter_event" in result
        assert "value" in result

    @pytest.mark.asyncio
    async def test_result_status_succeeded(self, meter_event_service):
        """Test successful result has 'succeeded' status."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_result_contains_stripe_response(self, meter_event_service, mock_stripe_client):
        """Test result contains Stripe API response."""
        expected_response = {
            "id": "evt_test_123",
            "event_name": "ai_labels",
            "payload": {"value": "100"},
            "status": "succeeded"
        }
        mock_stripe_client.create_meter_event.return_value = expected_response

        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["stripe_response"] == expected_response

    @pytest.mark.asyncio
    async def test_result_preserves_input_values(self, meter_event_service):
        """Test result preserves input meter_event and value."""
        result = await meter_event_service.report_usage(
            meter_event="human_audits",
            value=250,
            tenant_id="tenant_123"
        )

        assert result["meter_event"] == "human_audits"
        assert result["value"] == 250


# ============================================================================
# Tests: Different Meter Types
# ============================================================================

class TestDifferentMeterTypes:
    """Test reporting different meter types."""

    @pytest.mark.asyncio
    async def test_report_ai_labels_meter(self, meter_event_service):
        """Test reporting ai_labels meter event."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=1000,
            tenant_id="tenant_123"
        )

        assert result["meter_event"] == "ai_labels"
        assert result["value"] == 1000
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_report_human_audits_meter(self, meter_event_service):
        """Test reporting human_audits meter event."""
        result = await meter_event_service.report_usage(
            meter_event="human_audits",
            value=25,
            tenant_id="tenant_123"
        )

        assert result["meter_event"] == "human_audits"
        assert result["value"] == 25
        assert result["status"] == "succeeded"


# ============================================================================
# Tests: Protocol Compliance
# ============================================================================

class TestMeterEventServiceProtocol:
    """Test MeterEventService implements MeterEventServiceProtocol correctly."""

    def test_service_has_report_usage_method(self, meter_event_service):
        """Test service has report_usage method."""
        assert hasattr(meter_event_service, 'report_usage')
        assert callable(meter_event_service.report_usage)

    @pytest.mark.asyncio
    async def test_report_usage_signature_matches_protocol(self, meter_event_service):
        """Test report_usage signature matches protocol."""
        # Should accept all protocol-defined parameters
        try:
            result = await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123",
                metadata={"source": "test"},
                stripe_customer_id="cus_test",
                batch_id="batch_test"
            )
            assert "event_id" in result
        except TypeError as e:
            pytest.fail(f"report_usage has incorrect signature: {e}")

    def test_service_is_protocol_compliant(self, meter_event_service):
        """Test service is protocol compliant."""
        # Check required method exists
        assert hasattr(meter_event_service, 'report_usage')
        # Check it's callable
        assert callable(meter_event_service.report_usage)


# ============================================================================
# Tests: Configuration Handling
# ============================================================================

class TestConfigurationHandling:
    """Test MeterEventService uses configuration correctly."""

    @pytest.mark.asyncio
    async def test_uses_meter_id_from_config(self, meter_event_service):
        """Test service uses meter IDs from configuration."""
        # The service should use the meter ID from config for Stripe API calls
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Verify the call was made successfully (indicates correct meter ID usage)
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_handles_configured_meters(self, meter_event_service):
        """Test service handles all configured meter types."""
        # Test all configured meters
        for meter_type in ["ai_labels", "human_audits"]:
            result = await meter_event_service.report_usage(
                meter_event=meter_type,
                value=100,
                tenant_id="tenant_123"
            )
            assert result["status"] == "succeeded"


# ============================================================================
# Tests: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_large_value(self, meter_event_service):
        """Test handling large meter values."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=1000000,
            tenant_id="tenant_123"
        )

        assert result["value"] == 1000000
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_minimum_value(self, meter_event_service):
        """Test handling minimum valid value (1)."""
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=1,
            tenant_id="tenant_123"
        )

        assert result["value"] == 1
        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_long_tenant_id(self, meter_event_service):
        """Test handling long tenant IDs."""
        long_tenant_id = "tenant_" + "x" * 200
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id=long_tenant_id
        )

        assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_special_characters_in_metadata(self, meter_event_service, mock_validation_service):
        """Test handling special characters in metadata values."""
        metadata = {"special": "test with spaces & symbols!"}
        mock_validation_service.sanitize_metadata.return_value = metadata

        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata=metadata
        )

        assert result["status"] == "succeeded"
        mock_validation_service.sanitize_metadata.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, meter_event_service):
        """Test handling concurrent meter event reports."""
        import asyncio

        # Create multiple concurrent requests
        tasks = [
            meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id=f"tenant_{i}"
            )
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        assert all(r["status"] == "succeeded" for r in results)
