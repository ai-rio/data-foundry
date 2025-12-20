"""
CachedPromptManager - Enhanced PromptManager with Redis caching integration.

This module extends the PromptManager with distributed Redis caching capabilities,
providing:
- Distributed prompt caching across multiple instances
- Cache invalidation and synchronization
- Performance monitoring and statistics
- Graceful fallback to local cache
- Intelligent cache warming strategies
"""

import hashlib
import time
import threading
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from .prompt_manager import (
    PromptManager,
    PromptManagerError,
    PromptVersionError,
    CacheEntry
)
from ..cache import (
    RedisCache,
    CacheKeyGenerator,
    CacheError,
    CacheConnectionError,
    get_settings
)
from ...services.redis_service import get_redis_service


class CachedPromptManagerError(PromptManagerError):
    """Exception for cached prompt manager errors."""
    pass


@dataclass
class CacheStats:
    """Cache statistics for prompt manager."""
    redis_hits: int = 0
    redis_misses: int = 0
    local_hits: int = 0
    local_misses: int = 0
    cache_errors: int = 0
    total_requests: int = 0

    @property
    def redis_hit_rate(self) -> float:
        """Redis cache hit rate."""
        total = self.redis_hits + self.redis_misses
        return self.redis_hits / total if total > 0 else 0.0

    @property
    def local_hit_rate(self) -> float:
        """Local cache hit rate."""
        total = self.local_hits + self.local_misses
        return self.local_hits / total if total > 0 else 0.0

    @property
    def overall_hit_rate(self) -> float:
        """Overall cache hit rate."""
        total = self.total_requests
        hits = self.redis_hits + self.local_hits
        return hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "redis_hits": self.redis_hits,
            "redis_misses": self.redis_misses,
            "local_hits": self.local_hits,
            "local_misses": self.local_misses,
            "cache_errors": self.cache_errors,
            "total_requests": self.total_requests,
            "redis_hit_rate": self.redis_hit_rate,
            "local_hit_rate": self.local_hit_rate,
            "overall_hit_rate": self.overall_hit_rate
        }


class CachedPromptManager(PromptManager):
    """
    Enhanced PromptManager with Redis caching support.

    This class extends the base PromptManager to provide distributed caching
    capabilities using Redis. It maintains compatibility with the existing
    PromptManager interface while adding performance optimizations through
    intelligent caching strategies.
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        cache_ttl: float = 3600.0,
        redis_url: Optional[str] = None,
        redis_ttl: Optional[int] = None,
        enable_local_fallback: bool = True,
        cache_warm_up: bool = False,
        skip_singleton: bool = False,
    ):
        """
        Initialize the CachedPromptManager.

        Args:
            template_dir: Directory containing template files
            cache_enabled: Whether to enable caching
            cache_ttl: Local cache time-to-live in seconds
            redis_url: Redis connection URL (uses config if None)
            redis_ttl: Redis cache TTL in seconds (uses config if None)
            enable_local_fallback: Whether to fallback to local cache
            cache_warm_up: Whether to warm up cache on initialization
            skip_singleton: Skip singleton pattern (for testing)
        """
        super().__init__(
            template_dir=template_dir,
            cache_enabled=cache_enabled,
            cache_ttl=cache_ttl,
            skip_singleton=skip_singleton
        )

        settings = get_settings()
        self.redis_url = redis_url or settings.REDIS_URL
        self.redis_ttl = redis_ttl or settings.PROMPT_CACHE_TTL
        self.enable_local_fallback = enable_local_fallback
        self.cache_warm_up = cache_warm_up

        # Redis cache components
        self._redis_cache: Optional[RedisCache] = None
        self._redis_service = None
        self._key_generator = CacheKeyGenerator(
            prefix=settings.PROMPT_CACHE_KEY_PREFIX,
            separator=":"
        )

        # Cache statistics
        self._cache_stats = CacheStats()
        self._stats_lock = threading.Lock()

        # Initialize Redis cache
        if cache_enabled:
            self._initialize_redis_cache()

        # Warm up cache if requested
        if cache_warm_up and cache_enabled:
            asyncio.create_task(self._warm_up_cache())

    def _initialize_redis_cache(self):
        """Initialize Redis cache connection."""
        try:
            self._redis_cache = RedisCache(
                url=self.redis_url,
                key_generator=self._key_generator,
                default_ttl=self.redis_ttl,
                fallback_to_local=self.enable_local_fallback,
                local_cache_size=1000
            )

            self._redis_service = get_redis_service()

        except Exception as e:
            if self.enable_local_fallback:
                # Continue with local cache only
                print(f"Warning: Redis cache initialization failed, using local cache only: {e}")
            else:
                raise CachedPromptManagerError(f"Failed to initialize Redis cache: {e}") from e

    async def _warm_up_cache(self):
        """Warm up cache with commonly used prompts."""
        try:
            # Warm up system prompts
            system_prompts = self.list_system_prompts()
            for prompt_type in system_prompts:
                await self.get_system_prompt_cached(prompt_type)

            # Warm up commonly used templates
            common_templates = ["classification", "extraction", "generation"]
            for template_name in common_templates:
                try:
                    await self.get_template_cached(template_name)
                except PromptManagerError:
                    # Template might not exist, which is fine
                    pass

        except Exception as e:
            # Warm up failures shouldn't break the manager
            print(f"Cache warm up warning: {e}")

    def _update_stats(self, **kwargs):
        """Update cache statistics."""
        with self._stats_lock:
            for key, value in kwargs.items():
                if hasattr(self._cache_stats, key):
                    setattr(self._cache_stats, key, value)
                elif key == "increment_redis_hits":
                    self._cache_stats.redis_hits += 1
                    self._cache_stats.total_requests += 1
                elif key == "increment_redis_misses":
                    self._cache_stats.redis_misses += 1
                    self._cache_stats.total_requests += 1
                elif key == "increment_local_hits":
                    self._cache_stats.local_hits += 1
                    self._cache_stats.total_requests += 1
                elif key == "increment_local_misses":
                    self._cache_stats.local_misses += 1
                    self._cache_stats.total_requests += 1
                elif key == "increment_cache_errors":
                    self._cache_stats.cache_errors += 1

    def _generate_content_hash(self, content: str) -> str:
        """Generate a hash for content to detect changes."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

    async def get_system_prompt_cached(self, prompt_type: str) -> str:
        """
        Get a system prompt with caching.

        Args:
            prompt_type: The type of system prompt to retrieve

        Returns:
            The system prompt string

        Raises:
            PromptManagerError: If the prompt type is invalid
        """
        if not self.cache_enabled or not self._redis_cache:
            return self.get_system_prompt(prompt_type)

        cache_key = self._key_generator.generate_key(
            "system_prompt",
            {"type": prompt_type, "version": "1.0.0"}
        )

        try:
            # Try Redis cache first
            cached_prompt = await self._redis_cache.get(cache_key)
            if cached_prompt is not None:
                self._update_stats(increment_redis_hits=True)
                return cached_prompt

            self._update_stats(increment_redis_misses=True)

        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            # Fall back to base implementation
            if self.enable_local_fallback:
                return self.get_system_prompt(prompt_type)
            else:
                raise CachedPromptManagerError(f"Cache error: {e}") from e

        # Load from base implementation and cache
        prompt = self.get_system_prompt(prompt_type)

        try:
            await self._redis_cache.set(cache_key, prompt, ttl=self.redis_ttl)
        except Exception as e:
            # Cache set failure shouldn't break the operation
            self._update_stats(increment_cache_errors=True)
            print(f"Warning: Failed to cache system prompt: {e}")

        return prompt

    async def get_template_cached(self, template_name: str) -> Dict[str, Any]:
        """
        Get a template with caching.

        Args:
            template_name: Name of the template file

        Returns:
            Dictionary containing template data

        Raises:
            PromptManagerError: If template is not found or invalid
        """
        if not self.cache_enabled or not self._redis_cache:
            return self.get_template(template_name)

        cache_key = self._key_generator.generate_key(
            "template",
            {"name": template_name, "version": "1.0.0"}
        )

        try:
            # Try Redis cache first
            cached_template = await self._redis_cache.get(cache_key)
            if cached_template is not None:
                self._update_stats(increment_redis_hits=True)
                return cached_template

            self._update_stats(increment_redis_misses=True)

        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            if self.enable_local_fallback:
                return self.get_template(template_name)
            else:
                raise CachedPromptManagerError(f"Cache error: {e}") from e

        # Load from base implementation and cache
        template_data = self.get_template(template_name)

        try:
            await self._redis_cache.set(cache_key, template_data, ttl=self.redis_ttl)
        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            print(f"Warning: Failed to cache template: {e}")

        return template_data

    async def render_template_cached(
        self,
        template_name: str,
        variables: Dict[str, Any],
        cache_rendered: bool = True
    ) -> str:
        """
        Render a template with caching support.

        Args:
            template_name: Name of the template file
            variables: Dictionary of variables to substitute
            cache_rendered: Whether to cache the rendered result

        Returns:
            Rendered template string

        Raises:
            PromptManagerError: If rendering fails
        """
        if not self.cache_enabled or not cache_rendered or not self._redis_cache:
            return self.render_template(template_name, variables)

        # Generate cache key for rendered result
        variables_hash = self._generate_content_hash(str(sorted(variables.items())))
        cache_key = self._key_generator.generate_key(
            "rendered",
            {
                "template": template_name,
                "variables_hash": variables_hash,
                "version": "1.0.0"
            }
        )

        try:
            # Try Redis cache for rendered result
            cached_result = await self._redis_cache.get(cache_key)
            if cached_result is not None:
                self._update_stats(increment_redis_hits=True)
                return cached_result

            self._update_stats(increment_redis_misses=True)

        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            # Fall back to direct rendering
            return self.render_template(template_name, variables)

        # Render template
        rendered = self.render_template(template_name, variables)

        try:
            # Cache the rendered result with shorter TTL
            await self._redis_cache.set(cache_key, rendered, ttl=self.redis_ttl // 4)
        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            print(f"Warning: Failed to cache rendered template: {e}")

        return rendered

    async def invalidate_prompt_cache(self, prompt_type: Optional[str] = None):
        """
        Invalidate cached prompts.

        Args:
            prompt_type: Specific prompt type to invalidate, or None for all
        """
        if not self._redis_cache:
            return

        try:
            if prompt_type:
                # Invalidate specific prompt
                cache_key = self._key_generator.generate_key(
                    "system_prompt",
                    {"type": prompt_type, "version": "1.0.0"}
                )
                await self._redis_cache.delete(cache_key)
            else:
                # Invalidate all system prompts
                pattern = self._key_generator.generate_key("system_prompt", {})
                await self._redis_cache.clear()  # Clear all for simplicity

        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            print(f"Warning: Failed to invalidate prompt cache: {e}")

    async def invalidate_template_cache(self, template_name: Optional[str] = None):
        """
        Invalidate cached templates.

        Args:
            template_name: Specific template to invalidate, or None for all
        """
        if not self._redis_cache:
            return

        try:
            if template_name:
                # Invalidate specific template
                cache_key = self._key_generator.generate_key(
                    "template",
                    {"name": template_name, "version": "1.0.0"}
                )
                await self._redis_cache.delete(cache_key)

                # Also invalidate any cached rendered results
                pattern = f"{self._key_generator.prefix}:rendered:*template={template_name}*"
                # Note: This would require pattern deletion support

            else:
                # Invalidate all templates
                await self._redis_cache.clear()

        except Exception as e:
            self._update_stats(increment_cache_errors=True)
            print(f"Warning: Failed to invalidate template cache: {e}")

    async def get_cache_stats(self) -> CacheStats:
        """
        Get cache statistics.

        Returns:
            Cache statistics object
        """
        return self._cache_stats

    def reset_cache_stats(self):
        """Reset cache statistics."""
        with self._stats_lock:
            self._cache_stats = CacheStats()

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on caching system.

        Returns:
            Health check results
        """
        health_info = {
            "redis_cache_available": False,
            "local_cache_available": self.cache_enabled,
            "cache_stats": self._cache_stats.to_dict()
        }

        if self._redis_cache:
            try:
                # Test Redis connection
                test_key = "health_check_test"
                await self._redis_cache.set(test_key, "test", ttl=10)
                result = await self._redis_cache.get(test_key)
                await self._redis_cache.delete(test_key)

                health_info["redis_cache_available"] = result == "test"
            except Exception as e:
                health_info["redis_error"] = str(e)

        return health_info

    async def preload_common_prompts(self, prompt_types: List[str]):
        """
        Preload common prompts into cache.

        Args:
            prompt_types: List of prompt types to preload
        """
        for prompt_type in prompt_types:
            try:
                await self.get_system_prompt_cached(prompt_type)
            except PromptManagerError:
                # Skip invalid prompt types
                continue

    async def preload_common_templates(self, template_names: List[str]):
        """
        Preload common templates into cache.

        Args:
            template_names: List of template names to preload
        """
        for template_name in template_names:
            try:
                await self.get_template_cached(template_name)
            except PromptManagerError:
                # Skip non-existent templates
                continue

    async def optimize_cache(self):
        """
        Optimize cache performance.

        This method can be called periodically to optimize cache settings,
        clean up expired entries, and update statistics.
        """
        try:
            # Update Redis service statistics if available
            if self._redis_service:
                redis_stats = await self._redis_service.get_statistics()
                # Could use these to adjust caching strategies

            # Could implement other optimizations like:
            # - Preloading frequently accessed items
            # - Adjusting TTL based on access patterns
            # - Cleaning up rarely used items

        except Exception as e:
            print(f"Cache optimization warning: {e}")

    def __del__(self):
        """Cleanup when manager is destroyed."""
        if hasattr(self, '_redis_cache') and self._redis_cache:
            try:
                # Note: This is sync, so it might not work perfectly
                # In production, proper cleanup should be handled explicitly
                pass
            except:
                pass


# Global cached prompt manager instance
_global_cached_prompt_manager: Optional[CachedPromptManager] = None
_global_manager_lock = threading.Lock()


def get_cached_prompt_manager() -> CachedPromptManager:
    """
    Get the global CachedPromptManager instance.

    Returns:
        The singleton CachedPromptManager instance
    """
    global _global_cached_prompt_manager

    if _global_cached_prompt_manager is None:
        with _global_manager_lock:
            if _global_cached_prompt_manager is None:
                _global_cached_prompt_manager = CachedPromptManager()

    return _global_cached_prompt_manager


def reset_cached_prompt_manager() -> None:
    """
    Reset the global CachedPromptManager instance.
    Useful for testing or reconfiguration.
    """
    global _global_cached_prompt_manager

    with _global_manager_lock:
        _global_cached_prompt_manager = None
        CachedPromptManager._instance = None