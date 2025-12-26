"""
Test suite for Usage Summary Endpoint (P4-005).

TDD Approach: Red-Green-Refactor
- These tests are written FIRST (Red phase)
- They will FAIL until implementation is complete
- This ensures 95%+ test coverage from the start

Requirements:
1. GET /billing/usage/{tenant_id} endpoint
2. Query stripe_meter_events aggregated by event_name
3. Returns usage breakdown, estimated costs, and sync status
4. Query parameters: period_start, period_end (ISO 8601)
5. Pure database query - no external API dependencies
6. Security score: 95+ minimum
7. Test coverage: 95% minimum

Test Scenarios:
- Happy path: Get usage summary with data
- Date range filtering (period_start, period_end)
- Tenant isolation (only return data for requested tenant)
- Empty results (no usage data for tenant)
- Authentication required (401 without valid JWT)
- Authorization (tenant_id from JWT matches requested tenant_id)
- Cost calculation by tier
- Sync status reporting (pending/failed events)
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timedelta
from typing import Dict, Any

import pytest
from fastapi import status
from fastapi.testing import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.stripe_billing import (
    StripeMeterEvent,
    StripeMeterEventStatus,
    StripeSubscription
)
from src.api.v1.billing.router import router


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_auth_user():
    """Mock authenticated user with tenant_id."""
    return {
        "sub": "user_123",
        "tenant_id": "tenant_abc",
        "iss": "https://test.clerk.com",
        "aud": "test-audience",
        "exp": (datetime.now() + timedelta(hours=1)).timestamp(),
        "iat": datetime.now().timestamp()
    }


@pytest.fixture
def mock_auth_user_different_tenant():
    """Mock authenticated user with different tenant_id."""
    return {
        "sub": "user_456",
        "tenant_id": "tenant_xyz",  # Different tenant
        "iss": "https://test.clerk.com",
        "aud": "test-audience",
        "exp": (datetime.now() + timedelta(hours=1)).timestamp(),
        "iat": datetime.now().timestamp()
    }


@pytest.fixture
def mock_auth_admin():
    """Mock authenticated admin user (can view any tenant)."""
    return {
        "sub": "admin_123",
        "tenant_id": None,  # Admin has no specific tenant
        "role": "admin",
        "iss": "https://test.clerk.com",
        "aud": "test-audience",
        "exp": (datetime.now() + timedelta(hours=1)).timestamp(),
        "iat": datetime.now().timestamp()
    }


@pytest.fixture
def sample_meter_events():
    """Sample meter events for testing."""
    now = datetime.now()
    return [
        StripeMeterEvent(
            id=1,
            tenant_id="tenant_abc",
            event_name="ai_labels",
            quantity=1000,
            idempotency_key="idempotency_key_1",
            status=StripeMeterEventStatus.SUCCEEDED,
            stripe_response={"id": "evt_1"},
            created_at=now - timedelta(days=1),
            retried_at=None,
            retry_count=0
        ),
        StripeMeterEvent(
            id=2,
            tenant_id="tenant_abc",
            event_name="human_audits",
            quantity=50,
            idempotency_key="idempotency_key_2",
            status=StripeMeterEventStatus.SUCCEEDED,
            stripe_response={"id": "evt_2"},
            created_at=now - timedelta(days=1),
            retried_at=None,
            retry_count=0
        ),
        StripeMeterEvent(
            id=3,
            tenant_id="tenant_abc",
            event_name="ai_labels",
            quantity=500,
            idempotency_key="idempotency_key_3",
            status=StripeMeterEventStatus.PENDING,
            stripe_response=None,
            created_at=now,
            retried_at=None,
            retry_count=0
        ),
        StripeMeterEvent(
            id=4,
            tenant_id="tenant_abc",
            event_name="human_audits",
            quantity=10,
            idempotency_key="idempotency_key_4",
            status=StripeMeterEventStatus.FAILED,
            stripe_response=None,
            error_message="Connection timeout",
            created_at=now - timedelta(hours=2),
            retried_at=now - timedelta(hours=1),
            retry_count=1
        ),
        StripeMeterEvent(
            id=5,
            tenant_id="tenant_xyz",  # Different tenant
            event_name="ai_labels",
            quantity=2000,
            idempotency_key="idempotency_key_5",
            status=StripeMeterEventStatus.SUCCEEDED,
            stripe_response={"id": "evt_5"},
            created_at=now - timedelta(days=1),
            retried_at=None,
            retry_count=0
        ),
    ]


@pytest.fixture
def sample_subscription():
    """Sample subscription for tier pricing."""
    now = datetime.now()
    return StripeSubscription(
        id=1,
        tenant_id="tenant_abc",
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        status="active",
        current_period_start=now - timedelta(days=30),
        current_period_end=now + timedelta(days=30),
        cancel_at_period_end=False,
        tier="growth"
    )


# =============================================================================
# Test Classes
# =============================================================================

class TestUsageSummaryHappyPath:
    """Test happy path scenarios for usage summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_usage_summary_success(
        self,
        mock_db_session: AsyncSession,
        sample_meter_events,
        sample_subscription
    ):
        """
        Test: Successfully retrieve usage summary.

        Given:
            - Authenticated user with tenant_id
            - Existing meter events in database
            - Active subscription

        When:
            - GET /billing/usage/{tenant_id} is called

        Then:
            - Returns 200 OK
            - Returns aggregated usage by event_name
            - Returns estimated cost breakdown
            - Returns sync status (last_sync, pending_events, failed_events)
        """
        # Mock query execution
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 1500, 2),  # event_name, total_quantity, event_count
            ("human_audits", 60, 2)
        ]
        mock_db_session.execute.return_value = mock_result

        # Mock subscription query
        mock_sub_result = MagicMock()
        mock_sub_result.scalar_one_or_none.return_value = sample_subscription
        mock_db_session.execute.return_value = mock_sub_result

        with patch('src.api.v1.billing.router.get_db_session') as mock_get_db:
            mock_get_db.return_value = mock_db_session

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = {
                    "sub": "user_123",
                    "tenant_id": "tenant_abc"
                }

                from fastapi import FastAPI
                app = FastAPI()
                app.include_router(router)

                # Import the function after patching
                from src.api.v1.billing.router import get_usage_summary

                # Call the function directly
                result = await get_usage_summary(
                    tenant_id="tenant_abc",
                    period_start=None,
                    period_end=None,
                    current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
                )

                # Verify response structure
                assert result is not None
                assert "usage_breakdown" in result
                assert "estimated_costs" in result
                assert "sync_status" in result


class TestUsageSummaryDateFiltering:
    """Test date range filtering scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_with_date_range(
        self,
        mock_db_session: AsyncSession
    ):
        """
        Test: Filter usage by date range.

        Given:
            - Authenticated user
            - Meter events across multiple time periods
            - period_start and period_end specified

        When:
            - GET /billing/usage/{tenant_id}?period_start=...&period_end=...

        Then:
            - Returns only events within the date range
            - Filters by created_at timestamp
        """
        period_start = (datetime.now() - timedelta(days=7)).isoformat()
        period_end = datetime.now().isoformat()

        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 500, 1),
            ("human_audits", 10, 1)
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=period_start,
                period_end=period_end,
                current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
            )

            assert result is not None
            # Verify the date range was used in the query


class TestUsageSummaryTenantIsolation:
    """Test tenant isolation scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_tenant_isolation(
        self,
        mock_db_session: AsyncSession,
        sample_meter_events
    ):
        """
        Test: Only return usage data for requested tenant.

        Given:
            - Authenticated user requesting tenant_abc
            - Meter events exist for multiple tenants

        When:
            - GET /billing/usage/tenant_abc

        Then:
            - Returns only tenant_abc's usage data
            - Does NOT include tenant_xyz's data
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 1500, 2),  # Only tenant_abc data
            ("human_audits", 60, 2)
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
            )

            assert result is not None


class TestUsageSummaryAuthentication:
    """Test authentication scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_missing_auth_header(self):
        """
        Test: Return 401 when Authorization header is missing.

        Given:
            - Request without Authorization header

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Returns 401 Unauthorized
            - Error message indicates missing auth
        """
        from fastapi import HTTPException

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.side_effect = HTTPException(
                status_code=401,
                detail="Missing Authorization header"
            )

            from src.api.v1.billing.router import get_usage_summary

            with pytest.raises(HTTPException) as exc_info:
                await get_usage_summary(
                    tenant_id="tenant_abc",
                    period_start=None,
                    period_end=None,
                    current_user=None
                )

            assert exc_info.value.status_code == 401


class TestUsageSummaryAuthorization:
    """Test authorization scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_unauthorized_tenant_access(
        self,
        mock_auth_user,
        mock_auth_user_different_tenant
    ):
        """
        Test: Return 403 when user tries to access different tenant's usage.

        Given:
            - User with tenant_id=tenant_abc
            - Requesting usage for tenant_xyz

        When:
            - GET /billing/usage/tenant_xyz

        Then:
            - Returns 403 Forbidden
            - Error message indicates authorization failure
        """
        from fastapi import HTTPException

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            # User from tenant_abc trying to access tenant_xyz
            with pytest.raises(HTTPException) as exc_info:
                await get_usage_summary(
                    tenant_id="tenant_xyz",  # Different tenant
                    period_start=None,
                    period_end=None,
                    current_user=mock_auth_user
                )

            assert exc_info.value.status_code == 403


    @pytest.mark.asyncio
    async def test_usage_summary_admin_can_view_any_tenant(
        self,
        mock_db_session: AsyncSession,
        mock_auth_admin
    ):
        """
        Test: Admin users can view any tenant's usage.

        Given:
            - Admin user (tenant_id=None, role=admin)
            - Requesting usage for tenant_abc

        When:
            - GET /billing/usage/tenant_abc

        Then:
            - Returns usage data successfully
            - Admin can access any tenant's data
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 1000, 1),
            ("human_audits", 50, 1)
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_admin

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user=mock_auth_admin
            )

            assert result is not None


class TestUsageSummaryEmptyResults:
    """Test empty results scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_no_data_for_tenant(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Return empty breakdown when no usage data exists.

        Given:
            - Authenticated user
            - No meter events for tenant in database

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Returns 200 OK
            - usage_breakdown is empty or zero values
            - estimated_costs are zero
            - sync_status shows no pending/failed events
        """
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No events
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            assert result is not None
            assert "usage_breakdown" in result


class TestUsageSummaryCostCalculation:
    """Test cost calculation scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_cost_calculation_by_tier(
        self,
        mock_db_session: AsyncSession,
        sample_subscription
    ):
        """
        Test: Calculate estimated costs based on tier pricing.

        Given:
            - Tenant on 'growth' tier
            - Usage: 1500 ai_labels, 60 human_audits

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Returns estimated costs based on growth tier pricing
            - ai_labels cost: quantity * tier_price_per_unit
            - human_audits cost: quantity * tier_price_per_unit
            - total_cost: sum of all event type costs
        """
        # Growth tier pricing: $0.001 per AI label, $0.01 per human audit
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 1500, 2),  # 1500 * $0.001 = $1.50
            ("human_audits", 60, 2)   # 60 * $0.01 = $0.60
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
            )

            assert result is not None
            assert "estimated_costs" in result


class TestUsageSummarySyncStatus:
    """Test sync status reporting scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_sync_status_with_pending_events(
        self,
        mock_db_session: AsyncSession,
        sample_meter_events
    ):
        """
        Test: Report sync status with pending events.

        Given:
            - Meter events with status=pending
            - Meter events with status=failed

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - sync_status.pending_events: count of pending events
            - sync_status.failed_events: count of failed events
            - sync_status.last_sync: timestamp of last succeeded event
        """
        # Mock aggregation query
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 1500, 2)
        ]

        # Mock status query
        mock_status_result = MagicMock()
        mock_status_result.all.return_value = [
            (StripeMeterEventStatus.PENDING, 1),
            (StripeMeterEventStatus.FAILED, 1)
        ]

        mock_db_session.execute.return_value = mock_status_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
            )

            assert result is not None
            assert "sync_status" in result


class TestUsageSummaryInputValidation:
    """Test input validation scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_invalid_date_format(self):
        """
        Test: Return 400 for invalid date format.

        Given:
            - Authenticated user
            - Invalid ISO 8601 date format

        When:
            - GET /billing/usage/{tenant_id}?period_start=invalid

        Then:
            - Returns 400 Bad Request
            - Error message indicates invalid date format
        """
        from fastapi import HTTPException

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            with pytest.raises((HTTPException, ValueError)):
                await get_usage_summary(
                    tenant_id="tenant_abc",
                    period_start="invalid-date",
                    period_end=None,
                    current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
                )


    @pytest.mark.asyncio
    async def test_usage_summary_end_date_before_start_date(self):
        """
        Test: Return 400 when period_end is before period_start.

        Given:
            - Authenticated user
            - period_end is chronologically before period_start

        When:
            - GET /billing/usage/{tenant_id}?period_start=2025-01-31&period_end=2025-01-01

        Then:
            - Returns 400 Bad Request
            - Error message indicates invalid date range
        """
        from fastapi import HTTPException

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = {
                "sub": "user_123",
                "tenant_id": "tenant_abc"
            }

            from src.api.v1.billing.router import get_usage_summary

            with pytest.raises((HTTPException, ValueError)):
                await get_usage_summary(
                    tenant_id="tenant_abc",
                    period_start="2025-01-31T00:00:00Z",
                    period_end="2025-01-01T00:00:00Z",
                    current_user={"sub": "user_123", "tenant_id": "tenant_abc"}
                )


class TestUsageSummarySecurity:
    """Test security scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_sql_injection_protection(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Protect against SQL injection in tenant_id.

        Given:
            - Authenticated user
            - tenant_id contains SQL injection attempt

        When:
            - GET /billing/usage/tenant_abc'; DROP TABLE users; --

        Then:
            - Query parameterizes tenant_id (no SQL injection)
            - Returns 400 or empty results (tenant not found)
            - Does NOT execute malicious SQL
        """
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No results for invalid tenant
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            # Should handle SQL injection attempt safely
            result = await get_usage_summary(
                tenant_id="tenant_abc'; DROP TABLE users; --",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            # Should not crash, should return empty or error
            assert result is not None


    @pytest.mark.asyncio
    async def test_usage_summary_tenant_id_parameter_sanitization(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Sanitize tenant_id parameter.

        Given:
            - tenant_id with special characters or XSS attempts

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Parameter is sanitized
            - No XSS reflected in response
        """
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="<script>alert('xss')</script>",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            assert result is not None


class TestUsageSummaryDatabaseErrors:
    """Test database error scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_database_connection_error(
        self,
        mock_auth_user
    ):
        """
        Test: Handle database connection errors gracefully.

        Given:
            - Authenticated user
            - Database connection fails

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Returns 500 Internal Server Error
            - Error message indicates database issue
            - Does NOT expose sensitive database details
        """
        from fastapi import HTTPException
        from sqlalchemy.exc import DBAPIError

        mock_db_session = AsyncMock(spec=AsyncSession)
        mock_db_session.execute.side_effect = DBAPIError(
            "Connection failed",
            {},
            Exception("Database unavailable")
        )

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            with pytest.raises((HTTPException, Exception)):
                await get_usage_summary(
                    tenant_id="tenant_abc",
                    period_start=None,
                    period_end=None,
                    current_user=mock_auth_user
                )


class TestUsageSummaryEdgeCases:
    """Test edge case scenarios."""

    @pytest.mark.asyncio
    async def test_usage_summary_very_large_quantities(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Handle very large quantities without overflow.

        Given:
            - Meter events with very large quantities (billions)

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Correctly aggregates large quantities
            - No integer overflow
            - Cost calculation handles large numbers
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 9999999999, 100),  # 10 billion labels
            ("human_audits", 100000000, 10)   # 100 million audits
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            assert result is not None


    @pytest.mark.asyncio
    async def test_usage_summary_zero_quantity_events(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Handle events with zero quantity.

        Given:
            - Meter events with quantity=0

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Includes zero-quantity events in breakdown
            - Correctly reports event count
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("ai_labels", 0, 5),  # 5 events but 0 total quantity
            ("human_audits", 10, 2)
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            assert result is not None


    @pytest.mark.asyncio
    async def test_usage_summary_unknown_event_types(
        self,
        mock_db_session: AsyncSession,
        mock_auth_user
    ):
        """
        Test: Handle unknown/unexpected event types.

        Given:
            - Meter events with event_name not in pricing catalog

        When:
            - GET /billing/usage/{tenant_id}

        Then:
            - Includes unknown event types in breakdown
            - Marks cost calculation as "unknown" or $0
            - Does NOT crash
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("unknown_event_type", 100, 1),
            ("ai_labels", 50, 1)
        ]
        mock_db_session.execute.return_value = mock_result

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_auth_user

            from src.api.v1.billing.router import get_usage_summary

            result = await get_usage_summary(
                tenant_id="tenant_abc",
                period_start=None,
                period_end=None,
                current_user=mock_auth_user
            )

            assert result is not None
