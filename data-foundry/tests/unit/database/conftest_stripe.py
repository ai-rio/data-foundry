"""
Conftest for Stripe billing tests to avoid root conftest import issues.
"""

import sys
from unittest.mock import Mock

# Mock problematic imports before loading other modules
sys.modules['structlog'] = Mock()
sys.modules['jose'] = Mock()
sys.modules['jose.jwt'] = Mock()

import pytest
from unittest.mock import Mock, patch, AsyncMock


@pytest.fixture
async def mock_db_session():
    """Create a mock database session for testing."""
    session = AsyncMock()
    session.execute.return_value = None
    session.commit.return_value = None
    session.rollback.return_value = None
    return session
