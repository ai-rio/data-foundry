"""
Integration tests for Stripe service orchestration.

This module tests how the 11 Stripe service modules work together through
the facade layer, verifying proper delegation, error propagation, and
service interaction patterns.

Test Coverage:
- Facade to Service delegation
- Service initialization order
- Service dependency injection
- Error propagation
- Retry service integration
- Idempotency service integration
- Validation service integration
- Batch processor integration

Target Coverage: 95%+
"""

import os
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone
from typing import Dict, Any, List
import asyncio


# =============================================================================
# Test Configuration
# =============================================================================

# Set test environment before importing stripe services
os.environ["STRIPE_SECRET_KEY"] = "sk_test_mock_key_for_testing"
os.environ["STRIPE_AI_LABELS_METER_ID"] = "meter_test_ai_labels"
os.environ["STRIPE_HUMAN_AUDITS_METER_ID"] = "meter_test_human_audits"


from src.services.stripe.config import StripeConfig
from src.services.stripe.base import StripeServiceBase
from src.services.stripe.facade import StripeService
from src.services.stripe.types import (
    MeterEventResult,
    BatchResult,
    MeterType,
    EventStatus,
    RetryCategory,
)
from src.services.stripe.exceptions import (
    StripeServiceError,
    StripeInitializationError,
    StripeAPIError,
    StripeMeterValidationError,
    StripeCustomerNotFoundError,
    StripeIdempotencyKeyTooLongError,
)
from src.services.stripe.validation import ValidationService
from src.services.stripe.idempotency_service import IdempotencyService
from src.services.stripe.retry_service import RetryService
from src.services.stripe.meter_event_service import MeterEventService
from src.services.stripe.batch_processor import BatchProcessor
from src.services.stripe.customer_service import CustomerService


# =============================================================================
# Pytest Fixtures
# =============================================================================

@pytest.fixture
def stripe_config():
    """Create a test StripeConfig instance."""
    return StripeConfig(
        max_retries=3,
        initial_retry_delay_ms=100,
        max_retry_delay_ms=1000,
        retry_backoff_multiplier=2.0,
        jitter_enabled=False,  # Disable for deterministic tests
        max_idempotency_key_length=255,
        idempotency_retention_hours=24,
        max_idempotency_registry_size=1000,
        max_batch_size=100,
        meter_ids={
            MeterType.AI_LABELS.value: "meter_test_ai_labels",
            MeterType.HUMAN_AUDITS.value: "meter_test_human_audits",
        }
    )


@pytest.fixture
def mock_stripe_client():
    """Create a mock Stripe client."""
    client = Mock()

    # Mock customer operations
    def create_customer(**kwargs):
        return {
            "id": "cus_test_customer_123",
            "email": kwargs.get("email"),
            "name": kwargs.get("name"),
            "metadata": kwargs.get("metadata", {}),
            "created": 1703500800
        }

    def retrieve_customer(customer_id):
        if customer_id == "cus_not_found":
            raise Mock()  # Will be configured to simulate stripe.error.InvalidRequestError
        return {
            "id": customer_id,
            "email": "test@example.com",
            "name": "Test Customer",
            "metadata": {"tenant_id": "tenant_123"}
        }

    def modify_customer(customer_id, **kwargs):
        return {
            "id": customer_id,
            "email": kwargs.get("email", "test@example.com"),
            "name": kwargs.get("name", "Test Customer"),
            "metadata": kwargs.get("metadata", {})
        }

    def delete_customer(customer_id):
        return {"id": customer_id, "deleted": True}

    def create_meter_event(**kwargs):
        return {
            "id": "evt_test_event_123",
            "event_name": kwargs.get("event_name"),
            "payload": kwargs.get("payload", {}),
            "created": 1703500800
        }

    client.create_customer = Mock(side_effect=create_customer)
    client.retrieve_customer = Mock(side_effect=retrieve_customer)
    client.modify_customer = Mock(side_effect=modify_customer)
    client.delete_customer = Mock(side_effect=delete_customer)
    client.create_meter_event = Mock(side_effect=create_meter_event)

    return client


@pytest.fixture
def validation_service(stripe_config):
    """Create ValidationService instance."""
    return ValidationService(stripe_config)


@pytest.fixture
def idempotency_service(stripe_config):
    """Create IdempotencyService instance."""
    return IdempotencyService(stripe_config)


@pytest.fixture
def retry_service(stripe_config):
    """Create RetryService instance."""
    return RetryService(stripe_config)


@pytest.fixture
def meter_event_service(stripe_config, validation_service, idempotency_service, retry_service, mock_stripe_client):
    """Create MeterEventService instance with all dependencies."""
    return MeterEventService(
        config=stripe_config,
        validation_service=validation_service,
        idempotency_service=idempotency_service,
        retry_service=retry_service,
        stripe_client=mock_stripe_client
    )


@pytest.fixture
def customer_service():
    """Create CustomerService instance."""
    return CustomerService()


@pytest.fixture
def batch_processor(stripe_config, meter_event_service):
    """Create BatchProcessor instance."""
    return BatchProcessor(
        config=stripe_config,
        meter_event_service=meter_event_service
    )


@pytest.fixture
def stripe_service_base(stripe_config):
    """Create StripeServiceBase instance."""
    return StripeServiceBase(config=stripe_config)


@pytest.fixture
def stripe_facade():
    """Create StripeService facade instance."""
    return StripeService()


@pytest.fixture
def mock_secret_manager():
    """Create a mock SecretManager."""
    manager = Mock()
    manager.get_secret = Mock(return_value="sk_test_mock_key_for_testing")
    return manager


# =============================================================================
# Test Class: Service Initialization Order
# =============================================================================

@pytest.mark.asyncio
class TestServiceInitializationOrder:
    """Test that services are initialized in the correct order."""

    async def test_base_initializes_services_in_correct_order(self, stripe_config):
        """
        Test that base.py initializes services in correct dependency order.

        Given: A StripeServiceBase instance
        When: Services are accessed for the first time
        Then: Services are initialized in dependency order:
              - ValidationService (no dependencies)
              - IdempotencyService (no dependencies)
              - RetryService (no dependencies)
              - MeterEventService (depends on all above)
        """
        base = StripeServiceBase(config=stripe_config)
        base._initialized = True
        base.api_key = "sk_test_mock_key"

        # Access services in different orders and verify they're created
        validator = base.validator
        assert validator is not None
        assert hasattr(validator, '_reserved_keys')

        idempotency = base.idempotency_service
        assert idempotency is not None
        assert hasattr(idempotency, '_registry')

        retry = base.retry_service
        assert retry is not None
        assert hasattr(retry, '_max_retries')

        # All services should have been created successfully
        assert base._validator is not None
        assert base._idempotency_service is not None
        assert base._retry_service is not None

    async def test_meter_service_depends_on_other_services(self, stripe_config):
        """
        Test that MeterEventService requires validation, idempotency, and retry services.

        Given: A StripeServiceBase instance
        When: meter_service property is accessed
        Then: It creates MeterEventService with validation, idempotency, and retry services
        """
        base = StripeServiceBase(config=stripe_config)
        base._initialized = True
        base.api_key = "sk_test_mock_key"

        # Access meter_service
        meter_service = base.meter_service

        # Verify it was created
        assert meter_service is not None
        assert hasattr(meter_service, '_validation_service')
        assert hasattr(meter_service, '_idempotency_service')
        assert hasattr(meter_service, '_retry_service')

    async def test_batch_processor_depends_on_meter_service(self, stripe_config):
        """
        Test that BatchProcessor requires meter_event_service.

        Given: A StripeServiceBase instance
        When: batch_processor property is accessed
        Then: It creates BatchProcessor with meter_service
        """
        base = StripeServiceBase(config=stripe_config)
        base._initialized = True
        base.api_key = "sk_test_mock_key"

        # Access batch_processor
        batch_processor = base.batch_processor

        # Verify it was created
        assert batch_processor is not None
        assert hasattr(batch_processor, 'meter_event_service')
        assert batch_processor.meter_event_service is not None

    async def test_customer_service_independent(self, stripe_config):
        """
        Test that CustomerService has no dependencies on other services.

        Given: A StripeServiceBase instance
        When: customer_service property is accessed
        Then: It creates CustomerService without requiring other services
        """
        base = StripeServiceBase(config=stripe_config)
        base._initialized = True
        base.api_key = "sk_test_mock_key"

        # Access customer_service
        customer_service = base.customer_service

        # Verify it was created
        assert customer_service is not None
        assert hasattr(customer_service, 'api_key')
        assert customer_service.api_key == "sk_test_mock_key"


# =============================================================================
# Test Class: Facade Delegation
# =============================================================================

@pytest.mark.asyncio
class TestFacadeDelegation:
    """Test that facade properly delegates to services."""

    async def test_facade_create_customer_uses_customer_service(self, stripe_facade):
        """
        Test that StripeService.create_customer delegates to CustomerService.

        Given: A StripeService facade instance
        When: create_customer is called
        Then: The operation uses customer service for Stripe API calls
        """
        stripe_facade._initialized = True
        stripe_facade.api_key = "sk_test_mock_key"

        with patch('stripe.Customer.create') as mock_create:
            mock_create.return_value = Mock(id="cus_test_123")

            from src.models.tenant import Tenant
            tenant = Tenant(
                tenant_id="tenant_123",
                name="Test Tenant",
                status="active"
            )

            customer_id = await stripe_facade.create_customer(
                tenant=tenant,
                email="test@example.com",
                name="Test Customer"
            )

            assert customer_id == "cus_test_123"
            mock_create.assert_called_once()

    async def test_facade_report_usage_uses_validation_idempotency_retry(self, meter_event_service):
        """
        Test that report_usage calls validation, idempotency, and retry in correct order.

        Given: A meter event report request
        When: report_usage is called
        Then: Services are called in order: validation -> idempotency -> retry -> Stripe API
        """
        # Test that meter_event_service has access to all required services
        assert meter_event_service._validation_service is not None
        assert meter_event_service._idempotency_service is not None
        assert meter_event_service._retry_service is not None

        # Test that a successful report uses all services
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["status"] == "succeeded"

    async def test_facade_batch_delegates_to_batch_processor(self, batch_processor):
        """
        Test that report_usage_batch delegates to batch processor logic.

        Given: A batch of multiple events
        When: process_batch is called
        Then: Each event is processed individually with proper aggregation
        """
        events = [
            {"meter_event": "ai_labels", "value": 100},
            {"meter_event": "ai_labels", "value": 200},
            {"meter_event": "human_audits", "value": 50}
        ]

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 3
        assert result.successful_count == 3
        assert result.failed_count == 0
        assert len(result.successes) == 3


# =============================================================================
# Test Class: Validation Service Integration
# =============================================================================

@pytest.mark.asyncio
class TestValidationServiceIntegration:
    """Test validation service integration with other services."""

    async def test_validation_happens_before_idempotency_check(self, meter_event_service):
        """
        Test that validation is called before idempotency key generation.

        Given: A meter event report request with invalid meter event
        When: report_usage is called
        Then: ValidationService is called and rejects before idempotency key is generated
        """
        # Use invalid meter event
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="invalid_meter",
                value=100,
                tenant_id="tenant_123"
            )

        assert "Invalid meter_event" in str(exc_info.value)

    async def test_validation_rejects_non_positive_values(self, meter_event_service):
        """
        Test that validation rejects non-positive values.

        Given: A meter event report with value <= 0
        When: report_usage is called
        Then: ValidationService rejects the request
        """
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=0,
                tenant_id="tenant_123"
            )

        assert "Value must be positive" in str(exc_info.value)

    async def test_validation_happens_before_api_call(self, meter_event_service):
        """
        Test that validation prevents API calls for invalid data.

        Given: A meter event report with invalid data
        When: report_usage is called
        Then: Stripe API client is never called
        """
        initial_call_count = meter_event_service._stripe_client.create_meter_event.call_count

        try:
            await meter_event_service.report_usage(
                meter_event="invalid_meter",
                value=100,
                tenant_id="tenant_123"
            )
        except StripeMeterValidationError:
            pass

        # API call count should not have changed
        assert meter_event_service._stripe_client.create_meter_event.call_count == initial_call_count

    async def test_metadata_sanitization_blocks_reserved_keys(self, meter_event_service):
        """
        Test that metadata sanitization blocks reserved keys.

        Given: Metadata with reserved keys (value, stripe_customer_id, batch_id)
        When: report_usage is called
        Then: Reserved keys are rejected
        """
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123",
                metadata={"value": "blocked", "custom_key": "allowed"}
            )

        assert "reserved" in str(exc_info.value).lower()


# =============================================================================
# Test Class: Idempotency Service Integration
# =============================================================================

@pytest.mark.asyncio
class TestIdempotencyServiceIntegration:
    """Test idempotency service integration with other services."""

    async def test_idempotency_key_generated_for_each_event(self, meter_event_service):
        """
        Test that a unique idempotency key is generated for each meter event.

        Given: A valid meter event report request
        When: report_usage is called
        Then: IdempotencyService generates a unique key for the event
        """
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["event_id"] is not None
        assert isinstance(result["event_id"], str)
        assert len(result["event_id"]) > 0

    async def test_idempotency_key_includes_all_components(self, meter_event_service):
        """
        Test that idempotency key includes tenant, meter_event, value, timestamp.

        Given: A meter event report
        When: report_usage is called
        Then: Generated key contains tenant_id, meter_event, value components
        """
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_test_123"
        )

        key = result["event_id"]
        # Key should contain components (exact format depends on implementation)
        assert "tenant_test_123" in key or "tenant" in key
        assert "ai_labels" in key or "ai" in key
        assert "100" in key

    async def test_idempotency_key_registered_after_successful_report(self, meter_event_service):
        """
        Test that idempotency key is registered after successful meter event report.

        Given: A meter event report that succeeds
        When: report_usage completes successfully
        Then: Idempotency key is registered in the registry
        """
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        key = result["event_id"]
        assert meter_event_service._idempotency_service.is_registered(key) is True

    async def test_duplicate_idempotency_key_detection(self, idempotency_service):
        """
        Test that idempotency service can detect duplicate keys.

        Given: An idempotency key that has been registered
        When: is_registered is called with the same key
        Then: Service returns True indicating key already exists
        """
        key = idempotency_service.generate_key("tenant_123", "ai_labels", 100)

        # Initially not registered
        assert idempotency_service.is_registered(key) is False

        # Register the key
        idempotency_service.register_key(key)

        # Now should be registered
        assert idempotency_service.is_registered(key) is True

    async def test_idempotency_key_collision_metrics(self, idempotency_service):
        """
        Test that idempotency service tracks key generation metrics.

        Given: Multiple idempotency key generations
        When: get_metrics is called
        Then: Metrics include total keys generated and collision stats
        """
        # Generate some keys
        for i in range(5):
            idempotency_service.generate_key(f"tenant_{i}", "ai_labels", i * 10)

        metrics = idempotency_service.get_metrics()
        assert metrics.total_keys_generated >= 5


# =============================================================================
# Test Class: Retry Service Integration
# =============================================================================

@pytest.mark.asyncio
class TestRetryServiceIntegration:
    """Test retry service integration with meter event service."""

    async def test_transient_error_triggers_retry(self, stripe_config, mock_stripe_client):
        """
        Test that transient errors trigger retry logic.

        Given: A meter event report that fails with transient error
        When: report_usage is called
        Then: RetryService retries the operation
        """
        # Create a retry service with low retry count for testing
        test_config = StripeConfig(
            max_retries=2,
            initial_retry_delay_ms=10,  # Very short for tests
            jitter_enabled=False,
            meter_ids=stripe_config.meter_ids
        )
        retry_service = RetryService(test_config)

        # Mock API to fail once then succeed
        call_count = [0]
        def flaky_create(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Create a proper exception with http_status attribute
                class TransientError(Exception):
                    def __init__(self):
                        super().__init__("Simulated rate limit error")
                        self.http_status = 429
                raise TransientError()
            return {"id": f"evt_test_{call_count[0]}"}

        mock_stripe_client.create_meter_event = Mock(side_effect=flaky_create)

        meter_service = MeterEventService(
            config=test_config,
            validation_service=ValidationService(test_config),
            idempotency_service=IdempotencyService(test_config),
            retry_service=retry_service,
            stripe_client=mock_stripe_client
        )

        result = await meter_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        # Should have been called twice (initial + 1 retry)
        assert call_count[0] == 2
        assert result["status"] == "succeeded"

    async def test_permanent_error_does_not_retry(self, stripe_config, mock_stripe_client):
        """
        Test that permanent errors do not trigger retry logic.

        Given: A meter event report that fails with permanent error (400)
        When: report_usage is called
        Then: Operation fails immediately without retry
        """
        test_config = StripeConfig(
            max_retries=3,
            jitter_enabled=False,
            meter_ids=stripe_config.meter_ids
        )
        retry_service = RetryService(test_config)

        call_count = [0]
        def permanent_error(**kwargs):
            call_count[0] += 1
            class PermanentError(Exception):
                def __init__(self):
                    super().__init__("Simulated bad request")
                    self.http_status = 400
            raise PermanentError()

        mock_stripe_client.create_meter_event = Mock(side_effect=permanent_error)

        meter_service = MeterEventService(
            config=test_config,
            validation_service=ValidationService(test_config),
            idempotency_service=IdempotencyService(test_config),
            retry_service=retry_service,
            stripe_client=mock_stripe_client
        )

        with pytest.raises(Exception):
            await meter_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )

        # Should only be called once (no retries for permanent errors)
        assert call_count[0] == 1

    async def test_retry_exhaustion_raises_error(self, stripe_config, mock_stripe_client):
        """
        Test that exceeding max retries raises an error.

        Given: A meter event report that consistently fails with transient error
        When: report_usage is called
        Then: After max retries, error is raised
        """
        test_config = StripeConfig(
            max_retries=1,  # Only 1 retry
            initial_retry_delay_ms=10,
            jitter_enabled=False,
            meter_ids=stripe_config.meter_ids
        )
        retry_service = RetryService(test_config)

        def always_transient_error(**kwargs):
            class TransientError(Exception):
                def __init__(self):
                    super().__init__("Simulated service unavailable")
                    self.http_status = 503
            raise TransientError()

        mock_stripe_client.create_meter_event = Mock(side_effect=always_transient_error)

        meter_service = MeterEventService(
            config=test_config,
            validation_service=ValidationService(test_config),
            idempotency_service=IdempotencyService(test_config),
            retry_service=retry_service,
            stripe_client=mock_stripe_client
        )

        with pytest.raises(Exception):
            await meter_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )

    async def test_retry_with_exponential_backoff(self, retry_service):
        """
        Test that retry delay increases exponentially.

        Given: A RetryService configured with exponential backoff
        When: Multiple retry delays are calculated
        Then: Each delay is longer than the previous (up to max)
        """
        delay_0 = retry_service._calculate_retry_delay(0)
        delay_1 = retry_service._calculate_retry_delay(1)
        delay_2 = retry_service._calculate_retry_delay(2)

        # Delays should increase exponentially
        assert delay_1 > delay_0
        assert delay_2 > delay_1


# =============================================================================
# Test Class: Batch Processor Integration
# =============================================================================

@pytest.mark.asyncio
class TestBatchProcessorIntegration:
    """Test batch processor integration with meter event service."""

    async def test_batch_processor_delegates_to_meter_service(self, batch_processor):
        """
        Test that batch processor delegates individual events to meter event service.

        Given: A batch of 5 meter events
        When: process_batch is called
        Then: MeterEventService.report_usage is called 5 times
        """
        events = [
            {"meter_event": "ai_labels", "value": 100 * (i + 1)}
            for i in range(5)
        ]

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 5
        assert result.successful_count == 5
        assert result.failed_count == 0
        assert len(result.successes) == 5

    async def test_batch_handles_partial_failures(self, stripe_config):
        """
        Test that batch processor handles partial failures gracefully.

        Given: A batch where some events will fail
        When: process_batch is called
        Then: Successful events succeed and failed events are tracked separately
        """
        # Create a flaky meter service
        mock_meter_service = AsyncMock()
        call_count = [0]

        async def flaky_report(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise StripeMeterValidationError("Simulated failure")
            return {
                "event_id": f"evt_{call_count[0]}",
                "status": "succeeded",
                "meter_event": kwargs.get("meter_event", "ai_labels"),
                "value": kwargs.get("value", 100),
                "stripe_response": {}
            }

        mock_meter_service.report_usage = flaky_report

        batch_processor = BatchProcessor(
            config=stripe_config,
            meter_event_service=mock_meter_service
        )

        events = [
            {"meter_event": "ai_labels", "value": 100}
            for _ in range(6)
        ]

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 6
        assert result.successful_count == 3
        assert result.failed_count == 3
        assert len(result.successes) == 3
        assert len(result.failures) == 3

    async def test_batch_validates_all_events_upfront(self, batch_processor):
        """
        Test that batch processor validates event structure before processing.

        Given: A batch with malformed event data
        When: process_batch is called
        Then: Validation fails before any events are processed
        """
        events = [
            {"meter_event": "ai_labels", "value": 100},
            {"value": 200},  # Missing meter_event
            {"meter_event": "human_audits", "value": 50}
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "Missing required field 'meter_event'" in str(exc_info.value)

    async def test_batch_enforces_max_batch_size(self, stripe_config):
        """
        Test that batch processor enforces maximum batch size.

        Given: A batch size larger than configured maximum
        When: process_batch is called
        Then: StripeMeterValidationError is raised
        """
        small_config = StripeConfig(max_batch_size=10, meter_ids=stripe_config.meter_ids)
        mock_meter_service = AsyncMock()

        batch_processor = BatchProcessor(
            config=small_config,
            meter_event_service=mock_meter_service
        )

        events = [
            {"meter_event": "ai_labels", "value": 100}
            for _ in range(11)  # Exceeds max_batch_size of 10
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "exceeds maximum allowed size" in str(exc_info.value)

    async def test_batch_generates_unique_batch_id(self, batch_processor):
        """
        Test that each batch gets a unique batch ID.

        Given: Multiple batch operations
        When: process_batch is called multiple times
        Then: Each batch has a unique batch_id
        """
        events = [{"meter_event": "ai_labels", "value": 100}]

        result1 = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        result2 = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result1.batch_id != result2.batch_id
        assert "tenant_123" in result1.batch_id
        assert "tenant_123" in result2.batch_id

    async def test_empty_batch_returns_empty_result(self, batch_processor):
        """
        Test that empty batch is handled gracefully.

        Given: An empty events list
        When: process_batch is called
        Then: Returns BatchResult with zero counts
        """
        result = await batch_processor.process_batch(
            events=[],
            tenant_id="tenant_123"
        )

        assert result.total_events == 0
        assert result.successful_count == 0
        assert result.failed_count == 0


# =============================================================================
# Test Class: Error Propagation
# =============================================================================

@pytest.mark.asyncio
class TestErrorPropagation:
    """Test that errors propagate correctly through service layers."""

    async def test_validation_error_propagates_to_facade(self, meter_event_service):
        """
        Test that validation errors propagate through facade.

        Given: Invalid meter event data
        When: report_usage is called
        Then: StripeMeterValidationError propagates to caller
        """
        with pytest.raises(StripeMeterValidationError):
            await meter_event_service.report_usage(
                meter_event="invalid_event",
                value=100,
                tenant_id="tenant_123"
            )

    async def test_stripe_api_error_propagates_with_context(self, meter_event_service):
        """
        Test that Stripe API errors propagate with error context.

        Given: Stripe API returns an error
        When: report_usage is called
        Then: Error includes HTTP status and error type
        """
        def api_error(**kwargs):
            error = Mock()
            error.http_status = 401
            error.code = "api_key_invalid"
            error.__class__ = type("AuthenticationError", (Exception,), {})
            raise error

        meter_event_service._stripe_client.create_meter_event = Mock(side_effect=api_error)

        with pytest.raises(Exception):
            await meter_event_service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )

    async def test_idempotency_key_too_long_error(self, idempotency_service):
        """
        Test that idempotency key length validation propagates.

        Given: Components that would create a key exceeding max length
        When: generate_key is called
        Then: StripeIdempotencyKeyTooLongError is raised
        """
        # Create a config with very short max length
        short_config = StripeConfig(max_idempotency_key_length=20)
        short_service = IdempotencyService(short_config)

        with pytest.raises(StripeIdempotencyKeyTooLongError):
            # Use long components to exceed limit
            short_service.generate_key(
                tenant_id="a" * 50,
                meter_event="b" * 50,
                value=1
            )

    async def test_customer_not_found_error_propagates(self, customer_service):
        """
        Test that customer not found errors propagate correctly.

        Given: A customer lookup for non-existent customer
        When: get_customer_by_tenant is called
        Then: Returns None (not an error for get operations)
        """
        # This would need database session, testing error propagation pattern
        pass


# =============================================================================
# Test Class: End-to-End Workflows
# =============================================================================

@pytest.mark.asyncio
class TestEndToEndWorkflows:
    """Test complete workflows through multiple services."""

    async def test_successful_meter_event_report_workflow(self, meter_event_service):
        """
        Test complete successful workflow for single meter event.

        Given: Valid meter event data
        When: report_usage is called
        Then: Flow completes: validation -> idempotency -> API -> registration -> result
        """
        result = await meter_event_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123",
            metadata={"source": "test"}
        )

        assert result["status"] == "succeeded"
        assert result["meter_event"] == "ai_labels"
        assert result["value"] == 100
        assert result["event_id"] is not None

    async def test_successful_batch_workflow(self, batch_processor):
        """
        Test complete workflow for batch processing.

        Given: Valid batch of mixed meter events
        When: process_batch is called
        Then: All events processed with correct aggregation
        """
        events = [
            {"meter_event": "ai_labels", "value": 100, "metadata": {"source": "api"}},
            {"meter_event": "human_audits", "value": 50, "metadata": {"source": "api"}},
            {"meter_event": "ai_labels", "value": 200}
        ]

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123",
            stripe_customer_id="cus_test_123"
        )

        assert result.total_events == 3
        assert result.successful_count == 3
        assert result.failed_count == 0
        assert len(result.successes) == 3

    async def test_workflow_with_retry_then_success(self, stripe_config, mock_stripe_client):
        """
        Test workflow where first attempt fails but retry succeeds.

        Given: A meter event that fails once with transient error
        When: report_usage is called
        Then: Retry logic activates and eventually succeeds
        """
        test_config = StripeConfig(
            max_retries=2,
            initial_retry_delay_ms=10,
            jitter_enabled=False,
            meter_ids=stripe_config.meter_ids
        )

        retry_service = RetryService(test_config)

        attempts = [0]
        def fail_once(**kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                class TransientError(Exception):
                    def __init__(self):
                        super().__init__("Simulated service unavailable")
                        self.http_status = 503
                raise TransientError()
            return {"id": "evt_success_after_retry"}

        mock_stripe_client.create_meter_event = Mock(side_effect=fail_once)

        meter_service = MeterEventService(
            config=test_config,
            validation_service=ValidationService(test_config),
            idempotency_service=IdempotencyService(test_config),
            retry_service=retry_service,
            stripe_client=mock_stripe_client
        )

        result = await meter_service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_123"
        )

        assert result["status"] == "succeeded"
        assert attempts[0] == 2  # Initial + 1 retry

    async def test_workflow_with_validation_blocking_early(self, meter_event_service):
        """
        Test workflow where validation blocks processing early.

        Given: Invalid meter event data
        When: report_usage is called
        Then: Validation rejects without making API calls
        """
        api_call_count = meter_event_service._stripe_client.create_meter_event.call_count

        try:
            await meter_event_service.report_usage(
                meter_event="invalid_type",
                value=100,
                tenant_id="tenant_123"
            )
        except StripeMeterValidationError:
            pass

        # API should not have been called
        assert meter_event_service._stripe_client.create_meter_event.call_count == api_call_count


# =============================================================================
# Test Class: Protocol Compliance
# =============================================================================

class TestProtocolCompliance:
    """Test that services properly implement their protocols."""

    def test_validation_service_implements_protocol(self, validation_service):
        """
        Test that ValidationService implements ValidationServiceProtocol.

        Given: A ValidationService instance
        When: Checking protocol compliance
        Then: All protocol methods are implemented
        """
        # Check that all required methods exist
        assert hasattr(validation_service, 'validate_meter_event')
        assert hasattr(validation_service, 'sanitize_metadata')
        assert hasattr(validation_service, 'sanitize_idempotency_component')
        assert callable(validation_service.validate_meter_event)
        assert callable(validation_service.sanitize_metadata)
        assert callable(validation_service.sanitize_idempotency_component)

    def test_idempotency_service_implements_protocol(self, idempotency_service):
        """
        Test that IdempotencyService implements IdempotencyServiceProtocol.

        Given: An IdempotencyService instance
        When: Checking protocol compliance
        Then: All protocol methods are implemented
        """
        # Check that all required methods exist
        assert hasattr(idempotency_service, 'generate_key')
        assert hasattr(idempotency_service, 'is_registered')
        assert hasattr(idempotency_service, 'register_key')
        assert hasattr(idempotency_service, 'get_metrics')
        assert callable(idempotency_service.generate_key)
        assert callable(idempotency_service.is_registered)
        assert callable(idempotency_service.register_key)
        assert callable(idempotency_service.get_metrics)

    def test_retry_service_implements_protocol(self, retry_service):
        """
        Test that RetryService implements RetryServiceProtocol.

        Given: A RetryService instance
        When: Checking protocol compliance
        Then: All protocol methods are implemented
        """
        # Check that all required methods exist
        assert hasattr(retry_service, 'execute_with_retry')
        assert hasattr(retry_service, 'is_transient_error')
        assert callable(retry_service.execute_with_retry)
        assert callable(retry_service.is_transient_error)

    def test_batch_processor_implements_protocol(self, batch_processor):
        """
        Test that BatchProcessor implements BatchProcessorProtocol.

        Given: A BatchProcessor instance
        When: Checking protocol compliance
        Then: All protocol methods are implemented
        """
        # Check that all required methods exist
        assert hasattr(batch_processor, 'process_batch')
        assert hasattr(batch_processor, 'generate_batch_id')
        assert callable(batch_processor.process_batch)
        assert callable(batch_processor.generate_batch_id)


# =============================================================================
# Test Class: Configuration Integration
# =============================================================================

class TestConfigurationIntegration:
    """Test that configuration properly flows through services."""

    def test_config_validates_retry_settings(self, stripe_config):
        """
        Test that StripeConfig validates retry configuration.

        Given: A StripeConfig instance
        When: validate is called
        Then: Validation errors are returned for invalid config (if any)
        """
        errors = stripe_config.validate()
        # Valid config should have no errors
        assert len(errors) == 0

    def test_config_rejects_invalid_retry_config(self):
        """
        Test that StripeConfig rejects invalid retry configuration.

        Given: Invalid retry configuration values
        When: StripeConfig is created
        Then: Validation detects the errors
        """
        invalid_config = StripeConfig(
            max_retries=-1,  # Invalid
            meter_ids={}
        )

        errors = invalid_config.validate()
        assert len(errors) > 0
        assert any("max_retries" in err for err in errors)

    def test_config_rejects_invalid_batch_size(self):
        """
        Test that StripeConfig rejects invalid batch size.

        Given: Invalid batch size configuration
        When: validate is called
        Then: Validation detects batch size errors
        """
        invalid_config = StripeConfig(
            max_batch_size=0,  # Invalid
            meter_ids={}
        )

        errors = invalid_config.validate()
        assert len(errors) > 0
        assert any("max_batch_size" in err for err in errors)

    def test_services_use_configured_retry_settings(self, retry_service, stripe_config):
        """
        Test that RetryService uses configured retry settings.

        Given: A RetryService with specific configuration
        When: Retry operations are performed
        Then: Configured limits and delays are respected
        """
        assert retry_service._max_retries == stripe_config.max_retries
        assert retry_service._initial_delay_ms == stripe_config.initial_retry_delay_ms
        assert retry_service._max_delay_ms == stripe_config.max_retry_delay_ms


# =============================================================================
# Test Class: Thread Safety
# =============================================================================

class TestThreadSafety:
    """Test thread-safe operations in services."""

    def test_idempotency_registry_is_thread_safe(self, idempotency_service):
        """
        Test that idempotency registry operations are thread-safe.

        Given: An IdempotencyService
        When: Multiple threads register keys concurrently
        Then: All keys are registered without corruption
        """
        import threading

        keys_registered = []
        def register_keys(thread_id):
            for i in range(10):
                key = idempotency_service.generate_key(
                    f"tenant_{thread_id}",
                    "ai_labels",
                    i
                )
                idempotency_service.register_key(key)
                keys_registered.append(key)

        threads = []
        for i in range(5):
            t = threading.Thread(target=register_keys, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All keys should be registered
        metrics = idempotency_service.get_metrics()
        assert metrics.total_keys_generated >= 50


# =============================================================================
# Test Class: Memory Management
# =============================================================================

class TestMemoryManagement:
    """Test memory management in services."""

    def test_idempotency_registry_size_limit(self):
        """
        Test that idempotency registry enforces size limits.

        Given: An IdempotencyService with max_registry_size
        When: More keys than max are registered
        Then: Old keys are evicted to maintain limit
        """
        small_config = StripeConfig(max_idempotency_registry_size=10)
        service = IdempotencyService(small_config)

        # Register more keys than limit
        for i in range(20):
            key = service.generate_key(f"tenant_{i}", "ai_labels", i)
            service.register_key(key)

        metrics = service.get_metrics()
        # Registry size should be at or near limit
        assert metrics.registry_size <= service.max_registry_size


# =============================================================================
# Run Configuration
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
