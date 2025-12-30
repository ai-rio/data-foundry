"""
Pytest configuration for tasks tests.

This conftest extends the main conftest.py for task-specific testing.
Database fixtures and other shared fixtures are inherited from conftest.py
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from contextlib import contextmanager

# Add project root to path FIRST
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# =============================================================================
# Prefect Context Fixtures
# =============================================================================

@contextmanager
def prefect_test_context():
    """
    Context manager that provides a Prefect flow/task run context for testing.

    This allows tests to call Prefect tasks that use get_run_logger() without
    being inside an actual flow run.

    Usage:
        with prefect_test_context():
            result = await some_prefect_task()
    """
    from prefect import flow
    from unittest.mock import patch, MagicMock

    # Create a mock logger
    mock_logger = MagicMock()
    mock_logger.info = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.warning = MagicMock()
    mock_logger.error = MagicMock()
    mock_logger.exception = MagicMock()

    # Mock get_run_logger to return our mock logger
    with patch('prefect.get_run_logger', return_value=mock_logger):
        yield


@pytest.fixture
def prefect_context():
    """
    Pytest fixture that provides a Prefect context for testing.

    Use this fixture in tests that call Prefect tasks directly.
    """
    from prefect import flow
    from unittest.mock import patch, MagicMock

    # Create a mock logger
    mock_logger = MagicMock()
    mock_logger.info = MagicMock()
    mock_logger.debug = MagicMock()
    mock_logger.warning = MagicMock()
    mock_logger.error = MagicMock()
    mock_logger.exception = MagicMock()

    # Mock get_run_logger to return our mock logger
    with patch('prefect.get_run_logger', return_value=mock_logger):
        yield True  # Yield a value to show the fixture was activated


@pytest.fixture
def sample_tenant_id():
    return "tenant_test_001"


@pytest.fixture
def sample_user_id():
    return "user_test_001"


@pytest.fixture
def sample_transaction_data():
    return [
        {
            "id": "txn_001",
            "tenant_id": "tenant_test_001",
            "user_id": "user_test_001",
            "amount": 1000.0,
            "counterparty": "unknown_entity",
            "transaction_date": "2025-01-15T10:30:00Z"
        },
        {
            "id": "txn_002",
            "tenant_id": "tenant_test_001",
            "user_id": "user_test_001",
            "amount": 5000.0,
            "counterparty": "high_risk_jurisdiction",
            "transaction_date": "2025-01-15T11:30:00Z"
        }
    ]
