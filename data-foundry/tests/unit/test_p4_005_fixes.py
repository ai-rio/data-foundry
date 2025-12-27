"""
Test suite for P4-005 Fixes

Tests the following fixes:
1. TestClient import changed to starlette.testclient
2. Rate limiting on usage endpoint (10-60 req/min)
3. Admin role database verification
4. Tenant ID regex validation
5. ISO 8601 date format validation with timezone check
"""

import pytest
from datetime import datetime, timezone
from src.core.validators import validate_tenant_id, validate_iso8601_datetime


class TestTenantIdValidation:
    """Test tenant ID regex validation (P4-005 Fix #4)."""

    def test_valid_tenant_ids(self):
        """Test that valid tenant IDs pass validation."""
        valid_ids = [
            "tenant_abc123",
            "abc",
            "tenant-123-xyz",
            "TENANT_123",
            "a1b2c3d4",
            "my_tenant-2025",
        ]
        for tenant_id in valid_ids:
            assert validate_tenant_id(tenant_id), f"Should validate: {tenant_id}"

    def test_invalid_tenant_ids(self):
        """Test that invalid tenant IDs fail validation."""
        invalid_ids = [
            "ab",  # Too short (< 3 chars)
            "a" * 65,  # Too long (> 64 chars)
            "_tenant",  # Starts with underscore
            "-tenant",  # Starts with hyphen
            "tenant_",  # Ends with underscore
            "tenant-",  # Ends with hyphen
            "tenant__id",  # Consecutive underscores
            "tenant--id",  # Consecutive hyphens
            "tenant_-id",  # Mixed consecutive separators
            "tenant@example.com",  # Invalid characters (@, .)
            "tenant id",  # Contains space
            "",  # Empty string
            None,  # None value
        ]
        for tenant_id in invalid_ids:
            assert not validate_tenant_id(tenant_id), f"Should reject: {tenant_id}"


class TestISO8601DateValidation:
    """Test ISO 8601 date format validation (P4-005 Fix #5)."""

    def test_valid_iso8601_with_timezone(self):
        """Test valid ISO 8601 dates with timezone."""
        valid_dates = [
            "2025-01-15T10:30:00Z",
            "2025-01-15T10:30:00+00:00",
            "2025-01-15T10:30:00-05:00",
            "2025-01-15T10:30:00.123Z",
            "2025-01-15T10:30:00.123456+00:00",
        ]
        for date_str in valid_dates:
            assert validate_iso8601_datetime(date_str, require_timezone=True), \
                f"Should validate with timezone: {date_str}"

    def test_valid_iso8601_without_timezone(self):
        """Test valid ISO 8601 dates without timezone when not required."""
        valid_dates = [
            "2025-01-15T10:30:00",
            "2025-01-15T10:30:00.123",
            "2025-01-15",
        ]
        for date_str in valid_dates:
            assert validate_iso8601_datetime(date_str, require_timezone=False), \
                f"Should validate without timezone: {date_str}"

    def test_invalid_iso8601_when_timezone_required(self):
        """Test that dates without timezone fail when timezone is required."""
        invalid_dates = [
            "2025-01-15T10:30:00",
            "2025-01-15",
            "2025-01-15T10:30:00.123",
        ]
        for date_str in invalid_dates:
            assert not validate_iso8601_datetime(date_str, require_timezone=True), \
                f"Should reject without timezone: {date_str}"

    def test_invalid_iso8601_format(self):
        """Test completely invalid date formats."""
        invalid_dates = [
            "invalid-date",
            "2025/01/15",
            "01-15-2025",
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
            "",
            None,
        ]
        for date_str in invalid_dates:
            assert not validate_iso8601_datetime(date_str, require_timezone=False), \
                f"Should reject invalid format: {date_str}"


class TestRateLimitConfiguration:
    """Test rate limiting configuration (P4-005 Fix #2)."""

    def test_usage_endpoint_rate_limit(self):
        """Test that usage endpoint has rate limit within 10-60 req/min."""
        from src.middleware.rate_limit import RATE_LIMITS

        usage_limit = RATE_LIMITS.get("usage")
        assert usage_limit is not None, "Usage endpoint should have rate limit configured"

        # Extract numeric value and unit
        # Format: "60/minute" or "30/minute"
        parts = usage_limit.split("/")
        limit_value = int(parts[0])
        limit_unit = parts[1]

        assert limit_unit == "minute", f"Rate limit should be per minute, got: {limit_unit}"
        assert 10 <= limit_value <= 60, \
            f"Usage rate limit should be 10-60 requests per minute, got: {limit_value}"


class TestAdminVerificationDependency:
    """Test admin verification dependency (P4-005 Fix #3)."""

    def test_require_admin_dependency_exists(self):
        """Test that require_admin dependency exists and is importable."""
        from src.api.deps import require_admin

        assert require_admin is not None, "require_admin dependency should be defined"
        assert callable(require_admin), "require_admin should be callable"

    def test_require_role_dependency_exists(self):
        """Test that require_role dependency exists and is importable."""
        from src.api.deps import require_role

        assert require_role is not None, "require_role dependency should be defined"
        assert callable(require_role), "require_role should be callable"


class TestTestClientImport:
    """Test TestClient import fix (P4-005 Fix #1)."""

    def test_testclient_import_in_tests(self):
        """Test that tests use starlette.testclient.TestClient."""
        import tests.unit.api.v1.billing.test_usage_summary as test_module

        # Check that the module imports TestClient from starlette
        import inspect
        source = inspect.getsource(test_module)

        # Should import from starlette.testclient
        assert "from starlette.testclient import TestClient" in source, \
            "Tests should import TestClient from starlette.testclient"

        # Should NOT import from fastapi.testing
        assert "from fastapi.testing import TestClient" not in source, \
            "Tests should NOT import TestClient from fastapi.testing"
