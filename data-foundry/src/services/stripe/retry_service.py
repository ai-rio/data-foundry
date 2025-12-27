"""
Retry service with exponential backoff for transient failures.

This module implements the retry logic used by Stripe service operations.
It classifies errors as transient or permanent and applies exponential
backoff with jitter to prevent thundering herd problems.

Phase: 2.5.2 (Infrastructure Services)
Task: 2.5.2.2 - Extract retry_service.py with RetryService using TDD
Created: 2025-12-25

Security Considerations:
- Jitter prevents synchronized retry storms (DoS protection)
- Max retry limits prevent infinite retry loops
- Transient error classification prevents retrying permanent failures
"""

import asyncio
import logging
import random
from typing import Callable, Awaitable, Any

from src.services.stripe.types import RetryServiceProtocol
from src.services.stripe.config import StripeConfig


logger = logging.getLogger(__name__)


class RetryService(RetryServiceProtocol):
    """
    Service for executing operations with automatic retry and exponential backoff.

    This service implements the RetryServiceProtocol and provides:
    - Error classification (transient vs permanent)
    - Exponential backoff with jitter
    - Configurable retry limits and delays

    Transient errors (retried):
        - HTTP 429: Rate limit errors
        - HTTP 5xx: Server errors (500, 502, 503, 504)

    Permanent errors (not retried):
        - HTTP 400: Bad request
        - HTTP 401: Unauthorized
        - HTTP 404: Not found

    Example:
        >>> config = StripeConfig()
        >>> retry_service = RetryService(config)
        >>> result = await retry_service.execute_with_retry(
        ...     func=stripe_api_call,
        ...     operation_name="create_customer",
        ...     email="test@example.com"
        ... )
    """

    def __init__(self, config: StripeConfig):
        """
        Initialize RetryService with configuration.

        Args:
            config: StripeConfig instance with retry settings
        """
        self._max_retries = config.max_retries
        self._initial_delay_ms = config.initial_retry_delay_ms
        self._max_delay_ms = config.max_retry_delay_ms
        self._backoff_multiplier = config.retry_backoff_multiplier
        self._jitter_enabled = config.jitter_enabled

    def is_transient_error(self, error: Exception) -> bool:
        """
        Determine if an error is transient (should retry) or permanent (should not retry).

        Transient errors (retry):
        - HTTP 429: Rate limit errors
        - HTTP 500: Internal server errors
        - HTTP 502: Bad gateway
        - HTTP 503: Service unavailable
        - HTTP 504: Gateway timeout

        Permanent errors (no retry):
        - HTTP 400: Bad request
        - HTTP 401: Unauthorized
        - HTTP 404: Not found

        Args:
            error: Exception to classify

        Returns:
            True if error is transient (should retry), False otherwise
        """
        # Check if it's a Stripe error with HTTP status code
        if hasattr(error, 'http_status'):
            status_code = error.http_status

            # Retry on rate limits and server errors
            if status_code in [429, 500, 502, 503, 504]:
                return True

            # Don't retry on client errors
            if status_code in [400, 401, 404]:
                return False

        # Check for specific Stripe SDK error types
        try:
            import stripe.error

            if isinstance(error, stripe.error.RateLimitError):
                return True
            if isinstance(error, stripe.error.APIError):
                # APIError can be transient - check HTTP status if available
                if hasattr(error, 'http_status'):
                    return error.http_status in [429, 500, 502, 503, 504]
                # Assume APIError is transient if no status code
                return True
            if isinstance(error, (
                stripe.error.InvalidRequestError,
                stripe.error.AuthenticationError,
                stripe.error.PermissionError
            )):
                # Client errors - don't retry
                return False
        except ImportError:
            # Stripe SDK not available - skip Stripe-specific checks
            pass

        # Default: don't retry on unknown errors
        return False

    def _calculate_retry_delay(self, attempt: int) -> int:
        """
        Calculate exponential backoff delay for retry attempt.

        Implements exponential backoff: delay = initial * (multiplier ^ attempt)
        Delays are capped at max_delay_ms to prevent excessive wait times.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in milliseconds

        Example:
            >>> service = RetryService(StripeConfig())
            >>> service._calculate_retry_delay(0)  # First retry
            1000
            >>> service._calculate_retry_delay(1)  # Second retry
            2000
            >>> service._calculate_retry_delay(2)  # Third retry
            4000
        """
        # Calculate exponential backoff
        delay_ms = self._initial_delay_ms * (self._backoff_multiplier ** attempt)

        # Cap at max delay
        return int(min(delay_ms, self._max_delay_ms))

    def _calculate_retry_delay_with_jitter(self, attempt: int) -> int:
        """
        Calculate backoff delay with random jitter to prevent thundering herd.

        Adds jitter to distribute retry attempts across time and prevent
        synchronized retry storms when multiple clients experience errors.

        Jitter range: +/- 50% of base delay
        Formula: delay * (0.5 + random() * 0.5)

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Delay in milliseconds with jitter applied

        Example:
            >>> service = RetryService(StripeConfig())
            >>> # Will return value between 500ms and 1500ms for attempt 0
            >>> delay = service._calculate_retry_delay_with_jitter(0)
        """
        base_delay = self._calculate_retry_delay(attempt)

        if self._jitter_enabled:
            # Add jitter: delay * (0.5 + random * 0.5)
            # This gives us [0.5 * base, 1.5 * base]
            jittered_delay = base_delay * (0.5 + random.random() * 0.5)
            return int(jittered_delay)

        return base_delay

    async def execute_with_retry(
        self,
        func: Callable[..., Awaitable[Any]],
        operation_name: str,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic and exponential backoff.

        Wraps async function calls with automatic retry on transient failures.
        Implements exponential backoff with jitter to prevent thundering herd.

        Args:
            func: Async function to execute (will be retried on transient errors)
            operation_name: Human-readable operation name for logging
            *args: Positional arguments to pass to func
            **kwargs: Keyword arguments to pass to func

        Returns:
            Result from func on success

        Raises:
            Exception: The last exception encountered after all retries exhausted

        Example:
            >>> result = await retry_service.execute_with_retry(
            ...     func=stripe.Customer.create,
            ...     operation_name="create_customer",
            ...     email="test@example.com"
            ... )
        """
        last_exception = None

        for attempt in range(self._max_retries + 1):  # +1 for initial attempt
            try:
                # Attempt the operation
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    # Handle sync functions too
                    result = func(*args, **kwargs)

                # Success - return result
                if attempt > 0:
                    logger.info(
                        f"{operation_name} succeeded after {attempt} retries"
                    )
                return result

            except Exception as e:
                last_exception = e

                # Check if error is transient (should retry)
                if not self.is_transient_error(e):
                    # Permanent error - don't retry
                    logger.error(
                        f"{operation_name} failed with permanent error: {e}"
                    )
                    raise

                # Transient error - check if we should retry
                if attempt < self._max_retries:
                    # Calculate backoff delay with jitter
                    delay_ms = self._calculate_retry_delay_with_jitter(attempt)
                    delay_sec = delay_ms / 1000.0

                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self._max_retries + 1}): {e}. "
                        f"Retrying in {delay_ms:.0f}ms..."
                    )

                    # Sleep before retry (async to avoid blocking event loop)
                    await asyncio.sleep(delay_sec)
                else:
                    # Max retries exhausted
                    logger.error(
                        f"{operation_name} failed after {self._max_retries} retries: {e}"
                    )
                    raise

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
