"""
Simple conftest for coverage analysis without FastAPI dependencies
"""

import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

# Mock all the FastAPI and database dependencies
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = Mock()
    return session

@pytest.fixture
def mock_redis_service():
    """Mock Redis service."""
    redis = Mock()
    redis.health_check = AsyncMock(return_value=True)
    redis.clear_cache = AsyncMock()
    redis.close = AsyncMock()
    return redis

# Mock all imports that would cause issues
import sys
from unittest.mock import MagicMock

# Mock modules
sys.modules['fastapi'] = MagicMock()
sys.modules['fastapi.testclient'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.ext.asyncio'] = MagicMock()
sys.modules['sqlmodel'] = MagicMock()
sys.modules['uvicorn'] = MagicMock()
sys.modules['jose'] = MagicMock()