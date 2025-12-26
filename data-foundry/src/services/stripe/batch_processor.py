"""
Batch processing service for Stripe meter events.

This module provides the BatchProcessor class for processing multiple
meter events in a single batch operation. It handles error isolation,
batch ID generation, and aggregates results for comprehensive reporting.

Phase: 2.5.3 (Domain Services)
Task: 2.5.3.3 - Extract batch_processor.py with BatchProcessor
Created: 2025-12-25

Features:
- process_batch(): Processes multiple meter events in a single batch
- generate_batch_id(): Generates unique batch identifier

Business Logic:
- Delegates to MeterEventService for individual event processing
- Aggregates results in BatchResult with success/failure tracking
- Error isolation - individual event failures don't stop batch
- Configurable batch size limits via StripeConfig

Security:
- Input validation prevents injection attacks
- Batch size limits prevent DoS attacks
- Event structure validation ensures type safety
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from src.services.stripe.types import (
    BatchProcessorProtocol,
    MeterEventData,
    BatchResult,
    MeterEventResult,
)
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import StripeMeterValidationError


logger = logging.getLogger(__name__)


class BatchProcessor(BatchProcessorProtocol):
    """
    Service for processing meter events in batches.

    Handles batch processing of meter events with proper error isolation,
    result aggregation, and comprehensive tracking. Individual event failures
    don't stop the batch from processing remaining events.

    Attributes:
        config: StripeConfig instance with batch size limits
        meter_event_service: Service for processing individual meter events

    Example:
        >>> processor = BatchProcessor(config, meter_event_service)
        >>> events = [
        ...     {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
        ...     {"meter_event": "human_audits", "value": 50, "tenant_id": "tenant_123"},
        ... ]
        >>> result = await processor.process_batch(
        ...     events=events,
        ...     tenant_id="tenant_123",
        ...     stripe_customer_id="cus_abc123"
        ... )
        >>> print(f"Processed: {result.successful_count}/{result.total_events}")
    """

    def __init__(
        self,
        config: StripeConfig,
        meter_event_service: Any
    ):
        """
        Initialize BatchProcessor.

        Args:
            config: StripeConfig instance for configuration
            meter_event_service: Service implementing MeterEventServiceProtocol
        """
        self.config = config
        self.meter_event_service = meter_event_service

    async def process_batch(
        self,
        events: List[MeterEventData],
        tenant_id: str,
        stripe_customer_id: Optional[str] = None
    ) -> BatchResult:
        """
        Process a batch of meter events.

        Processes multiple meter events sequentially, handling partial failures
        gracefully. Each event is processed independently, with successes and
        failures tracked separately in the BatchResult.

        Args:
            events: List of meter event data dictionaries
            tenant_id: Tenant identifier
            stripe_customer_id: Optional Stripe customer ID for all events

        Returns:
            BatchResult with aggregate statistics including:
            - batch_id: Unique batch identifier
            - total_events: Total number of events
            - successful_count: Number of successful events
            - failed_count: Number of failed events
            - successes: List of successful event results
            - failures: List of failed event results with errors

        Raises:
            StripeMeterValidationError: If batch size exceeds limit or event
                                       structure is invalid

        Example:
            >>> events = [
            ...     {"meter_event": "ai_labels", "value": 100, "tenant_id": "tenant_123"},
            ...     {"meter_event": "human_audits", "value": 50, "tenant_id": "tenant_123"},
            ... ]
            >>> result = await processor.process_batch(
            ...     events=events,
            ...     tenant_id="tenant_123"
            ... )
        """
        # Generate batch ID for tracking
        batch_id = self.generate_batch_id(tenant_id)

        # Initialize batch result
        result = BatchResult(
            batch_id=batch_id,
            total_events=len(events),
            successful_count=0,
            failed_count=0,
            successes=[],
            failures=[]
        )

        # Handle empty batch
        if not events:
            logger.info(f"Empty batch received for tenant {tenant_id}")
            return result

        # Validate batch size to prevent DoS attacks
        if len(events) > self.config.max_batch_size:
            raise StripeMeterValidationError(
                f"Batch size exceeds maximum allowed size of {self.config.max_batch_size}. "
                f"Got {len(events)} events."
            )

        # Validate event structure upfront
        self._validate_batch_events(events)

        # Process each event sequentially with error isolation
        for event_data in events:
            meter_event = event_data["meter_event"]
            value = event_data["value"]
            event_metadata = event_data.get("metadata", {})

            try:
                # Delegate to meter event service for processing
                event_result = await self.meter_event_service.report_usage(
                    meter_event=meter_event,
                    value=value,
                    tenant_id=tenant_id,
                    metadata=event_metadata,
                    stripe_customer_id=stripe_customer_id,
                    batch_id=batch_id
                )

                # Track success
                result.successes.append(event_result)
                result.successful_count += 1

            except Exception as e:
                # Track failure with details
                failure_info = self._create_failure_info(
                    event_data=meter_event,
                    value=value,
                    metadata=event_metadata,
                    error=e
                )

                result.failures.append(failure_info)
                result.failed_count += 1

                logger.warning(
                    f"Event failed in batch {batch_id}: {meter_event}={value} - {str(e)}"
                )

        # Log batch summary
        logger.info(
            f"Batch {batch_id} completed: "
            f"{result.successful_count}/{result.total_events} succeeded, "
            f"{result.failed_count} failed"
        )

        return result

    def generate_batch_id(self, tenant_id: str) -> str:
        """
        Generate a unique batch ID for tracking batch operations.

        Combines tenant_id, timestamp, and UUID to ensure uniqueness
        across concurrent operations and time boundaries.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Unique batch ID string in format: batch_{tenant_id}_{timestamp}_{nonce}

        Example:
            >>> batch_id = processor.generate_batch_id("tenant_123")
            >>> print(batch_id)  # e.g., batch_tenant_123_20251225123045_a1b2c3d4
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique_suffix = uuid.uuid4().hex[:8]
        return f"batch_{tenant_id}_{timestamp}_{unique_suffix}"

    def _validate_batch_events(self, events: List[MeterEventData]) -> None:
        """
        Validate event structure for all events in batch.

        Ensures all events have required fields (meter_event, value) with
        correct types before processing begins. Fail-fast approach.

        Args:
            events: List of event dictionaries to validate

        Raises:
            StripeMeterValidationError: If any event is missing required fields
                                       or has invalid types
        """
        validation_errors = []

        for i, event in enumerate(events):
            # Check for required meter_event field
            if "meter_event" not in event:
                validation_errors.append(
                    f"Event at index {i}: Missing required field 'meter_event'"
                )
            else:
                # Validate meter_event is a string
                if not isinstance(event["meter_event"], str):
                    validation_errors.append(
                        f"Event at index {i}: 'meter_event' must be a string, "
                        f"got {type(event['meter_event']).__name__}"
                    )

            # Check for required value field
            if "value" not in event:
                validation_errors.append(
                    f"Event at index {i}: Missing required field 'value'"
                )
            else:
                # Validate value is an integer
                if not isinstance(event["value"], int):
                    validation_errors.append(
                        f"Event at index {i}: 'value' must be an integer, "
                        f"got {type(event['value']).__name__}"
                    )

        if validation_errors:
            raise StripeMeterValidationError(
                f"Batch event validation failed: {'; '.join(validation_errors)}",
                validation_errors=validation_errors
            )

    def _create_failure_info(
        self,
        event_data: str,
        value: int,
        metadata: Dict[str, Any],
        error: Exception
    ) -> Dict[str, Any]:
        """
        Create failure information dictionary for tracking.

        Extracts relevant error details and context for failed events.

        Args:
            event_data: Meter event name
            value: Event value
            metadata: Event metadata
            error: Exception that occurred

        Returns:
            Dictionary with failure information including event details,
            error message, and error type
        """
        failure_info = {
            "event": {
                "meter_event": event_data,
                "value": value,
                "metadata": metadata
            },
            "error": str(error),
            "error_type": type(error).__name__
        }

        # Add specific error details if available
        if hasattr(error, 'validation_errors') and error.validation_errors:
            failure_info["validation_errors"] = error.validation_errors
        if hasattr(error, 'meter_event'):
            failure_info["meter_event"] = error.meter_event

        return failure_info
