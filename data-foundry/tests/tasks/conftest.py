"""
Pytest configuration for tasks tests.

This conftest is isolated to avoid importing the main FastAPI app
which has dependencies that may not be installed in all environments.
"""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


# Minimal fixtures for tasks tests
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
