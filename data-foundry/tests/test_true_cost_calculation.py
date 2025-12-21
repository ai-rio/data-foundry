"""
TRUE Cost Calculation Integration Tests

This test suite validates real cost calculation with:
- Actual OpenRouter API pricing
- Real token usage tracking
- Precise Decimal calculations
- Cost aggregation across tenants
- Performance cost tracking
- Accuracy validation against actual API costs

Tests use real API calls and validate actual costs.
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.services.redis_service import RedisService
from src.services.cost_service import CostService
from src.core.config import settings


class TestTrueCostCalculation:
    """TRUE cost calculation tests - NO MOCKING ALLOWED"""

    @pytest.fixture
    async def litellm_service(self):
        """LiteLLM service with real cost calculation."""
        service = LiteLLMService()
        await service.initialize()

        # Verify service is healthy
        health = await service.health_check()
        assert health["healthy"], "Service should be healthy"

        yield service
        await service.close()

    @pytest.fixture
    async def cost_service(self):
        """Real cost service."""
        cost_service = CostService()
        await cost_service.initialize()

        yield cost_service
        await cost_service.close()

    @pytest.fixture
    async def redis_service(self):
        """Real Redis service for cost caching."""
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
    def test_data_scenarios(self):
        """Various data scenarios for cost testing."""
        return [
            {
                "name": "simple_contact",
                "data": '{"name": "John Doe", "email": "john@example.com"}',
                "expected_tokens": {"prompt": 50, "completion": 75, "total": 125}
            },
            {
                "name": "complex_contact",
                "data": '{"name": "Jane Smith", "email": "jane@startup.io", "title": "Senior Product Manager", "company": "StartupIO Inc.", "phone": "+1-555-0123", "location": "San Francisco, CA", "website": "https://startup.io", "bio": "Experienced product leader with 10+ years in tech"}',
                "expected_tokens": {"prompt": 200, "completion": 300, "total": 500}
            },
            {
                "name": "company_data",
                "data": '{"name": "Enterprise Corp", "industry": "Technology", "size": "Large", "employees": 10000, "revenue": "500M", "founded": 1995, "ceo": "John Smith", "headquarters": "New York, NY"}',
                "expected_tokens": {"prompt": 150, "completion": 250, "total": 400}
            },
            {
                "name": "large_dataset",
                "data": json.dumps([{
                    "name": f"User {i}",
                    "email": f"user{i}@example.com",
                    "department": "Engineering" if i % 2 == 0 else "Sales",
                    "level": f"Level {i % 5}",
                    "skills": ["Python", "SQL", "ML"] if i % 3 == 0 else ["Java", "Spring"],
                    "experience_years": i + 1
                } for i in range(10)]),
                "expected_tokens": {"prompt": 400, "completion": 600, "total": 1000}
            }
        ]

    @pytest.mark.true_cost
    async def test_real_api_cost_accuracy(self, litellm_service, cost_service, test_data_scenarios):
        """Test real API cost accuracy against actual pricing."""
        scenario = test_data_scenarios[1]  # Use complex scenario

        start_time = time.time()

        # Make real API call
        response = await litellm_service.completion(
            prompt=f"Cost accuracy test: {scenario['data']}",
            tenant_id="test_cost_accuracy",
            model="openrouter/openai/gpt-4o-mini",
            use_cache=False
        )

        response_time = time.time() - start_time

        # Validate response
        assert response is not None
        assert response.cost > 0
        assert isinstance(response.cost, Decimal)

        # Verify real token usage
        actual_tokens = response.usage
        assert actual_tokens["prompt_tokens"] > 0
        assert actual_tokens["completion_tokens"] > 0
        assert actual_tokens["total_tokens"] > 0

        # Calculate expected cost using actual pricing
        # gpt-4o-mini pricing: $0.15 per 1M input tokens, $0.60 per 1M output tokens
        input_cost = (actual_tokens["prompt_tokens"] / 1_000_000) * Decimal("0.15")
        output_cost = (actual_tokens["completion_tokens"] / 1_000_000) * Decimal("0.60")
        expected_cost = input_cost + output_cost

        # Validate cost accuracy (allow small variance due to rounding)
        cost_variance = abs(response.cost - expected_cost)
        max_variance = expected_cost * Decimal("0.1")  # 10% tolerance

        assert cost_variance <= max_variance, (
            f"Cost variance too large: {response.cost} vs {expected_cost} "
            f"(variance: {cost_variance}, max allowed: {max_variance})"
        )

        # Validate response time
        assert response_time < 5, f"Response time too slow: {response_time:.2f}s"

        # Verify cost service calculation matches
        service_cost = await cost_service.calculate_cost(
            model="openrouter/openai/gpt-4o-mini",
            prompt_tokens=actual_tokens["prompt_tokens"],
            completion_tokens=actual_tokens["completion_tokens"],
            tenant_id="test_cost_accuracy"
        )

        assert service_cost == expected_cost, "Cost service should match manual calculation"

    @pytest.mark.true_cost
    async def test_real_decimal_precision(self, litellm_service, cost_service):
        """Test real Decimal precision in cost calculations."""
        # Test with various token amounts to verify precision
        test_cases = [
            {"prompt": 100, "completion": 200},  # Small amounts
            {"prompt": 15432, "completion": 25678},  # Medium amounts
            {"prompt": 1000000, "completion": 2000000},  # Large amounts
        ]

        for i, tokens in enumerate(test_cases):
            prompt_tokens = tokens["prompt"]
            completion_tokens = tokens["completion"]

            start_time = time.time()
            response = await litellm_service.completion(
                prompt=f"Precision test {i}: " + "x" * prompt_tokens // 100,
                tenant_id="test_decimal_precision",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=False
            )
            response_time = time.time() - start_time

            # Validate cost precision
            assert isinstance(response.cost, Decimal), f"Cost should be Decimal for case {i}"
            assert response.cost > 0, f"Cost should be positive for case {i}"
            assert response_time < 5, f"Response time too slow for case {i}: {response_time:.2f}s"

            # Verify no floating point errors
            cost_str = str(response.cost)
            assert not cost_str.endswith(".000000"), f"Should avoid floating point artifacts: {cost_str}"

            # Compare with cost service
            service_cost = await cost_service.calculate_cost(
                model="openrouter/openai/gpt-4o-mini",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                tenant_id="test_decimal_precision"
            )

            assert service_cost == response.cost, f"Cost service should match API cost for case {i}"

    @pytest.mark.true_cost
    async def test_real_cost_aggregation(self, litellm_service, cost_service, test_data_scenarios):
        """Test real cost aggregation across multiple requests."""
        # Clear metrics
        await litellm_service.reset_metrics()

        tenant_id = "test_cost_aggregation"
        total_expected_cost = Decimal("0")
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}

        # Make multiple requests
        for i, scenario in enumerate(test_data_scenarios):
            start_time = time.time()
            response = await litellm_service.completion(
                prompt=f"Aggregation test {i}: {scenario['data']}",
                tenant_id=tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=False
            )
            response_time = time.time() - start_time

            # Accumulate costs and tokens
            total_expected_cost += response.cost
            total_tokens["prompt"] += response.usage["prompt_tokens"]
            total_tokens["completion"] += response.usage["completion_tokens"]
            total_tokens["total"] += response.usage["total_tokens"]

            assert response_time < 5, f"Request {i} too slow: {response_time:.2f}s"

        # Verify aggregated metrics
        metrics = await litellm_service.get_metrics()

        assert metrics["total_cost"] == total_expected_cost, (
            f"Aggregated cost should match: {metrics['total_cost']} vs {total_expected_cost}"
        )
        assert metrics["total_tokens"] == total_tokens["total"], (
            f"Aggregated tokens should match: {metrics['total_tokens']} vs {total_tokens['total']}"
        )
        assert metrics["requests_total"] == len(test_data_scenarios), (
            f"Request count should match: {metrics['requests_total']} vs {len(test_data_scenarios)}"
        )

        # Verify cost service aggregation
        tenant_usage = await cost_service.get_tenant_usage(tenant_id)
        assert tenant_usage.total_cost == total_expected_cost, "Tenant usage should match aggregated cost"
        assert tenant_usage.total_tokens == total_tokens["total"], "Tenant tokens should match aggregated tokens"
        assert tenant_usage.request_count == len(test_data_scenarios), "Tenant request count should match"

    @pytest.mark.true_cost
    async def test_real_model_cost_comparison(self, litellm_service, cost_service, test_data_scenarios):
        """Test real cost comparison between different models."""
        test_data = test_data_scenarios[2]["data"]  # Use company data
        models = ["openrouter/openai/gpt-4o-mini", "openrouter/anthropic/claude-3.5-sonnet", "openrouter/openai/gpt-4o"]

        cost_results = {}

        for model in models:
            try:
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=f"Model comparison: {test_data}",
                    tenant_id="test_model_comparison",
                    model=model,
                    use_cache=False
                )
                response_time = time.time() - start_time

                # Record results
                cost_results[model] = {
                    "cost": response.cost,
                    "response_time": response_time,
                    "tokens": response.usage,
                    "provider": response.provider
                }

                # Validate response
                assert response.cost > 0, f"Model {model} should have cost"
                assert isinstance(response.cost, Decimal), f"Model {model} cost should be Decimal"
                assert response_time < 5, f"Model {model} response time too slow: {response_time:.2f}s"

            except Exception as e:
                pytest.fail(f"Model {model} cost test failed: {str(e)}")

        # Verify all models were tested
        assert len(cost_results) == len(models), f"Should test all {len(models)} models"

        # Cost comparison
        costs = [result["cost"] for result in cost_results.values()]
        min_cost = min(costs)
        max_cost = max(costs)

        # Validate cost ranges (gpt-4o-mini should be cheapest, gpt-4o most expensive)
        assert cost_results["openrouter/openai/gpt-4o-mini"]["cost"] == min_cost, "gpt-4o-mini should be cheapest"
        assert cost_results["openrouter/openai/gpt-4o"]["cost"] == max_cost, "gpt-4o should be most expensive"

        # Verify cost service calculations for each model
        for model, result in cost_results.items():
            service_cost = await cost_service.calculate_cost(
                model=model,
                prompt_tokens=result["tokens"]["prompt_tokens"],
                completion_tokens=result["tokens"]["completion_tokens"],
                tenant_id="test_model_comparison"
            )

            assert service_cost == result["cost"], (
                f"Cost service should match for {model}: {service_cost} vs {result['cost']}"
            )

    @pytest.mark.true_cost
    async def test_real_cost_caching_impact(self, litellm_service, redis_service, test_data_scenarios):
        """Test real cost impact of Redis caching."""
        # Clear cache
        await redis_service.clear_cache()

        scenario = test_data_scenarios[1]  # Complex scenario
        test_prompt = f"Caching impact test: {scenario['data']}"

        # First pass (cache misses - real API calls)
        start_time = time.time()
        first_pass_costs = []
        first_pass_tokens = []

        for i in range(3):
            response = await litellm_service.completion(
                prompt=test_prompt,
                tenant_id="test_cache_impact",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True  # Will be cache miss
            )
            first_pass_costs.append(response.cost)
            first_pass_tokens.append(response.usage["total_tokens"])

        first_pass_time = time.time() - start_time
        first_pass_total_cost = sum(first_pass_costs)

        # Verify cache misses
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.misses >= 3, f"Should have 3 cache misses: {redis_stats.misses}"

        # Second pass (cache hits - no API calls)
        start_time = time.time()
        second_pass_costs = []
        second_pass_tokens = []

        for i in range(3):
            response = await litellm_service.completion(
                prompt=test_prompt,
                tenant_id="test_cache_impact",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True  # Should be cache hit
            )
            second_pass_costs.append(response.cost)
            second_pass_tokens.append(response.usage["total_tokens"])

        second_pass_time = time.time() - start_time
        second_pass_total_cost = sum(second_pass_costs)

        # Verify cache hits
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.hits >= 3, f"Should have 3 cache hits: {redis_stats.hits}"

        # Performance comparison
        assert second_pass_time < first_pass_time, (
            f"Cached {second_pass_time:.3f}s should be faster than uncached {first_pass_time:.3f}s"
        )

        # Cost should be identical (cached responses)
        assert second_pass_total_cost == first_pass_total_cost, "Cached costs should match original"

        # Individual costs should be identical
        for i in range(3):
            assert second_pass_costs[i] == first_pass_costs[i], (
                f"Cost {i} should match: {second_pass_costs[i]} vs {first_pass_costs[i]}"
            )

    @pytest.mark.true_cost
    async def test_real_cost_error_handling(self, litellm_service, cost_service):
        """Test real cost error handling."""
        error_scenarios = [
            ("very_long_prompt", "x" * 100000),  # Very long prompt
            ("special_characters", "Special chars: áéíóú 中文 🚀"),
            ("malformed_json", "Invalid json: {test"),
            ("empty_prompt", ""),
        ]

        for scenario_name, prompt in error_scenarios:
            try:
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=f"Error test {scenario_name}: {prompt}",
                    tenant_id="test_error_costs",
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=False
                )
                response_time = time.time() - start_time

                # Should still return cost even for errors
                assert response.cost > 0, f"Should have cost for {scenario_name}"
                assert isinstance(response.cost, Decimal), f"Cost should be Decimal for {scenario_name}"
                assert response_time < 5, f"Response time too slow for {scenario_name}: {response_time:.2f}s"

            except Exception as e:
                # Should handle gracefully
                assert "error" in str(e).lower(), f"Should handle error gracefully for {scenario_name}"

        # Verify cost service remains functional
        try:
            test_cost = await cost_service.calculate_cost(
                model="openrouter/openai/gpt-4o-mini",
                prompt_tokens=100,
                completion_tokens=200,
                tenant_id="test_error_costs"
            )
            assert test_cost > 0, "Cost service should remain functional"
        except Exception as e:
            pytest.fail(f"Cost service should remain functional: {str(e)}")

    @pytest.mark.true_cost
    async def test_real_cost_performance_tracking(self, litellm_service, cost_service, test_data_scenarios):
        """Test real cost performance tracking."""
        # Reset metrics
        await litellm_service.reset_metrics()

        tenant_id = "test_performance_tracking"
        total_cost = Decimal("0")
        total_processing_time = 0

        # Process multiple scenarios
        for scenario in test_data_scenarios:
            start_time = time.time()

            response = await litellm_service.completion(
                prompt=f"Performance test: {scenario['data']}",
                tenant_id=tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=False
            )

            response_time = time.time() - start_time
            processing_time = response.response_time_ms / 1000

            # Accumulate metrics
            total_cost += response.cost
            total_processing_time += response_time

            # Validate performance metrics
            assert response.cost > 0, "Should have cost"
            assert response_time < 5, f"Response time too slow: {response_time:.2f}s"
            assert processing_time > 0, "Processing time should be positive"
            assert response.response_time_ms > 0, "Response time in ms should be positive"

            # Calculate cost per second
            cost_per_second = response.cost / processing_time
            assert cost_per_second > 0, "Cost per second should be positive"

        # Verify aggregate metrics
        metrics = await litellm_service.get_metrics()

        assert metrics["total_cost"] == total_cost, "Total cost should match"
        assert metrics["total_tokens"] > 0, "Total tokens should be tracked"
        assert metrics["requests_total"] == len(test_data_scenarios), "Request count should match"

        # Calculate performance metrics
        avg_response_time = total_processing_time / len(test_data_scenarios)
        avg_cost_per_request = total_cost / len(test_data_scenarios)

        # Validate performance benchmarks
        assert avg_response_time < 3, f"Average response time too slow: {avg_response_time:.2f}s"
        assert avg_cost_per_request > 0, "Average cost should be positive"
        assert avg_cost_per_request < Decimal("0.10"), "Average cost should be small"

        # Verify tenant usage tracking
        tenant_usage = await cost_service.get_tenant_usage(tenant_id)
        assert tenant_usage.total_cost == total_cost, "Tenant usage should match"
        assert tenant_usage.request_count == len(test_data_scenarios), "Tenant request count should match"

    @pytest.mark.true_cost
    async def test_real_cost_currency_precision(self, litellm_service, cost_service):
        """Test real currency precision with different decimal places."""
        # Test with various token amounts to test precision
        test_cases = [
            {"prompt": 1, "completion": 1},  # Minimal tokens
            {"prompt": 100, "completion": 200},  # Small amounts
            {"prompt": 10000, "completion": 20000},  # Medium amounts
            {"prompt": 1000000, "completion": 2000000},  # Large amounts
        ]

        for i, tokens in enumerate(test_cases):
            prompt_tokens = tokens["prompt"]
            completion_tokens = tokens["completion"]

            start_time = time.time()
            response = await litellm_service.completion(
                prompt=f"Currency precision {i}: " + "a" * prompt_tokens // 100,
                tenant_id="test_currency_precision",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=False
            )
            response_time = time.time() - start_time

            # Validate currency precision
            cost_str = str(response.cost)
            decimal_places = len(cost_str.split('.')[1]) if '.' in cost_str else 0

            # Should have appropriate decimal places (up to 6 for billing)
            assert decimal_places <= 6, f"Too many decimal places: {decimal_places} in {cost_str}"
            assert response.cost > 0, f"Cost should be positive for case {i}"
            assert response_time < 5, f"Response time too slow for case {i}: {response_time:.2f}s"

            # Verify no arithmetic errors
            manual_cost = (
                (prompt_tokens / 1_000_000) * Decimal("0.15") +
                (completion_tokens / 1_000_000) * Decimal("0.60")
            )
            assert abs(response.cost - manual_cost) < Decimal("0.000001"), (
                f"Cost calculation error for case {i}: {response.cost} vs {manual_cost}"
            )

    @pytest.mark.true_cost
    async def test_real_cost_scaling(self, litellm_service, cost_service):
        """Test real cost scaling with large token volumes."""
        # Create large prompt to test scaling
        large_prompt = json.dumps([{
            "user_id": i,
            "name": f"User {i}",
            "email": f"user{i}@example.com",
            "data": "x" * 100,  # 100 chars per user
            "metadata": {"created": "2024-01-01", "type": "test"}
        } for i in range(100)])  # 100 users

        start_time = time.time()
        response = await litellm_service.completion(
            prompt=f"Scaling test: {large_prompt}",
            tenant_id="test_cost_scaling",
            model="openrouter/openai/gpt-4o-mini",
            use_cache=False
        )
        response_time = time.time() - start_time

        # Validate scaling behavior
        assert response.cost > Decimal("0.01"), "Large prompt should have significant cost"
        assert response.cost < Decimal("1.00"), "Cost should be reasonable"
        assert response.usage["prompt_tokens"] > 10000, "Should have many tokens"
        assert response_time < 5, f"Large prompt too slow: {response_time:.2f}s"

        # Verify cost service handles large numbers
        service_cost = await cost_service.calculate_cost(
            model="openrouter/openai/gpt-4o-mini",
            prompt_tokens=response.usage["prompt_tokens"],
            completion_tokens=response.usage["completion_tokens"],
            tenant_id="test_cost_scaling"
        )

        assert service_cost == response.cost, "Cost service should handle large numbers"
        assert service_cost > Decimal("0.01"), "Service should recognize significant cost"

    @pytest.mark.true_cost
    async def test_real_cost_multi_tenant_tracking(self, litellm_service, cost_service):
        """Test real cost tracking across multiple tenants."""
        tenants = ["tenant_alpha", "tenant_beta", "tenant_gamma"]
        tenant_costs = {tenant: Decimal("0") for tenant in tenants}

        # Process requests for each tenant
        for i, tenant in enumerate(tenants):
            for j in range(2):  # 2 requests per tenant
                start_time = time.time()
                response = await litellm_service.completion(
                    prompt=f"Multi-tenant test {tenant}-{j}: Request data",
                    tenant_id=tenant,
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=False
                )
                response_time = time.time() - start_time

                # Track tenant costs
                tenant_costs[tenant] += response.cost

                assert response_time < 5, f"Tenant {tenant} request {j} too slow: {response_time:.2f}s"
                assert response.cost > 0, f"Tenant {tenant} should have cost"

        # Verify individual tenant cost tracking
        for tenant, expected_cost in tenant_costs.items():
            tenant_usage = await cost_service.get_tenant_usage(tenant)
            assert tenant_usage.total_cost == expected_cost, (
                f"Tenant {tenant} cost should match: {tenant_usage.total_cost} vs {expected_cost}"
            )
            assert tenant_usage.request_count == 2, f"Tenant {tenant} should have 2 requests"

        # Verify overall totals
        total_cost = sum(tenant_costs.values())
        overall_usage = await cost_service.get_tenant_usage("all")

        # Note: "all" might not be a valid tenant ID, so check what we get
        if overall_usage:
            assert overall_usage.total_cost >= total_cost, "Overall cost should include all tenants"

    @pytest.mark.true_cost
    async def test_real_cost_cache_invalidation(self, litellm_service, redis_service):
        """Test real cost cache invalidation behavior."""
        # Clear cache
        await redis_service.clear_cache()

        test_prompt = "Cache invalidation test: Data"
        tenant_id = "test_cache_invalidation"

        # First request
        response1 = await litellm_service.completion(
            prompt=test_prompt,
            tenant_id=tenant_id,
            model="openrouter/openai/gpt-4o-mini",
            use_cache=True
        )
        cost1 = response1.cost

        # Verify cached
        assert response1.cached is False, "First request should not be cached"

        # Second identical request
        response2 = await litellm_service.completion(
            prompt=test_prompt,
            tenant_id=tenant_id,
            model="openrouter/openai/gpt-4o-mini",
            use_cache=True
        )
        cost2 = response2.cost

        # Should be cached and same cost
        assert response2.cached is True, "Second request should be cached"
        assert cost1 == cost2, "Cached costs should be identical"

        # Third request with different prompt
        response3 = await litellm_service.completion(
            prompt="Different prompt: Data",
            tenant_id=tenant_id,
            model="openrouter/openai/gpt-4o-mini",
            use_cache=True
        )
        cost3 = response3.cost

        # Should not be cached and should have different cost
        assert response3.cached is False, "Different prompt should not be cached"
        assert cost3 != cost1, "Different prompts should have different costs"

        # Verify cache statistics reflect this
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.sets >= 2, f"Should have at least 2 cache entries: {redis_stats.sets}"
        assert redis_stats.hits >= 1, f"Should have at least 1 cache hit: {redis_stats.hits}"
        assert redis_stats.misses >= 2, f"Should have at least 2 cache misses: {redis_stats.misses}"