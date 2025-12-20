"""Simple test to verify basic test setup is working."""

import pytest


def test_basic():
    """A simple test to verify pytest is working."""
    assert True


def test_import():
    """Test that basic imports work."""
    import src.core.config
    from src.core.config import settings

    assert settings is not None
    assert settings.APP_NAME == "Data Foundry"


@pytest.mark.asyncio
async def test_async():
    """Test async test functionality."""
    async def async_function():
        return "async works"

    result = await async_function()
    assert result == "async works"