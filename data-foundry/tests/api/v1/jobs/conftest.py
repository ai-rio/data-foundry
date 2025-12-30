"""
Configuration fixtures for jobs router tests.
"""

import pytest


@pytest.fixture
def auth_headers(test_tenant) -> dict[str, str]:
    """
    Create authorization headers for test requests.

    In production, this would include valid JWT tokens.
    For testing, we include tenant identification.
    """
    return {"X-Tenant-ID": test_tenant.tenant_id}
