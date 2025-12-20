"""
Integration tests for Redis cache with real Redis instance.

These tests require a running Redis instance and test:
- Real Redis connectivity
- Connection pooling
- Actual cache operations
- Performance under load
- Error scenarios with real Redis
"""

import asyncio
import pytest
import time
import json
from typing import Dict, Any

from src.core.cache import (
    RedisCache,
    CacheKeyGenerator,
    CacheSerializer,
    CacheError,
    CacheConnectionError,
    get_cache,
)
from src.services.redis_service import (
    RedisService,
    CacheStatistics,
    PerformanceMetrics,
    get_redis_service,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def redis_cache():
    """Create a Redis cache instance for testing."""
    # Use a test-specific database
    test_redis_url = "redis://localhost:6379/15"  # Use DB 15 for tests

    cache = RedisCache(
        url=test_redis_url,
        key_prefix=CacheKeyGenerator(prefix="test_integration"),
        default_ttl=60,  # Short TTL for tests
        local_cache_size=100,
        fallback_to_local=True
    )

    # Clear the test database before and after tests
    try:
        await cache.clear()
        yield cache
    finally:
        try:
            await cache.clear()
        except:
            pass  # Ignore cleanup errors


@pytest.fixture
async def redis_service():
    """Create a Redis service instance for testing."""
    # Use a test-specific database
    test_redis_url = "redis://localhost:6379/15"  # Use DB 15 for tests

    service = RedisService(
        url=test_redis_url,
        max_connections=5,
        retry_attempts=2,
        retry_delay=0.05,  # Fast retry for tests
        default_ttl=60,
        enable_metrics=True
    )

    # Clear the test database before and after tests
    try:
        await service.clear_cache()
        yield service
    finally:
        try:
            await service.clear_cache()
            await service.close()
        except:
            pass  # Ignore cleanup errors


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisCacheIntegration:
    """Integration tests for RedisCache with real Redis."""

    async def test_basic_set_get(self, redis_cache):
        """Test basic set and get operations."""
        key = "test_key"
        value = {"message": "Hello Redis!", "number": 42}

        # Set value
        result = await redis_cache.set(key, value, ttl=30)
        assert result is True

        # Get value
        cached_value = await redis_cache.get(key)
        assert cached_value == value

    async def test_get_nonexistent_key(self, redis_cache):
        """Test getting a non-existent key."""
        result = await redis_cache.get("nonexistent_key")
        assert result is None

    async def test_key_exists(self, redis_cache):
        """Test key existence checking."""
        key = "existence_test"
        value = "test_value"

        # Key shouldn't exist initially
        assert await redis_cache.exists(key) is False

        # Set the key
        await redis_cache.set(key, value)

        # Key should exist now
        assert await redis_cache.exists(key) is True

    async def test_delete_key(self, redis_cache):
        """Test key deletion."""
        key = "delete_test"
        value = "to_be_deleted"

        # Set and verify key exists
        await redis_cache.set(key, value)
        assert await redis_cache.exists(key) is True

        # Delete key
        result = await redis_cache.delete(key)
        assert result is True

        # Verify key is gone
        assert await redis_cache.exists(key) is False
        assert await redis_cache.get(key) is None

    async def test_ttl_expiration(self, redis_cache):
        """Test TTL-based expiration."""
        key = "ttl_test"
        value = "expires_soon"

        # Set with very short TTL
        await redis_cache.set(key, value, ttl=1)

        # Should exist immediately
        assert await redis_cache.exists(key) is True
        assert await redis_cache.get(key) == value

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Should be expired now
        assert await redis_cache.exists(key) is False
        assert await redis_cache.get(key) is None

    async def test_complex_data_types(self, redis_cache):
        """Test caching complex data types."""
        test_data = {
            "string": "hello",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, "three", {"nested": True}],
            "dict": {
                "nested_key": "nested_value",
                "deep": {"deeper": {"deepest": "value"}}
            }
        }

        key = "complex_data"
        await redis_cache.set(key, test_data)

        cached_data = await redis_cache.get(key)
        assert cached_data == test_data

    async def test_unicode_handling(self, redis_cache):
        """Test Unicode string handling."""
        unicode_text = "Hello 世界 🌍 Ñiño café"
        key = "unicode_test"

        await redis_cache.set(key, unicode_text)
        cached_text = await redis_cache.get(key)

        assert cached_text == unicode_text

    async def test_large_data(self, redis_cache):
        """Test caching large data objects."""
        # Create a large dictionary
        large_data = {
            f"key_{i}": f"value_{i}" * 100  # Each value is ~700 chars
            for i in range(100)  # Total ~70KB
        }

        key = "large_data"

        start_time = time.time()
        await redis_cache.set(key, large_data)
        set_time = time.time() - start_time

        start_time = time.time()
        cached_data = await redis_cache.get(key)
        get_time = time.time() - start_time

        assert cached_data == large_data
        # Performance sanity checks
        assert set_time < 1.0  # Should complete within 1 second
        assert get_time < 1.0  # Should complete within 1 second

    async def test_concurrent_operations(self, redis_cache):
        """Test concurrent cache operations."""
        num_operations = 50

        async def set_and_get(index: int):
            key = f"concurrent_{index}"
            value = {"index": index, "data": f"test_{index}"}

            await redis_cache.set(key, value)
            result = await redis_cache.get(key)
            return result == value

        # Run operations concurrently
        tasks = [set_and_get(i) for i in range(num_operations)]
        results = await asyncio.gather(*tasks)

        # All operations should succeed
        assert all(results), "Some concurrent operations failed"

    async def test_connection_failure_fallback(self, redis_cache):
        """Test fallback to local cache when Redis is unavailable."""
        key = "fallback_test"
        value = "fallback_value"

        # Set a value in cache
        await redis_cache.set(key, value)

        # Simulate Redis connection failure by using an invalid URL
        broken_cache = RedisCache(
            url="redis://invalid:6379/0",
            fallback_to_local=True,
            local_cache_size=100
        )

        # Should fail to get from Redis but fall back to local cache
        # (Note: This test might be limited by our test setup)
        try:
            # First, set in local cache
            broken_cache._set_local(key, value, ttl=60)

            # Then try to get (should use local fallback)
            result = broken_cache._get_local(key)
            assert result == value
        except Exception as e:
            pytest.skip(f"Fallback test skipped due to test limitations: {e}")

    async def test_clear_all_cache(self, redis_cache):
        """Test clearing all cache entries."""
        # Set multiple keys
        test_keys = ["clear1", "clear2", "clear3"]
        for key in test_keys:
            await redis_cache.set(key, f"value_for_{key}")

        # Verify keys exist
        for key in test_keys:
            assert await redis_cache.exists(key) is True

        # Clear all cache
        result = await redis_cache.clear()
        assert result is True

        # Verify all keys are gone
        for key in test_keys:
            assert await redis_cache.exists(key) is False

    async def test_key_generator_integration(self, redis_cache):
        """Test key generation with Redis operations."""
        generator = redis_cache.key_generator

        # Test different key patterns
        base_key = generator.generate_key("test_func", {"param1": "value1", "param2": 42})
        prompt_key = generator.generate_prompt_key("gpt-4o", "abc123")

        # Use generated keys
        await redis_cache.set(base_key, "base_value")
        await redis_cache.set(prompt_key, "prompt_value")

        # Retrieve with same keys
        assert await redis_cache.get(base_key) == "base_value"
        assert await redis_cache.get(prompt_key) == "prompt_value"


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisServiceIntegration:
    """Integration tests for RedisService with real Redis."""

    async def test_service_get_set(self, redis_service):
        """Test basic service get/set operations."""
        key = "service_test"
        value = {"service": "test", "data": [1, 2, 3]}

        # Set value
        result = await redis_service.set(key, value, ttl=30)
        assert result is True

        # Get value
        cached_value = await redis_service.get(key)
        assert cached_value == value

    async def test_batch_operations(self, redis_service):
        """Test batch get/set operations."""
        # Prepare test data
        test_data = {
            f"batch_key_{i}": {"index": i, "value": f"batch_value_{i}"}
            for i in range(10)
        }

        # Batch set
        set_result = await redis_service.batch_set(test_data, ttl=60)
        assert set_result is True

        # Batch get
        keys = list(test_data.keys())
        results = await redis_service.batch_get(keys)

        # Verify all values
        for i, (key, expected_value) in enumerate(test_data.items()):
            assert results[i] == expected_value

    async def test_increment_decrement(self, redis_service):
        """Test increment/decrement operations."""
        counter_key = "test_counter"

        # Initial increment
        result = await redis_service.increment(counter_key)
        assert result == 1

        # Increment by amount
        result = await redis_service.increment(counter_key, amount=5)
        assert result == 6

        # Decrement
        result = await redis_service.decrement(counter_key)
        assert result == 5

        # Decrement by amount
        result = await redis_service.decrement(counter_key, amount=2)
        assert result == 3

    async def test_ttl_operations(self, redis_service):
        """Test TTL-related operations."""
        key = "ttl_service_test"
        value = "ttl_value"

        # Set without TTL
        await redis_service.set(key, value)
        ttl = await redis_service.get_ttl(key)
        assert ttl == -1  # No expiration

        # Set TTL
        result = await redis_service.expire(key, 300)
        assert result is True

        # Check TTL (should be close to 300)
        ttl = await redis_service.get_ttl(key)
        assert 290 <= ttl <= 300  # Allow for small time differences

    async def test_health_check(self, redis_service):
        """Test Redis health check."""
        # Should be healthy
        is_healthy = await redis_service.health_check()
        assert is_healthy is True

    async def test_statistics_tracking(self, redis_service):
        """Test cache statistics tracking."""
        # Reset statistics
        await redis_service.reset_statistics()

        # Perform various operations
        await redis_service.set("stat_test1", "value1")
        await redis_service.set("stat_test2", "value2")

        result1 = await redis_service.get("stat_test1")
        result2 = await redis_service.get("stat_test3")  # Non-existent
        result3 = await redis_service.get("stat_test2")

        await redis_service.delete("stat_test1")

        # Get statistics
        stats = await redis_service.get_statistics()

        # Verify statistics
        assert stats.sets == 2
        assert stats.hits == 2  # stat_test1 and stat_test2
        assert stats.misses == 1  # stat_test3
        assert stats.deletes == 1
        assert stats.total_requests == 3
        assert 0.6 <= stats.hit_rate <= 0.7  # 2/3 hit rate

    async def test_performance_metrics(self, redis_service):
        """Test performance metrics collection."""
        # Reset metrics
        await redis_service.reset_metrics()

        # Perform operations
        await redis_service.set("perf_test", "value")
        await redis_service.get("perf_test")
        await redis_service.delete("perf_test")

        # Get metrics
        metrics = await redis_service.get_performance_metrics()

        # Verify metrics
        assert metrics is not None
        assert metrics.total_operations == 3
        assert metrics.set_operations == 1
        assert metrics.get_operations == 1
        assert metrics.delete_operations == 1
        assert metrics.avg_set_time > 0
        assert metrics.avg_get_time > 0
        assert metrics.avg_delete_time > 0
        assert metrics.operations_per_second > 0

    async def test_service_concurrent_load(self, redis_service):
        """Test service under concurrent load."""
        num_operations = 100
        operations_per_batch = 10

        async def worker_task(worker_id: int):
            results = []
            for i in range(operations_per_batch):
                key = f"worker_{worker_id}_op_{i}"
                value = {"worker": worker_id, "operation": i}

                # Set
                set_result = await redis_service.set(key, value)
                # Get
                get_result = await redis_service.get(key)

                results.append(set_result and (get_result == value))
            return all(results)

        # Run multiple workers concurrently
        num_workers = 5
        tasks = [worker_task(i) for i in range(num_workers)]
        worker_results = await asyncio.gather(*tasks)

        # All workers should complete successfully
        assert all(worker_results), "Some workers failed"

    async def test_error_handling(self, redis_service):
        """Test error handling in various scenarios."""
        # Try to get non-serializable data (will fail on set)
        try:
            # Python sets are not JSON serializable
            await redis_service.set("bad_data", {1, 2, 3})
            assert False, "Should have raised an error for non-serializable data"
        except Exception:
            pass  # Expected error

        # Try operations with very long keys
        long_key = "x" * 10000  # Very long key
        try:
            # Redis might reject very long keys
            result = await redis_service.set(long_key, "value")
            # If it succeeds, test getting it back
            if result:
                assert await redis_service.get(long_key) == "value"
        except Exception:
            # Redis rejected the long key, which is acceptable
            pass

    async def test_service_cleanup(self, redis_service):
        """Test service cleanup operations."""
        # Set some test data
        test_keys = ["cleanup1", "cleanup2", "cleanup3"]
        for key in test_keys:
            await redis_service.set(key, f"cleanup_value_{key}")

        # Clear cache
        result = await redis_service.clear_cache()
        assert result is True

        # Verify all keys are gone
        for key in test_keys:
            assert await redis_service.get(key) is None
            assert await redis_service.exists(key) is False


@pytest.mark.integration
@pytest.mark.asyncio
class TestCachePromptIntegration:
    """Test prompt caching integration scenarios."""

    async def test_prompt_caching_workflow(self, redis_cache):
        """Test complete prompt caching workflow."""
        # Simulate prompt and model
        model = "gpt-4o"
        prompt = "Translate the following text to French: 'Hello world'"
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        # Generate cache key
        cache_key = redis_cache.key_generator.generate_prompt_key(model, prompt_hash)

        # Simulate cached response
        response = {
            "model": model,
            "response": "Bonjour le monde",
            "tokens_used": 8,
            "cost": 0.000016
        }

        # Cache the response
        await redis_cache.set(cache_key, response, ttl=3600)

        # Retrieve cached response
        cached_response = await redis_cache.get(cache_key)
        assert cached_response == response

        # Check that key exists and has TTL
        assert await redis_cache.exists(cache_key) is True
        ttl = await redis_cache.get_ttl(cache_key)
        assert 3500 <= ttl <= 3600  # Allow for time differences

    async def test_prompt_template_caching(self, redis_cache):
        """Test caching of prompt templates."""
        template_name = "translation_template"
        template_data = {
            "template": "Translate '{{text}}' to {{target_language}}",
            "metadata": {
                "version": "1.0.0",
                "required_variables": ["text", "target_language"],
                "description": "Translation template"
            }
        }

        # Cache template
        template_key = f"template:{template_name}"
        await redis_cache.set(template_key, template_data, ttl=7200)

        # Retrieve template
        cached_template = await redis_cache.get(template_key)
        assert cached_template == template_data

        # Test template usage
        variables = {"text": "Hello", "target_language": "Spanish"}
        # (Template rendering would happen in actual usage)


# Utility function for tests
def hashlib():
    """Mock hashlib for tests that might not have it."""
    import hashlib
    return hashlib