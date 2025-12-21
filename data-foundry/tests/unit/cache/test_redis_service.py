"""
Unit tests for Redis service with mocked Redis.

Tests cover:
- Redis connection management
- High-level Redis operations
- Cache statistics
- Batch operations
- Health checks
- Performance metrics
"""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional

from src.services.redis_service import (
    RedisService,
    RedisServiceError,
    RedisConnectionError,
    RedisBatchError,
    CacheStatistics,
    PerformanceMetrics,
)


class TestRedisService:
    """Test Redis service functionality."""

    @pytest.fixture
    def mock_redis_pool(self):
        """Create a mock Redis connection pool with async context manager support."""
        mock_client = AsyncMock()

        # Setup default async mock responses
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.get = AsyncMock(return_value=None)
        mock_client.set = AsyncMock(return_value=True)
        mock_client.setex = AsyncMock(return_value=True)
        mock_client.delete = AsyncMock(return_value=1)
        mock_client.exists = AsyncMock(return_value=0)
        mock_client.expire = AsyncMock(return_value=True)
        mock_client.ttl = AsyncMock(return_value=-1)
        mock_client.flushdb = AsyncMock(return_value=True)
        mock_client.mget = AsyncMock(return_value=[])
        mock_client.mset = AsyncMock(return_value=True)
        mock_client.incrby = AsyncMock(return_value=1)
        mock_client.decrby = AsyncMock(return_value=1)
        mock_client.decr = AsyncMock(return_value=1)
        mock_client.incr = AsyncMock(return_value=1)
        # Setup pipeline mock
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[True])
        mock_pipeline.setex = Mock(return_value=None)
        mock_client.pipeline = Mock(return_value=mock_pipeline)

        # Create a mock pool with an async context manager for get_connection
        mock_pool = Mock()

        async def get_connection_impl():
            """Returns an async context manager."""
            @asynccontextmanager
            async def cm():
                yield mock_client
            return cm()

        # Make get_connection return a new context manager coroutine each time
        async def get_connection_coroutine():
            @asynccontextmanager
            async def cm():
                yield mock_client
            return await cm().__aenter__(), await cm().__aexit__(None, None, None)

        # Use a simple approach: get_connection returns an object with async context manager support
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return mock_client
            async def __aexit__(self, *args):
                pass

        # Make get_connection return a new instance each time
        mock_pool.get_connection = Mock(side_effect=lambda: AsyncContextManagerMock())
        # Add health_check method to pool
        mock_pool.health_check = AsyncMock(return_value=True)

        return mock_pool, mock_client

    @pytest.fixture
    def redis_service(self, mock_redis_pool):
        """Create RedisService instance with mocked dependencies."""
        mock_pool, mock_client = mock_redis_pool

        with patch('src.services.redis_service.RedisConnectionPool') as mock_pool_class:
            with patch('src.services.redis_service.get_settings') as mock_settings_fn:
                # Mock settings to return 0 for PROMPT_CACHE_TTL so None passes through
                mock_settings = Mock()
                mock_settings.REDIS_URL = "redis://localhost:6379/0"
                mock_settings.PROMPT_CACHE_TTL = 0
                mock_settings_fn.return_value = mock_settings

                mock_pool_class.return_value = mock_pool

                service = RedisService(
                    url="redis://localhost:6379/0",
                    max_connections=10,
                    retry_attempts=3,
                    retry_delay=0.1,
                    default_ttl=None
                )

                # Replace the connection pool with the mock
                service.connection_pool = mock_pool
                return service

    @pytest.mark.asyncio
    async def test_service_initialization(self, redis_service):
        """Test Redis service initialization."""
        assert redis_service.url == "redis://localhost:6379/0"
        assert redis_service.max_connections == 10
        assert redis_service.retry_attempts == 3
        assert redis_service.retry_delay == 0.1
        assert redis_service._stats.hits == 0
        assert redis_service._stats.misses == 0

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, redis_service, mock_redis_pool):
        """Test cache get operation with hit."""
        _, mock_client = mock_redis_pool
        mock_client.get.return_value = '"cached_value"'
        mock_client.ttl.return_value = 300

        result = await redis_service.get("test_key")

        assert result == "cached_value"
        mock_client.get.assert_called_once_with("test_key")
        assert redis_service._stats.hits == 1
        assert redis_service._stats.misses == 0

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, redis_service, mock_redis_pool):
        """Test cache get operation with miss."""
        _, mock_client = mock_redis_pool
        mock_client.get.return_value = None

        result = await redis_service.get("test_key")

        assert result is None
        mock_client.get.assert_called_once_with("test_key")
        assert redis_service._stats.hits == 0
        assert redis_service._stats.misses == 1

    @pytest.mark.asyncio
    async def test_get_with_deserialization_error(self, redis_service, mock_redis_pool):
        """Test cache get with deserialization error."""
        _, mock_client = mock_redis_pool
        # Mock get to raise an exception
        mock_client.get.side_effect = Exception("Deserialization failed")

        with pytest.raises(RedisConnectionError):
            await redis_service.get("test_key")

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, redis_service, mock_redis_pool):
        """Test cache set operation with TTL."""
        _, mock_client = mock_redis_pool
        mock_client.setex.return_value = True

        result = await redis_service.set("test_key", "test_value", ttl=300)

        assert result is True
        mock_client.setex.assert_called_once_with("test_key", 300, "test_value")

    @pytest.mark.asyncio
    async def test_set_without_ttl(self, redis_service, mock_redis_pool):
        """Test cache set operation without TTL."""
        _, mock_client = mock_redis_pool
        # Reset the set mock to be fresh
        mock_client.set.reset_mock()
        mock_client.set.return_value = True

        result = await redis_service.set("test_key", "test_value")

        assert result is True
        mock_client.set.assert_called_once_with("test_key", "test_value")

    @pytest.mark.asyncio
    async def test_set_complex_object(self, redis_service, mock_redis_pool):
        """Test cache set with complex object."""
        _, mock_client = mock_redis_pool
        test_data = {"nested": {"key": "value"}, "list": [1, 2, 3]}

        result = await redis_service.set("test_key", test_data, ttl=600)

        assert result is True
        call_args = mock_client.setex.call_args
        assert call_args[0][0] == "test_key"
        assert call_args[0][1] == 600
        # Check that complex data was serialized (will contain nested dict structure)
        assert "nested" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_delete_single_key(self, redis_service, mock_redis_pool):
        """Test deleting a single key."""
        _, mock_client = mock_redis_pool
        mock_client.delete.return_value = 1

        result = await redis_service.delete("test_key")

        assert result == 1
        mock_client.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_delete_multiple_keys(self, redis_service, mock_redis_pool):
        """Test deleting multiple keys."""
        _, mock_client = mock_redis_pool
        mock_client.delete.return_value = 2

        result = await redis_service.delete("key1", "key2")

        assert result == 2
        mock_client.delete.assert_called_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_exists_true(self, redis_service, mock_redis_pool):
        """Test exists check when key exists."""
        _, mock_client = mock_redis_pool
        mock_client.exists.return_value = 1

        result = await redis_service.exists("test_key")

        assert result is True
        mock_client.exists.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_exists_false(self, redis_service, mock_redis_pool):
        """Test exists check when key doesn't exist."""
        _, mock_client = mock_redis_pool
        mock_client.exists.return_value = 0

        result = await redis_service.exists("test_key")

        assert result is False
        mock_client.exists.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_ttl(self, redis_service, mock_redis_pool):
        """Test getting TTL for a key."""
        _, mock_client = mock_redis_pool
        mock_client.ttl.return_value = 300

        result = await redis_service.get_ttl("test_key")

        assert result == 300
        mock_client.ttl.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_ttl_no_expire(self, redis_service, mock_redis_pool):
        """Test getting TTL for key with no expiration."""
        _, mock_client = mock_redis_pool
        mock_client.ttl.return_value = -1

        result = await redis_service.get_ttl("test_key")

        assert result == -1  # No expiration
        mock_client.ttl.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_ttl_not_exists(self, redis_service, mock_redis_pool):
        """Test getting TTL for non-existent key."""
        _, mock_client = mock_redis_pool
        mock_client.ttl.return_value = -2

        result = await redis_service.get_ttl("test_key")

        assert result == -2  # Key doesn't exist
        mock_client.ttl.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_expire_key(self, redis_service, mock_redis_pool):
        """Test setting expiration on a key."""
        _, mock_client = mock_redis_pool
        mock_client.expire.return_value = True

        result = await redis_service.expire("test_key", 600)

        assert result is True
        mock_client.expire.assert_called_once_with("test_key", 600)

    @pytest.mark.asyncio
    async def test_health_check_success(self, redis_service, mock_redis_pool):
        """Test successful health check."""
        mock_pool, _ = mock_redis_pool
        mock_pool.health_check.return_value = True

        result = await redis_service.health_check()

        assert result is True
        mock_pool.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, redis_service, mock_redis_pool):
        """Test failed health check."""
        mock_pool, _ = mock_redis_pool
        mock_pool.health_check.side_effect = Exception("Connection failed")

        result = await redis_service.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_batch_get(self, redis_service, mock_redis_pool):
        """Test batch get operation."""
        _, mock_client = mock_redis_pool
        mock_client.mget.return_value = ['"value1"', None, '"value3"']

        results = await redis_service.batch_get(["key1", "key2", "key3"])

        assert results == ["value1", None, "value3"]
        mock_client.mget.assert_called_once_with("key1", "key2", "key3")

    @pytest.mark.asyncio
    async def test_batch_set(self, redis_service, mock_redis_pool):
        """Test batch set operation."""
        _, mock_client = mock_redis_pool
        mock_client.mset.return_value = True

        # Setup pipeline for TTL case - pipeline() returns an object with async methods
        mock_pipeline = Mock()
        mock_pipeline.setex = Mock(return_value=None)
        mock_pipeline.execute = AsyncMock(return_value=[True, True, True])
        mock_client.pipeline.return_value = mock_pipeline

        data = {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3"
        }

        result = await redis_service.batch_set(data, ttl=300)

        assert result is True
        # Verify pipeline was used for TTL case
        mock_client.pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_delete(self, redis_service, mock_redis_pool):
        """Test batch delete operation."""
        _, mock_client = mock_redis_pool
        mock_client.delete.return_value = 3

        result = await redis_service.batch_delete(["key1", "key2", "key3"])

        assert result == 3
        mock_client.delete.assert_called_once_with("key1", "key2", "key3")

    @pytest.mark.asyncio
    async def test_clear_cache(self, redis_service, mock_redis_pool):
        """Test clearing all cache."""
        _, mock_client = mock_redis_pool
        mock_client.flushdb.return_value = True

        result = await redis_service.clear_cache()

        assert result is True
        mock_client.flushdb.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_statistics(self, redis_service):
        """Test getting cache statistics."""
        # Simulate some cache operations
        redis_service._stats.hits = 10
        redis_service._stats.misses = 5
        redis_service._stats.sets = 8
        redis_service._stats.deletes = 2

        stats = await redis_service.get_statistics()

        assert stats.hits == 10
        assert stats.misses == 5
        assert stats.sets == 8
        assert stats.deletes == 2
        assert stats.total_requests == 15
        assert stats.hit_rate == 10 / 15

    @pytest.mark.asyncio
    async def test_reset_statistics(self, redis_service):
        """Test resetting cache statistics."""
        # Set some stats
        redis_service._stats.hits = 10
        redis_service._stats.misses = 5

        await redis_service.reset_statistics()

        assert redis_service._stats.hits == 0
        assert redis_service._stats.misses == 0
        assert redis_service._stats.sets == 0
        assert redis_service._stats.deletes == 0

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, redis_service):
        """Test getting performance metrics."""
        # Simulate some operations
        redis_service._metrics.record_operation("get", 0.05)
        redis_service._metrics.record_operation("set", 0.1)
        redis_service._metrics.record_operation("get", 0.03)

        metrics = await redis_service.get_performance_metrics()

        assert metrics.avg_get_time > 0
        assert metrics.avg_set_time > 0
        assert metrics.total_operations == 3
        assert metrics.operations_per_second > 0

    @pytest.mark.asyncio
    async def test_increment_counter(self, redis_service, mock_redis_pool):
        """Test incrementing a counter."""
        _, mock_client = mock_redis_pool
        mock_client.incrby.return_value = 5

        result = await redis_service.increment("counter_key", amount=2)

        assert result == 5
        mock_client.incrby.assert_called_once_with("counter_key", 2)

    @pytest.mark.asyncio
    async def test_decrement_counter(self, redis_service, mock_redis_pool):
        """Test decrementing a counter."""
        _, mock_client = mock_redis_pool
        # The service calls decrby for amount > 1, but we're testing amount=1, so it calls decr
        mock_client.decr.return_value = 3

        result = await redis_service.decrement("counter_key", amount=1)

        assert result == 3
        mock_client.decr.assert_called_once_with("counter_key")

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, redis_service, mock_redis_pool):
        """Test handling of connection errors."""
        _, mock_client = mock_redis_pool
        mock_client.get.side_effect = ConnectionError("Redis connection failed")

        with pytest.raises(RedisConnectionError, match="Redis connection failed"):
            await redis_service.get("test_key")

    @pytest.mark.asyncio
    async def test_retry_logic(self, redis_service, mock_redis_pool):
        """Test retry logic on failed operations."""
        _, mock_client = mock_redis_pool
        # Fail first two attempts, succeed on third
        mock_client.get.side_effect = [
            ConnectionError("Failed"),
            ConnectionError("Failed"),
            '"success"'
        ]

        result = await redis_service.get("test_key")

        assert result == "success"
        assert mock_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, redis_service, mock_redis_pool):
        """Test when retries are exhausted."""
        _, mock_client = mock_redis_pool
        mock_client.get.side_effect = ConnectionError("Always fails")

        with pytest.raises(RedisConnectionError):
            await redis_service.get("test_key")

        assert mock_client.get.call_count == 4  # Initial + 3 retries


class TestCacheStatistics:
    """Test cache statistics functionality."""

    def test_statistics_initialization(self):
        """Test statistics initialization."""
        stats = CacheStatistics()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.sets == 0
        assert stats.deletes == 0
        assert stats.errors == 0

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStatistics()
        stats.hits = 8
        stats.misses = 2

        assert stats.hit_rate == 0.8
        assert stats.total_requests == 10

    def test_hit_rate_no_requests(self):
        """Test hit rate with no requests."""
        stats = CacheStatistics()
        assert stats.hit_rate == 0.0

    def test_miss_rate_calculation(self):
        """Test miss rate calculation."""
        stats = CacheStatistics()
        stats.hits = 3
        stats.misses = 7

        assert stats.miss_rate == 0.7

    def test_to_dict(self):
        """Test statistics to dictionary conversion."""
        stats = CacheStatistics()
        stats.hits = 10
        stats.misses = 5
        stats.sets = 8
        stats.deletes = 2
        stats.errors = 1

        stats_dict = stats.to_dict()

        assert stats_dict["hits"] == 10
        assert stats_dict["misses"] == 5
        assert stats_dict["hit_rate"] == 0.6666666666666666
        assert stats_dict["total_requests"] == 15


class TestPerformanceMetrics:
    """Test performance metrics functionality."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = PerformanceMetrics()
        assert metrics.total_operations == 0
        assert metrics.total_time == 0.0

    def test_record_operation(self):
        """Test recording an operation."""
        metrics = PerformanceMetrics()
        metrics.record_operation("get", 0.05)
        metrics.record_operation("set", 0.1)
        metrics.record_operation("get", 0.03)

        assert metrics.total_operations == 3
        assert metrics.total_time == pytest.approx(0.18)
        assert metrics.avg_get_time == pytest.approx(0.04)  # (0.05 + 0.03) / 2
        assert metrics.avg_set_time == pytest.approx(0.1)

    def test_operations_per_second(self):
        """Test operations per second calculation."""
        metrics = PerformanceMetrics()
        metrics.start_time = time.time() - 10  # Started 10 seconds ago
        metrics.record_operation("get", 0.05)
        metrics.record_operation("set", 0.1)

        # Should be approximately 0.2 ops/sec (2 ops in 10 seconds)
        ops_per_sec = metrics.operations_per_second
        assert 0.1 < ops_per_sec < 0.3  # Allow for timing variations

    def test_reset_metrics(self):
        """Test resetting metrics."""
        metrics = PerformanceMetrics()
        metrics.record_operation("get", 0.05)
        metrics.record_operation("set", 0.1)

        metrics.reset()

        assert metrics.total_operations == 0
        assert metrics.total_time == 0.0

    def test_to_dict(self):
        """Test metrics to dictionary conversion."""
        metrics = PerformanceMetrics()
        metrics.record_operation("get", 0.05)
        metrics.record_operation("set", 0.1)

        metrics_dict = metrics.to_dict()

        assert metrics_dict["total_operations"] == 2
        assert metrics_dict["total_time"] == pytest.approx(0.15)
        assert metrics_dict["avg_get_time"] == pytest.approx(0.05)
        assert metrics_dict["avg_set_time"] == pytest.approx(0.1)
        assert "operations_per_second" in metrics_dict