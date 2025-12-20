"""
Data Foundry Prompt Management System

This module provides comprehensive prompt management capabilities for AI-powered data processing.
It includes system prompts, user prompt templates, validation, and management utilities.

The system follows PromptOps best practices with externalized prompt management,
versioning support, and multi-provider AI integration through LiteLLM.

Enhanced with Redis caching capabilities for improved performance in distributed environments.
"""

from .system import (
    SystemPromptType,
    get_system_prompt,
    get_all_system_prompts,
    DataLabelingExpert,
    PIIAnalyst,
    ConfidenceAssessor,
)
from .templates import (
    load_template,
    render_template,
    get_template_metadata,
    TemplateType,
    DataClassificationTemplate,
)
from .prompt_manager import (
    PromptManager,
    PromptManagerError,
    PromptVersionError,
    get_prompt_manager,
    reset_prompt_manager,
)
from .cached_prompt_manager import (
    CachedPromptManager,
    CachedPromptManagerError,
    CacheStats,
    get_cached_prompt_manager,
    reset_cached_prompt_manager,
)
from .validation import (
    validate_template_syntax,
    validate_template_variables,
    validate_response_format_schema,
)

# Factory function to get appropriate manager based on configuration
def get_manager(use_cached: bool = None):
    """
    Get the appropriate prompt manager based on configuration.

    Args:
        use_cached: Force use of cached manager (True) or basic manager (False)
                   If None, uses configuration to decide

    Returns:
        PromptManager instance (either basic or cached)
    """
    from ..config import get_settings

    settings = get_settings()

    # Determine which manager to use
    if use_cached is None:
        # Use configuration to decide
        use_cached = (
            settings.PROMPT_CACHE_ENABLED and
            settings.REDIS_URL and
            settings.PROMPT_CACHE_ENABLED
        )

    if use_cached:
        try:
            return get_cached_prompt_manager()
        except Exception as e:
            # Fall back to basic manager if cached fails
            print(f"Warning: Failed to initialize cached prompt manager, falling back to basic: {e}")
            return get_prompt_manager()
    else:
        return get_prompt_manager()


# Convenience functions that work with either manager type
async def get_system_prompt_cached(prompt_type: str) -> str:
    """
    Get a system prompt with caching if available.

    Args:
        prompt_type: The type of system prompt to retrieve

    Returns:
        The system prompt string
    """
    try:
        manager = get_cached_prompt_manager()
        return await manager.get_system_prompt_cached(prompt_type)
    except Exception:
        # Fall back to basic manager
        manager = get_prompt_manager()
        return manager.get_system_prompt(prompt_type)


async def get_template_cached(template_name: str) -> dict:
    """
    Get a template with caching if available.

    Args:
        template_name: Name of the template file

    Returns:
        Dictionary containing template data
    """
    try:
        manager = get_cached_prompt_manager()
        return await manager.get_template_cached(template_name)
    except Exception:
        # Fall back to basic manager
        manager = get_prompt_manager()
        return manager.get_template(template_name)


async def render_template_cached(
    template_name: str,
    variables: dict,
    cache_rendered: bool = True
) -> str:
    """
    Render a template with caching if available.

    Args:
        template_name: Name of the template file
        variables: Dictionary of variables to substitute
        cache_rendered: Whether to cache the rendered result

    Returns:
        Rendered template string
    """
    try:
        manager = get_cached_prompt_manager()
        return await manager.render_template_cached(template_name, variables, cache_rendered)
    except Exception:
        # Fall back to basic manager
        manager = get_prompt_manager()
        return manager.render_template(template_name, variables)


async def invalidate_prompt_cache(prompt_type: str = None):
    """
    Invalidate cached prompts.

    Args:
        prompt_type: Specific prompt type to invalidate, or None for all
    """
    try:
        manager = get_cached_prompt_manager()
        await manager.invalidate_prompt_cache(prompt_type)
    except Exception:
        # No cache to invalidate
        pass


async def invalidate_template_cache(template_name: str = None):
    """
    Invalidate cached templates.

    Args:
        template_name: Specific template to invalidate, or None for all
    """
    try:
        manager = get_cached_prompt_manager()
        await manager.invalidate_template_cache(template_name)
    except Exception:
        # No cache to invalidate
        pass


async def get_cache_stats():
    """
    Get cache statistics.

    Returns:
        CacheStats object or None if no cached manager
    """
    try:
        manager = get_cached_prompt_manager()
        return await manager.get_cache_stats()
    except Exception:
        return None


async def prompt_manager_health_check():
    """
    Perform health check on prompt manager caching system.

    Returns:
        Health check results dictionary
    """
    try:
        manager = get_cached_prompt_manager()
        return await manager.health_check()
    except Exception:
        return {
            "cached_manager_available": False,
            "basic_manager_available": True
        }


__all__ = [
    # System prompts
    "SystemPromptType",
    "get_system_prompt",
    "get_all_system_prompts",
    "DataLabelingExpert",
    "PIIAnalyst",
    "ConfidenceAssessor",

    # Templates
    "load_template",
    "render_template",
    "get_template_metadata",
    "TemplateType",
    "DataClassificationTemplate",

    # Basic prompt manager
    "PromptManager",
    "PromptManagerError",
    "PromptVersionError",
    "get_prompt_manager",
    "reset_prompt_manager",

    # Cached prompt manager
    "CachedPromptManager",
    "CachedPromptManagerError",
    "CacheStats",
    "get_cached_prompt_manager",
    "reset_cached_prompt_manager",

    # Validation
    "validate_template_syntax",
    "validate_template_variables",
    "validate_response_format_schema",

    # Factory and convenience functions
    "get_manager",
    "get_system_prompt_cached",
    "get_template_cached",
    "render_template_cached",
    "invalidate_prompt_cache",
    "invalidate_template_cache",
    "get_cache_stats",
    "prompt_manager_health_check",
]