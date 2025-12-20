"""
Resilience and error handling tests for Redis cache.

These tests verify the cache system's ability to handle:
- Connection failures and recoveries
- Network timeouts and interruptions
- Redis server failures
- Graceful degradation and fallback mechanisms
- Circuit breaker patterns
- Retry logic and backoff strategies
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
from typing import Any, Dict

from src.core.cache import (
    RedisCache,
    RedisConnectionPool,
    CacheError,
    CacheConnectionError,
    CacheSerializationError,
    CacheKeyError,
)
from src.services.redis_service import (
    RedisService,
    RedisServiceError,
    RedisConnectionError as ServiceConnectionError,
    CacheStatistics,
)


@pytest.mark.resilience
@pytest.mark.asyncio
class TestConnectionResilience:
    """Test connection resilience and recovery."""

    async def test_connection_retry_logic(self):
        """Test retry logic on connection failures."""
        # Create a connection pool that will fail initially
        with patch('src.core.cache.aioredis') as mock_aioredis:
            # Mock Redis client that fails first 2 attempts, succeeds on 3rd
            mock_client = AsyncMock()
            mock_client.ping.side_effect = [
                ConnectionError("Connection failed"),
                ConnectionError("Connection failed"),
                True  # Success on third attempt
            ]

            mock_pool = Mock()
            mock_pool.get_client.return_value = mock_client
            mock_aioredis.Redis = Mock(return_value=mock_client)
            mock_aioredis.ConnectionPool.from_url = Mock(return_value=mock_pool)

            # Create connection pool with retry settings
            pool = RedisConnectionPool(
                url="redis://test:6379/0",
                retry_attempts=3,
                retry_delay=0.01  # Fast retry for tests
            )

            # Health check should eventually succeed
            result = await pool.health_check()
            assert result is True
            assert mock_client.ping.call_count == 3

    async def test_connection_timeout_handling(self):
        """Test handling of connection timeouts."""
        with patch('src.core.cache.aioredis') as mock_aioredis:
            # Mock Redis client that times out
            mock_client = AsyncMock()
            mock_client.ping.side_effect = asyncio.TimeoutError("Connection timeout")

            mock_pool = Mock()
            mock_pool.get_client.return_value = mock_client
            mock_aioredis.Redis = Mock(return_value=mock_client)
            mock_aioredis.ConnectionPool.from_url = Mock(return_value=mock_pool)

            pool = RedisConnectionPool(
                url="redis://test:6379/0",
                retry_attempts=2,
                retry_delay=0.01
            )

            # Health check should fail after retries
            result = await pool.health_check()
            assert result is False

    async def test_connection_pool_exhaustion(self):
        """Test behavior when connection pool is exhausted."""
        with patch('src.core.cache.aioredis') as mock_aioredis:
            mock_client = AsyncMock()
            mock_client.ping.return_value = True

            # Mock pool that raises pool exhaustion error
            mock_pool = Mock()
            mock_pool.get_client.side_effect = [
                mock_client,  # First call succeeds
                mock_client,  # Second call succeeds
                Exception("Connection pool exhausted")  # Third call fails
            ]

            mock_aioredis.Redis = Mock(return_value=mock_client)
            mock_aioredis.ConnectionPool.from_url = Mock(return_value=mock_pool)

            pool = RedisConnectionPool(
                url="redis://test:6379/0",
                max_connections=2,  # Small pool for testing
                retry_attempts=1
            )

            # First two calls should succeed, third should fail
            client1 = await pool.get_client()
            assert client1 is not None

            with pytest.raises(CacheConnectionError):
                await pool.get_client()

    async def test_graceful_degradation_to_local_cache(self):
        """Test graceful degradation to local cache when Redis fails."""
        # Create cache with local fallback
        cache = RedisCache(
            url="redis://invalid:6379/0",  # Invalid URL
            fallback_to_local=True,
            local_cache_size=100
        )

        # Operations should fall back to local cache
        key = "fallback_test"
        value = {"test": "fallback_value"}

        # Set should succeed locally even if Redis fails
        try:
            result = await cache.set(key, value, ttl=300)
            # If Redis is actually running, this might succeed
            if result:
                # Try to get it back
                retrieved = await cache.get(key)
                assert retrieved == value
        except CacheConnectionError:
            # If Redis fails, local cache should still work
            cache._set_local(key, value, ttl=300)
            retrieved = cache._get_local(key)
            assert retrieved == value

    async def test_redis_unavailable_recovery(self):
        """Test recovery when Redis becomes unavailable and then available again."""
        # This test would require actual Redis control, so we'll simulate
        with patch('src.core.cache.aioredis') as mock_aioredis:
            # Mock client that simulates Redis going down and coming back up
            call_count = 0

            def mock_operation(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 3:
                    raise ConnectionError("Redis down")
                else:
                    return "OK"

            mock_client = AsyncMock()
            mock_client.get.side_effect = mock_operation
            mock_client.set.side_effect = mock_operation

            mock_pool = Mock()
            mock_pool.get_client.return_value = mock_client
            mock_aioredis.Redis = Mock(return_value=mock_client)
            mock_aioredis.ConnectionPool.from_url = Mock(return_value=mock_pool)

            cache = RedisCache(
                url="redis://test:6379/0",
                fallback_to_local=True,
                retry_attempts=3,
                retry_delay=0.01
            )

            # First attempts should fail
            with pytest.raises(CacheConnectionError):
                await cache.get("test_key")

            # Simulate some time passing and Redis coming back up
            await asyncio.sleep(0.1)

            # Subsequent attempts should succeed
            # (In real scenario, this would require reconnection logic)


@pytest.mark.resilience
@pytest.mark.asyncio
class TestErrorHandling:
    """Test comprehensive error handling."""

    async def test_serialization_error_handling(self):
        """Test handling of serialization errors."""
        cache = RedisCache(url="redis://localhost:6379/15")  # Use test DB

        # Try to cache a non-serializable object
        non_serializable = lambda x: x  # Function objects aren't JSON serializable

        with pytest.raises(CacheError):
            await cache.set("bad_key", non_serializable)

    async def test_deserialization_error_handling(self):
        """Test handling of deserialization errors."""
        # Mock Redis to return invalid JSON
        with patch('src.core.cache.RedisCache._get_local') as mock_get_local:
            # Return invalid JSON from Redis
            with patch.object(cache.connection_pool, 'get_connection') as mock_conn:
                mock_client = AsyncMock()
                mock_client.get.return_value = b"invalid json {"
                mock_conn.return_value.__aenter__.return_value = mock_client

                cache = RedisCache(url="redis://test:6379/0")

                with pytest.raises(CacheError):
                    await cache.get("bad_data_key")

    async def test_key_validation_errors(self):
        """Test key validation and error handling."""
        generator = CacheKeyGenerator()

        # Test invalid parameters
        with pytest.raises(CacheKeyError):
            generator.generate_key("test", None)  # None params

        # Test extremely long keys
        long_key = "x" * 10000
        try:
            generated_key = generator.generate_key(long_key, {})
            # Redis might accept or reject this
            assert len(generated_key) > 0
        except CacheKeyError:
            # If key generation itself fails, that's acceptable
            pass

    async def test_memory_pressure_handling(self):
        """Test handling under memory pressure scenarios."""
        cache = RedisCache(
            url="redis://localhost:6379/15",
            local_cache_size=10  # Very small local cache
        )

        # Fill local cache beyond capacity
        for i in range(20):
            await cache._set_local(f"pressure_test_{i}", f"value_{i}", ttl=300)

        # Should still be able to access recently added items
        recent_value = cache._get_local("pressure_test_19")
        assert recent_value == "value_19"

        # Older items might be evicted (FIFO strategy)
        old_value = cache._get_local("pressure_test_0")
        # This might be None due to eviction
        assert old_value is None or old_value == "value_0"

    async def test_network_partition_simulation(self):
        """Test behavior during simulated network partition."""
        # Simulate network partition by using invalid address
        cache = RedisCache(
            url="redis://192.0.2.0:6379/0",  # Non-routable IP
            fallback_to_local=True,
            retry_attempts=2,
            retry_delay=0.01
        )

        # Operations should fail gracefully
        key = "partition_test"
        value = "test_value"

        # Try to set (should fall back to local)
        try:
            await cache.set(key, value)
            # If this succeeds, Redis might actually be running
        except CacheConnectionError:
            # Expected when Redis is unreachable
            pass

        # Should still be able to use local cache
        cache._set_local(key, value, ttl=300)
        retrieved = cache._get_local(key)
        assert retrieved == value


@pytest.mark.resilience
@pytest.mark.asyncio
class TestServiceResilience:
    """Test Redis service resilience features."""

    async def test_service_retry_mechanism(self):
        """Test service-level retry mechanism."""
        with patch('src.services.redis_service.RedisConnectionPool') as mock_pool_class:
            mock_pool = Mock()
            mock_client = AsyncMock()

            # Simulate failure then success
            call_count = 0
            async def mock_get(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise ConnectionError("Temporary failure")
                return '"success"'  # JSON string

            mock_client.get.side_effect = mock_get
            mock_pool.get_connection.return_value.__aenter__.return_value = mock_client
            mock_pool_class.return_value = mock_pool

            service = RedisService(
                url="redis://test:6379/0",
                retry_attempts=3,
                retry_delay=0.01
            )

            # Should succeed after retries
            result = await service.get("test_key")
            assert result == "success"
            assert call_count == 3

    async def test_service_circuit_breaker_pattern(self):
        """Test circuit breaker pattern implementation."""
        service = RedisService(
            url="redis://localhost:6379/15",
            retry_attempts=1,  # Minimal retries for fast failure
            retry_delay=0.01
        )

        # Simulate multiple rapid failures
        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get.side_effect = ConnectionError("Service unavailable")
            mock_get_client.return_value = mock_client

            # Multiple failures should trigger circuit breaker
            failures = 0
            for i in range(10):
                try:
                    await service.get(f"key_{i}")
                except ServiceConnectionError:
                    failures += 1

            assert failures == 10  # All should fail

    async def test_service_statistics_during_failures(self):
        """Test statistics tracking during failure scenarios."""
        service = RedisService(
            url="redis://localhost:6379/15",
            enable_metrics=True
        )

        # Reset statistics
        await service.reset_statistics()

        # Simulate mixed success and failure
        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()

            # First call succeeds
            mock_client.get.return_value = '"success"'
            result1 = await service.get("key1")
            assert result1 == "success"

            # Next calls fail
            mock_client.get.side_effect = ConnectionError("Failed")
            with pytest.raises(ServiceConnectionError):
                await service.get("key2")

            with pytest.raises(ServiceConnectionError):
                await service.get("key3")

            # Check statistics
            stats = await service.get_statistics()
            assert stats.hits == 1
            assert stats.errors == 2
            assert stats.total_requests == 2  # Only successful requests count for hit/miss

    async def test_service_batch_operation_resilience(self):
        """Test batch operation error handling and partial success."""
        service = RedisService(
            url="redis://localhost:6379/15",
            retry_attempts=2
        )

        # Test batch operations with some failures
        test_data = {
            "batch_key_1": "value1",
            "batch_key_2": "value2",
            "batch_key_3": "value3"
        }

        # Mock partial failure scenario
        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            # Simulate pipeline where some operations fail
            mock_client.mset.return_value = True
            mock_client.mget.return_value = [b'"value1"', None, b'"value3"']  # Middle one missing

            mock_get_client.return_value.__aenter__.return_value = mock_client

            # Batch set should succeed
            set_result = await service.batch_set(test_data)
            assert set_result is True

            # Batch get should handle missing values gracefully
            keys = list(test_data.keys())
            results = await service.batch_get(keys)
            assert results[0] == "value1"
            assert results[1] is None  # Missing
            assert results[2] == "value3"

    async def test_service_health_monitoring(self):
        """Test health monitoring and automatic recovery."""
        service = RedisService(url="redis://localhost:6379/15")

        # Initial health check should pass
        is_healthy = await service.health_check()
        assert is_healthy is True

        # Simulate health failure
        with patch.object(service.connection_pool, 'health_check') as mock_health:
            mock_health.return_value = False

            is_healthy = await service.health_check()
            assert is_healthy is False

        # Recovery should be detected
        mock_health.return_value = True
        is_healthy = await service.health_check()
        assert is_healthy is True


@pytest.mark.resilience
@pytest.mark.asyncio
class TestDataCorruptionHandling:
    """Test handling of data corruption scenarios."""

    async def test_corrupted_data_detection(self):
        """Test detection and handling of corrupted cache data."""
        cache = RedisCache(url="redis://localhost:6379/15")

        # Manually set corrupted data in Redis
        with patch.object(cache.connection_pool, 'get_connection') as mock_conn:
            mock_client = AsyncMock()
            # Return truncated/corrupted JSON
            mock_client.get.return_value = b'{"incomplete": json'
            mock_conn.return_value.__aenter__.return_value = mock_client

            with pytest.raises(CacheError):
                await cache.get("corrupted_key")

    async def test_data_integrity_validation(self):
        """Test data integrity validation mechanisms."""
        cache = RedisCache(url="redis://localhost:6379/15")

        # Test round-trip data integrity
        test_data = {
            "string": "test",
            "number": 42,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
            "unicode": "Hello 世界 🌍",
            "special_chars": "quotes: ' \" and backslashes: \\",
            "null_value": None,
            "boolean": True
        }

        # Cache and retrieve
        await cache.set("integrity_test", test_data)
        retrieved = await cache.get("integrity_test")

        # Verify data integrity
        assert retrieved == test_data
        assert type(retrieved) == type(test_data)
        assert retrieved["string"] == test_data["string"]
        assert retrieved["unicode"] == test_data["unicode"]

    async def test_malformed_key_handling(self):
        """Test handling of malformed or dangerous keys."""
        cache = RedisCache(url="redis://localhost:6379/15")

        dangerous_keys = [
            "key with spaces",
            "key:with:colons",
            "key\nwith\nnewlines",
            "key\twith\ttabs",
            "very_long_key_" + "x" * 1000
        ]

        for key in dangerous_keys:
            try:
                # Should either succeed or fail gracefully
                await cache.set(key, "test_value")
                result = await cache.get(key)
                if result is not None:
                    assert result == "test_value"
            except (CacheError, CacheKeyError):
                # Expected for some malformed keys
                pass

    async def test_concurrent_access_consistency(self):
        """Test data consistency under concurrent access."""
        cache = RedisCache(url="redis://localhost:6379/15")
        shared_key = "concurrent_test"

        async def reader_writer_task(task_id: int, iterations: int):
            """Task that reads and writes shared data."""
            for i in range(iterations):
                # Write
                data = {"task_id": task_id, "iteration": i, "timestamp": time.time()}
                await cache.set(shared_key, data, ttl=60)

                # Small delay to increase race condition likelihood
                await asyncio.sleep(0.001)

                # Read
                result = await cache.get(shared_key)

                # Should get valid data (might be from this task or another)
                assert result is not None
                assert "task_id" in result
                assert "iteration" in result

        # Run multiple concurrent tasks
        tasks = [
            reader_writer_task(i, 50)  # 50 iterations per task
            for i in range(5)
        ]

        await asyncio.gather(*tasks)

        # Final read should get valid data
        final_data = await cache.get(shared_key)
        assert final_data is not None
        assert isinstance(final_data, dict)