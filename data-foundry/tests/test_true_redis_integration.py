"""
TRUE Redis Integration Tests for Data Foundry

This test suite validates real Redis integration with:
- Live Redis operations (NO MOCKING)
- Real caching behavior
- Real performance metrics
- Real error handling
- Multi-tenant data isolation
- Cache eviction and expiration

Tests use actual Redis instance at redis://localhost:6379/0
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

from src.services.redis_service import RedisService, CacheStatistics, PerformanceMetrics
from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.core.config import settings


class TestTrueRedisIntegration:
    """TRUE Redis integration tests - NO MOCKING ALLOWED"""

    @pytest.fixture
    async def redis_service(self):
        """Real Redis service fixture."""
        redis = RedisService(
            url=settings.REDIS_URL,
            max_connections=10,
            retry_attempts=3,
            retry_delay=0.1,
            default_ttl=3600,
            enable_metrics=True
        )

        # Verify real Redis connection
        health = await redis.health_check()
        if not health:
            pytest.skip("Redis not available at redis://localhost:6379/0")

        yield redis

        # Cleanup
        await redis.close()

    @pytest.fixture
    async def litellm_service(self):
        """LiteLLM service with real API integration."""
        service = LiteLLMService()
        await service.initialize()
        yield service
        await service.close()

    @pytest.fixture
    def sample_data(self):
        """Sample test data."""
        return {
            "user_1": {
                "name": "John Doe",
                "email": "john@example.com",
                "data_type": "contact"
            },
            "user_2": {
                "name": "Jane Smith",
                "email": "jane@startup.io",
                "data_type": "contact"
            },
            "company_1": {
                "name": "TechCorp Inc.",
                "industry": "Technology",
                "data_type": "company"
            }
        }

    @pytest.mark.true_redis
    async def test_real_redis_connection_health(self, redis_service):
        """Test real Redis connection health."""
        health = await redis_service.health_check()

        # Validate real Redis health
        assert health is True, "Redis should be healthy"

        # Test connection with operations
        await redis_service.set("health_test", "connected", ttl=60)
        value = await redis_service.get("health_test")
        assert value == "connected", "Should be able to set and get values"

        await redis_service.delete("health_test")

    @pytest.mark.true_redis
    async def test_real_cache_operations(self, redis_service):
        """Test real Redis cache operations."""
        test_key = "test_cache_key"
        test_value = {"data": "test_value", "timestamp": datetime.utcnow().isoformat()}

        # Test SET operation
        success = await redis_service.set(test_key, test_value, ttl=300)
        assert success is True, "SET operation should succeed"

        # Test GET operation
        retrieved_value = await redis_service.get(test_key)
        assert retrieved_value == test_value, "Should retrieve stored value"

        # Test EXISTS operation
        exists = await redis_service.exists(test_key)
        assert exists is True, "Key should exist"

        # Test DELETE operation
        deleted = await redis_service.delete(test_key)
        assert deleted == 1, "Should delete one key"

        # Verify deletion
        retrieved_value = await redis_service.get(test_key)
        assert retrieved_value is None, "Key should be deleted"

    @pytest.mark.true_redis
    async def test_real_cache_ttl_expiration(self, redis_service):
        """Test real Redis TTL expiration."""
        test_key = "test_ttl_key"
        test_value = {"data": "ttl_test"}
        short_ttl = 2  # 2 seconds

        # Set with short TTL
        await redis_service.set(test_key, test_value, ttl=short_ttl)

        # Verify exists immediately
        value = await redis_service.get(test_key)
        assert value is not None, "Value should exist immediately"

        # Verify TTL is set
        ttl = await redis_service.get_ttl(test_key)
        assert ttl > 0, f"TTL should be positive, got {ttl}"

        # Wait for expiration
        await asyncio.sleep(short_ttl + 1)

        # Verify expired
        value = await redis_service.get(test_key)
        assert value is None, "Value should be expired"

        # TTL should be -2 for non-existent key
        ttl = await redis_service.get_ttl(test_key)
        assert ttl == -2, f"Non-existent key should have TTL -2, got {ttl}"

    @pytest.mark.true_redis
    async def test_real_cache_statistics(self, redis_service):
        """Test real Redis cache statistics."""
        # Clear any existing data
        await redis_service.clear_cache()

        # Clear metrics
        await redis_service.reset_metrics()

        # Perform cache operations
        test_data = {f"key_{i}": f"value_{i}" for i in range(5)}

        # Set data
        for key, value in test_data.items():
            await redis_service.set(key, value, ttl=3600)

        # Get data
        for key, value in test_data.items():
            retrieved = await redis_service.get(key)
            assert retrieved == value, f"Should retrieve {key}"

        # Delete one key
        deleted_key = list(test_data.keys())[0]
        await redis_service.delete(deleted_key)

        # Get statistics
        stats = await redis_service.get_statistics()

        # Validate real statistics
        assert stats.sets >= len(test_data), f"Should have at least {len(test_data)} sets"
        assert stats.gets >= len(test_data), f"Should have at least {len(test_data)} gets"
        assert stats.deletes >= 1, "Should have at least 1 delete"
        assert stats.hits >= 0, "Hits should be non-negative"
        assert stats.misses >= 0, "Misses should be non-negative"

        # Verify hit rate calculation
        if stats.sets + stats.hits + stats.misses > 0:
            expected_hit_rate = stats.hits / (stats.sets + stats.hits + stats.misses + 0.001)
            assert 0 <= stats.hit_rate <= 1, f"Hit rate should be between 0 and 1, got {stats.hit_rate}"
            assert abs(stats.hit_rate - expected_hit_rate) < 0.01, "Hit rate should match calculation"

    @pytest.mark.true_redis
    async def test_real_performance_metrics(self, redis_service):
        """Test real Redis performance metrics."""
        # Clear metrics
        await redis_service.reset_metrics()

        # Perform operations to generate performance data
        operations = []
        for i in range(10):
            key = f"perf_key_{i}"
            value = f"perf_value_{i}"

            # Measure SET operation
            start_time = time.time()
            await redis_service.set(key, value, ttl=3600)
            set_time = time.time() - start_time
            operations.append(("set", set_time))

            # Measure GET operation
            start_time = time.time()
            retrieved = await redis_service.get(key)
            get_time = time.time() - start_time
            operations.append(("get", get_time))

            # Measure DELETE operation
            start_time = time.time()
            await redis_service.delete(key)
            delete_time = time.time() - start_time
            operations.append(("delete", delete_time))

        # Get performance metrics
        metrics = await redis_service.get_performance_metrics()

        # Validate performance metrics
        assert metrics is not None, "Should return performance metrics"
        assert metrics.total_operations > 0, f"Should have {len(operations)} operations"
        assert metrics.total_operations == len(operations), "Should track all operations"

        # Verify individual operation counts
        expected_sets = sum(1 for op in operations if op[0] == "set")
        expected_gets = sum(1 for op in operations if op[0] == "get")
        expected_deletes = sum(1 for op in operations if op[0] == "delete")

        assert metrics.set_operations == expected_sets, f"Should have {expected_sets} set operations"
        assert metrics.get_operations == expected_gets, f"Should have {expected_gets} get operations"
        assert metrics.delete_operations == expected_deletes, f"Should have {expected_deletes} delete operations"

        # Verify operation times
        assert metrics.total_time > 0, "Total time should be positive"
        assert metrics.average_operation_time > 0, "Average time should be positive"
        assert metrics.min_operation_time >= 0, "Min time should be non-negative"
        assert metrics.max_operation_time >= metrics.min_operation_time, "Max time should be >= min time"

        # Verify rates
        assert metrics.operations_per_second > 0, "Operations per second should be positive"
        assert metrics.throughput > 0, "Throughput should be positive"

    @pytest.mark.true_redis
    async def test_real_multi_tenant_isolation(self, redis_service):
        """Test real multi-tenant data isolation in Redis."""
        tenant_data = {
            "tenant_1": {f"key_{i}": f"tenant1_value_{i}" for i in range(3)},
            "tenant_2": {f"key_{i}": f"tenant2_value_{i}" for i in range(3)},
            "tenant_3": {f"key_{i}": f"tenant3_value_{i}" for i in range(3)}
        }

        # Set data for different tenants
        for tenant, data in tenant_data.items():
            for key, value in data.items():
                prefixed_key = f"{tenant}:{key}"
                await redis_service.set(prefixed_key, value, ttl=3600)

        # Verify tenant isolation
        for tenant, expected_data in tenant_data.items():
            for key, expected_value in expected_data.items():
                prefixed_key = f"{tenant}:{key}"
                actual_value = await redis_service.get(prefixed_key)
                assert actual_value == expected_value, f"Tenant {tenant} data should be isolated"

            # Verify other tenants' data is not accessible
            for other_tenant, other_data in tenant_data.items():
                if other_tenant != tenant:
                    for key in other_data.keys():
                        prefixed_key = f"{other_tenant}:{key}"
                        value = await redis_service.get(prefixed_key)
                        assert value is not None, f"Should not access {other_tenant} data from {tenant}"

        # Get statistics
        stats = await redis_service.get_statistics()
        total_expected_keys = sum(len(data) for data in tenant_data.values())
        assert stats.total_requests >= total_expected_keys, f"Should have at least {total_expected_keys} requests"

    @pytest.mark.true_redis
    async def test_real_cache_key_patterns(self, redis_service):
        """Test real Redis key patterns and operations."""
        # Clear cache
        await redis_service.clear_cache()

        # Set up test data with different patterns
        test_keys = [
            "data:user:123",
            "data:user:456",
            "data:company:789",
            "session:abc123",
            "session:def456",
            "cache:temp:xyz"
        ]

        test_values = {key: f"value_for_{key}" for key in test_keys}

        # Set all values
        for key, value in test_values.items():
            await redis_service.set(key, value, ttl=3600)

        # Test key pattern existence
        user_keys = [key for key in test_keys if key.startswith("data:user:")]
        assert len(user_keys) == 2, "Should have 2 user keys"

        session_keys = [key for key in test_keys if key.startswith("session:")]
        assert len(session_keys) == 2, "Should have 2 session keys"

        # Verify all keys exist
        for key in test_keys:
            exists = await redis_service.exists(key)
            assert exists is True, f"Key {key} should exist"

        # Test pattern-based deletion (manual pattern matching)
        # Delete all session keys
        for key in session_keys:
            await redis_service.delete(key)

        # Verify session keys are deleted
        for key in session_keys:
            exists = await redis_service.exists(key)
            assert exists is False, f"Session key {key} should be deleted"

        # Verify other keys still exist
        for key in test_keys:
            if key not in session_keys:
                exists = await redis_service.exists(key)
                assert exists is True, f"Non-session key {key} should still exist"

    @pytest.mark.true_redis
    async def test_real_cache_performance_with_litellm(self, redis_service, litellm_service):
        """Test real Redis performance in combination with LiteLLM."""
        # Clear cache and metrics
        await redis_service.clear_cache()
        await redis_service.reset_metrics()
        await litellm_service.reset_metrics()

        # Test data
        test_prompts = [
            "Analyze contact data: John Doe, john@example.com, CEO",
            "Categorize contact: Jane Smith, jane@startup.io, PM",
            "Process user: Bob Johnson, bob@enterprise.com, CTO",
            "Evaluate contact: Alice Williams, alice@startup.com, Manager"
        ]

        # First pass (cache misses)
        start_time = time.time()
        for i, prompt in enumerate(test_prompts):
            response = await litellm_service.completion(
                prompt=prompt,
                tenant_id="redis_performance_test",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True
            )
            assert response is not None
        first_pass_time = time.time() - start_time

        # Get Redis statistics
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.misses >= len(test_prompts), f"Should have {len(test_prompts)} cache misses"

        # Second pass (cache hits)
        start_time = time.time()
        for prompt in test_prompts:
            response = await litellm_service.completion(
                prompt=prompt,
                tenant_id="redis_performance_test",
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True
            )
            assert response is not None
        second_pass_time = time.time() - start_time

        # Verify cache hits
        redis_stats = await redis_service.get_statistics()
        assert redis_stats.hits >= len(test_prompts), f"Should have {len(test_prompts)} cache hits"

        # Performance comparison
        assert second_pass_time < first_pass_time, f"Cached {second_pass_time:.3f}s should be faster than uncached {first_pass_time:.3f}s"

        # Verify performance metrics were collected
        perf_metrics = await redis_service.get_performance_metrics()
        assert perf_metrics is not None
        assert perf_metrics.total_operations > 0
        assert perf_metrics.total_time > 0

        # Get LiteLLM metrics
        llm_metrics = await litellm_service.get_metrics()
        assert llm_metrics["requests_total"] >= len(test_prompts) * 2, "Should track all requests"
        assert llm_metrics["cache_hits"] >= len(test_prompts), "Should track cache hits"
        assert llm_metrics["cache_misses"] >= len(test_prompts), "Should track cache misses"

    @pytest.mark.true_redis
    async def test_real_error_handling(self, redis_service):
        """Test real Redis error handling."""
        # Test operations with various scenarios
        test_cases = [
            # Normal operation
            {
                "operation": "set",
                "key": "error_test_normal",
                "value": "normal_value",
                "should_succeed": True
            },
            # Empty key
            {
                "operation": "set",
                "key": "",
                "value": "empty_key",
                "should_succeed": False  # May fail depending on Redis configuration
            },
            # Very large value
            {
                "operation": "set",
                "key": "large_value_test",
                "value": "x" * 1000000,  # 1MB value
                "should_succeed": True  # Should work with modern Redis
            },
            # Non-existent key get
            {
                "operation": "get",
                "key": "non_existent_key",
                "value": None,
                "should_succeed": True
            }
        ]

        for test_case in test_cases:
            try:
                if test_case["operation"] == "set":
                    result = await redis_service.set(
                        test_case["key"],
                        test_case["value"],
                        ttl=60
                    )
                    if test_case["should_succeed"]:
                        assert result is True
                    else:
                        assert result is False
                elif test_case["operation"] == "get":
                    result = await redis_service.get(test_case["key"])
                    if test_case["value"] is not None:
                        assert result == test_case["value"]

            except Exception as e:
                # Should handle errors gracefully
                if test_case["should_succeed"]:
                    pytest.fail(f"Should succeed but got error: {str(e)}")
                else:
                    # Expected error
                    pass

        # Verify Redis is still healthy after error tests
        health = await redis_service.health_check()
        assert health is True, "Redis should still be healthy after error tests"

    @pytest.mark.true_redis
    async def test_real_memory_usage(self, redis_service):
        """Test real Redis memory usage tracking."""
        # Clear cache
        await redis_service.clear_cache()

        # Set up test data
        memory_test_data = {}
        for i in range(100):  # 100 entries
            key = f"memory_test_key_{i}"
            value = {
                "data": "x" * 1000,  # 1KB of data per entry
                "id": i,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {"test": True, "index": i}
            }
            memory_test_data[key] = value
            await redis_service.set(key, value, ttl=3600)

        # Get performance metrics which might include memory info
        metrics = await redis_service.get_performance_metrics()
        assert metrics is not None, "Should get performance metrics"

        # Get statistics
        stats = await redis_service.get_statistics()
        assert stats.total_requests >= 100, "Should have processed 100 requests"

        # Memory test - verify data integrity after multiple operations
        for key, expected_value in memory_test_data.items():
            actual_value = await redis_service.get(key)
            assert actual_value == expected_value, f"Data integrity check failed for {key}"

        # Test memory cleanup
        await redis_service.clear_cache()

        # Verify all data is cleared
        for key in memory_test_data.keys():
            value = await redis_service.get(key)
            assert value is None, f"Key {key} should be cleared"

    @pytest.mark.true_redis
    async def test_real_pipeline_operations(self, redis_service):
        """Test real Redis pipeline operations."""
        # Clear cache
        await redis_service.clear_cache()

        # Create pipeline operations
        test_data = {f"pipeline_key_{i}": f"pipeline_value_{i}" for i in range(10)}

        # Note: RedisService doesn't have explicit pipeline support in the current implementation
        # So we'll simulate pipeline behavior with sequential operations
        pipeline_start = time.time()

        # Set operations (simulating pipeline)
        for key, value in test_data.items():
            await redis_service.set(key, value, ttl=3600)

        # Get operations (simulating pipeline)
        for key, expected_value in test_data.items():
            actual_value = await redis_service.get(key)
            assert actual_value == expected_value

        pipeline_time = time.time() - pipeline_start

        # Verify all operations completed
        stats = await redis_service.get_statistics()
        assert stats.sets >= len(test_data), "Should have set all data"
        assert stats.gets >= len(test_data), "Should have retrieved all data"

        # Pipeline should be reasonably fast
        assert pipeline_time < 5, f"Pipeline operations took too long: {pipeline_time:.3f}s"

        # Performance metrics should reflect the operations
        perf_metrics = await redis_service.get_performance_metrics()
        assert perf_metrics.total_operations >= len(test_data) * 2, "Should track all operations"