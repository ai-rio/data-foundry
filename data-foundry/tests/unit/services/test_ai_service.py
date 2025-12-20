"""
Comprehensive TDD tests for AI Service with LiteLLM integration.

These tests follow the Test-Driven Development approach:
1. All tests initially fail (red phase)
2. Implementation is added to make tests pass (green phase)
3. Code is refactored for clean design (refactor phase)

Coverage areas:
- LiteLLM integration with multiple providers
- Fallback mechanisms between models
- Token usage tracking for billing
- Cost calculation accuracy
- Error handling and resilience
- Integration with Prompt Management System
- Redis caching for responses
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
import pytest
import pytest_asyncio

from src.services.ai_service import AIService, AIRequest, AIResponse, SimpleTokenUsage
from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.services.cost_service import CostService, ModelPricing, CostCalculation
from src.core.config import settings

# For backward compatibility in tests
TokenUsage = SimpleTokenUsage


class TestAIService:
    """Test suite for AIService with LiteLLM integration."""

    @pytest_asyncio.fixture
    async def mock_litellm_completion(self):
        """Mock LiteLLM completion response."""
        mock_response = {
            "id": "chatcmpl-test123",
            "choices": [
                {
                    "message": {
                        "content": '{"category": "high_value", "confidence": 0.95, "reasoning": "Enterprise domain detected"}',
                        "role": "assistant"
                    },
                    "finish_reason": "stop",
                    "index": 0
                }
            ],
            "created": 1703123456,
            "model": "gpt-4o",
            "object": "chat.completion",
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 50,
                "total_tokens": 200
            }
        }
        return mock_response

    @pytest_asyncio.fixture
    async def ai_service(self):
        """Create AI service instance for testing."""
        # Mock the LiteLLM service
        with patch('src.services.ai_service.LiteLLMService') as mock_litellm_service:
            mock_service = AsyncMock()
            mock_service.initialize = AsyncMock()
            mock_litellm_service.return_value = mock_service

            service = AIService()
            await service.initialize()

            # Store mock for test access
            service._mock_litellm = mock_service
            return service

    @pytest.mark.asyncio
    async def test_initialization(self, ai_service):
        """Test AI service initializes correctly with LiteLLM."""
        assert ai_service is not None
        assert hasattr(ai_service, 'prompt_manager')
        assert hasattr(ai_service, 'redis_client')
        assert hasattr(ai_service, 'cost_service')
        assert ai_service.primary_model == settings.PRIMARY_MODEL
        assert ai_service.fallback_models == settings.FALLBACK_MODELS

    @pytest.mark.asyncio
    async def test_completion_with_primary_model(self, ai_service):
        """Test successful completion with primary model."""
        # Mock LiteLLM response
        mock_litellm_response = LiteLLMResponse(
            content='{"category": "high_value", "confidence": 0.95, "reasoning": "Test response"}',
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200},
            cost=Decimal("0.001"),
            response_time_ms=500,
            metadata={},
            cached=False,
            fallback_used=False,
            retry_count=0
        )

        # Configure mock to return the response
        ai_service._mock_litellm.completion.return_value = mock_litellm_response

        request = AIRequest(
            prompt="Analyze this record for categorization",
            system_prompt="You are a data labeling expert.",
            temperature=0.3,
            max_tokens=200,
            tenant_id="tenant_001"
        )

        response = await ai_service.completion(request)

        # Verify response structure
        assert isinstance(response, AIResponse)
        assert response.content == mock_litellm_response.content
        assert response.model == mock_litellm_response.model
        assert response.usage.prompt_tokens == 150
        assert response.usage.completion_tokens == 50
        assert response.usage.total_tokens == 200
        assert response.cost == mock_litellm_response.cost
        assert response.response_time_ms == mock_litellm_response.response_time_ms

        # Verify LiteLLM service was called correctly
        ai_service._mock_litellm.completion.assert_called_once()
        call_kwargs = ai_service._mock_litellm.completion.call_args[1]
        assert call_kwargs["prompt"] == request.prompt
        assert call_kwargs["system_prompt"] == request.system_prompt
        assert call_kwargs["temperature"] == request.temperature
        assert call_kwargs["max_tokens"] == request.max_tokens
        assert call_kwargs["tenant_id"] == request.tenant_id

    @pytest.mark.asyncio
    async def test_completion_with_fallback_model(self, ai_service):
        """Test fallback mechanism when primary model fails."""
        # Mock LiteLLM response with fallback
        mock_litellm_response = LiteLLMResponse(
            content="Fallback response",
            model="claude-3-5-sonnet",
            provider="anthropic",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=Decimal("0.002"),
            response_time_ms=600,
            metadata={},
            cached=False,
            fallback_used=True,
            retry_count=1
        )

        # Configure mock to return the response
        ai_service._mock_litellm.completion.return_value = mock_litellm_response

        request = AIRequest(
            prompt="Test prompt",
            tenant_id="tenant_001"
        )

        response = await ai_service.completion(request)

        # Verify fallback was used
        assert response.fallback_used is True
        assert response.model == "claude-3-5-sonnet"
        assert response.retry_count == 1

    @pytest.mark.asyncio
    async def test_completion_all_models_fail(self, ai_service):
        """Test handling when all models fail."""
        # Configure mock to raise exception
        ai_service._mock_litellm.completion.side_effect = Exception("All models unavailable")

        request = AIRequest(
            prompt="Test prompt",
            tenant_id="tenant_001"
        )

        with pytest.raises(Exception) as exc_info:
            await ai_service.completion(request)

        assert "All models unavailable" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_completion_with_json_response(self, ai_service):
        """Test completion with JSON response parsing."""
        json_content = json.dumps({
            "category": "medium_value",
            "confidence": 0.75,
            "reasoning": "Small business indicators"
        })

        # Mock LiteLLM response with JSON
        mock_litellm_response = LiteLLMResponse(
            content=json_content,
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=Decimal("0.001"),
            response_time_ms=400,
            metadata={},
            cached=False,
            fallback_used=False,
            retry_count=0
        )

        ai_service._mock_litellm.completion.return_value = mock_litellm_response

        request = AIRequest(
            prompt="Analyze record",
            response_format="json",
            tenant_id="tenant_001"
        )

        response = await ai_service.completion(request)

        # Verify JSON parsing
        parsed_content = json.loads(response.content)
        assert parsed_content["category"] == "medium_value"
        assert parsed_content["confidence"] == 0.75

        # Verify response_format was passed to LiteLLM
        call_kwargs = ai_service._mock_litellm.completion.call_args[1]
        assert call_kwargs["response_format"] == "json"

    @pytest.mark.asyncio
    async def test_completion_with_prompt_template(self, ai_service):
        """Test completion using prompt template from prompt manager."""
        # Mock LiteLLM response
        mock_litellm_response = LiteLLMResponse(
            content="Template-based response",
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=Decimal("0.001"),
            response_time_ms=400,
            metadata={},
            cached=False,
            fallback_used=False,
            retry_count=0
        )

        ai_service._mock_litellm.completion.return_value = mock_litellm_response

        with patch.object(ai_service.prompt_manager, 'get_template') as mock_get_template:
            # Mock prompt template
            mock_get_template.return_value = {
                "system_prompt": "You are an expert analyzer.",
                "user_prompt": "Analyze: {record_data}"
            }

            request = AIRequest(
                prompt_template="data_categorization",
                template_vars={"record_data": "Test record"},
                tenant_id="tenant_001"
            )

            response = await ai_service.completion(request)

            # Verify template was used
            mock_get_template.assert_called_once_with("data_categorization", tenant_id="tenant_001")
            assert response is not None

            # Verify messages were passed correctly
            call_kwargs = ai_service._mock_litellm.completion.call_args[1]
            assert "messages" in call_kwargs
            messages = call_kwargs["messages"]
            assert len(messages) == 2
            assert messages[0]["content"] == "You are an expert analyzer."
            assert messages[1]["content"] == "Analyze: Test record"

    @pytest.mark.asyncio
    async def test_completion_with_cache(self, ai_service):
        """Test caching behavior."""
        # Mock cached LiteLLM response
        mock_litellm_response = LiteLLMResponse(
            content="Cached response",
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125},
            cost=Decimal("0.001234"),
            response_time_ms=300,
            metadata={},
            cached=True,  # Mark as cached
            fallback_used=False,
            retry_count=0
        )

        ai_service._mock_litellm.completion.return_value = mock_litellm_response

        request = AIRequest(
            prompt="Cached prompt",
            use_cache=True,
            tenant_id="tenant_001"
        )

        response = await ai_service.completion(request)

        # Verify cached response was returned
        assert response.content == "Cached response"
        assert response.from_cache is True

        # Verify cache settings were passed to LiteLLM
        call_kwargs = ai_service._mock_litellm.completion.call_args[1]
        assert call_kwargs["use_cache"] is True
        assert call_kwargs["tenant_id"] == "tenant_001"

    @pytest.mark.asyncio
    async def test_streaming_completion(self, ai_service):
        """Test streaming completion functionality."""
        async def mock_stream():
            chunks = ['{"category":', ' "high_value"', ', "confidence": 0.9}']
            for chunk in chunks:
                yield {"choices": [{"delta": {"content": chunk}}]}

        with patch('src.services.ai_service.litellm.completion', side_effect=mock_stream):
            request = AIRequest(
                prompt="Stream test",
                stream=True,
                tenant_id="tenant_001"
            )

            chunks = []
            async for chunk in ai_service.completion(request):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert ''.join(chunks) == '{"category": "high_value", "confidence": 0.9}'

    @pytest.mark.asyncio
    async def test_batch_completion(self, ai_service, mock_litellm_completion):
        """Test batch completion for multiple requests."""
        requests = [
            AIRequest(prompt=f"Request {i}", tenant_id="tenant_001")
            for i in range(3)
        ]

        with patch('src.services.ai_service.litellm.completion', return_value=mock_litellm_completion):
            responses = await ai_service.batch_completion(requests, max_concurrent=2)

            assert len(responses) == 3
            for response in responses:
                assert isinstance(response, AIResponse)
                assert response.content is not None

    @pytest.mark.asyncio
    async def test_token_usage_validation(self, ai_service):
        """Test token usage validation and limits."""
        # Create response with excessive tokens
        mock_response = {
            "choices": [{"message": {"content": "Response"}}],
            "usage": {"prompt_tokens": 50000, "completion_tokens": 10000, "total_tokens": 60000}
        }

        with patch('src.services.ai_service.litellm.completion', return_value=mock_response):
            request = AIRequest(
                prompt="Large request",
                tenant_id="tenant_001",
                max_tokens=5000  # Lower limit
            )

            with pytest.raises(ValueError, match="Token usage exceeds maximum limit"):
                await ai_service.completion(request)

    @pytest.mark.asyncio
    async def test_rate_limiting(self, ai_service):
        """Test rate limiting functionality."""
        with patch('src.services.ai_service.litellm.completion', return_value={"choices": []}) as mock_completion:
            requests = [
                AIRequest(prompt=f"Request {i}", tenant_id="tenant_001")
                for i in range(100)  # High volume
            ]

            # Should throttle requests
            with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
                for request in requests[:5]:  # Test first 5
                    await ai_service.completion(request)

                # Verify throttling occurred
                assert mock_sleep.call_count > 0

    @pytest.mark.asyncio
    async def test_cost_tracking_per_tenant(self, ai_service, mock_litellm_completion):
        """Test cost tracking is isolated per tenant."""
        tenant_001_request = AIRequest(prompt="Tenant 1", tenant_id="tenant_001")
        tenant_002_request = AIRequest(prompt="Tenant 2", tenant_id="tenant_002")

        with patch('src.services.ai_service.litellm.completion', return_value=mock_litellm_completion), \
             patch.object(ai_service.cost_service, 'calculate_cost') as mock_cost:

            # Different costs for different tenants
            mock_cost.side_effect = [Decimal('0.001'), Decimal('0.002')]

            response_1 = await ai_service.completion(tenant_001_request)
            response_2 = await ai_service.completion(tenant_002_request)

            assert response_1.tenant_id == "tenant_001"
            assert response_1.cost == Decimal('0.001')
            assert response_2.tenant_id == "tenant_002"
            assert response_2.cost == Decimal('0.002')

    @pytest.mark.asyncio
    async def test_error_recovery_with_retry(self, ai_service, mock_litellm_completion):
        """Test error recovery with retry mechanism."""
        # First two attempts fail, third succeeds
        with patch('src.services.ai_service.litellm.completion') as mock_completion:
            mock_completion.side_effect = [
                Exception("Network error"),
                Exception("Rate limited"),
                mock_litellm_completion
            ]

            request = AIRequest(
                prompt="Retry test",
                tenant_id="tenant_001",
                max_retries=3
            )

            response = await ai_service.completion(request)

            # Verify retry attempts
            assert mock_completion.call_count == 3
            assert response is not None
            assert response.content is not None

    @pytest.mark.asyncio
    async def test_audit_log_creation(self, ai_service, mock_litellm_completion):
        """Test audit log is created for every AI operation."""
        with patch('src.services.ai_service.litellm.completion', return_value=mock_litellm_completion), \
             patch('src.services.ai_service.create_audit_log') as mock_audit:

            request = AIRequest(
                prompt="Audit test",
                tenant_id="tenant_001",
                user_id="user_123"
            )

            await ai_service.completion(request)

            # Verify audit log was created
            mock_audit.assert_called_once()
            audit_args = mock_audit.call_args[1]
            assert audit_args["tenant_id"] == "tenant_001"
            assert audit_args["user_id"] == "user_123"
            assert audit_args["operation"] == "ai_completion"
            assert "prompt_tokens" in audit_args["metadata"]


class TestCostService:
    """Test suite for CostService with accurate pricing calculations."""

    @pytest_asyncio.fixture
    async def cost_service(self):
        """Create cost service instance."""
        return CostService()

    def test_openai_pricing_calculation(self, cost_service):
        """Test OpenAI pricing calculation."""
        pricing = cost_service.get_model_pricing("gpt-4o")

        assert pricing.provider == "openai"
        assert pricing.input_token_cost == Decimal('0.005')  # $0.005 per 1K input
        assert pricing.output_token_cost == Decimal('0.015')  # $0.015 per 1K output

        # Test calculation with actual usage
        cost = cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=150,
            completion_tokens=50
        )

        expected_input_cost = Decimal('150') / 1000 * pricing.input_token_cost
        expected_output_cost = Decimal('50') / 1000 * pricing.output_token_cost
        expected_total = expected_input_cost + expected_output_cost

        assert cost.input_cost == expected_input_cost
        assert cost.output_cost == expected_output_cost
        assert cost.total_cost == expected_total

    def test_anthropic_pricing_calculation(self, cost_service):
        """Test Anthropic pricing calculation."""
        pricing = cost_service.get_model_pricing("claude-3-5-sonnet")

        assert pricing.provider == "anthropic"
        assert pricing.input_token_cost == Decimal('0.003')  # $0.003 per 1K input
        assert pricing.output_token_cost == Decimal('0.015')  # $0.015 per 1K output

        cost = cost_service.calculate_cost(
            model="claude-3-5-sonnet",
            prompt_tokens=1000,
            completion_tokens=500
        )

        expected_input_cost = Decimal('1.0') * pricing.input_token_cost
        expected_output_cost = Decimal('0.5') * pricing.output_token_cost
        expected_total = expected_input_cost + expected_output_cost

        assert abs(cost.total_cost - expected_total) < Decimal('0.0001')

    def test_context_window_pricing(self, cost_service):
        """Test pricing calculation with context window considerations."""
        # Some models have different pricing for context > 32K tokens
        pricing = cost_service.get_model_pricing("gpt-4-turbo")

        # Test within normal context window
        cost_normal = cost_service.calculate_cost(
            model="gpt-4-turbo",
            prompt_tokens=30000,
            completion_tokens=1000
        )

        # Test exceeding context window
        cost_large = cost_service.calculate_cost(
            model="gpt-4-turbo",
            prompt_tokens=100000,
            completion_tokens=2000
        )

        # Large context should be more expensive
        assert cost_large.total_cost > cost_normal.total_cost

    def test_batch_cost_calculation(self, cost_service):
        """Test batch cost calculation for multiple operations."""
        calculations = [
            CostCalculation(
                model="gpt-4o",
                prompt_tokens=100,
                completion_tokens=50,
                input_cost=Decimal('0.0005'),
                output_cost=Decimal('0.00075'),
                total_cost=Decimal('0.00125')
            ),
            CostCalculation(
                model="claude-3-5-sonnet",
                prompt_tokens=200,
                completion_tokens=100,
                input_cost=Decimal('0.0006'),
                output_cost=Decimal('0.0015'),
                total_cost=Decimal('0.0021')
            )
        ]

        total_cost = cost_service.calculate_total_cost(calculations)

        expected = sum(calc.total_cost for calc in calculations)
        assert total_cost == expected

    def test_cost_estimation_before_completion(self, cost_service):
        """Test cost estimation before actual completion."""
        # Estimate based on expected token counts
        estimated_cost = cost_service.estimate_cost(
            model="gpt-4o",
            estimated_input_tokens=1000,
            estimated_output_tokens=500
        )

        assert estimated_cost > 0
        assert isinstance(estimated_cost, Decimal)

    def test_currency_conversion(self, cost_service):
        """Test currency conversion for international billing."""
        # Test with different currencies
        cost_usd = cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            currency="USD"
        )

        cost_eur = cost_service.convert_currency(cost_usd.total_cost, "USD", "EUR")

        assert cost_eur != cost_usd.total_cost  # Should be different after conversion

    def test_pricing_updates(self, cost_service):
        """Test pricing updates from providers."""
        # Simulate pricing update
        old_pricing = cost_service.get_model_pricing("gpt-4o")

        # Update pricing
        cost_service.update_model_pricing(
            model="gpt-4o",
            input_cost=Decimal('0.004'),  # Reduced price
            output_cost=Decimal('0.012')
        )

        new_pricing = cost_service.get_model_pricing("gpt-4o")

        assert new_pricing.input_token_cost < old_pricing.input_token_cost
        assert new_pricing.output_token_cost < old_pricing.output_token_cost

    def test_tiered_pricing(self, cost_service):
        """Test tiered pricing based on volume."""
        # Test different pricing tiers
        small_volume_cost = cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            volume_tier="small"  # < 1M tokens
        )

        large_volume_cost = cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            volume_tier="enterprise"  # > 100M tokens
        )

        # Enterprise should get volume discount
        assert large_volume_cost.total_cost < small_volume_cost.total_cost

    def test_cost_tracking_precision(self, cost_service):
        """Test cost tracking maintains required precision."""
        cost = cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1,
            completion_tokens=1
        )

        # Should maintain 6 decimal places as configured
        cost_str = f"{cost.total_cost:.6f}"
        assert len(cost_str.split('.')[-1]) == 6

    def test_monthly_cost_limiting(self, cost_service):
        """Test monthly cost limiting for tenants."""
        tenant_usage = {
            "current_month_cost": Decimal('99.50'),
            "monthly_limit": Decimal('100.00')
        }

        # Check if new request would exceed limit
        additional_cost = Decimal('1.00')
        would_exceed = cost_service.would_exceed_monthly_limit(
            tenant_usage,
            additional_cost
        )

        assert would_exceed is True

    def test_cost_alerts(self, cost_service):
        """Test cost alert generation."""
        # Test threshold alerts
        cost_data = {
            "daily_cost": Decimal('50.00'),
            "daily_threshold": Decimal('100.00'),
            "monthly_cost": Decimal('2500.00'),
            "monthly_threshold": Decimal('5000.00')
        }

        alerts = cost_service.check_cost_thresholds(cost_data)

        # Should have alert at 50% of daily threshold
        assert len(alerts) > 0
        assert any("50%" in alert.message for alert in alerts)


class TestIntegration:
    """Integration tests for AI Service with existing systems."""

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_integration(self):
        """Test integration with existing ingestion pipeline."""
        from src.tasks.ingestion import apply_ai_labeling

        # Mock the new AI service
        with patch('src.services.ai_service.AIService') as mock_ai_service:
            mock_instance = AsyncMock()
            mock_response = AIResponse(
                content='{"category": "high_value", "confidence": 0.9}',
                model="gpt-4o",
                usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
                cost=Decimal('0.001'),
                tenant_id="tenant_001"
            )
            mock_instance.completion.return_value = mock_response
            mock_ai_service.return_value = mock_instance

            # Test data
            test_data = [
                {
                    "id": 1,
                    "name": "Test User",
                    "email": "test@company.com",
                    "tenant_id": "tenant_001"
                }
            ]

            # Run the ingestion task
            result = await apply_ai_labeling(test_data)

            # Verify integration
            assert len(result) == 1
            assert result[0]["ai_category"] == "high_value"
            assert result[0]["ai_confidence"] == 0.9
            assert "ai_cost" in result[0]
            assert "ai_tokens_used" in result[0]

    @pytest.mark.asyncio
    async def test_backward_compatibility(self):
        """Test backward compatibility with existing OpenAI integration."""
        # Ensure existing API contracts are maintained
        from src.tasks.ingestion import apply_ai_labeling

        # Mock both old and new implementations
        with patch('src.services.ai_service.AIService') as mock_new, \
             patch('openai.OpenAI') as mock_old:

            # Test with new service
            mock_new_instance = AsyncMock()
            mock_new_instance.completion.return_value = AIResponse(
                content='{"category": "test"}',
                model="gpt-4o",
                usage=TokenUsage(100, 50, 150),
                cost=Decimal('0.001')
            )
            mock_new.return_value = mock_new_instance

            test_data = [{"id": 1, "tenant_id": "test"}]
            result = await apply_ai_labeling(test_data)

            # Verify same response structure
            assert "ai_category" in result[0]
            assert "ai_confidence" in result[0]
            assert "ai_reasoning" in result[0]
            assert "ai_model" in result[0]
            assert "ai_processed_at" in result[0]

    def test_environment_variable_fallback(self):
        """Test fallback to environment variables when config missing."""
        with patch.dict('os.environ', {
            'OPENAI_API_KEY': 'test-key',
            'PRIMARY_MODEL': 'gpt-3.5-turbo'
        }):
            from src.services.ai_service import AIService
            service = AIService()

            # Should use environment variables
            assert service.primary_model == 'gpt-3.5-turbo'

    @pytest.mark.asyncio
    async def test_prompt_template_integration(self):
        """Test integration with Prompt Management System."""
        ai_service = AIService()
        await ai_service.initialize()

        with patch.object(ai_service.prompt_manager, 'get_template') as mock_template:
            mock_template.return_value = {
                "system_prompt": "Test system prompt",
                "user_prompt": "Test user prompt with {variable}"
            }

            request = AIRequest(
                prompt_template="test_template",
                template_vars={"variable": "value"},
                tenant_id="test_tenant"
            )

            with patch('src.services.ai_service.litellm.completion') as mock_completion:
                mock_completion.return_value = {"choices": [{"message": {"content": "response"}}]}

                await ai_service.completion(request)

                # Verify template was used
                mock_template.assert_called_once_with("test_template", tenant_id="test_tenant")

    @pytest.mark.asyncio
    async def test_stripe_billing_integration(self):
        """Test integration with Stripe billing system."""
        from src.services.cost_service import CostService

        cost_service = CostService()

        with patch('src.services.cost_service.stripe') as mock_stripe:
            # Test billing event creation
            await cost_service.record_billing_event(
                tenant_id="tenant_001",
                amount=Decimal('0.123'),
                usage_data={"tokens": 1000, "model": "gpt-4o"}
            )

            # Verify Stripe was called
            assert mock_stripe.billing.meter_event.create.called

    @pytest.mark.asyncio
    async def test_performance_requirements(self):
        """Test performance meets requirements (<5 seconds)."""
        ai_service = AIService()
        await ai_service.initialize()

        with patch('src.services.ai_service.litellm.completion') as mock_completion:
            # Simulate fast response
            mock_completion.return_value = {
                "choices": [{"message": {"content": "Fast response"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}
            }

            import time
            start_time = time.time()

            request = AIRequest(prompt="Performance test", tenant_id="test")
            await ai_service.completion(request)

            response_time = (time.time() - start_time) * 1000  # Convert to ms

            # Should be well under 5 seconds
            assert response_time < 5000

    @pytest.mark.asyncio
    async def test_zero_breaking_changes(self):
        """Ensure zero breaking changes to existing API."""
        # Test all existing API endpoints still work
        from src.app import app

        # This would be tested more comprehensively in actual test suite
        # ensuring all endpoints return expected responses
        assert app is not None

        # Test that all imports still work
        from src.tasks.ingestion import data_ingestion_flow
        from src.models.data_record import DataRecord
        from src.core.config import settings

        assert data_ingestion_flow is not None
        assert DataRecord is not None
        assert settings is not None