"""
Unit tests for RetryService.

This test suite verifies the retry logic implementation following TDD approach.
Tests cover:
- Transient vs permanent error classification
- Exponential backoff with jitter
- Max retry enforcement
- Retry delay calculation

Phase: 2.5.2 (Infrastructure Services)
Task: 2.5.2.2 - Extract retry_service.py with RetryService using TDD
Created: 2025-12-25
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Callable, Awaitable, Any

from src.services.stripe.types import RetryServiceProtocol
from src.services.stripe.config import StripeConfig
from src.services.stripe.retry_service import RetryService
from src.services.stripe.exceptions import StripeAPIError, StripeRateLimitError, StripeServerError


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def retry_config():
    """Provide retry configuration for testing."""
    return StripeConfig(
        max_retries=3,
        initial_retry_delay_ms=1000,
        max_retry_delay_ms=32000,
        retry_backoff_multiplier=2.0,
        jitter_enabled=True
    )


@pytest.fixture
def retry_service(retry_config):
    """Provide RetryService instance for testing."""
    return RetryService(retry_config)


@pytest.fixture
def mock_stripe_rate_limit_error():
    """Create mock Stripe rate limit error (HTTP 429)."""
    class MockRateLimitError(Exception):
        def __init__(self):
            super().__init__("Rate limit exceeded")
            self.http_status = 429
            self.code = "rate_limit"
    return MockRateLimitError()


@pytest.fixture
def mock_stripe_server_error():
    """Create mock Stripe server error (HTTP 500)."""
    class MockServerError(Exception):
        def __init__(self):
            super().__init__("Internal server error")
            self.http_status = 500
            self.code = "api_error"
    return MockServerError()


@pytest.fixture
def mock_stripe_bad_request_error():
    """Create mock Stripe bad request error (HTTP 400)."""
    class MockBadRequestError(Exception):
        def __init__(self):
            super().__init__("Bad request")
            self.http_status = 400
            self.code = "invalid_request_error"
    return MockBadRequestError()


@pytest.fixture
def mock_stripe_unauthorized_error():
    """Create mock Stripe unauthorized error (HTTP 401)."""
    class MockUnauthorizedError(Exception):
        def __init__(self):
            super().__init__("Unauthorized")
            self.http_status = 401
            self.code = "authentication_error"
    return MockUnauthorizedError()


@pytest.fixture
def mock_stripe_not_found_error():
    """Create mock Stripe not found error (HTTP 404)."""
    class MockNotFoundError(Exception):
        def __init__(self):
            super().__init__("Not found")
            self.http_status = 404
            self.code = "invalid_request_error"
    return MockNotFoundError()


# ============================================================================
# Tests: is_transient_error() - Transient Errors (Should Retry)
# ============================================================================

class TestIsTransientErrorTransient:
    """Test that transient errors are correctly identified."""

    def test_rate_limit_error_is_transient(self, retry_service, mock_stripe_rate_limit_error):
        """HTTP 429 (rate limit) should be transient."""
        assert retry_service.is_transient_error(mock_stripe_rate_limit_error) is True

    def test_http_500_is_transient(self, retry_service, mock_stripe_server_error):
        """HTTP 500 (internal server error) should be transient."""
        assert retry_service.is_transient_error(mock_stripe_server_error) is True

    def test_http_502_is_transient(self, retry_service):
        """HTTP 502 (bad gateway) should be transient."""
        error = Mock()
        error.http_status = 502
        assert retry_service.is_transient_error(error) is True

    def test_http_503_is_transient(self, retry_service):
        """HTTP 503 (service unavailable) should be transient."""
        error = Mock()
        error.http_status = 503
        assert retry_service.is_transient_error(error) is True

    def test_http_504_is_transient(self, retry_service):
        """HTTP 504 (gateway timeout) should be transient."""
        error = Mock()
        error.http_status = 504
        assert retry_service.is_transient_error(error) is True


# ============================================================================
# Tests: is_transient_error() - Permanent Errors (Should Not Retry)
# ============================================================================

class TestIsTransientErrorPermanent:
    """Test that permanent errors are correctly identified."""

    def test_bad_request_error_is_not_transient(self, retry_service, mock_stripe_bad_request_error):
        """HTTP 400 (bad request) should not be transient."""
        assert retry_service.is_transient_error(mock_stripe_bad_request_error) is False

    def test_unauthorized_error_is_not_transient(self, retry_service, mock_stripe_unauthorized_error):
        """HTTP 401 (unauthorized) should not be transient."""
        assert retry_service.is_transient_error(mock_stripe_unauthorized_error) is False

    def test_not_found_error_is_not_transient(self, retry_service, mock_stripe_not_found_error):
        """HTTP 404 (not found) should not be transient."""
        assert retry_service.is_transient_error(mock_stripe_not_found_error) is False

    def test_unknown_error_is_not_transient(self, retry_service):
        """Errors without HTTP status should not be transient by default."""
        error = Exception("Unknown error")
        assert retry_service.is_transient_error(error) is False


# ============================================================================
# Tests: _calculate_retry_delay() - Exponential Backoff
# ============================================================================

class TestCalculateRetryDelay:
    """Test exponential backoff delay calculation."""

    def test_initial_attempt_delay(self, retry_service):
        """First retry should use initial delay."""
        delay = retry_service._calculate_retry_delay(attempt=0)
        assert delay == 1000  # initial_retry_delay_ms

    def test_second_retry_doubles_delay(self, retry_service):
        """Second retry should double the delay (2^1 * initial)."""
        delay = retry_service._calculate_retry_delay(attempt=1)
        assert delay == 2000  # 1000 * 2^1

    def test_third_retry_quadruples_delay(self, retry_service):
        """Third retry should quadruple the delay (2^2 * initial)."""
        delay = retry_service._calculate_retry_delay(attempt=2)
        assert delay == 4000  # 1000 * 2^2

    def test_exponential_growth(self, retry_service):
        """Verify exponential backoff growth pattern."""
        delays = [
            retry_service._calculate_retry_delay(attempt=i)
            for i in range(5)
        ]
        assert delays == [1000, 2000, 4000, 8000, 16000]

    def test_max_delay_capping(self, retry_service):
        """Delays should be capped at max_retry_delay_ms."""
        # With initial=1000, multiplier=2, max=32000:
        # Attempt 0: 1000
        # Attempt 1: 2000
        # Attempt 2: 4000
        # Attempt 3: 8000
        # Attempt 4: 16000
        # Attempt 5: 32000 (reaches max)
        # Attempt 6: 32000 (capped at max)
        # Attempt 7: 32000 (capped at max)
        assert retry_service._calculate_retry_delay(attempt=5) == 32000
        assert retry_service._calculate_retry_delay(attempt=6) == 32000
        assert retry_service._calculate_retry_delay(attempt=7) == 32000


# ============================================================================
# Tests: _calculate_retry_delay_with_jitter() - Jitter Addition
# ============================================================================

class TestCalculateRetryDelayWithJitter:
    """Test jitter addition to prevent thundering herd."""

    def test_jitter_adds_randomness(self, retry_service):
        """Jitter should add randomness to the base delay."""
        base_delay = retry_service._calculate_retry_delay(attempt=0)
        jittered_delay = retry_service._calculate_retry_delay_with_jitter(attempt=0)

        # Jittered delay should be different (most of the time)
        # and within reasonable bounds
        assert isinstance(jittered_delay, int)

    def test_jitter_bounds(self, retry_service):
        """Jitter should stay within +/- 50% of base delay."""
        base_delay = retry_service._calculate_retry_delay(attempt=0)
        jittered_delay = retry_service._calculate_retry_delay_with_jitter(attempt=0)

        # Jitter should be within [0.5 * base, 1.5 * base]
        min_delay = int(base_delay * 0.5)
        max_delay = int(base_delay * 1.5)
        assert min_delay <= jittered_delay <= max_delay

    def test_jitter_distribution(self, retry_service):
        """Multiple jitter calls should produce different values."""
        delays = [
            retry_service._calculate_retry_delay_with_jitter(attempt=0)
            for _ in range(100)
        ]

        # Should have variation in delays
        assert len(set(delays)) > 10  # At least 10 unique values out of 100


# ============================================================================
# Tests: execute_with_retry() - Success Cases
# ============================================================================

class TestExecuteWithRetrySuccess:
    """Test execute_with_retry for successful operations."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self, retry_service):
        """Should succeed immediately without retries if no errors."""
        async_func = AsyncMock(return_value="success")

        result = await retry_service.execute_with_retry(
            func=async_func,
            operation_name="test_operation"
        )

        assert result == "success"
        assert async_func.call_count == 1

    @pytest.mark.asyncio
    async def test_passes_arguments_correctly(self, retry_service):
        """Should pass positional and keyword arguments to function."""
        async_func = AsyncMock(return_value="result")

        await retry_service.execute_with_retry(
            async_func,
            "test_operation",
            "arg1",
            "arg2",
            kwarg1="value1",
            kwarg2="value2"
        )

        async_func.assert_called_once_with("arg1", "arg2", kwarg1="value1", kwarg2="value2")

    @pytest.mark.asyncio
    async def test_succeeds_after_transient_error_retries(self, retry_service, mock_stripe_rate_limit_error):
        """Should succeed after retrying transient errors."""
        # Fail twice, then succeed
        async_func = AsyncMock(
            side_effect=[
                mock_stripe_rate_limit_error,
                mock_stripe_rate_limit_error,
                "success"
            ]
        )

        result = await retry_service.execute_with_retry(
            func=async_func,
            operation_name="test_operation"
        )

        assert result == "success"
        assert async_func.call_count == 3


# ============================================================================
# Tests: execute_with_retry() - Transient Error Retries
# ============================================================================

class TestExecuteWithRetryTransientErrors:
    """Test execute_with_retry with transient errors."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit_error(self, retry_service, mock_stripe_rate_limit_error):
        """Should retry on HTTP 429 rate limit errors."""
        async_func = AsyncMock(
            side_effect=[
                mock_stripe_rate_limit_error,
                "success"
            ]
        )

        result = await retry_service.execute_with_retry(
            func=async_func,
            operation_name="test_operation"
        )

        assert result == "success"
        assert async_func.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_server_error(self, retry_service, mock_stripe_server_error):
        """Should retry on HTTP 500 server errors."""
        async_func = AsyncMock(
            side_effect=[
                mock_stripe_server_error,
                "success"
            ]
        )

        result = await retry_service.execute_with_retry(
            func=async_func,
            operation_name="test_operation"
        )

        assert result == "success"
        assert async_func.call_count == 2


# ============================================================================
# Tests: execute_with_retry() - Permanent Error Handling
# ============================================================================

class TestExecuteWithRetryPermanentErrors:
    """Test execute_with_retry with permanent errors."""

    @pytest.mark.asyncio
    async def test_no_retry_on_bad_request(self, retry_service, mock_stripe_bad_request_error):
        """Should NOT retry on HTTP 400 bad request errors."""
        async_func = AsyncMock(side_effect=mock_stripe_bad_request_error)

        with pytest.raises(Exception) as exc_info:
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

        assert async_func.call_count == 1  # No retries
        assert exc_info.value is mock_stripe_bad_request_error

    @pytest.mark.asyncio
    async def test_no_retry_on_unauthorized(self, retry_service, mock_stripe_unauthorized_error):
        """Should NOT retry on HTTP 401 unauthorized errors."""
        async_func = AsyncMock(side_effect=mock_stripe_unauthorized_error)

        with pytest.raises(Exception) as exc_info:
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

        assert async_func.call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_no_retry_on_not_found(self, retry_service, mock_stripe_not_found_error):
        """Should NOT retry on HTTP 404 not found errors."""
        async_func = AsyncMock(side_effect=mock_stripe_not_found_error)

        with pytest.raises(Exception):
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

        assert async_func.call_count == 1  # No retries


# ============================================================================
# Tests: execute_with_retry() - Max Retries Enforcement
# ============================================================================

class TestExecuteWithRetryMaxRetries:
    """Test max retries enforcement."""

    @pytest.mark.asyncio
    async def test_respects_max_retries_limit(self, retry_service, mock_stripe_rate_limit_error):
        """Should not exceed max_retries attempts."""
        # Always fail with transient error
        async_func = AsyncMock(side_effect=mock_stripe_rate_limit_error)

        with pytest.raises(Exception):
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

        # Initial attempt + 3 retries = 4 total attempts
        assert async_func.call_count == 4

    @pytest.mark.asyncio
    async def test_raises_last_exception_after_max_retries(self, retry_service, mock_stripe_rate_limit_error):
        """Should raise the last exception after exhausting retries."""
        async_func = AsyncMock(side_effect=mock_stripe_rate_limit_error)

        with pytest.raises(Exception) as exc_info:
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

        assert exc_info.value is mock_stripe_rate_limit_error


# ============================================================================
# Tests: execute_with_retry() - Delay Between Retries
# ============================================================================

class TestExecuteWithRetryDelays:
    """Test delay timing between retries."""

    @pytest.mark.asyncio
    async def test_waits_between_retries(self, retry_service, mock_stripe_rate_limit_error):
        """Should wait with exponential backoff between retries."""
        async_func = AsyncMock(
            side_effect=[
                mock_stripe_rate_limit_error,
                mock_stripe_rate_limit_error,
                "success"
            ]
        )

        with patch('asyncio.sleep') as mock_sleep:
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

            # Should have slept twice (first retry, second retry)
            assert mock_sleep.call_count == 2

            # Check that delays follow exponential backoff pattern
            first_delay = mock_sleep.call_args_list[0][0][0]
            second_delay = mock_sleep.call_args_list[1][0][0]

            # Second delay should be larger than first
            assert second_delay > first_delay

    @pytest.mark.asyncio
    async def test_applies_jitter_to_delays(self, retry_service, mock_stripe_rate_limit_error):
        """Should apply jitter to retry delays."""
        async_func = AsyncMock(
            side_effect=[
                mock_stripe_rate_limit_error,
                "success"
            ]
        )

        with patch('asyncio.sleep') as mock_sleep:
            await retry_service.execute_with_retry(
                func=async_func,
                operation_name="test_operation"
            )

            # Get the delay argument (convert to ms)
            delay_seconds = mock_sleep.call_args[0][0]
            delay_ms = delay_seconds * 1000

            # Should be jittered around 1000ms (initial delay)
            # Jitter range: [500, 1500]
            assert 0.5 <= delay_seconds <= 1.5


# ============================================================================
# Tests: Protocol Compliance
# ============================================================================

class TestRetryServiceProtocol:
    """Test that RetryService implements RetryServiceProtocol correctly."""

    def test_is_transient_error_signature(self, retry_service):
        """is_transient_error should match protocol signature."""
        # This test ensures the method exists and accepts an Exception
        try:
            retry_service.is_transient_error(Exception("test"))
        except TypeError:
            pytest.fail("is_transient_error has incorrect signature")

    @pytest.mark.asyncio
    async def test_execute_with_retry_signature(self, retry_service):
        """execute_with_retry should match protocol signature."""
        async def test_func(x: int, y: str) -> str:
            return f"{x}:{y}"

        # This test ensures the method accepts the correct arguments
        try:
            result = await retry_service.execute_with_retry(
                test_func,
                "test",
                42,
                "hello"
            )
            assert result == "42:hello"
        except TypeError:
            pytest.fail("execute_with_retry has incorrect signature")

    def test_retry_service_is_protocol_compliant(self, retry_service):
        """RetryService should be compatible with RetryServiceProtocol."""
        # Protocol compliance is checked by verifying all required methods exist
        # with correct signatures. isinstance() requires @runtime_checkable on Protocol.
        assert hasattr(retry_service, 'is_transient_error')
        assert hasattr(retry_service, 'execute_with_retry')
        assert callable(retry_service.is_transient_error)
        assert callable(retry_service.execute_with_retry)


# ============================================================================
# Tests: Configuration
# ============================================================================

class TestRetryServiceConfiguration:
    """Test RetryService configuration handling."""

    def test_uses_config_retry_settings(self):
        """Should use retry settings from configuration."""
        config = StripeConfig(
            max_retries=5,
            initial_retry_delay_ms=2000,
            max_retry_delay_ms=16000,
            retry_backoff_multiplier=3.0,
            jitter_enabled=True
        )

        service = RetryService(config)

        # Test that configuration values are used
        assert service._max_retries == 5
        assert service._initial_delay_ms == 2000
        assert service._max_delay_ms == 16000
        assert service._backoff_multiplier == 3.0

    def test_default_configuration(self):
        """Should work with default StripeConfig."""
        config = StripeConfig()  # Use defaults
        service = RetryService(config)

        # Should have default values
        assert service._max_retries == 5  # Default
        assert service._initial_delay_ms == 1000  # Default
        assert service._max_delay_ms == 32000  # Default
