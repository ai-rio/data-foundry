"""
PromptManager - Central management for system prompts and user templates

This module provides a unified interface for managing both system prompts and user-facing templates.
It handles loading, caching, validation, and versioning of prompts.

Features:
- System prompt management
- Template loading and caching
- Template rendering with Jinja2
- Version compatibility checking
- Performance optimization through caching
- Error handling and validation
"""

import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
import weakref

from .system import (
    SystemPromptType,
    get_system_prompt,
    get_all_system_prompts,
)
from .templates import (
    load_template,
    render_template,
    get_template_metadata,
    validate_template_consistency,
    clear_cache as clear_template_cache,
)
from .validation import validate_template_syntax, validate_response_format_schema


class PromptManagerError(Exception):
    """Base exception for PromptManager errors."""
    pass


class PromptVersionError(PromptManagerError):
    """Exception raised when prompt version is incompatible."""
    pass


@dataclass
class CacheEntry:
    """Cache entry for templates or prompts."""
    data: Any
    timestamp: float
    version: str = ""

    def is_expired(self, ttl: float) -> bool:
        """Check if the cache entry has expired."""
        return time.time() - self.timestamp > ttl


class PromptManager:
    """
    Central manager for system prompts and user templates.

    This class provides a unified interface for managing prompts used throughout
    the Data Foundry platform, with built-in caching, validation, and error handling.
    """

    _instance: Optional['PromptManager'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern implementation."""
        # Don't use singleton for tests to allow multiple instances
        if kwargs.pop('skip_singleton', False):
            return super().__new__(cls)

        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        cache_ttl: float = 3600.0,
        skip_singleton: bool = False,
    ):
        """
        Initialize the PromptManager.

        Args:
            template_dir: Directory containing template files
            cache_enabled: Whether to enable caching
            cache_ttl: Cache time-to-live in seconds
        """
        # Avoid re-initialization if already initialized
        if hasattr(self, '_initialized'):
            return

        self.template_dir = template_dir or Path(__file__).parent / "templates"
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl

        # Internal caches
        self._template_cache: Dict[str, CacheEntry] = {}
        self._system_prompts_cache: Dict[str, CacheEntry] = {}

        # Thread safety
        self._cache_lock = threading.RLock()

        # Validate template directory exists
        if not self.template_dir.exists():
            raise PromptManagerError(f"Template directory does not exist: {self.template_dir}")

        self._initialized = True

    def get_system_prompt(self, prompt_type: str) -> str:
        """
        Get a system prompt by type.

        Args:
            prompt_type: The type of system prompt to retrieve

        Returns:
            The system prompt string

        Raises:
            PromptManagerError: If the prompt type is invalid
        """
        cache_key = f"system_{prompt_type}"

        # Check cache first
        if self.cache_enabled:
            with self._cache_lock:
                if cache_key in self._system_prompts_cache:
                    entry = self._system_prompts_cache[cache_key]
                    if not entry.is_expired(self.cache_ttl):
                        return entry.data

        try:
            # Convert string to enum
            if prompt_type not in [t.value for t in SystemPromptType]:
                raise PromptManagerError(f"Invalid system prompt type: {prompt_type}")

            system_type = SystemPromptType(prompt_type)
            prompt = get_system_prompt(system_type)

            # Cache the result
            if self.cache_enabled:
                with self._cache_lock:
                    self._system_prompts_cache[cache_key] = CacheEntry(
                        data=prompt,
                        timestamp=time.time(),
                        version="1.0.0"
                    )

            return prompt

        except ValueError as e:
            raise PromptManagerError(f"Invalid system prompt type: {prompt_type}") from e

    def get_template(self, template_name: str) -> Dict[str, Any]:
        """
        Get a template by name.

        Args:
            template_name: Name of the template file

        Returns:
            Dictionary containing template data

        Raises:
            PromptManagerError: If template is not found or invalid
        """
        # Check cache first
        if self.cache_enabled:
            with self._cache_lock:
                if template_name in self._template_cache:
                    entry = self._template_cache[template_name]
                    if not entry.is_expired(self.cache_ttl):
                        return entry.data

        # Load from file
        template_data = self._load_template_from_file(template_name)

        # Cache the result
        if self.cache_enabled:
            with self._cache_lock:
                metadata = template_data.get('metadata', {})
                version = metadata.get('version', '1.0.0')
                self._template_cache[template_name] = CacheEntry(
                    data=template_data,
                    timestamp=time.time(),
                    version=version
                )

        return template_data

    def render_template(self, template_name: str, variables: Dict[str, Any]) -> str:
        """
        Render a template with the provided variables.

        Args:
            template_name: Name of the template file
            variables: Dictionary of variables to substitute

        Returns:
            Rendered template string

        Raises:
            PromptManagerError: If rendering fails
        """
        try:
            # Get template data
            template_data = self.get_template(template_name)

            # Extract required variables from metadata
            required_vars = template_data.get('metadata', {}).get('required_variables', [])

            # Validate variables
            self._validate_variables(template_data['template'], variables, required_vars)

            # Render template
            return render_template(template_name, variables)

        except ValueError as e:
            raise PromptManagerError(f"Template validation failed: {e}") from e
        except Exception as e:
            raise PromptManagerError(f"Failed to render template {template_name}: {e}") from e

    def get_template_metadata(self, template_name: str) -> Dict[str, Any]:
        """
        Get metadata for a template without loading the full template.

        Args:
            template_name: Name of the template file

        Returns:
            Dictionary containing template metadata

        Raises:
            PromptManagerError: If template is not found
        """
        try:
            template_data = self.get_template(template_name)
            return template_data.get('metadata', {})
        except Exception as e:
            raise PromptManagerError(f"Failed to get template metadata: {e}") from e

    def list_templates(self) -> List[str]:
        """
        List all available templates.

        Returns:
            List of template filenames
        """
        if not self.template_dir.exists():
            return []

        yaml_files = list(self.template_dir.glob("*.yaml"))
        yml_files = list(self.template_dir.glob("*.yml"))

        templates = [f.name for f in yaml_files + yml_files]
        return sorted(templates)

    def list_system_prompts(self) -> List[str]:
        """
        List all available system prompt types.

        Returns:
            List of system prompt type strings
        """
        return [prompt_type.value for prompt_type in SystemPromptType]

    def clear_cache(self) -> None:
        """Clear all caches."""
        with self._cache_lock:
            self._template_cache.clear()
            self._system_prompts_cache.clear()

        # Also clear template module cache
        clear_template_cache()

    def validate_template(self, template_name: str) -> bool:
        """
        Validate a template file.

        Args:
            template_name: Name of the template file

        Returns:
            True if template is valid

        Raises:
            PromptManagerError: If template is invalid
        """
        try:
            template_data = self._load_template_from_file(template_name)

            # Validate structure
            self._validate_template_structure(template_data)

            # Validate template syntax
            validate_template_syntax(template_data.get('template', ''))

            # Validate response format
            response_format = template_data.get('response_format', {})
            validate_response_format_schema(response_format)

            # Check for consistency issues
            warnings = validate_template_consistency(template_data)
            if warnings:
                # Log warnings but don't fail validation
                for warning in warnings:
                    print(f"Template warning ({template_name}): {warning}")

            return True

        except Exception as e:
            raise PromptManagerError(f"Template validation failed: {e}") from e

    def _load_template_from_file(self, template_name: str) -> Dict[str, Any]:
        """
        Load a template from file.

        Args:
            template_name: Name of the template file

        Returns:
            Dictionary containing template data

        Raises:
            PromptManagerError: If template cannot be loaded
        """
        try:
            template_path = self.template_dir / template_name

            if not template_path.exists():
                raise PromptManagerError(f"Template not found: {template_name}")

            return load_template(template_name)

        except FileNotFoundError as e:
            raise PromptManagerError(f"Template not found: {template_name}") from e
        except Exception as e:
            raise PromptManagerError(f"Failed to load template {template_name}: {e}") from e

    def _validate_template_structure(self, template_data: Dict[str, Any]) -> None:
        """
        Validate that template has required structure.

        Args:
            template_data: Template data to validate

        Raises:
            PromptManagerError: If structure is invalid
        """
        required_sections = ['metadata', 'template', 'response_format']

        for section in required_sections:
            if section not in template_data:
                raise PromptManagerError(f"Template missing required section: {section}")

    def _validate_variables(
        self,
        template_content: str,
        provided_variables: Dict[str, Any],
        required_variables: List[str]
    ) -> None:
        """
        Validate that all required variables are provided.

        Args:
            template_content: The template content
            provided_variables: Variables being provided
            required_variables: List of required variables

        Raises:
            PromptManagerError: If variables are missing
        """
        from .validation import validate_template_variables

        try:
            validate_template_variables(template_content, provided_variables, required_variables)
        except ValueError as e:
            raise PromptManagerError(f"Missing required template variables: {e}") from e

    def _check_template_version(self, template_name: str, expected_version: str) -> None:
        """
        Check that template version is compatible.

        Args:
            template_name: Name of the template
            expected_version: Expected version string

        Raises:
            PromptVersionError: If version is incompatible
        """
        metadata = self.get_template_metadata(template_name)
        actual_version = metadata.get('version', '1.0.0')

        # Simple version comparison - could be enhanced with semantic versioning
        if actual_version != expected_version:
            raise PromptVersionError(
                f"Template {template_name} version mismatch: "
                f"expected {expected_version}, got {actual_version}"
            )


# Global instance
_global_prompt_manager: Optional[PromptManager] = None
_global_manager_lock = threading.Lock()


def get_prompt_manager() -> PromptManager:
    """
    Get the global PromptManager instance.

    Returns:
        The singleton PromptManager instance
    """
    global _global_prompt_manager

    if _global_prompt_manager is None:
        with _global_manager_lock:
            if _global_prompt_manager is None:
                _global_prompt_manager = PromptManager()

    return _global_prompt_manager


def reset_prompt_manager() -> None:
    """
    Reset the global PromptManager instance.
    Useful for testing or reconfiguration.
    """
    global _global_prompt_manager

    with _global_manager_lock:
        _global_prompt_manager = None
        PromptManager._instance = None