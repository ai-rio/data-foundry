# Redis Caching Infrastructure for Data Foundry

This document provides comprehensive information about the Redis caching infrastructure implemented for Data Foundry, including architecture, configuration, usage patterns, and best practices.

## Overview

The Redis caching infrastructure provides high-performance, distributed caching capabilities for the Data Foundry platform. It offers:

- **Distributed Caching**: Redis-based caching across multiple service instances
- **Intelligent Fallback**: Local cache fallback when Redis is unavailable
- **Performance Monitoring**: Comprehensive metrics and statistics tracking
- **Resilience**: Robust error handling and automatic recovery
- **Integration**: Seamless integration with the Prompt Management System

## Architecture

### Core Components

1. **Core Cache Module** (`src/core/cache.py`)
   - `RedisCache`: High-level Redis operations with fallback
   - `RedisConnectionPool`: Managed connection pooling
   - `CacheKeyGenerator`: Consistent cache key generation
   - `CacheSerializer`: JSON-based serialization
   - Cache decorators and utilities

2. **Redis Service** (`src/services/redis_service.py`)
   - `RedisService`: High-level Redis operations
   - Batch operations support
   - Performance metrics collection
   - Health monitoring
   - Statistics tracking

3. **Cached Prompt Manager** (`src/core/prompts/cached_prompt_manager.py`)
   - `CachedPromptManager`: Enhanced prompt manager with Redis caching
   - Cache invalidation strategies
   - Performance optimization
   - Integration with existing prompt system

### Data Flow

```
Application Request
        ↓
Cache Check (Redis)
        ↓ (miss)
Local Cache Check
        ↓ (miss)
Data Source
        ↓
Cache Storage (Redis + Local)
        ↓
Response
```

## Configuration

### Environment Variables

```bash
# Redis Connection
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_DB=0
REDIS_CACHE_PREFIX=data_foundry
REDIS_MAX_CONNECTIONS=20
REDIS_RETRY_ATTEMPTS=3
REDIS_RETRY_DELAY=0.1

# Cache Settings
PROMPT_CACHE_ENABLED=true
PROMPT_CACHE_TTL=3600
PROMPT_CACHE_KEY_PREFIX=prompt_cache
PROMPT_CACHE_MAX_SIZE=10000
PROMPT_CACHE_LOCAL_FALLBACK=true
```

### Configuration File (config.py)

The caching settings are integrated into the main configuration system:

```python
# Redis Configuration
REDIS_URL: str = "redis://localhost:6379/0"
REDIS_CACHE_DB: int = 0
REDIS_CACHE_PREFIX: str = "data_foundry"
REDIS_MAX_CONNECTIONS: int = 20
REDIS_RETRY_ATTEMPTS: int = 3
REDIS_RETRY_DELAY: float = 0.1

# Prompt Cache Configuration
PROMPT_CACHE_ENABLED: bool = True
PROMPT_CACHE_TTL: int = 3600
PROMPT_CACHE_KEY_PREFIX: str = "prompt_cache"
PROMPT_CACHE_MAX_SIZE: int = 10000
PROMPT_CACHE_LOCAL_FALLBACK: bool = True
```

## Usage

### Basic Caching

```python
from src.core.cache import get_cache

# Get the global cache instance
cache = get_cache()

# Set a value
await cache.set("my_key", {"data": "value"}, ttl=3600)

# Get a value
value = await cache.get("my_key")

# Delete a value
await cache.delete("my_key")
```

### Using Cache Decorators

```python
from src.core.cache import cache_result, cached_with_ttl

# Simple caching
@cache_result
async def expensive_operation(param1, param2):
    # Expensive computation
    return result

# Caching with specific TTL
@cached_with_ttl(1800)  # 30 minutes
async def api_call(endpoint):
    # Make API call
    return response
```

### Redis Service Operations

```python
from src.services.redis_service import get_redis_service

# Get the Redis service
service = get_redis_service()

# Basic operations
await service.set("key", "value", ttl=300)
value = await service.get("key")

# Batch operations
data = {"key1": "value1", "key2": "value2"}
await service.batch_set(data, ttl=300)
results = await service.batch_get(["key1", "key2"])

# Statistics
stats = await service.get_statistics()
print(f"Hit rate: {stats.hit_rate:.2%}")
```

### Cached Prompt Manager

```python
from src.core.prompts import get_cached_prompt_manager

# Get cached prompt manager
manager = get_cached_prompt_manager()

# Get system prompt with caching
prompt = await manager.get_system_prompt_cached("classification")

# Get template with caching
template = await manager.get_template_cached("my_template")

# Render template with caching
rendered = await manager.render_template_cached(
    "my_template",
    {"variable": "value"},
    cache_rendered=True
)
```

### Factory Functions

```python
from src.core.prompts import get_manager, get_system_prompt_cached

# Get appropriate manager based on configuration
manager = get_manager()  # Automatically chooses cached or basic

# Convenience functions with automatic fallback
prompt = await get_system_prompt_cached("classification")
template = await get_template_cached("my_template")
```

## Cache Key Patterns

The system uses consistent key patterns for different types of cached data:

### System Prompts
```
prompt_cache:system_prompt:type={prompt_type}:version=1.0.0
```

### Templates
```
prompt_cache:template:name={template_name}:version=1.0.0
```

### Rendered Templates
```
prompt_cache:rendered:template={name}:variables_hash={hash}:version=1.0.0
```

### Custom Keys
```python
from src.core.cache import CacheKeyGenerator

generator = CacheKeyGenerator(prefix="myapp")
key = generator.generate_key("function", {"param1": "value1", "param2": 42})
# Result: "myapp:function:param1=value1:param2=42"
```

## Performance Monitoring

### Cache Statistics

```python
# Get cache statistics
stats = await manager.get_cache_stats()
print(f"Redis hit rate: {stats.redis_hit_rate:.2%}")
print(f"Local hit rate: {stats.local_hit_rate:.2%}")
print(f"Overall hit rate: {stats.overall_hit_rate:.2%}")
print(f"Total requests: {stats.total_requests}")
```

### Performance Metrics

```python
# Get Redis service metrics
service = get_redis_service()
metrics = await service.get_performance_metrics()

print(f"Average get time: {metrics.avg_get_time * 1000:.2f}ms")
print(f"Operations per second: {metrics.operations_per_second:.2f}")
print(f"Total operations: {metrics.total_operations}")
```

### Health Monitoring

```python
# Health check
health = await manager.health_check()
print(f"Redis available: {health['redis_cache_available']}")
print(f"Local cache available: {health['local_cache_available']}")
```

## Best Practices

### 1. Cache Key Design

- Use descriptive, hierarchical keys
- Include version information for cache invalidation
- Use consistent separators (colons are recommended)
- Avoid very long keys

### 2. TTL Management

- Set appropriate TTL based on data volatility
- Use shorter TTL for frequently changing data
- Consider cache warming for critical data

### 3. Error Handling

- Always handle cache failures gracefully
- Implement fallback mechanisms
- Monitor cache error rates

### 4. Performance Optimization

- Use batch operations for multiple keys
- Implement cache warming strategies
- Monitor hit rates and optimize accordingly

### 5. Memory Management

- Set appropriate local cache sizes
- Monitor Redis memory usage
- Implement cache eviction policies

## Cache Invalidation Strategies

### Manual Invalidation

```python
# Invalidate specific prompt
await manager.invalidate_prompt_cache("classification")

# Invalidate specific template
await manager.invalidate_template_cache("my_template")

# Clear all cache
await cache.clear()
```

### TTL-Based Invalidation

```python
# Set with automatic expiration
await cache.set("key", value, ttl=3600)  # Expires in 1 hour

# Update TTL for existing key
await cache.set_ttl("key", 1800)  # 30 minutes
```

### Version-Based Invalidation

Include version information in cache keys:

```python
key = generator.generate_key(
    "data",
    {"type": "user", "id": user_id, "version": "v2.0"}
)
```

## Troubleshooting

### Common Issues

1. **Redis Connection Failures**
   - Check Redis server status
   - Verify connection URL and credentials
   - Check network connectivity

2. **Low Hit Rates**
   - Review cache key generation
   - Check TTL settings
   - Analyze access patterns

3. **Memory Issues**
   - Monitor Redis memory usage
   - Adjust cache sizes
   - Implement proper eviction policies

4. **Performance Issues**
   - Check connection pool settings
   - Monitor batch operation efficiency
   - Review serialization overhead

### Debugging

Enable debug mode and logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable cache debug mode
settings.PROMPT_DEBUG_MODE = True
```

### Monitoring

Set up monitoring for:

- Redis connection status
- Cache hit/miss ratios
- Response times
- Error rates
- Memory usage

## Testing

### Unit Tests

Run unit tests with mocked Redis:

```bash
pytest tests/unit/cache/ -v
```

### Integration Tests

Run integration tests with real Redis:

```bash
pytest tests/integration/cache/ -v -m integration
```

### Performance Tests

Run performance benchmarks:

```bash
pytest tests/integration/cache/test_cache_performance.py -v -m benchmark
```

## Deployment Considerations

### Production Configuration

```python
# Production settings
REDIS_MAX_CONNECTIONS = 50
REDIS_RETRY_ATTEMPTS = 5
REDIS_RETRY_DELAY = 0.5
REDIS_HEALTH_CHECK_INTERVAL = 60.0

PROMPT_CACHE_TTL = 7200  # 2 hours
PROMPT_CACHE_MAX_SIZE = 50000
```

### High Availability

- Use Redis Cluster for scaling
- Implement proper connection pooling
- Set up Redis monitoring and alerting
- Plan for Redis failover scenarios

### Security

- Use Redis AUTH for authentication
- Enable TLS/SSL for connections
- Implement proper network isolation
- Regular security updates

## Migration Guide

### From Local Cache Only

1. Install Redis dependencies:
```bash
pip install aioredis
```

2. Update configuration with Redis settings

3. Replace `PromptManager` with `CachedPromptManager`:

```python
# Before
from src.core.prompts import PromptManager
manager = PromptManager()

# After
from src.core.prompts import CachedPromptManager
manager = CachedPromptManager()
```

4. Or use the factory function:
```python
from src.core.prompts import get_manager
manager = get_manager()  # Automatically uses cached if available
```

### Gradual Migration

1. Start with local cache fallback enabled
2. Monitor cache performance and hit rates
3. Gradually increase reliance on Redis cache
4. Implement cache warming strategies
5. Optimize based on usage patterns

## Future Enhancements

### Planned Features

- **Cache Segmentation**: Separate cache pools for different data types
- **Smart Preloading**: Predictive cache warming based on usage patterns
- **Distributed Cache Invalidation**: Cross-instance cache coordination
- **Advanced Metrics**: More detailed performance analytics
- **Cache Compression**: Redis-side compression for large objects

### Scalability Improvements

- Redis Cluster integration
- Geographic distributed caching
- Multi-level caching strategies
- Cache-aware load balancing

## API Reference

### Core Cache Classes

#### RedisCache

Main cache interface with Redis backend and local fallback.

```python
class RedisCache:
    def __init__(self, url: str, default_ttl: int = None,
                 fallback_to_local: bool = True, local_cache_size: int = 1000)

    async def get(self, key: str) -> Any
    async def set(self, key: str, value: Any, ttl: int = None) -> bool
    async def delete(self, key: str) -> bool
    async def exists(self, key: str) -> bool
    async def clear(self) -> bool
```

#### RedisService

High-level Redis operations with monitoring.

```python
class RedisService:
    async def batch_get(self, keys: List[str]) -> List[Any]
    async def batch_set(self, data: Dict[str, Any], ttl: int = None) -> bool
    async def get_statistics(self) -> CacheStatistics
    async def get_performance_metrics(self) -> PerformanceMetrics
    async def health_check(self) -> bool
```

#### CachedPromptManager

Enhanced prompt manager with Redis caching.

```python
class CachedPromptManager:
    async def get_system_prompt_cached(self, prompt_type: str) -> str
    async def get_template_cached(self, template_name: str) -> Dict[str, Any]
    async def render_template_cached(self, template_name: str,
                                   variables: Dict[str, Any],
                                   cache_rendered: bool = True) -> str
    async def invalidate_prompt_cache(self, prompt_type: str = None)
    async def invalidate_template_cache(self, template_name: str = None)
    async def get_cache_stats(self) -> CacheStats
```

### Utility Functions

#### Cache Decorators

```python
@cache_result(key_prefix="myapp", ttl=300)
async def my_function(param1, param2):
    return result

@cached_with_ttl(1800)
async def another_function():
    return result
```

#### Key Generation

```python
from src.core.cache import generate_cache_key

key = generate_cache_key("function", {"param": "value"}, prefix="app")
# Result: "app:function:param=value"
```

## Support and Contributing

For issues, questions, or contributions related to the Redis caching infrastructure:

1. Check existing documentation and tests
2. Review the code in `src/core/cache.py` and `src/services/redis_service.py`
3. Run the test suite to verify behavior
4. Submit issues and pull requests through the standard project channels

## License

This caching infrastructure is part of the Data Foundry project and follows the same licensing terms.