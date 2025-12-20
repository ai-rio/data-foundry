"""
Test that prompt management configuration is properly integrated with core settings.
"""

import pytest
from src.core.config import Settings, get_settings, PROMPT_CONFIG


class TestPromptConfig:
    """Test prompt management configuration integration."""

    def test_prompt_config_settings(self):
        """Test that prompt configuration settings are properly defined."""
        settings = get_settings()

        # Check that all prompt config settings exist
        assert hasattr(settings, 'PROMPT_TEMPLATE_DIR')
        assert hasattr(settings, 'PROMPT_CACHE_ENABLED')
        assert hasattr(settings, 'PROMPT_CACHE_TTL')
        assert hasattr(settings, 'PROMPT_VERSION_CHECK')
        assert hasattr(settings, 'PROMPT_VALIDATION_ENABLED')
        assert hasattr(settings, 'PROMPT_DEBUG_MODE')
        assert hasattr(settings, 'PROMPT_MAX_LENGTH')
        assert hasattr(settings, 'PROMPT_TRUNCATE_ENABLED')
        assert hasattr(settings, 'PROMPT_COST_TRACKING')

        # Check default values
        assert settings.PROMPT_TEMPLATE_DIR == "src/core/prompts/templates"
        assert settings.PROMPT_CACHE_ENABLED is True
        assert settings.PROMPT_CACHE_TTL == 3600
        assert settings.PROMPT_VERSION_CHECK is True
        assert settings.PROMPT_VALIDATION_ENABLED is True
        assert settings.PROMPT_DEBUG_MODE is False
        assert settings.PROMPT_MAX_LENGTH == 32000
        assert settings.PROMPT_TRUNCATE_ENABLED is False
        assert settings.PROMPT_COST_TRACKING is True

    def test_prompt_template_dir_path_property(self):
        """Test that prompt_template_dir_path returns valid path."""
        settings = get_settings()
        template_path = settings.prompt_template_dir_path

        assert isinstance(template_path, str)
        assert template_path.endswith("src/core/prompts/templates")

    def test_prompt_config_dict(self):
        """Test that PROMPT_CONFIG dictionary is properly constructed."""
        assert isinstance(PROMPT_CONFIG, dict)

        required_keys = [
            "template_dir",
            "cache_enabled",
            "cache_ttl",
            "version_check",
            "validation_enabled",
            "debug_mode",
            "max_length",
            "truncate_enabled",
            "cost_tracking",
        ]

        for key in required_keys:
            assert key in PROMPT_CONFIG

        # Check values match settings
        settings = get_settings()
        assert PROMPT_CONFIG["template_dir"] == settings.prompt_template_dir_path
        assert PROMPT_CONFIG["cache_enabled"] == settings.PROMPT_CACHE_ENABLED
        assert PROMPT_CONFIG["cache_ttl"] == settings.PROMPT_CACHE_TTL

    def test_custom_prompt_config(self):
        """Test that custom prompt configuration can be set."""
        custom_settings = Settings(
            PROMPT_CACHE_ENABLED=False,
            PROMPT_CACHE_TTL=7200,
            PROMPT_DEBUG_MODE=True
        )

        assert custom_settings.PROMPT_CACHE_ENABLED is False
        assert custom_settings.PROMPT_CACHE_TTL == 7200
        assert custom_settings.PROMPT_DEBUG_MODE is True