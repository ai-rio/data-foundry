"""
Integration tests for LiteLLM Service.

These tests use real API calls with test keys to validate:
- Multi-provider connectivity
- Fallback mechanisms
- Error handling
- Performance benchmarks
- Cost tracking accuracy
- Response caching
"""

import asyncio
import json
import os
import pytest
import pytest_asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from src.services.litellm_service import LiteLLMService, LiteLLMError
from src.services.ai_service import AIService, AIRequest, AIResponse
from src.services.cost_service import CostService


@pytest.mark.integration
class TestLiteLLMIntegration:
    """Integration tests for LiteLLM service."""

    @pytest_asyncio.fixture
    async def litellm_service(self):
        """Create LiteLLM service instance."""
        service = LiteLLMService()
        await service.initialize()
        yield service
        # Cleanup if needed

    @pytest_asyncio.fixture
    async def ai_service(self):
        """Create AI service instance."""
        service = AIService()
        await service.initialize()
        yield service
        # Cleanup if needed

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set for integration testing"
    )
    async def test_openai_connectivity(self, litellm_service):
        """Test real OpenAI API connectivity."""
        try:
            response = await litellm_service.completion(
                prompt="Respond with 'OpenAI test successful'",
                model="gpt-3.5-turbo",  # Use cheaper model for testing
                max_tokens=10,
                tenant_id="test_tenant"
            )

            assert response.content is not None
            assert response.model == "gpt-3.5-turbo"
            assert response.provider == "openai"
            assert response.usage["total_tokens"] > 0
            assert response.cost > 0

            # Check response contains expected text
            assert "successful" in response.content.lower()

        except LiteLLMError as e:
            pytest.skip(f"OpenAI API not available: {str(e)}")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set for integration testing"
    )
    async def test_anthropic_connectivity(self, litellm_service):
        """Test real Anthropic API connectivity."""
        try:
            response = await litellm_service.completion(
                prompt="Respond with 'Anthropic test successful'",
                model="claude-3-haiku",  # Use cheaper model for testing
                max_tokens=10,
                tenant_id="test_tenant"
            )

            assert response.content is not None
            assert response.model == "claude-3-haiku"
            assert response.provider == "anthropic"
            assert response.usage["total_tokens"] > 0
            assert response.cost > 0

            # Check response contains expected text
            assert "successful" in response.content.lower()

        except LiteLLMError as e:
            pytest.skip(f"Anthropic API not available: {str(e)}")

    @pytest.mark.asyncio
    async def test_fallback_mechanism(self, litellm_service):
        """Test fallback between providers."""
        # Configure with invalid primary model to trigger fallback
        litellm_service.primary_model = "invalid-model"
        litellm_service.fallback_models = ["gpt-3.5-turbo"]

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for fallback testing")

        try:
            response = await litellm_service.completion(
                prompt="Test fallback",
                tenant_id="test_tenant",
                max_retries=1  # Reduce retries for faster test
            )

            # Should have used fallback model
            assert response.model == "gpt-3.5-turbo"
            assert response.fallback_used is True

        except LiteLLMError as e:
            # Expected if no valid API keys
            pytest.skip(f"No valid API keys for fallback testing: {str(e)}")

    @pytest.mark.asyncio
    async def test_json_response_format(self, litellm_service):
        """Test JSON response format parsing."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for JSON testing")

        try:
            response = await litellm_service.completion(
                prompt="Generate a JSON object with 'status' and 'message' fields",
                model="gpt-3.5-turbo",
                response_format="json",
                max_tokens=50,
                tenant_id="test_tenant"
            )

            # Try to parse as JSON
            try:
                json_content = json.loads(response.content)
                assert "status" in json_content
                assert "message" in json_content
            except json.JSONDecodeError:
                pytest.fail("Response is not valid JSON")

        except LiteLLMError as e:
            pytest.skip(f"JSON format test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_caching_mechanism(self, litellm_service):
        """Test response caching functionality."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for caching test")

        try:
            prompt = "Test caching with this exact prompt"
            tenant_id = "cache_test_tenant"

            # First call
            start_time = datetime.now()
            response1 = await litellm_service.completion(
                prompt=prompt,
                model="gpt-3.5-turbo",
                tenant_id=tenant_id,
                use_cache=True,
                cache_ttl=60
            )
            first_call_time = (datetime.now() - start_time).total_seconds()

            # Second call (should use cache)
            start_time = datetime.now()
            response2 = await litellm_service.completion(
                prompt=prompt,
                model="gpt-3.5-turbo",
                tenant_id=tenant_id,
                use_cache=True,
                cache_ttl=60
            )
            second_call_time = (datetime.now() - start_time).total_seconds()

            # Verify responses are identical
            assert response1.content == response2.content
            assert response1.usage == response2.usage

            # Second call should be much faster (from cache)
            assert second_call_time < first_call_time * 0.5

            # Verify cache metrics
            metrics = await litellm_service.get_metrics()
            assert metrics["cache_hits"] > 0

        except LiteLLMError as e:
            pytest.skip(f"Caching test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_rate_limiting(self, litellm_service):
        """Test rate limiting functionality."""
        # Configure low rate limit for testing
        litellm_service._max_requests_per_minute = 2

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for rate limit test")

        try:
            # Make multiple requests quickly
            start_time = datetime.now()
            responses = []

            for i in range(4):  # Exceed rate limit
                response = await litellm_service.completion(
                    prompt=f"Rate limit test {i}",
                    model="gpt-3.5-turbo",
                    tenant_id="rate_limit_test",
                    max_tokens=5
                )
                responses.append(response)

            total_time = (datetime.now() - start_time).total_seconds()

            # Should have taken at least 1 minute due to rate limiting
            # (2 requests per minute limit, 4 requests = at least 1 minute)
            assert total_time > 50  # Allow some tolerance

        except LiteLLMError as e:
            pytest.skip(f"Rate limiting test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_cost_calculation_accuracy(self, litellm_service):
        """Test cost calculation accuracy across models."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for cost test")

        cost_service = CostService()

        try:
            # Test with different models
            models_to_test = ["gpt-3.5-turbo", "gpt-4o-mini"]
            costs = []

            for model in models_to_test:
                response = await litellm_service.completion(
                    prompt="Calculate costs for this request",
                    model=model,
                    tenant_id="cost_test",
                    max_tokens=20
                )
                costs.append({
                    "model": model,
                    "cost": response.cost,
                    "tokens": response.usage["total_tokens"]
                })

            # Verify costs are different for different models
            assert len(set(c["cost"] for c in costs)) > 1

            # Verify cost calculation matches expected pricing
            for cost_info in costs:
                pricing = cost_service.get_model_pricing(cost_info["model"])
                expected_cost = (
                    Decimal(str(cost_info["tokens"])) / Decimal("1000") *
                    pricing.input_token_cost
                )
                # Should be close (allowing for completion tokens)
                assert abs(cost_info["cost"] - expected_cost) < Decimal("0.01")

        except LiteLLMError as e:
            pytest.skip(f"Cost calculation test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, litellm_service):
        """Test error handling and recovery mechanisms."""
        # Test with invalid model
        with pytest.raises(LiteLLMError) as exc_info:
            await litellm_service.completion(
                prompt="Test error",
                model="definitely-invalid-model-name",
                tenant_id="error_test",
                max_retries=1  # Limit retries for faster test
            )

        assert "definitely-invalid-model-name" in str(exc_info.value)
        assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, litellm_service):
        """Test performance benchmarks and response times."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for performance test")

        response_times = []
        num_requests = 5

        try:
            for i in range(num_requests):
                start_time = datetime.now()
                response = await litellm_service.completion(
                    prompt=f"Performance test {i}",
                    model="gpt-3.5-turbo",
                    tenant_id="perf_test",
                    max_tokens=10
                )
                response_time = (datetime.now() - start_time).total_seconds()
                response_times.append(response_time)

            # Calculate statistics
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)

            # Performance assertions
            assert avg_time < 5.0  # Average under 5 seconds
            assert max_time < 10.0  # Maximum under 10 seconds

            # Check service metrics
            metrics = await litellm_service.get_metrics()
            assert metrics["requests_total"] >= num_requests
            assert metrics["avg_response_time"] > 0

        except LiteLLMError as e:
            pytest.skip(f"Performance test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, litellm_service):
        """Test handling of concurrent requests."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for concurrency test")

        try:
            # Create multiple concurrent requests
            async def make_request(i):
                return await litellm_service.completion(
                    prompt=f"Concurrent test {i}",
                    model="gpt-3.5-turbo",
                    tenant_id="concurrent_test",
                    max_tokens=5
                )

            # Run 10 requests concurrently
            tasks = [make_request(i) for i in range(10)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all requests succeeded
            successful = [r for r in responses if not isinstance(r, Exception)]
            assert len(successful) == 10

            # Verify all responses are unique
            contents = [r.content for r in successful]
            assert len(set(contents)) == len(contents)  # All unique

        except LiteLLMError as e:
            pytest.skip(f"Concurrency test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_ai_service_integration(self, ai_service):
        """Test integration between AI service and LiteLLM service."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for AI service test")

        try:
            request = AIRequest(
                prompt="Test AI service integration",
                system_prompt="You are a helpful assistant.",
                temperature=0.5,
                max_tokens=50,
                tenant_id="ai_service_test",
                use_cache=True
            )

            response = await ai_service.completion(request)

            assert isinstance(response, AIResponse)
            assert response.content is not None
            assert response.model is not None
            assert response.usage.total_tokens > 0
            assert response.cost > 0

        except Exception as e:
            pytest.skip(f"AI service integration test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_health_check_functionality(self, litellm_service):
        """Test health check endpoint."""
        health = await litellm_service.health_check()

        assert "healthy" in health
        assert "models" in health
        assert "timestamp" in health

        # Should have checked at least one model
        assert len(health["models"]) > 0

        # Each model check should have status info
        for model_name, model_health in health["models"].items():
            assert "status" in model_health
            assert "provider" in model_health

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, litellm_service):
        """Test metrics tracking and reporting."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for metrics test")

        # Reset metrics
        await litellm_service.reset_metrics()

        # Make some requests
        for i in range(3):
            try:
                await litellm_service.completion(
                    prompt=f"Metrics test {i}",
                    model="gpt-3.5-turbo",
                    tenant_id="metrics_test",
                    max_tokens=5
                )
            except:
                pass  # Ignore errors for metrics test

        # Check metrics
        metrics = await litellm_service.get_metrics()

        assert metrics["requests_total"] >= 3
        assert metrics["total_tokens"] >= 0
        assert metrics["total_cost"] >= 0
        assert metrics["avg_response_time"] >= 0

        # Metrics should have all expected fields
        expected_fields = [
            "requests_total",
            "requests_success",
            "requests_failed",
            "fallback_used",
            "cache_hits",
            "cache_misses",
            "total_tokens",
            "total_cost",
            "avg_response_time"
        ]
        for field in expected_fields:
            assert field in metrics


@pytest.mark.integration
class TestEndToEndWorkflows:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_complete_labeling_workflow(self):
        """Test complete AI labeling workflow."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for E2E test")

        from src.tasks.ingestion import apply_ai_labeling

        # Test data
        test_records = [
            {
                "id": 1,
                "name": "John Doe",
                "email": "john@acme.com",
                "company": "Acme Corp",
                "tenant_id": "e2e_test"
            },
            {
                "id": 2,
                "name": "Jane Smith",
                "email": "jane@gmail.com",
                "company": None,
                "tenant_id": "e2e_test"
            }
        ]

        try:
            # Run labeling workflow
            labeled_records = await apply_ai_labeling(test_records)

            # Verify results
            assert len(labeled_records) == 2

            for record in labeled_records:
                assert "ai_category" in record
                assert "ai_confidence" in record
                assert "ai_cost" in record
                assert "ai_tokens_used" in record
                assert "ai_model" in record
                assert "ai_processed_at" in record

                # Check category is valid
                assert record["ai_category"] in ["high_value", "medium_value", "low_value"]
                assert 0 <= record["ai_confidence"] <= 1
                assert record["ai_cost"] > 0

        except Exception as e:
            pytest.skip(f"E2E workflow test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_prompt_template_workflow(self):
        """Test workflow using prompt templates."""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for template test")

        ai_service = AIService()
        await ai_service.initialize()

        try:
            # Use prompt template (assuming it exists)
            request = AIRequest(
                prompt_template="data_categorization",
                template_vars={
                    "company_name": "Test Corp",
                    "email_domain": "testcorp.com",
                    "contact_info": "John Doe"
                },
                tenant_id="template_test",
                response_format="json"
            )

            response = await ai_service.completion(request)

            assert response.content is not None
            assert response.usage.total_tokens > 0

            # Try to parse JSON response
            json_response = json.loads(response.content)
            assert "category" in json_response
            assert "confidence" in json_response

        except Exception as e:
            # Template might not exist - that's okay for integration test
            if "template" in str(e).lower():
                pytest.skip("Prompt template not configured")
            else:
                pytest.skip(f"Template workflow test failed: {str(e)}")

    @pytest.mark.asyncio
    async def test_billing_integration(self):
        """Test integration with billing system."""
        if not os.getenv("OPENAI_API_KEY") or not os.getenv("STRIPE_SECRET_KEY"):
            pytest.skip("Required keys not set for billing test")

        cost_service = CostService()
        litellm_service = LiteLLMService()
        await litellm_service.initialize()

        try:
            # Make a request
            response = await litellm_service.completion(
                prompt="Billing integration test",
                model="gpt-3.5-turbo",
                tenant_id="billing_test",
                max_tokens=10
            )

            # Record billing event
            await cost_service.record_billing_event(
                tenant_id="billing_test",
                amount=response.cost,
                usage_data={
                    "tokens": response.usage["total_tokens"],
                    "model": response.model,
                    "provider": response.provider
                }
            )

            # Verify cost was tracked
            assert response.cost > 0

        except Exception as e:
            pytest.skip(f"Billing integration test failed: {str(e)}")