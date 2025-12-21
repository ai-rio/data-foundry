"""
TRUE Model Fallback Integration Tests

This test suite validates real model fallback functionality with:
- Real OpenRouter API calls for fallback testing
- Actual model failures and recovery
- Performance measurement during fallback
- Cost tracking with fallback models
- Error handling and retry logic

Tests validate the complete fallback mechanism without mocking.
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from src.services.litellm_service import LiteLLMService, LiteLLMResponse, LiteLLMError
from src.services.redis_service import RedisService
from src.core.config import settings


class TestTrueModelFallback:
    """TRUE model fallback tests - NO MOCKING ALLOWED"""

    @pytest.fixture
    async def litellm_service(self):
        """LiteLLM service with real fallback configuration."""
        service = LiteLLMService()
        await service.initialize()

        # Verify all configured models are available
        health = await service.health_check()
        assert health["healthy"], "Service should be healthy"

        yield service
        await service.close()

    @pytest.fixture
    async def redis_service(self):
        """Real Redis service for fallback caching."""
        redis = RedisService(
            url=settings.REDIS_URL,
            max_connections=5,
            retry_attempts=3,
            retry_delay=0.1,
            default_ttl=3600,
            enable_metrics=True
        )

        # Verify Redis is available
        assert await redis.health_check(), "Redis should be available"

        yield redis
        await redis.close()

    @pytest.fixture
    def test_data_samples(self):
        """Test data samples for fallback testing."""
        return [
            {
                "name": "Fallback Test User 1",
                "email": "fallback1@example.com",
                "title": "Software Engineer",
                "company": "Test Corp"
            },
            {
                "name": "Fallback Test User 2",
                "email": "fallback2@startup.io",
                "title": "Product Manager",
                "company": "Startup Co"
            },
            {
                "name": "Fallback Test User 3",
                "email": "fallback3@enterprise.com",
                "title": "CTO",
                "company": "Enterprise Inc"
            }
        ]

    @pytest.mark.true_fallback
    async def test_real_fallback_from_invalid_primary_model(self, litellm_service, test_data_samples):
        """Test real fallback from invalid primary model to valid fallback models."""
        invalid_model = "openrouter/invalid/nonexistent-model"
        valid_fallback = litellm_service.fallback_models[0]

        start_time = time.time()

        # This should trigger fallback mechanism
        response = await litellm_service.completion(
            prompt=f"Fallback test: {json.dumps(test_data_samples[0])}",
            tenant_id="test_fallback_primary",
            model=invalid_model,  # Invalid model to force fallback
            use_cache=False  # Ensure real API call
        )

        response_time = time.time() - start_time

        # Validate fallback occurred
        assert response.fallback_used is True, "Should have used fallback model"
        assert response.model == valid_fallback, f"Should use fallback model {valid_fallback}"
        assert response.model != invalid_model, "Should not use invalid model"
        assert response.retry_count > 0, "Should have retry count"

        # Validate response quality
        assert response.content is not None, "Response should have content"
        assert response_time < 5, f"Fallback response time should be < 5s: {response_time:.2f}s"

        # Parse and validate AI response
        ai_data = json.loads(response.content)
        assert "category" in ai_data, "Should provide category"
        assert "confidence" in ai_data, "Should provide confidence"
        assert 0 <= ai_data["confidence"] <= 1, "Confidence should be between 0 and 1"

    @pytest.mark.true_fallback
    async def test_real_fallback_chain(self, litellm_service, test_data_samples):
        """Test real fallback chain through multiple models."""
        invalid_model = "openrouter/invalid/chain-test"
        fallback_models = litellm_service.fallback_models.copy()

        start_time = time.time()

        # This should try fallback models in order
        response = await litellm_service.completion(
            prompt=f"Chain fallback test: {json.dumps(test_data_samples[1])}",
            tenant_id="test_fallback_chain",
            model=invalid_model,  # Force fallback
            use_cache=False
        )

        response_time = time.time() - start_time

        # Validate fallback chain worked
        assert response.fallback_used is True, "Should have used fallback chain"
        assert response.model in fallback_models, f"Should use one of configured fallback models: {fallback_models}"
        assert response.model != invalid_model, "Should not use invalid model"
        assert response.retry_count > 0, "Should have retry attempts"

        # Validate response
        assert response.content is not None, "Response should have content"
        assert response_time < 10, f"Chain fallback response time should be < 10s: {response_time:.2f}s"

    @pytest.mark.true_fallback
    async def test_real_primary_model_success(self, litellm_service, test_data_samples):
        """Test that primary model works correctly when available."""
        primary_model = litellm_service.primary_model

        start_time = time.time()

        # Use primary model directly
        response = await litellm_service.completion(
            prompt=f"Primary model test: {json.dumps(test_data_samples[0])}",
            tenant_id="test_primary_success",
            model=primary_model,
            use_cache=False
        )

        response_time = time.time() - start_time

        # Validate primary model response
        assert response.fallback_used is False, "Should not use fallback for primary model"
        assert response.model == primary_model, f"Should use primary model {primary_model}"
        assert response.retry_count == 0, "Primary model should not need retries"

        # Validate response quality
        assert response.content is not None, "Response should have content"
        assert response.cost > 0, "Primary model should have cost"
        assert response_time < 5, f"Primary model response time should be < 5s: {response_time:.2f}s"

    @pytest.mark.true_fallback
    async def test_real_fallback_cost_accuracy(self, litellm_service, test_data_samples):
        """Test cost accuracy during fallback scenarios."""
        invalid_model = "openrouter/invalid/cost-test"
        fallback_models = litellm_service.fallback_models

        # Track costs for different scenarios
        primary_cost = None
        fallback_costs = []

        # Test primary model cost
        primary_response = await litellm_service.completion(
            prompt=f"Cost test primary: {json.dumps(test_data_samples[0])}",
            tenant_id="test_cost_accuracy",
            model=litellm_service.primary_model,
            use_cache=False
        )
        primary_cost = primary_response.cost

        # Test fallback model costs
        for i, fallback_model in enumerate(fallback_models):
            response = await litellm_service.completion(
                prompt=f"Cost test fallback {i}: {json.dumps(test_data_samples[i+1])}",
                tenant_id="test_cost_accuracy",
                model=fallback_model,
                use_cache=False
            )
            fallback_costs.append(response.cost)

        # Validate costs are positive and reasonable
        assert primary_cost > 0, "Primary model should have positive cost"
        assert primary_cost < Decimal("0.10"), "Primary model cost should be small"

        for i, cost in enumerate(fallback_costs):
            assert cost > 0, f"Fallback model {i} should have positive cost"
            assert cost < Decimal("0.10"), f"Fallback model {i} cost should be small"

        # Verify fallback costs are tracked in metrics
        metrics = await litellm_service.get_metrics()
        assert metrics["total_cost"] > 0, "Total cost should be tracked"
        assert isinstance(metrics["total_cost"], Decimal), "Total cost should be Decimal"

    @pytest.mark.true_fallback
    async def test_real_fallback_performance_tracking(self, litellm_service, test_data_samples):
        """Test performance tracking during fallback operations."""
        invalid_model = "openrouter/invalid/perf-test"

        # Test scenarios
        scenarios = [
            ("primary_success", litellm_service.primary_model, False),
            ("fallback_used", invalid_model, True)
        ]

        performance_results = {}

        for scenario_name, model, expect_fallback in scenarios:
            start_time = time.time()

            response = await litellm_service.completion(
                prompt=f"Performance {scenario_name}: {json.dumps(test_data_samples[0])}",
                tenant_id="test_performance",
                model=model,
                use_cache=False
            )

            response_time = time.time() - start_time

            performance_results[scenario_name] = {
                "response_time": response_time,
                "fallback_used": response.fallback_used,
                "retry_count": response.retry_count,
                "model": response.model
            }

            # Validate expectations
            assert response.fallback_used == expect_fallback, f"Scenario {scenario_name} fallback mismatch"
            assert response_time < 5, f"Scenario {scenario_name} too slow: {response_time:.2f}s"

        # Performance analysis
        primary_time = performance_results["primary_success"]["response_time"]
        fallback_time = performance_results["fallback_used"]["response_time"]

        # Fallback should be reasonably close to primary (might be slightly slower)
        assert fallback_time < primary_time * 1.5, (
            f"Fallback {fallback_time:.3f}s should not be much slower than primary {primary_time:.3f}s"
        )

    @pytest.mark.true_fallback
    async def test_real_fallback_with_cache(self, litellm_service, redis_service, test_data_samples):
        """Test fallback behavior with Redis caching enabled."""
        # Clear cache
        await redis_service.clear_cache()

        invalid_model = "openrouter/invalid/cache-test"

        # First call with invalid model (should fallback and cache result)
        start_time = time.time()
        response1 = await litellm_service.completion(
            prompt=f"Cache fallback test: {json.dumps(test_data_samples[0])}",
            tenant_id="test_fallback_cache",
            model=invalid_model,
            use_cache=True
        )
        first_call_time = time.time() - start_time

        # Verify fallback occurred
        assert response1.fallback_used is True, "First call should use fallback"
        assert response1.cached is False, "First call should not be cached"

        # Second identical call (should hit cache)
        start_time = time.time()
        response2 = await litellm_service.completion(
            prompt=f"Cache fallback test: {json.dumps(test_data_samples[0])}",
            tenant_id="test_fallback_cache",
            model=invalid_model,
            use_cache=True
        )
        second_call_time = time.time() - start_time

        # Should use cached response (no fallback needed)
        assert response2.fallback_used is False, "Second call should not use fallback"
        assert response2.cached is True, "Second call should be cached"
        assert response1.content == response2.content, "Cached response should be identical"
        assert second_call_time < first_call_time, "Cached call should be faster"

        # Verify cache statistics
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.sets >= 1, "Should have cached result"
        assert redis_stats.hits >= 1, "Should have cache hit"

    @pytest.mark.true_fallback
    async def test_real_fallback_error_handling(self, litellm_service, test_data_samples):
        """Test error handling during fallback scenarios."""
        invalid_model = "openrouter/invalid/error-test"

        # Test various error scenarios
        error_scenarios = [
            ("invalid_model", invalid_model),
            ("invalid_format", "openrouter/openai/invalid-format"),
            ("rate_limit_simulated", "openrouter/openai/rate-limited")  # Will trigger fallback
        ]

        for scenario_name, model in error_scenarios:
            try:
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=f"Error test {scenario_name}: {json.dumps(test_data_samples[0])}",
                    tenant_id="test_error_handling",
                    model=model,
                    use_cache=False
                )
                response_time = time.time() - start_time

                # Should either succeed with fallback or fail gracefully
                assert response_time < 5, f"Error scenario {scenario_name} too slow: {response_time:.2f}s"
                assert response.content is not None, f"Should return response for {scenario_name}"

                if response.fallback_used:
                    assert response.model in litellm_service.fallback_models, (
                        f"Should use valid fallback model for {scenario_name}"
                    )

            except Exception as e:
                # Should handle errors gracefully
                assert "error" in str(e).lower() or "failed" in str(e).lower(), (
                    f"Should handle error gracefully for {scenario_name}: {str(e)}"
                )

        # Verify service remains healthy after error tests
        health = await litellm_service.health_check()
        assert health["healthy"], "Service should remain healthy after error tests"

    @pytest.mark.true_fallback
    async def test_real_concurrent_fallback_requests(self, litellm_service, test_data_samples):
        """Test concurrent fallback requests."""
        invalid_model = "openrouter/invalid/concurrent-test"

        # Create concurrent requests that will trigger fallback
        async def make_fallback_request(i):
            return await litellm_service.completion(
                prompt=f"Concurrent fallback test {i}: {json.dumps(test_data_samples[i % len(test_data_samples)])}",
                tenant_id="test_concurrent_fallback",
                model=invalid_model,
                use_cache=True  # Enable caching for better performance
            )

        # Execute 5 concurrent fallback requests
        start_time = time.time()
        tasks = [make_fallback_request(i) for i in range(5)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Verify all succeeded
        for i, response in enumerate(responses):
            assert isinstance(response, LiteLLMResponse), f"Request {i} failed: {response}"
            assert response.fallback_used is True, f"Request {i} should use fallback"
            assert response.content is not None, f"Request {i} should have content"

        # Should complete reasonably fast (< 15s for 5 concurrent requests)
        assert total_time < 15, f"Concurrent fallback requests too slow: {total_time:.2f}s"

        # Verify fallback usage
        fallback_count = sum(1 for r in responses if r.fallback_used)
        assert fallback_count == 5, f"All 5 requests should use fallback: {fallback_count}"

    @pytest.mark.true_fallback
    async def test_real_fallback_with_different_data_types(self, litellm_service):
        """Test fallback with different types of data."""
        invalid_model = "openrouter/invalid/data-type-test"

        test_data_types = [
            ("contact", '{"name": "John Doe", "email": "john@example.com", "title": "CEO"}'),
            ("company", '{"name": "TechCorp Inc.", "industry": "Technology", "size": "large"}'),
            ("product", '{"name": "Software Product", "version": "1.0", "price": 99.99}'),
            ("document", '{"content": "This is a test document with sensitive information"}')
        ]

        results = {}

        for data_type, data in test_data_types:
            start_time = time.time()

            response = await litellm_service.completion(
                prompt=f"Data type test {data_type}: {data}",
                tenant_id="test_data_types",
                model=invalid_model,
                use_cache=False
            )

            response_time = time.time() - start_time

            # Validate response
            assert response is not None, f"Should process {data_type} data"
            assert response.fallback_used is True, f"Should fallback for {data_type}"
            assert response_time < 5, f"{data_type} processing too slow: {response_time:.2f}s"

            # Parse and validate AI response
            try:
                ai_data = json.loads(response.content)
                assert "category" in ai_data, f"Should provide category for {data_type}"
                assert "confidence" in ai_data, f"Should provide confidence for {data_type}"
            except json.JSONDecodeError:
                # Some responses might not be JSON, but should still be valid
                assert response.content is not None, f"Should have content for {data_type}"

            results[data_type] = {
                "response_time": response_time,
                "content": response.content,
                "model": response.model
            }

        # Verify all data types were processed
        assert len(results) == len(test_data_types), f"Should process all {len(test_data_types)} data types"

    @pytest.mark.true_fallback
    async def test_real_fallback_metrics_tracking(self, litellm_service, test_data_samples):
        """Test metrics tracking during fallback operations."""
        # Reset metrics
        await litellm_service.reset_metrics()

        invalid_model = "openrouter/invalid/metrics-test"
        fallback_models = litellm_service.fallback_models

        # Test mix of primary and fallback requests
        for i in range(3):
            # Primary model request
            await litellm_service.completion(
                prompt=f"Metrics primary {i}: {json.dumps(test_data_samples[i % len(test_data_samples)])}",
                tenant_id="test_metrics",
                model=litellm_service.primary_model,
                use_cache=False
            )

            # Fallback request
            await litellm_service.completion(
                prompt=f"Metrics fallback {i}: {json.dumps(test_data_samples[i % len(test_data_samples)])}",
                tenant_id="test_metrics",
                model=invalid_model,
                use_cache=False
            )

        # Get metrics
        metrics = await litellm_service.get_metrics()

        # Validate metrics include fallback data
        assert metrics["requests_total"] >= 6, "Should track all requests"
        assert metrics["requests_success"] >= 6, "Should track successful requests"
        assert metrics["fallback_used"] >= 3, f"Should track 3 fallback usages: {metrics['fallback_used']}"
        assert metrics["retry_count"] >= 3, f"Should track retry attempts: {metrics['retry_count']}"
        assert metrics["total_cost"] > 0, "Should track total cost"
        assert isinstance(metrics["total_cost"], Decimal), "Total cost should be Decimal"

        # Verify fallback models are tracked
        assert "fallback_models_used" in metrics, "Should track fallback models used"
        fallback_models_used = metrics["fallback_models_used"]
        assert len(fallback_models_used) > 0, "Should record used fallback models"

    @pytest.mark.true_fallback
    async def test_real_fallback_reliability(self, litellm_service, test_data_samples):
        """Test reliability of fallback mechanism over multiple requests."""
        invalid_model = "openrouter/invalid/reliability-test"

        # Test multiple fallback requests
        results = []
        success_count = 0

        for i in range(10):  # 10 requests to test reliability
            try:
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=f"Reliability test {i}: {json.dumps(test_data_samples[i % len(test_data_samples)])}",
                    tenant_id="test_reliability",
                    model=invalid_model,
                    use_cache=False
                )

                response_time = time.time() - start_time

                # Validate response
                assert response is not None
                assert response.fallback_used is True
                assert response.content is not None
                assert response_time < 5

                results.append({
                    "success": True,
                    "response_time": response_time,
                    "model": response.model,
                    "retry_count": response.retry_count
                })
                success_count += 1

            except Exception as e:
                results.append({
                    "success": False,
                    "error": str(e)
                })

        # Calculate reliability
        reliability = success_count / len(results)
        assert reliability > 0.9, f"Reliability should be > 90%, got {reliability:.2%}"

        # Verify response times are consistent
        response_times = [r["response_time"] for r in results if r["success"]]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            assert avg_time < 3, f"Average response time should be < 3s, got {avg_time:.2f}s"

            # No single request should be too slow
            max_time = max(response_times)
            assert max_time < 5, f"Maximum response time should be < 5s, got {max_time:.2f}s"

    @pytest.mark.true_fallback
    async def test_real_fallback_model_comparison(self, litellm_service, test_data_samples):
        """Test and compare different fallback models."""
        test_prompt = f"Model comparison test: {json.dumps(test_data_samples[0])}"
        tenant_id = "test_model_comparison"

        results = {}

        # Test each fallback model
        for model in litellm_service.fallback_models:
            try:
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=test_prompt,
                    tenant_id=tenant_id,
                    model=model,
                    use_cache=False
                )

                response_time = time.time() - start_time

                # Validate response
                assert response is not None, f"Model {model} should return response"
                assert response.model == model, f"Should use model {model}"
                assert response.content is not None, f"Model {model} should have content"
                assert response_time < 5, f"Model {model} too slow: {response_time:.2f}s"

                # Parse response
                ai_data = json.loads(response.content)
                confidence = ai_data.get("confidence", 0)

                results[model] = {
                    "response_time": response_time,
                    "confidence": confidence,
                    "cost": response.cost,
                    "tokens": response.usage,
                    "content": response.content
                }

            except Exception as e:
                pytest.fail(f"Model {model} failed: {str(e)}")

        # Verify we tested all fallback models
        assert len(results) == len(litellm_service.fallback_models), (
            f"Should test all {len(litellm_service.fallback_models)} fallback models"
        )

        # Find best performing model
        best_model = min(results.items(), key=lambda x: x[1]["response_time"])
        print(f"\nBest performing fallback model: {best_model[0]} "
              f"with time {best_model[1]['response_time']:.3f}s")

        # Response times should be reasonable
        for model, result in results.items():
            assert result["response_time"] < 5, f"Model {model} response time too slow"
            assert result["cost"] > 0, f"Model {model} should have cost"
            assert 0 <= result["confidence"] <= 1, f"Model {model} confidence should be valid"