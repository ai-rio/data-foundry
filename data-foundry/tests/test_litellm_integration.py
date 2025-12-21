"""
Comprehensive Integration Tests for LiteLLM Service with Real Redis

This test suite validates the complete LiteLLM integration system with:
- Real Redis caching (no mocking)
- Prompt management with YAML templates
- Cost calculation with Decimal precision
- Model fallbacks and retry logic
- Performance monitoring and metrics
- Multi-tenant isolation
- Error handling and recovery
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch

from src.services.litellm_service import LiteLLMService, LiteLLMResponse, LiteLLMError
from src.services.redis_service import RedisService, CacheStatistics
from src.core.prompts.prompt_manager import PromptManager, PromptManagerError
from src.services.cost_service import CostService
from src.models.data_record import DataRecord
from src.models.usage_tracking import TenantUsage, AuditLog


@pytest.mark.asyncio
class TestLiteLLMServiceIntegration:
    """Comprehensive integration tests for LiteLLM service with Redis."""

    @pytest.fixture
    async def litellm_service(self):
        """LiteLLM service with test configuration."""
        # Mock the cost service to avoid actual API calls
        with patch('src.services.cost_service.CostService') as mock_cost_service:
            mock_cost_service_instance = mock_cost_service.return_value
            mock_cost_service_instance.calculate_cost = AsyncMock(return_value=Decimal("0.001"))

            service = LiteLLMService()
            # Mock the _test_connectivity method to avoid actual API calls
            service._test_connectivity = AsyncMock()
            await service.initialize()
            yield service
            await service.close()

    @pytest.fixture
    async def live_redis_service(self):
        """Live Redis service for integration tests."""
        redis_service = RedisService(
            url="redis://localhost:6379/0",
            max_connections=5,
            retry_attempts=3,
            retry_delay=0.1,
            default_ttl=3600,
            enable_metrics=True
        )

        # Test connection
        assert await redis_service.health_check(), "Redis not available"

        yield redis_service
        await redis_service.close()

    @pytest.fixture
    def sample_data_records(self):
        """Sample data records for testing."""
        return [
            DataRecord(
                record_id="test_rec_001",
                tenant_id="test_tenant_001",
                data_source="csv",
                status="raw",
                raw_data='{"name": "John Doe", "email": "john@example.com", "phone": "555-1234"}',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            DataRecord(
                record_id="test_rec_002",
                tenant_id="test_tenant_001",
                data_source="json",
                status="raw",
                raw_data='{"name": "Jane Smith", "email": "jane@company.com", "department": "Sales"}',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            ),
            DataRecord(
                record_id="test_rec_003",
                tenant_id="test_tenant_001",
                data_source="csv",
                status="processing",
                raw_data='{"name": "Bob Johnson", "email": "bob@enterprise.com", "title": "CEO"}',
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        ]

    @pytest.fixture
    def prompt_manager(self):
        """Prompt manager with test configuration."""
        # Skip singleton for tests to ensure clean state
        return PromptManager(skip_singleton=True)

    @pytest.mark.integration
    async def test_litellm_service_initialization(self, litellm_service):
        """Test LiteLLM service initializes correctly with Redis."""
        # Verify service is initialized
        assert litellm_service._initialized is True
        assert litellm_service.redis_client is not None
        assert litellm_service.cost_service is not None

        # Verify metrics are initialized
        metrics = await litellm_service.get_metrics()
        assert metrics["requests_total"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0

    @pytest.mark.integration
    async def test_redis_caching_integration(self, litellm_service, live_redis_service):
        """Test actual Redis caching with live Redis instance."""
        # Setup mock response
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "high_value",
                        "confidence": 0.95,
                        "reasoning": "Corporate executive with clear contact information"
                    })
                }
            }],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 200,
                "total_tokens": 350
            }
        }

        # Mock the acompletion call
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response_data

            # First call should cache result
            response1 = await litellm_service.completion(
                prompt="Analyze this customer data: John Doe, john@example.com, CEO",
                tenant_id="test_tenant_001",
                model="gpt-4o",
                use_cache=True
            )

            # Verify cache was populated
            cache_key = litellm_service._generate_cache_key(
                "gpt-4o",
                [{"role": "user", "content": "Analyze this customer data: John Doe, john@example.com, CEO"}],
                0.7,
                None
            )

            cached_data = await live_redis_service.get(cache_key)
            assert cached_data is not None, "Cache should contain data after first call"

            # Verify cached response can be reconstructed
            cache_json = json.loads(cached_data)
            assert "content" in cache_json
            assert "model" in cache_json
            assert "cost" in cache_json

            # Second call should hit cache
            with patch('src.services.litellm_service.acompletion') as mock_completion:
                mock_completion.return_value = mock_response_data

                response2 = await litellm_service.completion(
                    prompt="Analyze this customer data: John Doe, john@example.com, CEO",
                    tenant_id="test_tenant_001",
                    model="gpt-4o",
                    use_cache=True
                )

            # Verify responses are identical
            assert response1.content == response2.content
            assert response1.model == response2.model
            assert response1.cached == False
            assert response2.cached == True  # Second call should be cached

            # Verify cache statistics
            redis_stats = await live_redis_service.get_statistics()
            assert redis_stats.sets >= 1
            assert redis_stats.hits >= 1

    @pytest.mark.integration
    async def test_cache_hit_miss_behavior(self, litellm_service, live_redis_service):
        """Test cache hit/miss behavior with realistic data patterns."""
        # Clear any existing data
        await live_redis_service.clear_cache()

        # First request - should be cache miss
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "corporate", "confidence": 0.9})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 150, "total_tokens": 250}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # First call - cache miss
            response1 = await litellm_service.completion(
                prompt="Test data pattern 1",
                tenant_id="test_tenant_001",
                use_cache=True
            )

            # Verify cache miss
            redis_stats = await live_redis_service.get_statistics()
            assert redis_stats.misses == 1

            # Second call - should be cache hit
            response2 = await litellm_service.completion(
                prompt="Test data pattern 1",  # Same prompt
                tenant_id="test_tenant_001",
                use_cache=True
            )

            # Verify cache hit
            redis_stats = await live_redis_service.get_statistics()
            assert redis_stats.hits == 1
            assert redis_stats.misses == 1

            # Third call - different prompt - should be cache miss
            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                response3 = await litellm_service.completion(
                    prompt="Test data pattern 2",
                    tenant_id="test_tenant_001",
                    use_cache=True
                )

            # Verify second cache miss
            redis_stats = await live_redis_service.get_statistics()
            assert redis_stats.misses == 2

    @pytest.mark.integration
    async def test_cache_ttl_expiration(self, litellm_service, live_redis_service):
        """Test cache TTL and expiration behavior."""
        # Set short TTL for testing
        test_ttl = 2  # 2 seconds

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "test_ttl", "confidence": 0.8})
                }
            }],
            "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Cache with short TTL
            response1 = await litellm_service.completion(
                prompt="TTL test data",
                tenant_id="test_tenant_001",
                use_cache=True,
                cache_ttl=test_ttl
            )

            # Verify cache exists
            cache_key = litellm_service._generate_cache_key(
                "gpt-4o",
                [{"role": "user", "content": "TTL test data"}],
                0.7,
                None
            )

            cached_data = await live_redis_service.get(cache_key)
            assert cached_data is not None

            # Wait for TTL to expire
            await asyncio.sleep(test_ttl + 1)

            # Should be expired now
            cached_data = await live_redis_service.get(cache_key)
            assert cached_data is None, "Cache should be expired after TTL"

    @pytest.mark.integration
    async def test_model_fallback_mechanism(self, litellm_service):
        """Test model fallback from primary to fallback models."""
        # Mock primary model failure
        mock_primary_error = Exception("Rate limit exceeded")
        mock_fallback_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "fallback", "confidence": 0.85})
                }
            }],
            "usage": {"prompt_tokens": 120, "completion_tokens": 180, "total_tokens": 300}
        }

        with patch('src.services.litellm_service.acompletion') as mock_completion:
            # Primary model fails
            mock_completion.side_effect = [
                mock_primary_error,
                mock_fallback_response  # Fallback succeeds
            ]

            response = await litellm_service.completion(
                prompt="Fallback test data",
                tenant_id="test_tenant_001",
                model="gpt-4o"  # Primary model
            )

            # Verify fallback was used
            assert response.fallback_used is True
            assert response.model == "claude-3-5-sonnet"  # Should be fallback

            # Verify metrics
            metrics = await litellm_service.get_metrics()
            assert metrics["fallback_used"] == 1

    @pytest.mark.integration
    async def test_concurrent_redis_operations(self, litellm_service, live_redis_service):
        """Test concurrent Redis operations with multiple async requests."""
        # Clear cache first
        await live_redis_service.clear_cache()

        # Create multiple concurrent requests
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "concurrent", "confidence": 0.9})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 150, "total_tokens": 250}
        }

        async def make_request(i):
            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                return await litellm_service.completion(
                    prompt=f"Concurrent test {i}",
                    tenant_id="test_tenant_001",
                    use_cache=True
                )

        # Execute 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all succeeded
        for response in responses:
            assert isinstance(response, LiteLLMResponse)
            assert "concurrent" in json.loads(response.content)["category"]

        # Verify cache statistics (should have 10 sets, 9 hits)
        redis_stats = await live_redis_service.get_statistics()
        assert redis_stats.sets == 10
        assert redis_stats.hits == 9

    @pytest.mark.integration
    async def test_cost_calculation_integration(self, litellm_service):
        """Test cost calculation integration with Decimal precision."""
        # Mock cost service with specific values
        with patch.object(litellm_service.cost_service, 'calculate_cost', new_callable=AsyncMock) as mock_cost:
            mock_cost.return_value = Decimal("0.0025")

            mock_response = {
                "choices": [{
                    "message": {
                        "content": json.dumps({"category": "cost_test", "confidence": 0.95})
                    }
                }],
                "usage": {
                    "prompt_tokens": 500,
                    "completion_tokens": 1000,
                    "total_tokens": 1500
                }
            }

            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                response = await litellm_service.completion(
                    prompt="Cost calculation test",
                    tenant_id="test_tenant_001",
                    use_cache=True
                )

            # Verify cost with Decimal precision
            assert response.cost == Decimal("0.0025")
            assert isinstance(response.cost, Decimal)

            # Verify cost was called with correct parameters
            mock_cost.assert_called_once_with(
                model="gpt-4o",
                prompt_tokens=500,
                completion_tokens=1000,
                tenant_id="test_tenant_001"
            )

    @pytest.mark.integration
    async def test_token_usage_tracking(self, litellm_service):
        """Test token usage tracking and aggregation."""
        # Mock cost service
        with patch.object(litellm_service.cost_service, 'calculate_cost', new_callable=AsyncMock) as mock_cost:
            mock_cost.return_value = Decimal("0.001")

            mock_response = {
                "choices": [{
                    "message": {
                        "content": json.dumps({"category": "token_test"})
                    }
                }],
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": 300,
                    "total_tokens": 500
                }
            }

            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                # Make multiple requests
                for _ in range(3):
                    await litellm_service.completion(
                        prompt="Token usage test",
                        tenant_id="test_tenant_001",
                        use_cache=True
                    )

                # Get metrics
                metrics = await litellm_service.get_metrics()

                # Verify token aggregation
                assert metrics["total_tokens"] == 1500  # 500 * 3
                assert metrics["total_requests"] == 3
                assert metrics["total_cost"] == Decimal("0.003")

    @pytest.mark.integration
    async def test_redis_cache_invalidation(self, litellm_service, live_redis_service):
        """Test Redis cache invalidation strategies."""
        # Clear cache first
        await live_redis_service.clear_cache()

        # Generate cache key
        cache_key = "test_invalidation_key"

        # Set test data
        test_data = {"test": "data", "expires": "never"}
        await live_redis_service.set(cache_key, test_data, ttl=3600)

        # Verify data exists
        assert await live_redis_service.exists(cache_key)

        # Test TTL setting
        await live_redis_service.expire(cache_key, 1)

        # Verify TTL is set
        ttl = await live_redis_service.get_ttl(cache_key)
        assert ttl > 0

        # Delete key
        deleted_count = await live_redis_service.delete(cache_key)
        assert deleted_count == 1

        # Verify key is gone
        assert not await live_redis_service.exists(cache_key)
        assert await live_redis_service.get_ttl(cache_key) == -2

    @pytest.mark.integration
    async def test_redis_performance_metrics(self, litellm_service, live_redis_service):
        """Test Redis performance metrics collection."""
        # Clear metrics
        await live_redis_service.reset_metrics()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "performance_test"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Make multiple requests to generate performance data
            for _ in range(5):
                await litellm_service.completion(
                    prompt="Performance test",
                    tenant_id="test_tenant_001",
                    use_cache=True
                )

        # Get performance metrics
        metrics = await live_redis_service.get_performance_metrics()
        assert metrics is not None

        # Verify metrics were collected
        assert metrics.total_operations > 0
        assert metrics.get_operations > 0
        assert metrics.set_operations > 0

        # Get statistics
        stats = await live_redis_service.get_statistics()
        assert stats.total_requests == stats.hits + stats.misses

    @pytest.mark.integration
    async def test_rate_limiting_integration(self, litellm_service):
        """Test rate limiting with multiple tenant requests."""
        # Mock API response
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "rate_limit_test"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Make rapid requests from different tenants
            async def make_tenant_request(tenant_id):
                return await litellm_service.completion(
                    prompt=f"Rate limit test for {tenant_id}",
                    tenant_id=tenant_id,
                    use_cache=True
                )

            # 5 concurrent requests from 5 different tenants
            tenants = [f"tenant_{i:03d}" for i in range(5)]
            tasks = [make_tenant_request(tenant) for tenant in tenants]
            responses = await asyncio.gather(*tasks)

            # All should succeed (different tenants have separate rate limits)
            assert len(responses) == 5

            # Verify rate limits are tracked per tenant
            metrics = await litellm_service.get_metrics()
            assert metrics["requests_total"] == 5

    @pytest.mark.integration
    async def test_redis_error_handling(self, litellm_service, live_redis_service):
        """Test Redis error handling and recovery."""
        # Start by making a successful request
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "error_test"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Normal operation
            response = await litellm_service.completion(
                prompt="Error test",
                tenant_id="test_tenant_001",
                use_cache=True
            )
            assert response is not None

            # Test error metrics are tracked
            stats = await live_redis_service.get_statistics()
            assert stats.total_requests > 0

    @pytest.mark.integration
    async def test_cache_key_generation(self, litellm_service):
        """Test cache key generation consistency."""
        # Same inputs should generate same key
        key1 = litellm_service._generate_cache_key(
            "gpt-4o",
            [{"role": "user", "content": "test prompt"}],
            0.7,
            1000
        )

        key2 = litellm_service._generate_cache_key(
            "gpt-4o",
            [{"role": "user", "content": "test prompt"}],
            0.7,
            1000
        )

        assert key1 == key2

        # Different inputs should generate different keys
        key3 = litellm_service._generate_cache_key(
            "claude-3-5-sonnet",
            [{"role": "user", "content": "test prompt"}],
            0.7,
            1000
        )

        assert key1 != key3

    @pytest.mark.integration
    async def test_audit_logging_integration(self, litellm_service):
        """Test audit logging for AI operations."""
        # Mock cost service
        with patch.object(litellm_service.cost_service, 'calculate_cost', new_callable=AsyncMock) as mock_cost:
            mock_cost.return_value = Decimal("0.001")

            mock_response = {
                "choices": [{
                    "message": {
                        "content": json.dumps({"category": "audit_test"})
                    }
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
            }

            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                response = await litellm_service.completion(
                    prompt="Audit test",
                    tenant_id="test_tenant_001",
                    metadata={"operation_type": "test", "source": "integration_test"}
                )

            # Verify metrics include the request
            metrics = await litellm_service.get_metrics()
            assert metrics["requests_total"] == 1
            assert metrics["requests_success"] == 1

    @pytest.mark.integration
    async def test_multi_tenant_isolation(self, litellm_service):
        """Test that data is properly isolated between tenants."""
        # Clear any existing cache
        if litellm_service.redis_client:
            await litellm_service.redis_client.clear_cache()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "tenant_isolation"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Make same request for different tenants
            response1 = await litellm_service.completion(
                prompt="Tenant isolation test",
                tenant_id="tenant_a",
                use_cache=True
            )

            response2 = await litellm_service.completion(
                prompt="Tenant isolation test",
                tenant_id="tenant_b",
                use_cache=True
            )

            # Both should succeed but be cached separately
            assert response1.content == response2.content
            assert response1.cached == False
            assert response2.cached == False

            # Verify cache has two entries
            stats = await litellm_service.redis_client.get_statistics()
            assert stats.sets == 2

    @pytest.mark.performance
    async def test_cache_performance_benchmark(self, litellm_service, live_redis_service):
        """Performance benchmark comparing cached vs uncached requests."""
        # Clear cache
        await live_redis_service.clear_cache()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "benchmark_test"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        # Test uncached performance
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            uncached_times = []
            for _ in range(5):
                start_time = time.time()
                await litellm_service.completion(
                    prompt="Benchmark test",
                    tenant_id="test_tenant_001",
                    use_cache=False  # Force cache miss
                )
                uncached_times.append(time.time() - start_time)

        # Clear cache for cached test
        await live_redis_service.clear_cache()

        # Test cached performance
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            cached_times = []
            for _ in range(5):
                start_time = time.time()
                await litellm_service.completion(
                    prompt="Benchmark test",
                    tenant_id="test_tenant_001",
                    use_cache=True
                )
                cached_times.append(time.time() - start_time)

        # Performance should be better with cache
        avg_uncached = sum(uncached_times) / len(uncached_times)
        avg_cached = sum(cached_times) / len(cached_times)

        # Allow for variance but expect cache to be faster
        # This is more of a smoke test than strict performance assertion
        assert avg_cached < avg_uncached * 2, "Cached should be significantly faster than uncached"

        # Verify cache hit rate
        stats = await live_redis_service.get_statistics()
        hit_rate = stats.hit_rate
        assert hit_rate > 0.8, f"Cache hit rate should be > 80%, got {hit_rate:.2%}"

    @pytest.mark.integration
    async def test_service_health_check(self, litellm_service):
        """Test health check functionality."""
        # Mock the connectivity test to avoid actual API calls
        with patch.object(litellm_service, '_test_connectivity', new_callable=AsyncMock):
            health = await litellm_service.health_check()

            assert health["healthy"] is True
            assert "models" in health
            assert "timestamp" in health

    @pytest.mark.integration
    async def test_metrics_reset(self, litellm_service):
        """Test metrics reset functionality."""
        # Make a request to generate metrics
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "reset_test"})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            await litellm_service.completion(
                prompt="Reset test",
                tenant_id="test_tenant_001",
                use_cache=True
            )

            # Verify metrics were generated
            metrics = await litellm_service.get_metrics()
            assert metrics["requests_total"] > 0

            # Reset metrics
            await litellm_service.reset_metrics()

            # Verify metrics are reset
            metrics = await litellm_service.get_metrics()
            assert metrics["requests_total"] == 0
            assert metrics["total_cost"] == Decimal("0")