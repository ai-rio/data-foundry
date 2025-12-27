"""
Meter Event Service for Stripe meter event reporting.

This module provides the core domain service for reporting meter events to Stripe
for usage-based billing. It coordinates validation, idempotency, retry logic,
and Stripe API calls.

Task: P02-532 (Domain Layer - Meter Event Service)
Created: 2025-12-25

Security Features:
- Input validation via ValidationService
- Idempotency guarantees via IdempotencyService
- Retry logic with exponential backoff via RetryService
- Rich error context in MeterEventResult

Business Logic:
- Meter event validation (name and value)
- Idempotency key generation and registration
- Stripe API calls with retry
- Metadata sanitization and handling
"""

import logging
from typing import Dict, Any, Optional


# Import types and protocols
from .types import (
    MeterEventServiceProtocol,
    MeterEventResult,
    MeterType,
)
from .config import StripeConfig
from .exceptions import (
    StripeMeterValidationError,
    StripeAPIError,
)
from .validation import ValidationService
from .idempotency_service import IdempotencyService
from .retry_service import RetryService


logger = logging.getLogger(__name__)


class MeterEventService(MeterEventServiceProtocol):
    """
    Service for reporting meter events to Stripe.

    This service implements the MeterEventServiceProtocol and provides:
    - Meter event validation (name and value)
    - Idempotency key generation and registration
    - Stripe API calls with retry logic
    - Metadata sanitization and handling
    - Rich error context in results

    The service coordinates multiple infrastructure services:
    - ValidationService: Input validation and sanitization
    - IdempotencyService: Idempotency key management
    - RetryService: Retry logic with exponential backoff
    - Stripe Client: Actual Stripe API calls

    Attributes:
        config: StripeConfig instance with meter configuration
        validation_service: ValidationService for input validation
        idempotency_service: IdempotencyService for key management
        retry_service: RetryService for retry logic
        stripe_client: Stripe client for API calls

    Example:
        >>> config = StripeConfig.from_environment()
        >>> validation_service = ValidationService(config)
        >>> idempotency_service = IdempotencyService(config)
        >>> retry_service = RetryService(config)
        >>> meter_service = MeterEventService(
        ...     config,
        ...     validation_service,
        ...     idempotency_service,
        ...     retry_service,
        ...     stripe_client
        ... )
        >>> result = await meter_service.report_usage(
        ...     meter_event="ai_labels",
        ...     value=100,
        ...     tenant_id="tenant_123"
        ... )
    """

    def __init__(
        self,
        config: StripeConfig,
        validation_service: ValidationService,
        idempotency_service: IdempotencyService,
        retry_service: RetryService,
        stripe_client: Any,
    ):
        """
        Initialize MeterEventService with dependencies.

        Args:
            config: StripeConfig instance with meter configuration
            validation_service: ValidationService for input validation
            idempotency_service: IdempotencyService for key management
            retry_service: RetryService for retry logic
            stripe_client: Stripe client for API calls
        """
        self.config = config
        self._validation_service = validation_service
        self._idempotency_service = idempotency_service
        self._retry_service = retry_service
        self._stripe_client = stripe_client

    async def report_usage(
        self,
        meter_event: str,
        value: int,
        tenant_id: str,
        metadata: Optional[Dict[str, str]] = None,
        stripe_customer_id: Optional[str] = None,
        batch_id: Optional[str] = None
    ) -> MeterEventResult:
        """
        Report a single meter event to Stripe.

        This method performs the following steps:
        1. Validates meter event name and value
        2. Generates idempotency key
        3. Sanitizes metadata if provided
        4. Calls Stripe API with retry logic
        5. Registers idempotency key
        6. Returns rich result with event details

        Args:
            meter_event: Meter event name (e.g., "ai_labels", "human_audits")
            value: Event value/quantity (positive integer)
            tenant_id: Tenant identifier
            metadata: Optional metadata dictionary
            stripe_customer_id: Optional Stripe customer ID
            batch_id: Optional batch identifier for batch operations

        Returns:
            MeterEventResult with submission status and details

        Raises:
            StripeMeterValidationError: If validation fails
            StripeAPIError: If Stripe API call fails

        Example:
            >>> result = await service.report_usage(
            ...     meter_event="ai_labels",
            ...     value=100,
            ...     tenant_id="tenant_123",
            ...     metadata={"source": "api"}
            ... )
            >>> print(result["event_id"])
            >>> print(result["status"])
        """
        # Step 1: Validate meter event
        validation_errors = self._validation_service.validate_meter_event(
            meter_event, value
        )
        if validation_errors:
            raise StripeMeterValidationError(
                f"Meter event validation failed: {'; '.join(validation_errors)}",
                meter_event=meter_event,
                validation_errors=validation_errors
            )

        # Step 2: Generate idempotency key
        idempotency_key = self._idempotency_service.generate_key(
            tenant_id=tenant_id,
            meter_event=meter_event,
            value=value,
            batch_id=batch_id
        )

        # Step 3: Sanitize metadata if provided
        sanitized_metadata = None
        if metadata is not None:
            sanitized_metadata = self._validation_service.sanitize_metadata(metadata)

        # Step 4: Prepare Stripe API call
        def _create_stripe_meter_event():
            """Internal function that makes the actual Stripe API call."""
            # Get meter ID for this event type
            meter_id = self._get_meter_id(meter_event)

            # Prepare payload
            payload = {
                "value": str(value),
            }

            # Add optional fields
            if stripe_customer_id:
                payload["stripe_customer_id"] = stripe_customer_id

            if batch_id:
                payload["batch_id"] = batch_id

            if sanitized_metadata:
                payload.update(sanitized_metadata)

            # Make API call
            return self._stripe_client.create_meter_event(
                event_name=meter_event,
                payload=payload,
                idempotency_key=idempotency_key,
            )

        # Step 5: Execute with retry logic
        stripe_response = await self._retry_service.execute_with_retry(
            func=_create_stripe_meter_event,
            operation_name=f"report_meter_event_{meter_event}"
        )

        # Step 6: Register idempotency key
        self._idempotency_service.register_key(idempotency_key)

        # Step 7: Return result
        return MeterEventResult(
            event_id=idempotency_key,
            status="succeeded",
            stripe_response=stripe_response,
            meter_event=meter_event,
            value=value
        )

    def _get_meter_id(self, meter_event: str) -> str:
        """
        Get Stripe meter ID for a meter event.

        Args:
            meter_event: Meter event name

        Returns:
            Meter ID string

        Raises:
            StripeMeterValidationError: If meter ID not configured
        """
        meter_id = self.config.get_meter_id(MeterType(meter_event))

        if not meter_id:
            raise StripeMeterValidationError(
                f"Meter ID not configured for event '{meter_event}'. "
                f"Please set STRIPE_{meter_event.upper()}_METER_ID environment variable.",
                meter_event=meter_event
            )

        return meter_id
