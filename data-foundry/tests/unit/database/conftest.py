"""
Minimal conftest for database tests to avoid import issues.
"""

import sys
import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock the problematic imports
sys_modules_mock = {
    'jose': Mock(),
    'jose.jwt': Mock(),
    'src.app.middleware': Mock(),
    'src.main': Mock(),
    'fastapi.testclient': Mock(),
    'httpx': Mock(),
}


@pytest.fixture(autouse=True)
def mock_problematic_imports():
    """Mock imports that cause issues in test environment."""
    with patch.dict('sys.modules', sys_modules_mock):
        yield
