"""
Unit tests for LiteLLM Service.

These tests use mocking to validate core logic without making real API calls.
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime
from decimal import Decimal

from src.services.litellm_service import (
    LiteLLMService,
    LiteLLMError,
    LiteLLMResponse
)
from src.core.config import settings


@pytest.mark.unit
class TestLiteLLMService:
    """Unit tests for LiteLLM Service."""

    @pytest_asyncio.fixture
    async def service(self):
        """Create LiteLLM service instance."""
        service = LiteLLMService()

        # Mock dependencies
        service.redis_client = AsyncMock()
        service.cost_service = AsyncMock()

        await service.initialize()
        return service

    @pytest_asyncio.fixture
    def mock_litellm_response(self):
        """Mock LiteLLM response object."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Test response"))
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15
        )
        mock_response.model_dump.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15
        }
        return mock_response

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test service initialization."""
        with patch('src.services.litellm_service.litellm') as mock_litellm:
            service = LiteLLMService()

            # Should configure LiteLLM
            assert mock_litellm.set_verbose == settings.LITELLM_LOGGING
            assert mock_litellm.cache == settings.LITELLM_CACHE_TTL
            assert mock_litellm.request_timeout == settings.LITELLM_REQUEST_TIMEOUT

    @pytest.mark.asyncio
    async def test_completion_success(self, service, mock_litellm_response):
        """Test successful completion."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response

            # Mock cost calculation
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            response = await service.completion(
                prompt="Test prompt",
                model="gpt-4o",
                tenant_id="test_tenant"
            )

            assert isinstance(response, LiteLLMResponse)
            assert response.content == "Test response"
            assert response.model == "gpt-4o"
            assert response.provider == "openai"
            assert response.usage["total_tokens"] == 15
            assert response.cost == Decimal("0.001")
            assert response.fallback_used is False
            assert response.retry_count == 0

            # Verify LiteLLM was called correctly
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            assert call_args["model"] == "gpt-4o"
            assert call_args["messages"][0]["content"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_completion_with_system_prompt(self, service, mock_litellm_response):
        """Test completion with system prompt."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            await service.completion(
                prompt="User prompt",
                system_prompt="System prompt",
                model="gpt-4o",
                tenant_id="test_tenant"
            )

            # Verify both prompts were included
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            messages = call_args["messages"]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "System prompt"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "User prompt"

    @pytest.mark.asyncio
    async def test_completion_with_messages(self, service, mock_litellm_response):
        """Test completion with pre-defined messages."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            messages = [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "User"},
                {"role": "assistant", "content": "Assistant"},
                {"role": "user", "content": "New user message"}
            ]

            await service.completion(
                messages=messages,
                model="gpt-4o",
                tenant_id="test_tenant"
            )

            # Verify messages were passed through
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            assert call_args["messages"] == messages

    @pytest.mark.asyncio
    async def test_completion_with_json_format(self, service, mock_litellm_response):
        """Test completion with JSON response format."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            await service.completion(
                prompt="Generate JSON",
                response_format="json",
                model="gpt-4o",
                tenant_id="test_tenant"
            )

            # Verify JSON format was requested
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            assert call_args["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, service, mock_litellm_response):
        """Test fallback when primary model fails."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            # Primary model fails, fallback succeeds
            mock_acompletion.side_effect = [
                Exception("Primary model error"),
                mock_litellm_response
            ]
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            response = await service.completion(
                prompt="Test fallback",
                model="gpt-4o",
                tenant_id="test_tenant",
                max_retries=1
            )

            assert response.fallback_used is True

            # Should have called twice (primary + fallback)
            assert mock_acompletion.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_retryable_error(self, service, mock_litellm_response):
        """Test retry on retryable errors."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            # First two attempts fail with retryable errors
            mock_acompletion.side_effect = [
                Exception("rate_limit_error"),
                Exception("timeout_error"),
                mock_litellm_response
            ]
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            response = await service.completion(
                prompt="Test retry",
                model="gpt-4o",
                tenant_id="test_tenant",
                max_retries=3
            )

            assert response.retry_count == 2
            assert mock_acompletion.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self, service):
        """Test no retry on non-retryable errors."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            # Non-retryable error
            mock_acompletion.side_effect = Exception("invalid_api_key")

            with pytest.raises(LiteLLMError):
                await service.completion(
                    prompt="Test no retry",
                    model="gpt-4o",
                    tenant_id="test_tenant",
                    max_retries=3
                )

            # Should only call once
            assert mock_acompletion.call_count == 1

    @pytest.mark.asyncio
    async def test_all_models_fail(self, service):
        """Test handling when all models fail."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.side_effect = Exception("All models down")

            with pytest.raises(LiteLLMError) as exc_info:
                await service.completion(
                    prompt="Test all fail",
                    tenant_id="test_tenant",
                    max_retries=1
                )

            assert "All models failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cache_hit(self, service):
        """Test retrieving response from cache."""
        # Mock cached response
        cached_data = {
            "content": "Cached response",
            "model": "gpt-4o",
            "provider": "openai",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "cost": "0.001",
            "response_time_ms": 500,
            "metadata": {},
            "fallback_used": False,
            "retry_count": 0
        }

        service.redis_client.get.return_value = json.dumps(cached_data)

        response = await service.completion(
            prompt="Cached prompt",
            model="gpt-4o",
            tenant_id="test_tenant",
            use_cache=True
        )

        assert response.cached is True
        assert response.content == "Cached response"

        # Should not have made API call
        service.redis_client.get.assert_called_once()
        service.redis_client.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_and_store(self, service, mock_litellm_response):
        """Test cache miss and storing response."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            # No cached response
            service.redis_client.get.return_value = None
            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            await service.completion(
                prompt="Cache miss",
                model="gpt-4o",
                tenant_id="test_tenant",
                use_cache=True,
                cache_ttl=3600
            )

            # Should have checked cache
            service.redis_client.get.assert_called_once()

            # Should have stored response
            service.redis_client.setex.assert_called_once()
            cache_args = service.redis_client.setex.call_args[0]
            assert cache_args[1] == 3600  # TTL
            cached_data = json.loads(cache_args[2])
            assert cached_data["content"] == "Test response"

    @pytest.mark.asyncio
    async def test_rate_limiting(self, service, mock_litellm_response):
        """Test rate limiting functionality."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            # Set low rate limit for testing
            service._max_requests_per_minute = 2

            # Make 3 requests quickly
            await service.completion(prompt="1", tenant_id="rate_test")
            await service.completion(prompt="2", tenant_id="rate_test")
            await service.completion(prompt="3", tenant_id="rate_test")

            # Should have slept due to rate limit
            mock_sleep.assert_called_once()
            sleep_arg = mock_sleep.call_args[0][0]
            assert sleep_arg == 60  # Sleep for 1 minute

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, service, mock_litellm_response):
        """Test metrics are tracked correctly."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            # Reset metrics
            await service.reset_metrics()

            # Make some requests
            await service.completion(prompt="1", tenant_id="test")
            await service.completion(prompt="2", tenant_id="test")

            metrics = await service.get_metrics()

            assert metrics["requests_total"] == 2
            assert metrics["requests_success"] == 2
            assert metrics["total_tokens"] == 30  # 15 * 2
            assert metrics["total_cost"] == Decimal("0.002")  # 0.001 * 2

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        """Test health check functionality."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            # Mock healthy response
            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(message=MagicMock(content="OK"))
            ]
            mock_acompletion.return_value = mock_response

            health = await service.health_check()

            assert "healthy" in health
            assert "models" in health
            assert "timestamp" in health

            # Should check each model
            for model in service.all_models[:3]:  # Only checks first 3
                assert model in health["models"]
                model_health = health["models"][model]
                assert "status" in model_health
                assert "provider" in model_health

    @pytest.mark.asyncio
    async def test_provider_mapping(self, service):
        """Test model to provider mapping."""
        assert service._get_provider_for_model("gpt-4o") == "openai"
        assert service._get_provider_for_model("claude-3-5-sonnet") == "anthropic"
        assert service._get_provider_for_model("gemini-pro") == "google"
        assert service._get_provider_for_model("unknown-model") == "unknown"

    @pytest.mark.asyncio
    async def test_retry_delay_calculation(self, service):
        """Test exponential backoff delay calculation."""
        delay1 = service._calculate_retry_delay(1)
        delay2 = service._calculate_retry_delay(2)
        delay3 = service._calculate_retry_delay(3)

        # Should increase exponentially
        assert delay2 > delay1
        assert delay3 > delay2

        # Should not exceed max delay
        assert delay1 <= service._retry_config["max_delay"]
        assert delay2 <= service._retry_config["max_delay"]
        assert delay3 <= service._retry_config["max_delay"]

    @pytest.mark.asyncio
    async def test_cache_key_generation(self, service):
        """Test cache key generation is deterministic."""
        messages = [{"role": "user", "content": "Test"}]

        key1 = service._generate_cache_key("gpt-4o", messages, 0.7, 100)
        key2 = service._generate_cache_key("gpt-4o", messages, 0.7, 100)

        # Same parameters should generate same key
        assert key1 == key2

        # Different parameters should generate different keys
        key3 = service._generate_cache_key("gpt-4o", messages, 0.8, 100)
        key4 = service._generate_cache_key("claude-3-5-sonnet", messages, 0.7, 100)

        assert key1 != key3
        assert key1 != key4
        assert key3 != key4

    @pytest.mark.asyncio
    async def test_audit_log_creation(self, service):
        """Test audit log creation."""
        with patch('src.services.litellm_service.logger') as mock_logger:
            await service._create_audit_log(
                tenant_id="test_tenant",
                operation="completion",
                model="gpt-4o",
                success=True,
                usage={"total_tokens": 100},
                cost=Decimal("0.001"),
                duration_ms=500,
                metadata={"test": True}
            )

            # Should have logged audit entry
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args[0][0]

            # Parse JSON from log message
            log_data = json.loads(log_call.split("Audit log: ")[1])

            assert log_data["tenant_id"] == "test_tenant"
            assert log_data["operation"] == "completion"
            assert log_data["model"] == "gpt-4o"
            assert log_data["success"] is True
            assert log_data["usage"]["total_tokens"] == 100
            assert log_data["cost"] == "0.001"
            assert log_data["duration_ms"] == 500
            assert log_data["metadata"]["test"] is True

    @pytest.mark.asyncio
    async def test_completion_with_max_tokens(self, service, mock_litellm_response):
        """Test completion with max_tokens parameter."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            await service.completion(
                prompt="Test",
                model="gpt-4o",
                max_tokens=50,
                tenant_id="test"
            )

            # Verify max_tokens was passed
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            assert call_args["max_tokens"] == 50

    @pytest.mark.asyncio
    async def test_completion_with_temperature(self, service, mock_litellm_response):
        """Test completion with temperature parameter."""
        with patch('src.services.litellm_service.acompletion',
                  new_callable=AsyncMock) as mock_acompletion:

            mock_acompletion.return_value = mock_litellm_response
            service.cost_service.calculate_cost.return_value = Decimal("0.001")

            await service.completion(
                prompt="Test",
                model="gpt-4o",
                temperature=0.9,
                tenant_id="test"
            )

            # Verify temperature was passed
            mock_acompletion.assert_called_once()
            call_args = mock_acompletion.call_args[1]
            assert call_args["temperature"] == 0.9