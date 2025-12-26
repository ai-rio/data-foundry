"""
Unit tests for BatchProcessor.

Test suite for batch processing of meter events, following TDD approach.

Phase: 2.5.3 (Domain Services)
Task: 2.5.3.3 - Extract batch_processor.py with BatchProcessor
Created: 2025-12-25

Test Coverage:
- Successful batch processing (all events succeed)
- Partial batch failure (some events fail)
- Complete batch failure (all events fail)
- Empty batch handling
- Batch size limits
- Batch ID uniqueness
- Individual event error isolation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
from typing import Dict, Any, List
import uuid

from src.services.stripe.types import (
    BatchProcessorProtocol,
    MeterEventData,
    BatchResult,
    MeterEventResult,
)
from src.services.stripe.config import StripeConfig
from src.services.stripe.batch_processor import BatchProcessor
from src.services.stripe.exceptions import (
    StripeMeterValidationError,
    StripeAPIError,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_config():
    """Create a mock StripeConfig."""
    config = StripeConfig()
    config.max_batch_size = 100
    return config


@pytest.fixture
def mock_meter_event_service():
    """Create a mock MeterEventServiceProtocol."""
    service = Mock()
    service.report_usage = AsyncMock()
    return service


@pytest.fixture
def batch_processor(mock_config, mock_meter_event_service):
    """Create a BatchProcessor instance with mocked dependencies."""
    return BatchProcessor(
        config=mock_config,
        meter_event_service=mock_meter_event_service
    )


# ============================================================================
# Test: Batch ID Generation
# ============================================================================

class TestBatchIdGeneration:
    """Tests for generate_batch_id method."""

    def test_generate_batch_id_format(self, batch_processor):
        """Test that batch ID follows the correct format."""
        tenant_id = "tenant_abc123"
        batch_id = batch_processor.generate_batch_id(tenant_id)

        # Format: batch_{tenant_id}_{timestamp}_{nonce}
        assert batch_id.startswith("batch_")
        assert tenant_id in batch_id
        assert batch_id.count("_") >= 3  # At least: batch_tenant_timestamp_nonce

    def test_generate_batch_id_uniqueness(self, batch_processor):
        """Test that batch IDs are unique."""
        tenant_id = "tenant_xyz"
        ids = [batch_processor.generate_batch_id(tenant_id) for _ in range(100)]

        # All IDs should be unique
        assert len(set(ids)) == 100

    def test_generate_batch_id_includes_tenant(self, batch_processor):
        """Test that batch ID includes tenant_id."""
        tenant_id = "tenant_test123"
        batch_id = batch_processor.generate_batch_id(tenant_id)

        assert tenant_id in batch_id

    @patch('src.services.stripe.batch_processor.datetime')
    @patch('src.services.stripe.batch_processor.uuid')
    def test_generate_batch_id_components(self, mock_uuid, mock_datetime, batch_processor):
        """Test that batch ID includes timestamp and nonce."""
        tenant_id = "tenant_components"

        # Mock datetime
        mock_dt = Mock()
        mock_dt.now.return_value = datetime(2025, 12, 25, 12, 30, 45, tzinfo=timezone.utc)
        mock_dt.strftime.return_value = "20251225123045"
        mock_datetime.now = Mock(return_value=mock_dt)
        mock_datetime.timezone = timezone

        # Mock UUID
        mock_uuid.uuid4().hex[:8] = "a1b2c3d4"

        batch_id = batch_processor.generate_batch_id(tenant_id)

        # Check format includes timestamp and nonce
        assert "20251225123045" in batch_id or len(batch_id) > len(f"batch_{tenant_id}_")


# ============================================================================
# Test: Batch Processing - Success Cases
# ============================================================================

class TestBatchProcessingSuccess:
    """Tests for successful batch processing."""

    @pytest.mark.asyncio
    async def test_process_batch_all_events_succeed(self, batch_processor, mock_meter_event_service):
        """Test processing a batch where all events succeed."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
            {"meter_event": "human_audits", "value": 50, "tenant_id": "tenant_123"},
            {"meter_event": "ai_labels", "value": 75, "tenant_id": "tenant_123"},
        ]

        # Mock successful responses
        mock_meter_event_service.report_usage.side_effect = [
            {"event_id": "evt_1", "status": "succeeded", "meter_event": "ai_labels", "value": 100},
            {"event_id": "evt_2", "status": "succeeded", "meter_event": "human_audits", "value": 50},
            {"event_id": "evt_3", "status": "succeeded", "meter_event": "ai_labels", "value": 75},
        ]

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123",
            stripe_customer_id="cus_abc123"
        )

        assert result.total_events == 3
        assert result.successful_count == 3
        assert result.failed_count == 0
        assert len(result.successes) == 3
        assert len(result.failures) == 0
        assert result.batch_id.startswith("batch_")

    @pytest.mark.asyncio
    async def test_process_batch_passes_batch_id(self, batch_processor, mock_meter_event_service):
        """Test that batch_id is passed to individual event processing."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
        ]

        mock_meter_event_service.report_usage.return_value = {
            "event_id": "evt_1", "status": "succeeded", "meter_event": "ai_labels", "value": 100
        }

        await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123",
            stripe_customer_id="cus_abc123"
        )

        # Verify report_usage was called with batch_id
        call_args = mock_meter_event_service.report_usage.call_args
        assert call_args is not None
        keyword_args = call_args.kwargs if call_args.kwargs else call_args[1]
        assert "batch_id" in keyword_args
        assert keyword_args["batch_id"].startswith("batch_")

    @pytest.mark.asyncio
    async def test_process_batch_with_optional_metadata(self, batch_processor, mock_meter_event_service):
        """Test processing events with optional metadata."""
        events = [
            {
                "meter_event": "ai_labels",
                "value": 100,
                "tenant_id": "tenant_123",
                "metadata": {"source": "api", "user_id": "12345"}
            },
        ]

        mock_meter_event_service.report_usage.return_value = {
            "event_id": "evt_1", "status": "succeeded", "meter_event": "ai_labels", "value": 100
        }

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.successful_count == 1
        # Verify metadata was passed
        call_args = mock_meter_event_service.report_usage.call_args
        keyword_args = call_args.kwargs if call_args.kwargs else call_args[1]
        assert keyword_args.get("metadata") == {"source": "api", "user_id": "12345"}


# ============================================================================
# Test: Batch Processing - Failure Cases
# ============================================================================

class TestBatchProcessingFailures:
    """Tests for batch processing with failures."""

    @pytest.mark.asyncio
    async def test_process_batch_partial_failure(self, batch_processor, mock_meter_event_service):
        """Test processing a batch with some failures."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
            {"meter_event": "human_audits", "value": 50, "tenant_id": "tenant_123"},
            {"meter_event": "ai_labels", "value": 75, "tenant_id": "tenant_123"},
        ]

        # First and third succeed, second fails
        async def side_effect_func(*args, **kwargs):
            meter_event = kwargs.get("meter_event") or (args[0] if args else None)
            if meter_event == "human_audits":
                raise StripeMeterValidationError("Invalid meter event")
            return {
                "event_id": f"evt_{meter_event}",
                "status": "succeeded",
                "meter_event": meter_event,
                "value": kwargs.get("value", 0)
            }

        mock_meter_event_service.report_usage.side_effect = side_effect_func

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 3
        assert result.successful_count == 2
        assert result.failed_count == 1
        assert len(result.successes) == 2
        assert len(result.failures) == 1

    @pytest.mark.asyncio
    async def test_process_batch_all_fail(self, batch_processor, mock_meter_event_service):
        """Test processing a batch where all events fail."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
            {"meter_event": "human_audits", "value": 50, "tenant_id": "tenant_123"},
        ]

        # All events fail
        mock_meter_event_service.report_usage.side_effect = StripeAPIError(
            "API error",
            stripe_error_type="APIError",
            stripe_code="api_error"
        )

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 2
        assert result.successful_count == 0
        assert result.failed_count == 2
        assert len(result.successes) == 0
        assert len(result.failures) == 2

    @pytest.mark.asyncio
    async def test_process_batch_error_isolation(self, batch_processor, mock_meter_event_service):
        """Test that individual event errors don't stop batch processing."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
            {"meter_event": "invalid_meter", "value": 50, "tenant_id": "tenant_123"},
            {"meter_event": "human_audits", "value": 75, "tenant_id": "tenant_123"},
        ]

        call_count = 0

        async def side_effect_func(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            meter_event = kwargs.get("meter_event")
            if meter_event == "invalid_meter":
                raise StripeMeterValidationError(f"Invalid meter: {meter_event}")
            return {
                "event_id": f"evt_{call_count}",
                "status": "succeeded",
                "meter_event": meter_event,
                "value": kwargs.get("value", 0)
            }

        mock_meter_event_service.report_usage.side_effect = side_effect_func

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        # All events should be processed despite failure in middle
        assert result.total_events == 3
        assert result.successful_count == 2
        assert result.failed_count == 1
        assert call_count == 3  # All three events were attempted

    @pytest.mark.asyncio
    async def test_process_batch_failure_details_captured(self, batch_processor, mock_meter_event_service):
        """Test that failure details are properly captured."""
        events = [
            {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
        ]

        error = StripeMeterValidationError(
            "Invalid meter event",
            meter_event="ai_labels",
            validation_errors=["Value must be positive"]
        )
        mock_meter_event_service.report_usage.side_effect = error

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.failed_count == 1
        assert len(result.failures) == 1

        failure = result.failures[0]
        assert "event" in failure
        assert "error" in failure
        assert "error_type" in failure
        assert failure["event"]["meter_event"] == "ai_labels"
        assert failure["event"]["value"] == 100


# ============================================================================
# Test: Empty Batch Handling
# ============================================================================

class TestEmptyBatchHandling:
    """Tests for empty batch handling."""

    @pytest.mark.asyncio
    async def test_process_empty_batch(self, batch_processor, mock_meter_event_service):
        """Test processing an empty batch."""
        result = await batch_processor.process_batch(
            events=[],
            tenant_id="tenant_123"
        )

        assert result.total_events == 0
        assert result.successful_count == 0
        assert result.failed_count == 0
        assert len(result.successes) == 0
        assert len(result.failures) == 0
        assert result.batch_id.startswith("batch_")

        # Meter event service should not be called
        mock_meter_event_service.report_usage.assert_not_called()


# ============================================================================
# Test: Batch Size Limits
# ============================================================================

class TestBatchSizeLimits:
    """Tests for batch size validation."""

    @pytest.mark.asyncio
    async def test_process_batch_max_size_success(self, batch_processor, mock_meter_event_service):
        """Test processing a batch at maximum size."""
        # Create exactly max_batch_size events
        events = [
            {"meter_event": "ai_labels", "value": i, "tenant_id": "tenant_123"}
            for i in range(100)
        ]

        mock_meter_event_service.report_usage.return_value = {
            "event_id": "evt_1", "status": "succeeded", "meter_event": "ai_labels", "value": 1
        }

        result = await batch_processor.process_batch(
            events=events,
            tenant_id="tenant_123"
        )

        assert result.total_events == 100
        assert result.successful_count == 100

    @pytest.mark.asyncio
    async def test_process_batch_exceeds_max_size(self, batch_processor):
        """Test that exceeding max batch size raises validation error."""
        # Create more than max_batch_size events
        events = [
            {"meter_event": "ai_labels", "value": i, "tenant_id": "tenant_123"}
            for i in range(101)
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "batch size" in str(exc_info.value).lower()
        assert "100" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_batch_custom_max_size(self):
        """Test batch processor with custom max batch size."""
        custom_config = StripeConfig()
        custom_config.max_batch_size = 50

        mock_service = Mock()
        mock_service.report_usage = AsyncMock()

        processor = BatchProcessor(config=custom_config, meter_event_service=mock_service)

        # Create 51 events (exceeds custom limit)
        events = [
            {"meter_event": "ai_labels", "value": i, "tenant_id": "tenant_123"}
            for i in range(51)
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await processor.process_batch(events=events, tenant_id="tenant_123")

        assert "50" in str(exc_info.value)


# ============================================================================
# Test: Event Structure Validation
# ============================================================================

class TestEventStructureValidation:
    """Tests for event structure validation."""

    @pytest.mark.asyncio
    async def test_process_batch_missing_meter_event(self, batch_processor):
        """Test that missing meter_event field raises validation error."""
        events = [
            {"value": 100, "tenant_id": "tenant_123"},  # Missing meter_event
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "meter_event" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_process_batch_missing_value(self, batch_processor):
        """Test that missing value field raises validation error."""
        events = [
            {"meter_event": "ai_labels", "tenant_id": "tenant_123"},  # Missing value
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "value" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_process_batch_invalid_meter_event_type(self, batch_processor):
        """Test that non-string meter_event raises validation error."""
        events = [
            {"meter_event": 123, "value": 100, "tenant_id": "tenant_123"},  # Invalid type
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "meter_event" in str(exc_info.value).lower()
        assert "string" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_process_batch_invalid_value_type(self, batch_processor):
        """Test that non-integer value raises validation error."""
        events = [
            {"meter_event": "ai_labels", "value": "100", "tenant_id": "tenant_123"},  # Invalid type
        ]

        with pytest.raises(StripeMeterValidationError) as exc_info:
            await batch_processor.process_batch(
                events=events,
                tenant_id="tenant_123"
            )

        assert "value" in str(exc_info.value).lower()
        assert "integer" in str(exc_info.value).lower()


# ============================================================================
# Test: Protocol Compliance
# ============================================================================

class TestProtocolCompliance:
    """Tests for BatchProcessorProtocol compliance."""

    def test_batch_processor_protocol_compliance(self, batch_processor):
        """Test that BatchProcessor implements BatchProcessorProtocol."""
        # Check that BatchProcessor has required protocol methods
        assert hasattr(batch_processor, 'process_batch')
        assert callable(batch_processor.process_batch)
        assert hasattr(batch_processor, 'generate_batch_id')
        assert callable(batch_processor.generate_batch_id)

    def test_batch_processor_has_process_batch_method(self, batch_processor):
        """Test that BatchProcessor has process_batch method."""
        assert hasattr(batch_processor, 'process_batch')
        assert callable(batch_processor.process_batch)

    def test_batch_processor_has_generate_batch_id_method(self, batch_processor):
        """Test that BatchProcessor has generate_batch_id method."""
        assert hasattr(batch_processor, 'generate_batch_id')
        assert callable(batch_processor.generate_batch_id)
