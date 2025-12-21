"""
Core Cache Module for Data Foundry

This module provides comprehensive Redis caching functionality including:
- Redis connection management and connection pooling
- Generic cache decorators and utilities
- Cache key generation and serialization
- TTL management and cache invalidation
- Error handling and fallback mechanisms
"""

import json
import time
import threading
import asyncio
import hashlib
from typing import Any, Dict, Optional, Callable, Union, TypeVar, cast
from functools import wraps
from dataclasses import dataclass
from contextlib import asynccontextmanager

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis, ConnectionPool
    AIREDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    Redis = None
    ConnectionPool = None
    AIREDIS_AVAILABLE = False

from .config import get_settings

# Type variables
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])


class CacheError(Exception):
    """Base exception for cache-related errors."""
    pass


class CacheKeyError(CacheError):
    """Exception raised for cache key-related errors."""
    pass


class CacheSerializationError(CacheError):
    """Exception raised for serialization/deserialization errors."""
    pass


class CacheConnectionError(CacheError):
    """Exception raised for cache connection errors."""
    pass


@dataclass
class CacheEntry:
    """Represents a cached entry with metadata."""
    value: Any
    timestamp: float
    ttl: Optional[int] = None
    version: str = "1.0.0"

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl


class CacheKeyGenerator:
    """Generates consistent cache keys."""

    def __init__(self, prefix: str = "", separator: str = ":", sort_params: bool = False):
        """
        Initialize cache key generator.

        Args:
            prefix: Optional prefix for all keys
            separator: Separator between key components
            sort_params: Whether to sort parameters for consistent keys
        """
        self.prefix = prefix
        self.separator = separator
        self.sort_params = sort_params

    def generate_key(self, identifier: str, params: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate a cache key from identifier and parameters.

        Args:
            identifier: Base identifier for the key
            params: Optional parameters to include in the key

        Returns:
            Generated cache key string
        """
        if params is None:
            params = {}

        if not isinstance(params, dict):
            raise CacheKeyError(f"Parameters must be a dictionary, got {type(params)}")

        # Sort parameters if requested for consistent keys
        if self.sort_params:
            items = sorted(params.items())
        else:
            items = params.items()

        # Build key components
        components = [self.prefix, identifier] if self.prefix else [identifier]

        for key, value in items:
            # Handle special characters in values
            value_str = str(value).replace(self.separator, f"\\{self.separator}")
            components.append(f"{key}={value_str}")

        return self.separator.join(components)

    def generate_prompt_key(self, model: str, prompt_hash: str) -> str:
        """
        Generate a specialized cache key for prompts.

        Args:
            model: Model name/identifier
            prompt_hash: Hash of the prompt content

        Returns:
            Formatted prompt cache key
        """
        return self.generate_key(model, {"prompt_hash": prompt_hash})


class CacheSerializer:
    """Handles serialization and deserialization of cache values."""

    def serialize(self, value: Any) -> str:
        """
        Serialize a value for caching.

        Args:
            value: Value to serialize

        Returns:
            Serialized string

        Raises:
            CacheSerializationError: If serialization fails
        """
        try:
            # Handle basic types directly
            if value is None:
                return "null"
            elif isinstance(value, str):
                return value
            elif isinstance(value, (int, float, bool)):
                return str(value)
            elif isinstance(value, bytes):
                return value.decode('utf-8')
            else:
                # Use JSON for complex objects
                return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError, UnicodeDecodeError) as e:
            raise CacheSerializationError(f"Failed to serialize value: {e}") from e

    def deserialize(self, value: Union[str, bytes, None]) -> Any:
        """
        Deserialize a cached value.

        Args:
            value: Serialized value to deserialize

        Returns:
            Deserialized value

        Raises:
            CacheSerializationError: If deserialization fails
        """
        if value is None:
            return None

        try:
            # Handle bytes input
            if isinstance(value, bytes):
                value = value.decode('utf-8')

            # Try to parse as JSON first
            if value.startswith(('{', '[', '"')) or value in ('true', 'false', 'null'):
                return json.loads(value)

            # Try to parse as number
            try:
                if '.' in value:
                    return float(value)
                return int(value)
            except ValueError:
                pass

            # Try to parse as boolean
            if value.lower() == 'true':
                return True
            elif value.lower() == 'false':
                return False
            elif value.lower() == 'null':
                return None

            # Return as string
            return value

        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
            raise CacheSerializationError(f"Failed to deserialize value: {e}") from e


class RedisConnectionPool:
    """Manages Redis connection pooling."""

    def __init__(
        self,
        url: str,
        max_connections: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 0.1,
        health_check_interval: float = 30.0
    ):
        """
        Initialize Redis connection pool.

        Args:
            url: Redis connection URL
            max_connections: Maximum number of connections in pool
            retry_attempts: Number of retry attempts for failed operations
            retry_delay: Delay between retry attempts in seconds
            health_check_interval: Interval for health checks in seconds
        """
        self.url = url
        self.max_connections = max_connections
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval

        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._lock = threading.Lock()
        self._last_health_check = 0.0
        self._healthy = True

    def get_client(self) -> Redis:
        """
        Get a Redis client from the pool.

        Returns:
            Redis client instance

        Raises:
            CacheConnectionError: If connection fails
        """
        if not AIREDIS_AVAILABLE:
            raise CacheConnectionError("redis[hiredis] is not installed. Install with: uv add redis[hiredis]")

        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        self._pool = ConnectionPool.from_url(
                            self.url,
                            max_connections=self.max_connections,
                            retry_on_timeout=True,
                            socket_keepalive=True,
                            socket_keepalive_options={}
                        )
                        self._client = Redis(connection_pool=self._pool)
                    except Exception as e:
                        raise CacheConnectionError(f"Failed to create Redis connection: {e}") from e

        return self._client

    @asynccontextmanager
    async def get_connection(self):
        """Get a Redis connection from the pool."""
        client = await self.get_client()
        try:
            yield client
        except Exception as e:
            raise CacheConnectionError(f"Redis operation failed: {e}") from e

    async def health_check(self) -> bool:
        """
        Perform health check on Redis connection.

        Returns:
            True if healthy, False otherwise
        """
        current_time = time.time()

        # Skip health check if recently performed
        if current_time - self._last_health_check < self.health_check_interval:
            return self._healthy

        try:
            async with self.get_connection() as client:
                await client.ping()
                self._healthy = True
                self._last_health_check = current_time
                return True
        except Exception:
            self._healthy = False
            self._last_health_check = current_time
            return False

    async def close(self):
        """Close the connection pool."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None


class RedisCache:
    """High-level Redis cache implementation."""

    def __init__(
        self,
        url: Optional[str] = None,
        key_generator: Optional[CacheKeyGenerator] = None,
        serializer: Optional[CacheSerializer] = None,
        default_ttl: Optional[int] = None,
        local_cache_size: int = 1000,
        fallback_to_local: bool = True
    ):
        """
        Initialize Redis cache.

        Args:
            url: Redis connection URL
            key_generator: Custom key generator
            serializer: Custom serializer
            default_ttl: Default TTL for cache entries
            local_cache_size: Size of local fallback cache
            fallback_to_local: Whether to use local cache fallback
        """
        settings = get_settings()
        self.url = url or settings.REDIS_URL
        self.default_ttl = default_ttl or settings.PROMPT_CACHE_TTL

        self.key_generator = key_generator or CacheKeyGenerator()
        self.serializer = serializer or CacheSerializer()

        self.connection_pool = RedisConnectionPool(self.url)
        self.local_cache_size = local_cache_size
        self.fallback_to_local = fallback_to_local

        # Simple local cache for fallback
        self._local_cache: Dict[str, CacheEntry] = {}
        self._local_cache_lock = threading.Lock()

    async def get(self, key: str) -> Any:
        """
        Get a value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            async with self.connection_pool.get_connection() as client:
                value = await client.get(key)
                if value is not None:
                    return self.serializer.deserialize(value)
                return None
        except Exception as e:
            if self.fallback_to_local:
                return self._get_local(key)
            raise CacheError(f"Failed to get cache value for key {key}: {e}") from e

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        ttl = ttl or self.default_ttl
        serialized_value = self.serializer.serialize(value)

        try:
            async with self.connection_pool.get_connection() as client:
                if ttl:
                    result = await client.setex(key, ttl, serialized_value)
                else:
                    result = await client.set(key, serialized_value)

                # Update local cache if fallback is enabled
                if self.fallback_to_local and result:
                    self._set_local(key, value, ttl)

                return bool(result)
        except Exception as e:
            if self.fallback_to_local:
                self._set_local(key, value, ttl)
                return True
            raise CacheError(f"Failed to set cache value for key {key}: {e}") from e

    async def delete(self, key: str) -> bool:
        """
        Delete a value from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if key didn't exist
        """
        try:
            async with self.connection_pool.get_connection() as client:
                result = await client.delete(key)

                # Remove from local cache
                with self._local_cache_lock:
                    self._local_cache.pop(key, None)

                return result > 0
        except Exception as e:
            # Try to delete from local cache
            with self._local_cache_lock:
                deleted = key in self._local_cache
                self._local_cache.pop(key, None)
                return deleted

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            async with self.connection_pool.get_connection() as client:
                result = await client.exists(key)
                return result > 0
        except Exception as e:
            if self.fallback_to_local:
                return self._exists_local(key)
            raise CacheError(f"Failed to check if key exists {key}: {e}") from e

    async def clear(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if successful
        """
        try:
            async with self.connection_pool.get_connection() as client:
                await client.flushdb()

                # Clear local cache
                with self._local_cache_lock:
                    self._local_cache.clear()

                return True
        except Exception as e:
            raise CacheError(f"Failed to clear cache: {e}") from e

    def _get_local(self, key: str) -> Any:
        """Get value from local cache."""
        with self._local_cache_lock:
            entry = self._local_cache.get(key)
            if entry and not entry.is_expired():
                return entry.value
            elif entry:
                # Remove expired entry
                del self._local_cache[key]
            return None

    def _set_local(self, key: str, value: Any, ttl: Optional[int]) -> None:
        """Set value in local cache."""
        with self._local_cache_lock:
            # Remove oldest entries if cache is full
            if len(self._local_cache) >= self.local_cache_size:
                # Simple FIFO removal (could be improved with LRU)
                oldest_key = next(iter(self._local_cache))
                del self._local_cache[oldest_key]

            self._local_cache[key] = CacheEntry(
                value=value,
                timestamp=time.time(),
                ttl=ttl
            )

    def _exists_local(self, key: str) -> bool:
        """Check if key exists in local cache."""
        with self._local_cache_lock:
            entry = self._local_cache.get(key)
            if entry and not entry.is_expired():
                return True
            elif entry:
                del self._local_cache[key]
            return False


# Global cache instance
_global_cache: Optional[RedisCache] = None
_cache_lock = threading.Lock()


def get_cache() -> RedisCache:
    """
    Get the global cache instance.

    Returns:
        RedisCache instance
    """
    global _global_cache

    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = RedisCache()

    return _global_cache


def generate_cache_key(
    identifier: str,
    params: Optional[Dict[str, Any]] = None,
    prefix: str = ""
) -> str:
    """
    Generate a cache key.

    Args:
        identifier: Base identifier
        params: Optional parameters
        prefix: Optional prefix

    Returns:
        Generated cache key
    """
    generator = CacheKeyGenerator(prefix=prefix)
    return generator.generate_key(identifier, params)


def cache_result(
    func_or_prefix: Union[F, str] = None,
    *,
    key_prefix: str = "",
    ttl: Optional[int] = None,
    key_generator: Optional[CacheKeyGenerator] = None,
    unless: Optional[Callable[..., bool]] = None
) -> F:
    """
    Decorator to cache function results.

    Args:
        func_or_prefix: Function being decorated or prefix string
        key_prefix: Prefix for cache keys
        ttl: Time to live for cache entries
        key_generator: Custom key generator
        unless: Condition to skip caching

    Returns:
        Decorated function
    """
    def decorator(f: F) -> F:
        @wraps(f)
        def sync_wrapper(*args, **kwargs):
            # Skip caching if condition is met
            if unless and unless(*args, **kwargs):
                return f(*args, **kwargs)

            # Generate cache key
            if key_generator:
                key = key_generator.generate_key(f.__name__, {"args": args, "kwargs": kwargs})
            else:
                params = {f"arg{i}": arg for i, arg in enumerate(args)}
                params.update(kwargs)
                key = generate_cache_key(f.__name__, params, prefix=key_prefix)

            cache = get_cache()

            # Try to get from cache (sync version using local cache only)
            try:
                cached_result = cache._get_local(key)
                if cached_result is not None:
                    return cached_result
            except Exception:
                pass

            # Execute function and cache result
            result = f(*args, **kwargs)

            try:
                # For sync functions, use local cache only
                cache._set_local(key, result, ttl)
            except Exception:
                pass

            return result

        @wraps(f)
        async def async_wrapper(*args, **kwargs):
            # Skip caching if condition is met
            if unless and unless(*args, **kwargs):
                return await f(*args, **kwargs)

            # Generate cache key
            if key_generator:
                key = key_generator.generate_key(f.__name__, {"args": args, "kwargs": kwargs})
            else:
                params = {f"arg{i}": arg for i, arg in enumerate(args)}
                params.update(kwargs)
                key = generate_cache_key(f.__name__, params, prefix=key_prefix)

            cache = get_cache()

            # Try to get from cache
            try:
                cached_result = await cache.get(key)
                if cached_result is not None:
                    return cached_result
            except Exception:
                # Continue with function execution if cache fails
                pass

            # Execute function and cache result
            result = await f(*args, **kwargs)

            try:
                await cache.set(key, result, ttl)
            except Exception:
                # Ignore cache set errors
                pass

            return result

        # Choose appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(f):
            return cast(F, async_wrapper)
        else:
            return cast(F, sync_wrapper)

    # Handle both @cache and @cache(prefix) syntax
    if callable(func_or_prefix):
        return decorator(func_or_prefix)
    else:
        key_prefix = func_or_prefix or ""
        return decorator


def cached_with_ttl(ttl: int):
    """
    Convenience decorator for caching with specific TTL.

    Args:
        ttl: Time to live in seconds

    Returns:
        Decorator function
    """
    return cache_result(ttl=ttl)


# Utility functions for common caching patterns
async def invalidate_pattern(pattern: str) -> int:
    """
    Invalidate cache keys matching a pattern.

    Args:
        pattern: Pattern to match (supports wildcards)

    Returns:
        Number of keys invalidated
    """
    cache = get_cache()
    try:
        async with cache.connection_pool.get_connection() as client:
            keys = await client.keys(pattern)
            if keys:
                return await client.delete(*keys)
            return 0
    except Exception as e:
        raise CacheError(f"Failed to invalidate pattern {pattern}: {e}") from e


async def get_ttl(key: str) -> int:
    """
    Get remaining TTL for a cache key.

    Args:
        key: Cache key

    Returns:
        Remaining TTL in seconds, -1 if no expiry, -2 if key doesn't exist
    """
    cache = get_cache()
    try:
        async with cache.connection_pool.get_connection() as client:
            return await client.ttl(key)
    except Exception as e:
        raise CacheError(f"Failed to get TTL for key {key}: {e}") from e


async def set_ttl(key: str, ttl: int) -> bool:
    """
    Set TTL for an existing cache key.

    Args:
        key: Cache key
        ttl: Time to live in seconds

    Returns:
        True if successful
    """
    cache = get_cache()
    try:
        async with cache.connection_pool.get_connection() as client:
            return await client.expire(key, ttl)
    except Exception as e:
        raise CacheError(f"Failed to set TTL for key {key}: {e}") from e