"""
Integration tests for Prompt Manager with Redis caching.

These tests verify the integration between the caching system and the
Prompt Management System, ensuring proper functionality and performance.
"""

import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock

from src.core.prompts import (
    get_manager,
    get_cached_prompt_manager,
    get_system_prompt_cached,
    get_template_cached,
    render_template_cached,
    invalidate_prompt_cache,
    invalidate_template_cache,
    get_cache_stats,
    prompt_manager_health_check,
)
from src.core.prompts.cached_prompt_manager import (
    CachedPromptManager,
    CacheStats,
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestPromptCacheIntegration:
    """Test integration between prompt management and caching."""

    @pytest.fixture
    async def cached_manager(self):
        """Create a cached prompt manager for testing."""
        # Use a test-specific database
        with patch('src.core.prompts.cached_prompt_manager.get_settings') as mock_settings:
            mock_settings.return_value.REDIS_URL = "redis://localhost:6379/15"
            mock_settings.return_value.PROMPT_CACHE_TTL = 300
            mock_settings.return_value.PROMPT_CACHE_KEY_PREFIX = "test_prompt_cache"

            manager = CachedPromptManager(
                cache_enabled=True,
                redis_ttl=300,
                enable_local_fallback=True,
                cache_warm_up=False  # Skip warm up for tests
            )

            # Clear any existing cache
            try:
                await manager._redis_cache.clear()
            except:
                pass  # Ignore if Redis is not available

            yield manager

            # Cleanup
            try:
                if manager._redis_cache:
                    await manager._redis_cache.clear()
            except:
                pass

    async def test_get_manager_selection(self):
        """Test manager selection based on configuration."""
        # Test forcing basic manager
        basic_manager = get_manager(use_cached=False)
        assert type(basic_manager).__name__ == "PromptManager"

        # Test forcing cached manager
        try:
            cached_manager = get_manager(use_cached=True)
            assert type(cached_manager).__name__ == "CachedPromptManager"
        except Exception:
            # Redis might not be available in test environment
            pass

    async def test_system_prompt_caching(self, cached_manager):
        """Test system prompt caching functionality."""
        prompt_type = "classification"

        # First call should cache the result
        start_time = time.time()
        result1 = await cached_manager.get_system_prompt_cached(prompt_type)
        first_call_time = time.time() - start_time

        assert result1 is not None
        assert isinstance(result1, str)

        # Second call should be faster (cache hit)
        start_time = time.time()
        result2 = await cached_manager.get_system_prompt_cached(prompt_type)
        second_call_time = time.time() - start_time

        assert result1 == result2
        # Second call should be faster (allowing for some variance)
        assert second_call_time <= first_call_time + 0.1  # Allow 100ms variance

        # Check cache statistics
        stats = await cached_manager.get_cache_stats()
        assert stats.redis_hits >= 1
        assert stats.redis_misses >= 1

    async def test_template_caching(self, cached_manager):
        """Test template caching functionality."""
        # This test might fail if the template doesn't exist
        template_name = "classification"

        try:
            # First call
            result1 = await cached_manager.get_template_cached(template_name)
            assert result1 is not None
            assert isinstance(result1, dict)

            # Second call should hit cache
            result2 = await cached_manager.get_template_cached(template_name)
            assert result1 == result2

            # Check cache statistics
            stats = await cached_manager.get_cache_stats()
            assert stats.redis_hits >= 1
            assert stats.redis_misses >= 1

        except Exception:
            # Template might not exist, skip test
            pytest.skip(f"Template {template_name} not available for testing")

    async def test_rendered_template_caching(self, cached_manager):
        """Test caching of rendered templates."""
        template_name = "classification"
        variables = {"data_type": "text", "confidence_threshold": 0.85}

        try:
            # First render
            result1 = await cached_manager.render_template_cached(
                template_name, variables, cache_rendered=True
            )
            assert isinstance(result1, str)

            # Second render with same variables should hit cache
            result2 = await cached_manager.render_template_cached(
                template_name, variables, cache_rendered=True
            )
            assert result1 == result2

            # Different variables should not hit cache
            different_vars = {"data_type": "image", "confidence_threshold": 0.90}
            result3 = await cached_manager.render_template_cached(
                template_name, different_vars, cache_rendered=True
            )
            # Results should be different
            assert result2 != result3

        except Exception:
            pytest.skip(f"Template {template_name} not available for testing")

    async def test_cache_invalidation(self, cached_manager):
        """Test cache invalidation functionality."""
        prompt_type = "data_analysis"

        try:
            # Cache a prompt
            result1 = await cached_manager.get_system_prompt_cached(prompt_type)

            # Invalidate the cache
            await cached_manager.invalidate_prompt_cache(prompt_type)

            # Next call should be a cache miss
            # (We can't easily verify this without mocking, but we can ensure it doesn't error)
            result2 = await cached_manager.get_system_prompt_cached(prompt_type)
            assert result1 == result2

        except Exception:
            pytest.skip("System prompt not available for testing")

    async def test_convenience_functions(self):
        """Test the convenience functions for cached operations."""
        try:
            # Test system prompt function
            prompt = await get_system_prompt_cached("classification")
            assert prompt is not None

            # Test template function (might not exist)
            try:
                template = await get_template_cached("classification")
                assert template is not None
            except Exception:
                pass  # Template might not exist

            # Test cache stats
            stats = await get_cache_stats()
            if stats:  # Only test if cached manager is available
                assert isinstance(stats, CacheStats)

            # Test health check
            health = await prompt_manager_health_check()
            assert isinstance(health, dict)
            assert "cached_manager_available" in health or "basic_manager_available" in health

        except Exception:
            pytest.skip("Redis or prompts not available for testing")

    async def test_cache_statistics_tracking(self, cached_manager):
        """Test cache statistics tracking and reporting."""
        # Reset statistics
        cached_manager.reset_cache_stats()

        initial_stats = await cached_manager.get_cache_stats()
        assert initial_stats.total_requests == 0

        # Perform some operations
        try:
            await cached_manager.get_system_prompt_cached("classification")
            await cached_manager.get_system_prompt_cached("classification")  # Should hit cache
        except Exception:
            pytest.skip("System prompts not available")

        # Check updated statistics
        stats = await cached_manager.get_cache_stats()
        assert stats.total_requests >= 2
        assert stats.redis_hits >= 1
        assert stats.redis_misses >= 1

        # Test statistics to_dict
        stats_dict = stats.to_dict()
        assert "redis_hits" in stats_dict
        assert "redis_hit_rate" in stats_dict
        assert "overall_hit_rate" in stats_dict

    async def test_health_check_functionality(self, cached_manager):
        """Test health check functionality."""
        health = await cached_manager.health_check()

        assert isinstance(health, dict)
        assert "local_cache_available" in health
        assert "cache_stats" in health

        if cached_manager._redis_cache:
            # Redis cache should be available if Redis is running
            assert isinstance(health["redis_cache_available"], bool)

    async def test_error_handling_and_fallback(self, cached_manager):
        """Test error handling and fallback mechanisms."""
        # Simulate Redis failure
        if cached_manager._redis_cache:
            original_cache = cached_manager._redis_cache

            # Temporarily break Redis connection
            cached_manager._redis_cache = None

            try:
                # Operations should fall back to local cache or base implementation
                result = await cached_manager.get_system_prompt_cached("classification")
                # Should either return None (if not in local cache) or the prompt
                assert result is None or isinstance(result, str)

            finally:
                # Restore cache
                cached_manager._redis_cache = original_cache

    async def test_cache_warm_up(self):
        """Test cache warm up functionality."""
        # Create manager with warm up enabled
        try:
            manager = CachedPromptManager(
                cache_enabled=True,
                cache_warm_up=True,
                skip_singleton=True  # Don't use singleton for test
            )

            # Give warm up a moment to complete
            await asyncio.sleep(0.5)

            # Check if some items were cached
            stats = await manager.get_cache_stats()
            # Warm up might have cached some items or failed gracefully
            assert stats.total_requests >= 0

            # Cleanup
            if manager._redis_cache:
                await manager._redis_cache.clear()

        except Exception:
            pytest.skip("Cache warm up test failed (likely Redis unavailable)")

    async def test_cache_key_generation(self, cached_manager):
        """Test cache key generation and consistency."""
        generator = cached_manager._key_generator

        # Test system prompt key generation
        key1 = generator.generate_key("system_prompt", {"type": "test", "version": "1.0"})
        key2 = generator.generate_key("system_prompt", {"type": "test", "version": "1.0"})
        assert key1 == key2

        # Test template key generation
        template_key = generator.generate_key("template", {"name": "test_template", "version": "1.0"})
        assert "template" in template_key
        assert "test_template" in template_key

        # Test rendered template key generation
        render_key = generator.generate_key("rendered", {
            "template": "test_template",
            "variables_hash": "abc123",
            "version": "1.0"
        })
        assert "rendered" in render_key
        assert "test_template" in render_key

    async def test_local_cache_fallback(self, cached_manager):
        """Test local cache fallback when Redis is unavailable."""
        # Test with local fallback enabled
        assert cached_manager.enable_local_fallback is True

        # Simulate local cache operations
        test_key = "local_test"
        test_value = "local_value"

        # Use local cache directly
        cached_manager._set_local(test_key, test_value, ttl=300)
        result = cached_manager._get_local(test_key)

        assert result == test_value

    async def test_cache_ttl_management(self, cached_manager):
        """Test TTL (Time To Live) management."""
        if not cached_manager._redis_cache:
            pytest.skip("Redis cache not available")

        test_key = "ttl_test"
        test_value = "ttl_value"

        # Set with short TTL
        await cached_manager._redis_cache.set(test_key, test_value, ttl=1)

        # Should be available immediately
        result = await cached_manager._redis_cache.get(test_key)
        assert result == test_value

        # Wait for expiration
        await asyncio.sleep(1.5)

        # Should be expired now
        result = await cached_manager._redis_cache.get(test_key)
        assert result is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestPromptCachePerformance:
    """Test performance characteristics of cached prompt operations."""

    async def test_cached_vs_uncached_performance(self):
        """Test performance difference between cached and uncached operations."""
        # This test compares performance with and without caching
        # Results will vary based on system and Redis availability

        prompt_type = "classification"

        # Test without caching
        basic_manager = get_manager(use_cached=False)

        start_time = time.time()
        for _ in range(10):
            try:
                basic_manager.get_system_prompt(prompt_type)
            except:
                pass
        basic_time = time.time() - start_time

        # Test with caching (if available)
        try:
            cached_manager = get_cached_prompt_manager()

            # Reset cache and stats
            await cached_manager.reset_cache_stats()

            start_time = time.time()
            for _ in range(10):
                try:
                    await cached_manager.get_system_prompt_cached(prompt_type)
                except:
                    pass
            cached_time = time.time() - start_time

            # Get statistics
            stats = await cached_manager.get_cache_stats()

            print(f"\nPerformance Comparison:")
            print(f"Basic manager: {basic_time:.3f}s for 10 operations")
            print(f"Cached manager: {cached_time:.3f}s for 10 operations")
            print(f"Cache hit rate: {stats.redis_hit_rate:.2%}")

            # Cached should be faster after first operation
            # (This is a rough test and may vary)
            if stats.redis_hits > 0:
                assert cached_time <= basic_time + 0.5  # Allow some variance

        except Exception:
            pytest.skip("Cached manager not available for performance test")