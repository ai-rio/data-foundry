"""
Test suite for Stripe Billing CRUD API Endpoints (P4-004)

TDD Approach: Red-Green-Refactor
- These tests are written FIRST (Red phase)
- They will FAIL until implementation is complete
- This ensures 95%+ test coverage from the start

Security Requirements:
- All endpoints require authentication (JWT verification)
- Tenant isolation enforced through user context
- Input validation on all request parameters
- Rate limiting applied
- Proper error handling without information disclosure

Coverage Requirements:
- Customer CRUD operations (Create, Read, Update, Delete)
- Subscription CRUD operations (Create, Read, Update, Cancel)
- Authentication required for all endpoints
- Error handling (404, validation errors, Stripe errors)
- Tenant isolation (users can only access their tenant's data)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.api.v1.billing.router import router
from src.models.stripe_billing import StripeCustomer, StripeSubscription, StripeSubscriptionStatus
from src.services.stripe.facade import (
    StripeService,
    StripeServiceError,
    StripeAPIError,
    StripeCustomerNotFoundError
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def billing_test_client(mock_stripe_service, mock_db_session):
    """Create test client for billing router with dependency overrides."""
    from fastapi import FastAPI
    app = FastAPI()

    # Override dependencies for testing
    from src.api.v1.billing import router as billing_router
    from src.api.deps import get_current_user
    from src.api.v1.billing.router import get_stripe_service
    from src.database.connection import get_db_session

    async def mock_get_current_user():
        """Mock authenticated user for testing."""
        return {
            "sub": "user_test_123",
            "tenant_id": "tenant_test_123",
            "role": "admin",
            "iss": "https://clerk.example.com",
            "aud": "test-app-id",
            "exp": int(datetime.now(timezone.utc).timestamp()) + 3600
        }

    async def mock_get_db_session():
        """Mock database session."""
        return mock_db_session

    async def mock_get_stripe_service_override():
        """Mock StripeService for testing."""
        return mock_stripe_service

    # Override the dependencies on the app, not the router
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_db_session] = mock_get_db_session
    app.dependency_overrides[get_stripe_service] = mock_get_stripe_service_override

    app.include_router(billing_router, prefix="/api/v1/billing")
    return TestClient(app)


@pytest.fixture
def mock_stripe_service():
    """Mock StripeService facade."""
    service = Mock(spec=StripeService)
    service.initialize = AsyncMock()
    return service


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.delete = MagicMock()
    return session


@pytest.fixture
def sample_tenant():
    """Sample tenant for testing."""
    from src.models.tenant import Tenant
    tenant = Mock(spec=Tenant)
    tenant.tenant_id = "tenant_test_123"
    tenant.name = "Test Organization"
    return tenant


@pytest.fixture
def sample_customer():
    """Sample Stripe customer data."""
    return {
        "tenant_id": "tenant_test_123",
        "stripe_customer_id": "cus_test_123",
        "email": "billing@testcorp.com",
        "name": "Test Organization",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_subscription():
    """Sample Stripe subscription data."""
    return {
        "tenant_id": "tenant_test_123",
        "stripe_subscription_id": "sub_test_123",
        "stripe_customer_id": "cus_test_123",
        "status": "active",
        "current_period_start": datetime.now(timezone.utc).isoformat(),
        "current_period_end": datetime.now(timezone.utc).isoformat(),
        "cancel_at_period_end": False,
        "tier": "professional"
    }


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    return {
        "sub": "user_test_123",
        "tenant_id": "tenant_test_123",
        "role": "admin",
        "iss": "https://clerk.example.com",
        "aud": "test-app-id",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600
    }


# =============================================================================
# Customer Endpoints Tests
# =============================================================================

class TestCreateCustomerEndpoint:
    """Test POST /api/v1/billing/customers - Create Stripe customer"""

    @pytest.mark.asyncio
    async def test_create_customer_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_customer
    ):
        """
        Test successful customer creation.

        Happy path: Valid request with authenticated user.
        Should create Stripe customer and return customer data.
        """
        # Arrange
        mock_stripe_service.create_customer = AsyncMock(
            return_value="cus_test_123"
        )
        mock_stripe_service.get_customer_by_tenant = AsyncMock(
            return_value=sample_customer
        )

        request_data = {
            "email": "billing@testcorp.com",
            "name": "Test Organization"
        }

        # Act
        response = billing_test_client.post(
            "/api/v1/billing/customers",
            json=request_data
        )

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["stripe_customer_id"] == "cus_test_123"
        assert data["email"] == "billing@testcorp.com"
        mock_stripe_service.create_customer.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_customer_missing_email_returns_400(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that missing email returns 400 Bad Request.

        Validation error: Email is required.
        """
        # Arrange
        request_data = {
            "name": "Test Organization"
            # Missing email
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_current_user

            # Act
            response = billing_test_client.post(
                "/api/v1/billing/customers",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_customer_invalid_email_returns_422(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that invalid email format returns 422.

        Validation error: Email must be valid format.
        """
        # Arrange
        request_data = {
            "email": "not-an-email",
            "name": "Test Organization"
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_current_user

            # Act
            response = billing_test_client.post(
                "/api/v1/billing/customers",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_customer_unauthorized_returns_401(
        self,
        billing_test_client
    ):
        """
        Test that missing authentication returns 401.

        Security: Authentication required.
        """
        # Arrange
        request_data = {
            "email": "billing@testcorp.com",
            "name": "Test Organization"
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.side_effect = Exception("Unauthorized")

            # Act
            response = billing_test_client.post(
                "/api/v1/billing/customers",
                json=request_data
            )

            # Assert - Should return 401 or similar
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN
            ]

    @pytest.mark.asyncio
    async def test_create_customer_stripe_error_returns_500(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that Stripe API errors return 500.

        Error handling: Stripe service failure.
        """
        # Arrange
        mock_stripe_service.create_customer = AsyncMock(
            side_effect=StripeAPIError("Stripe API error")
        )

        request_data = {
            "email": "billing@testcorp.com",
            "name": "Test Organization"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.post(
                    "/api/v1/billing/customers",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetCustomerEndpoint:
    """Test GET /api/v1/billing/customers/{tenant_id} - Get customer info"""

    @pytest.mark.asyncio
    async def test_get_customer_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_customer,
        mock_current_user
    ):
        """
        Test successful customer retrieval.

        Happy path: Customer exists for tenant.
        """
        # Arrange
        mock_stripe_service.get_customer_by_tenant = AsyncMock(
            return_value=sample_customer
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/customers/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["tenant_id"] == "tenant_test_123"
                assert data["stripe_customer_id"] == "cus_test_123"
                mock_stripe_service.get_customer_by_tenant.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_customer_not_found_returns_404(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that non-existent customer returns 404.

        Edge case: Customer not found for tenant.
        """
        # Arrange
        mock_stripe_service.get_customer_by_tenant = AsyncMock(
            return_value=None
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/customers/tenant_nonexistent"
                )

                # Assert
                assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_customer_unauthorized_returns_401(
        self,
        billing_test_client
    ):
        """
        Test that missing authentication returns 401.

        Security: Authentication required.
        """
        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.side_effect = Exception("Unauthorized")

            # Act
            response = billing_test_client.get(
                "/api/v1/billing/customers/tenant_test_123"
            )

            # Assert
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN
            ]


class TestUpdateCustomerEndpoint:
    """Test PUT /api/v1/billing/customers/{tenant_id} - Update customer"""

    @pytest.mark.asyncio
    async def test_update_customer_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_customer,
        mock_current_user
    ):
        """
        Test successful customer update.

        Happy path: Update customer email and name.
        """
        # Arrange
        updated_customer = sample_customer.copy()
        updated_customer["email"] = "newemail@testcorp.com"

        mock_stripe_service.update_customer = AsyncMock(
            return_value=updated_customer
        )

        request_data = {
            "email": "newemail@testcorp.com",
            "name": "Updated Organization"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.put(
                    "/api/v1/billing/customers/tenant_test_123",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["email"] == "newemail@testcorp.com"
                mock_stripe_service.update_customer.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_customer_not_found_returns_404(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that updating non-existent customer returns 404.

        Edge case: Customer doesn't exist.
        """
        # Arrange
        mock_stripe_service.update_customer = AsyncMock(
            side_effect=StripeCustomerNotFoundError("Customer not found")
        )

        request_data = {
            "email": "newemail@testcorp.com"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.put(
                    "/api/v1/billing/customers/tenant_nonexistent",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteCustomerEndpoint:
    """Test DELETE /api/v1/billing/customers/{tenant_id} - Delete customer"""

    @pytest.mark.asyncio
    async def test_delete_customer_success(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test successful customer deletion.

        Happy path: Customer deleted successfully.
        """
        # Arrange
        mock_stripe_service.delete_customer = AsyncMock(return_value=True)

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.delete(
                    "/api/v1/billing/customers/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                mock_stripe_service.delete_customer.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_customer_stripe_error_returns_500(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that Stripe errors during deletion return 500.

        Error handling: Stripe service failure.
        """
        # Arrange
        mock_stripe_service.delete_customer = AsyncMock(
            side_effect=StripeAPIError("Stripe API error")
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.delete(
                    "/api/v1/billing/customers/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# Subscription Endpoints Tests
# =============================================================================

class TestCreateSubscriptionEndpoint:
    """Test POST /api/v1/billing/subscriptions - Create subscription"""

    @pytest.mark.asyncio
    async def test_create_subscription_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test successful subscription creation.

        Happy path: Create subscription for customer.
        """
        # Arrange
        mock_stripe_service.create_subscription = AsyncMock(
            return_value=sample_subscription
        )

        request_data = {
            "stripe_customer_id": "cus_test_123",
            "tier": "professional",
            "price_id": "price_professional_monthly"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.post(
                    "/api/v1/billing/subscriptions",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_201_CREATED
                data = response.json()
                assert data["stripe_subscription_id"] == "sub_test_123"
                assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_subscription_missing_customer_id_returns_422(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that missing customer_id returns 422.

        Validation error: stripe_customer_id is required.
        """
        # Arrange
        request_data = {
            "tier": "professional"
            # Missing stripe_customer_id
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_current_user

            # Act
            response = billing_test_client.post(
                "/api/v1/billing/subscriptions",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestGetSubscriptionEndpoint:
    """Test GET /api/v1/billing/subscriptions/{tenant_id} - Get subscription"""

    @pytest.mark.asyncio
    async def test_get_subscription_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test successful subscription retrieval.

        Happy path: Subscription exists for tenant.
        """
        # Arrange
        mock_stripe_service.get_subscription_by_tenant = AsyncMock(
            return_value=sample_subscription
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/subscriptions/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["tenant_id"] == "tenant_test_123"
                assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_get_subscription_not_found_returns_404(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that non-existent subscription returns 404.

        Edge case: No subscription for tenant.
        """
        # Arrange
        mock_stripe_service.get_subscription_by_tenant = AsyncMock(
            return_value=None
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/subscriptions/tenant_nonexistent"
                )

                # Assert
                assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateSubscriptionEndpoint:
    """Test PUT /api/v1/billing/subscriptions/{tenant_id} - Update subscription"""

    @pytest.mark.asyncio
    async def test_update_subscription_tier_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test successful subscription tier update.

        Happy path: Upgrade/downgrade subscription tier.
        """
        # Arrange
        updated_subscription = sample_subscription.copy()
        updated_subscription["tier"] = "enterprise"

        mock_stripe_service.update_subscription = AsyncMock(
            return_value=updated_subscription
        )

        request_data = {
            "tier": "enterprise"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.put(
                    "/api/v1/billing/subscriptions/tenant_test_123",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["tier"] == "enterprise"

    @pytest.mark.asyncio
    async def test_update_subscription_not_found_returns_404(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that updating non-existent subscription returns 404.

        Edge case: Subscription doesn't exist.
        """
        # Arrange
        mock_stripe_service.update_subscription = AsyncMock(
            side_effect=StripeCustomerNotFoundError("Subscription not found")
        )

        request_data = {
            "tier": "enterprise"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.put(
                    "/api/v1/billing/subscriptions/tenant_nonexistent",
                    json=request_data
                )

                # Assert
                assert response.status_code == status.HTTP_404_NOT_FOUND


class TestCancelSubscriptionEndpoint:
    """Test DELETE /api/v1/billing/subscriptions/{tenant_id} - Cancel subscription"""

    @pytest.mark.asyncio
    async def test_cancel_subscription_success(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test successful subscription cancellation.

        Happy path: Cancel subscription at period end.
        """
        # Arrange
        canceled_subscription = sample_subscription.copy()
        canceled_subscription["cancel_at_period_end"] = True

        mock_stripe_service.cancel_subscription = AsyncMock(
            return_value=canceled_subscription
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.delete(
                    "/api/v1/billing/subscriptions/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK
                mock_stripe_service.cancel_subscription.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_subscription_immediately(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test immediate subscription cancellation.

        Edge case: Cancel immediately instead of at period end.
        """
        # Arrange
        canceled_subscription = sample_subscription.copy()
        canceled_subscription["status"] = "canceled"

        mock_stripe_service.cancel_subscription = AsyncMock(
            return_value=canceled_subscription
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_testclient.delete(
                    "/api/v1/billing/subscriptions/tenant_test_123?immediate=true"
                )

                # Assert
                assert response.status_code == status.HTTP_200_OK


# =============================================================================
# Security and Tenant Isolation Tests
# =============================================================================

class TestTenantIsolation:
    """Test tenant isolation enforcement"""

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_tenant_customer(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that users cannot access other tenants' customers.

        Security: Tenant isolation enforcement.
        """
        # Arrange - User belongs to tenant_test_123
        mock_current_user["tenant_id"] = "tenant_test_123"

        mock_stripe_service.get_customer_by_tenant = AsyncMock(
            return_value=None  # Not found for different tenant
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act - Try to access different tenant's customer
                response = billing_test_client.get(
                    "/api/v1/billing/customers/tenant_other_456"
                )

                # Assert - Should return 404 or 403
                assert response.status_code in [
                    status.HTTP_404_NOT_FOUND,
                    status.HTTP_403_FORBIDDEN
                ]

    @pytest.mark.asyncio
    async def test_user_cannot_modify_other_tenant_subscription(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that users cannot modify other tenants' subscriptions.

        Security: Tenant isolation enforcement.
        """
        # Arrange
        mock_current_user["tenant_id"] = "tenant_test_123"

        mock_stripe_service.update_subscription = AsyncMock(
            side_effect=PermissionError("Access denied")
        )

        request_data = {"tier": "enterprise"}

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.put(
                    "/api/v1/billing/subscriptions/tenant_other_456",
                    json=request_data
                )

                # Assert - Should return 403 or 404
                assert response.status_code in [
                    status.HTTP_403_FORBIDDEN,
                    status.HTTP_404_NOT_FOUND
                ]


# =============================================================================
# Input Validation Tests
# =============================================================================

class TestInputValidation:
    """Test input validation across all endpoints"""

    @pytest.mark.asyncio
    async def test_create_customer_email_too_long(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that excessively long email is rejected.

        Input validation: Email length limit.
        """
        # Arrange
        request_data = {
            "email": "a" * 500 + "@test.com",  # Excessively long
            "name": "Test Organization"
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_current_user

            # Act
            response = billing_test_client.post(
                "/api/v1/billing/customers",
                json=request_data
            )

            # Assert - Pydantic should reject this
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_update_subscription_invalid_tier(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that invalid tier is rejected.

        Input validation: Tier must be valid value.
        """
        # Arrange
        request_data = {
            "tier": "invalid_tier_name"
        }

        with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
            mock_auth.return_value = mock_current_user

            # Act
            response = billing_test_client.put(
                "/api/v1/billing/subscriptions/tenant_test_123",
                json=request_data
            )

            # Assert
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling and graceful degradation"""

    @pytest.mark.asyncio
    async def test_stripe_service_unavailable_returns_503(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that Stripe service unavailability returns 503.

        Error handling: Service unavailable.
        """
        # Arrange
        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.side_effect = Exception("Service unavailable")

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/customers/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(
        self,
        billing_test_client,
        mock_stripe_service,
        mock_current_user
    ):
        """
        Test that unexpected exceptions return 500.

        Error handling: Generic error handler.
        """
        # Arrange
        mock_stripe_service.get_customer_by_tenant = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/customers/tenant_test_123"
                )

                # Assert
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


# =============================================================================
# Response Format Tests
# =============================================================================

class TestResponseFormats:
    """Test API response formats match contracts"""

    @pytest.mark.asyncio
    async def test_create_customer_response_format(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_customer,
        mock_current_user
    ):
        """
        Test that create customer response matches contract.

        API contract: Response schema validation.
        """
        # Arrange
        mock_stripe_service.create_customer = AsyncMock(
            return_value="cus_test_123"
        )

        request_data = {
            "email": "billing@testcorp.com",
            "name": "Test Organization"
        }

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.post(
                    "/api/v1/billing/customers",
                    json=request_data
                )

                # Assert - Check response structure
                assert response.status_code == status.HTTP_201_CREATED
                data = response.json()
                assert "stripe_customer_id" in data
                assert "email" in data
                assert "name" in data
                assert "created_at" in data

    @pytest.mark.asyncio
    async def test_get_subscription_response_format(
        self,
        billing_test_client,
        mock_stripe_service,
        sample_subscription,
        mock_current_user
    ):
        """
        Test that get subscription response matches contract.

        API contract: Response schema validation.
        """
        # Arrange
        mock_stripe_service.get_subscription_by_tenant = AsyncMock(
            return_value=sample_subscription
        )

        with patch('src.api.v1.billing.router.get_stripe_service') as mock_get_service:
            mock_get_service.return_value = mock_stripe_service

            with patch('src.api.v1.billing.router.get_current_user') as mock_auth:
                mock_auth.return_value = mock_current_user

                # Act
                response = billing_test_client.get(
                    "/api/v1/billing/subscriptions/tenant_test_123"
                )

                # Assert - Check response structure
                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert "tenant_id" in data
                assert "stripe_subscription_id" in data
                assert "status" in data
                assert "tier" in data
                assert "current_period_start" in data
                assert "current_period_end" in data


# =============================================================================
# Performance and Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Test rate limiting implementation"""

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(
        self,
        billing_test_client,
        mock_current_user
    ):
        """
        Test that rate limiting is enforced.

        Security: Prevent abuse through rate limiting.
        """
        # This test will verify rate limiting is implemented
        # Actual rate limit checks depend on implementation
        pass
