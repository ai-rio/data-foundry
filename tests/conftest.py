"""
Pytest configuration and fixtures.

This file contains shared pytest configuration and fixtures for all test types
(unit, integration, e2e).
"""

import sys
from pathlib import Path
import pytest
import pytest_asyncio
import asyncio

# Add data-foundry directory to Python path (parent of src, so we can import from src)
# This allows imports like "from src.models..."
data_foundry_path = Path(__file__).parent.parent / "data-foundry"
if str(data_foundry_path.resolve()) not in sys.path:
    sys.path.insert(0, str(data_foundry_path.resolve()))


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """
    Configure pytest with custom markers.

    Markers:
    - unit: Unit tests (fast, isolated)
    - integration: Integration tests (slower, require database)
    - e2e: End-to-end tests (slowest, require full system)
    - slow: Tests that take longer to run
    """
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, isolated)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (require database)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (require full system)"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )


@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.

    This fixture ensures that all async tests use the same event loop
    within a test session, which improves performance and reliability.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Test Configuration
# =============================================================================

# Test database URL (can be overridden with environment variable)
import os
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:"
)

# Stripe test configuration
STRIPE_TEST_API_KEY = os.getenv(
    "STRIPE_TEST_API_KEY",
    "sk_test_dummy_key_for_testing"
)

STRIPE_TEST_WEBHOOK_SECRET = os.getenv(
    "STRIPE_TEST_WEBHOOK_SECRET",
    "whsec_test_dummy_secret_for_testing"
)
