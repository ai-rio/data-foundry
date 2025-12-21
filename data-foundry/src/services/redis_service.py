"""
Redis Service for Data Foundry

This module provides high-level Redis operations for prompt caching with:
- Cache statistics and monitoring
- Batch operations support
- Connection health checks
- Performance metrics collection
- Retry logic and error handling
"""

import time
import asyncio
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from ..core.cache import (
    RedisConnectionPool,
    CacheSerializer,
    CacheError,
    CacheConnectionError,
    CacheSerializationError,
    get_settings
)


class RedisServiceError(Exception):
    """Base exception for Redis service errors."""
    pass


class RedisConnectionError(RedisServiceError):
    """Exception for Redis connection errors."""
    pass


class RedisBatchError(RedisServiceError):
    """Exception for batch operation errors."""
    pass


@dataclass
class CacheStatistics:
    """Cache statistics tracking."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    batch_operations: int = 0

    @property
    def total_requests(self) -> int:
        """Total number of requests."""
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self.total_requests
        return self.hits / total if total > 0 else 0.0

    @property
    def miss_rate(self) -> float:
        """Cache miss rate (0.0 to 1.0)."""
        total = self.total_requests
        return self.misses / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "errors": self.errors,
            "batch_operations": self.batch_operations,
            "total_requests": self.total_requests,
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics tracking."""
    total_operations: int = 0
    total_time: float = 0.0
    get_operations: int = 0
    get_time: float = 0.0
    set_operations: int = 0
    set_time: float = 0.0
    delete_operations: int = 0
    delete_time: float = 0.0
    batch_operations: int = 0
    batch_time: float = 0.0
    start_time: float = field(default_factory=time.time)

    def record_operation(self, operation_type: str, duration: float):
        """Record an operation with its duration."""
        self.total_operations += 1
        self.total_time += duration

        if operation_type == "get":
            self.get_operations += 1
            self.get_time += duration
        elif operation_type == "set":
            self.set_operations += 1
            self.set_time += duration
        elif operation_type == "delete":
            self.delete_operations += 1
            self.delete_time += duration
        elif operation_type == "batch":
            self.batch_operations += 1
            self.batch_time += duration

    @property
    def avg_get_time(self) -> float:
        """Average get operation time."""
        return self.get_time / self.get_operations if self.get_operations > 0 else 0.0

    @property
    def avg_set_time(self) -> float:
        """Average set operation time."""
        return self.set_time / self.set_operations if self.set_operations > 0 else 0.0

    @property
    def avg_delete_time(self) -> float:
        """Average delete operation time."""
        return self.delete_time / self.delete_operations if self.delete_operations > 0 else 0.0

    @property
    def avg_batch_time(self) -> float:
        """Average batch operation time."""
        return self.batch_time / self.batch_operations if self.batch_operations > 0 else 0.0

    @property
    def operations_per_second(self) -> float:
        """Operations per second since start."""
        elapsed = time.time() - self.start_time
        return self.total_operations / elapsed if elapsed > 0 else 0.0

    def reset(self):
        """Reset all metrics."""
        self.total_operations = 0
        self.total_time = 0.0
        self.get_operations = 0
        self.get_time = 0.0
        self.set_operations = 0
        self.set_time = 0.0
        self.delete_operations = 0
        self.delete_time = 0.0
        self.batch_operations = 0
        self.batch_time = 0.0
        self.start_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_operations": self.total_operations,
            "total_time": self.total_time,
            "avg_get_time": self.avg_get_time,
            "avg_set_time": self.avg_set_time,
            "avg_delete_time": self.avg_delete_time,
            "avg_batch_time": self.avg_batch_time,
            "operations_per_second": self.operations_per_second,
            "get_operations": self.get_operations,
            "set_operations": self.set_operations,
            "delete_operations": self.delete_operations,
            "batch_operations": self.batch_operations
        }


class RedisService:
    """High-level Redis service with caching capabilities."""

    def __init__(
        self,
        url: Optional[str] = None,
        max_connections: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 0.1,
        default_ttl: Optional[int] = None,
        enable_metrics: bool = True
    ):
        """
        Initialize Redis service.

        Args:
            url: Redis connection URL
            max_connections: Maximum connections in pool
            retry_attempts: Number of retry attempts
            retry_delay: Delay between retries
            default_ttl: Default TTL for cache entries
            enable_metrics: Whether to track performance metrics
        """
        settings = get_settings()
        self.url = url or settings.REDIS_URL
        self.max_connections = max_connections
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.default_ttl = default_ttl or settings.PROMPT_CACHE_TTL

        self.connection_pool = RedisConnectionPool(
            url=self.url,
            max_connections=max_connections,
            retry_attempts=retry_attempts,
            retry_delay=retry_delay
        )

        self.serializer = CacheSerializer()
        self._stats = CacheStatistics()
        self._metrics = PerformanceMetrics() if enable_metrics else None

        # Alias for tests that expect redis_client attribute
        self.redis_client = self.connection_pool

        # TTL attribute for tests
        self.ttl = self.default_ttl

    async def get(self, key: str) -> Any:
        """
        Get a value from Redis.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found

        Raises:
            RedisServiceError: If operation fails
        """
        start_time = time.time()

        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    value = await client.get(key)

                    if value is not None:
                        try:
                            result = self.serializer.deserialize(value)
                            self._stats.hits += 1
                            if self._metrics:
                                self._metrics.record_operation("get", time.time() - start_time)
                            return result
                        except CacheSerializationError as e:
                            self._stats.errors += 1
                            raise RedisServiceError(f"Failed to deserialize cached value: {e}") from e
                    else:
                        self._stats.misses += 1
                        if self._metrics:
                            self._metrics.record_operation("get", time.time() - start_time)
                        return None

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to get key {key} after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set a value in Redis.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise

        Raises:
            RedisServiceError: If operation fails
        """
        start_time = time.time()
        ttl = ttl or self.default_ttl

        try:
            serialized_value = self.serializer.serialize(value)
        except CacheSerializationError as e:
            self._stats.errors += 1
            raise RedisServiceError(f"Failed to serialize value: {e}") from e

        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    if ttl:
                        result = await client.setex(key, ttl, serialized_value)
                    else:
                        result = await client.set(key, serialized_value)

                    self._stats.sets += 1
                    if self._metrics:
                        self._metrics.record_operation("set", time.time() - start_time)

                    return bool(result)

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to set key {key} after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return False

    async def delete(self, *keys: str) -> int:
        """
        Delete keys from Redis.

        Args:
            keys: Keys to delete

        Returns:
            Number of keys deleted

        Raises:
            RedisServiceError: If operation fails
        """
        if not keys:
            return 0

        start_time = time.time()

        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    result = await client.delete(*keys)

                    self._stats.deletes += 1
                    if self._metrics:
                        self._metrics.record_operation("delete", time.time() - start_time)

                    return result

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to delete keys after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return 0

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise

        Raises:
            RedisServiceError: If operation fails
        """
        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    result = await client.exists(key)
                    return result > 0

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to check key existence after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return False

    async def get_ttl(self, key: str) -> int:
        """
        Get TTL for a key.

        Args:
            key: Cache key

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist

        Raises:
            RedisServiceError: If operation fails
        """
        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    return await client.ttl(key)

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to get TTL after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return -2

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set TTL for an existing key.

        Args:
            key: Cache key
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise

        Raises:
            RedisServiceError: If operation fails
        """
        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    result = await client.expire(key, ttl)
                    return bool(result)

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to set TTL after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return False

    async def batch_get(self, keys: List[str]) -> List[Any]:
        """
        Get multiple values from Redis.

        Args:
            keys: List of keys to retrieve

        Returns:
            List of values (None for missing keys)

        Raises:
            RedisServiceError: If operation fails
        """
        if not keys:
            return []

        start_time = time.time()

        try:
            async with self.connection_pool.get_connection() as client:
                values = await client.mget(*keys)

                results = []
                for value in values:
                    if value is not None:
                        try:
                            results.append(self.serializer.deserialize(value))
                            self._stats.hits += 1
                        except CacheSerializationError:
                            results.append(None)
                            self._stats.errors += 1
                    else:
                        results.append(None)
                        self._stats.misses += 1

                self._stats.batch_operations += 1
                if self._metrics:
                    self._metrics.record_operation("batch", time.time() - start_time)

                return results

        except Exception as e:
            self._stats.errors += 1
            raise RedisBatchError(f"Batch get failed: {e}") from e

    async def batch_set(
        self,
        data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set multiple values in Redis.

        Args:
            data: Dictionary of key-value pairs
            ttl: Optional TTL for all keys

        Returns:
            True if successful, False otherwise

        Raises:
            RedisServiceError: If operation fails
        """
        if not data:
            return True

        start_time = time.time()
        ttl = ttl or self.default_ttl

        try:
            # Serialize all values
            serialized_data = {}
            for key, value in data.items():
                serialized_data[key] = self.serializer.serialize(value)

            async with self.connection_pool.get_connection() as client:
                if ttl:
                    # With TTL, we need to use a pipeline or multiple setex calls
                    pipe = client.pipeline()
                    for key, value in serialized_data.items():
                        pipe.setex(key, ttl, value)
                    results = await pipe.execute()
                    success = all(results)
                else:
                    # Without TTL, use mset for atomic operation
                    await client.mset(serialized_data)
                    success = True

                self._stats.sets += len(data)
                self._stats.batch_operations += 1
                if self._metrics:
                    self._metrics.record_operation("batch", time.time() - start_time)

                return success

        except Exception as e:
            self._stats.errors += 1
            raise RedisBatchError(f"Batch set failed: {e}") from e

    async def batch_delete(self, keys: List[str]) -> int:
        """
        Delete multiple keys from Redis.

        Args:
            keys: List of keys to delete

        Returns:
            Number of keys deleted

        Raises:
            RedisServiceError: If operation fails
        """
        if not keys:
            return 0

        return await self.delete(*keys)

    async def increment(self, key: str, amount: int = 1) -> int:
        """
        Increment a numeric value in Redis.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value

        Raises:
            RedisServiceError: If operation fails
        """
        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    if amount == 1:
                        result = await client.incr(key)
                    else:
                        result = await client.incrby(key, amount)
                    return result

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to increment after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return 0

    async def decrement(self, key: str, amount: int = 1) -> int:
        """
        Decrement a numeric value in Redis.

        Args:
            key: Cache key
            amount: Amount to decrement by

        Returns:
            New value

        Raises:
            RedisServiceError: If operation fails
        """
        for attempt in range(self.retry_attempts + 1):
            try:
                async with self.connection_pool.get_connection() as client:
                    if amount == 1:
                        result = await client.decr(key)
                    else:
                        result = await client.decrby(key, amount)
                    return result

            except Exception as e:
                if attempt == self.retry_attempts:
                    self._stats.errors += 1
                    raise RedisConnectionError(f"Failed to decrement after {attempt + 1} attempts: {e}") from e

                await asyncio.sleep(self.retry_delay)

        return 0

    async def clear_cache(self) -> bool:
        """
        Clear all cache entries from Redis.

        Returns:
            True if successful

        Raises:
            RedisServiceError: If operation fails
        """
        try:
            async with self.connection_pool.get_connection() as client:
                await client.flushdb()
                return True

        except Exception as e:
            self._stats.errors += 1
            raise RedisServiceError(f"Failed to clear cache: {e}") from e

    async def health_check(self) -> bool:
        """
        Perform health check on Redis connection.

        Returns:
            True if healthy, False otherwise
        """
        try:
            return await self.connection_pool.health_check()
        except Exception:
            return False

    async def get_statistics(self) -> CacheStatistics:
        """
        Get cache statistics.

        Returns:
            Cache statistics object
        """
        return self._stats

    async def reset_statistics(self):
        """Reset cache statistics."""
        self._stats = CacheStatistics()

    async def get_performance_metrics(self) -> Optional[PerformanceMetrics]:
        """
        Get performance metrics.

        Returns:
            Performance metrics object or None if disabled
        """
        return self._metrics

    async def reset_metrics(self):
        """Reset performance metrics."""
        if self._metrics:
            self._metrics.reset()

    async def close(self):
        """Close Redis connections."""
        await self.connection_pool.close()


# Global Redis service instance
_global_redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    """
    Get the global Redis service instance.

    Returns:
        Redis service instance
    """
    global _global_redis_service

    if _global_redis_service is None:
        _global_redis_service = RedisService()

    return _global_redis_service


async def close_redis_service():
    """Close the global Redis service instance."""
    global _global_redis_service

    if _global_redis_service:
        await _global_redis_service.close()
        _global_redis_service = None