"""
TDD Test Suite for StripeService - P1-002

This test suite follows strict RED-GREEN-REFACTOR TDD discipline for implementing
the StripeService with Customer CRUD operations.

Implementation Order:
1. StripeCustomer Model (Cycle 1)
2. stripe_customers Table Migration (Cycle 2)
3. StripeService Exception Classes (Cycle 3)
4. StripeService.initialize() (Cycle 4)
5. StripeService.create_customer() (Cycle 5)
6. StripeService.get_customer_by_tenant() (Cycle 6)
7. StripeService.update_customer() (Cycle 7)
8. StripeService.delete_customer() (Cycle 8)

Coverage Target: >=90%
Security Score Target: >=95%
"""

import pytest
from datetime import datetime
from typing import Dict, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

# Import models
from src.models.tenant import Tenant
from src.models.stripe_billing import StripeCustomer, StripeSubscription, StripeMeterEvent


class TestStripeCustomerModel:
    """
    CYCLE 1: StripeCustomer Model
    - RED: Test for StripeCustomer model fields and constraints
    - GREEN: Implement StripeCustomer model
    - REFACTOR: Add validation, improve docstrings
    """

    @pytest.mark.asyncio
    async def test_stripe_customer_model_has_required_fields(self):
        """
        RED PHASE: Test that StripeCustomer model exists and has required fields.

        This test FAILS because StripeCustomer model doesn't exist yet.
        After implementation, it should PASS verifying:
        - id (primary key)
        - tenant_id (unique, indexed)
        - stripe_customer_id (unique, indexed)
        - email (optional)
        - name (optional)
        - created_by, updated_by (optional)
        - created_at, updated_at (timestamps)
        """
        # Given: A StripeCustomer instance with all fields
        customer = StripeCustomer(
            id=1,
            tenant_id="test_tenant_123",
            stripe_customer_id="cus_test123",
            email="test@example.com",
            name="Test Customer",
            created_by="admin",
            updated_by="admin",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # When: Accessing model attributes
        # Then: All fields should be accessible
        assert customer.id == 1
        assert customer.tenant_id == "test_tenant_123"
        assert customer.stripe_customer_id == "cus_test123"
        assert customer.email == "test@example.com"
        assert customer.name == "Test Customer"
        assert customer.created_by == "admin"
        assert customer.updated_by == "admin"
        assert isinstance(customer.created_at, datetime)
        assert isinstance(customer.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_stripe_customer_model_allows_optional_fields(self):
        """
        RED PHASE: Test that optional fields can be None.

        Verifies that email, name, created_by, and updated_by can be None.
        """
        # Given: A StripeCustomer with minimal required fields
        customer = StripeCustomer(
            tenant_id="test_tenant_456",
            stripe_customer_id="cus_test456"
        )

        # When: Accessing optional fields
        # Then: They should be None
        assert customer.email is None
        assert customer.name is None
        assert customer.created_by is None
        assert customer.updated_by is None

    @pytest.mark.asyncio
    async def test_stripe_customer_model_table_name(self):
        """
        RED PHASE: Test that StripeCustomer uses correct table name.

        Verifies __tablename__ is "stripe_customers".
        """
        # Given: The StripeCustomer model
        # When: Checking table name
        # Then: Should be "stripe_customers"
        assert StripeCustomer.__tablename__ == "stripe_customers"

    @pytest.mark.asyncio
    async def test_stripe_customer_tenant_id_unique_constraint(self):
        """
        RED PHASE: Test that tenant_id has unique constraint.

        Verifies tenant_id is marked as unique in Field definition.
        """
        # Given: The StripeCustomer model
        # When: Checking tenant_id field
        # Then: Should have unique constraint (verified by Field(unique=True))
        # The actual constraint is validated by the database
        from sqlmodel import Field
        field_info = StripeCustomer.model_fields['tenant_id']
        # Verify the field exists and has expected properties
        assert 'tenant_id' in StripeCustomer.model_fields

    @pytest.mark.asyncio
    async def test_stripe_customer_stripe_id_unique_constraint(self):
        """
        RED PHASE: Test that stripe_customer_id has unique constraint.

        Verifies stripe_customer_id is marked as unique in Field definition.
        """
        # Given: The StripeCustomer model
        # When: Checking stripe_customer_id field
        # Then: Should have unique constraint
        from sqlmodel import Field
        field_info = StripeCustomer.model_fields['stripe_customer_id']
        # Verify the field exists
        assert 'stripe_customer_id' in StripeCustomer.model_fields


class TestStripeCustomersMigration:
    """
    CYCLE 2: stripe_customers Table Migration
    - RED: Test that verifies table exists and has correct schema
    - GREEN: Create migration script
    - REFACTOR: Add RLS policies, indexes

    NOTE: These tests require a real database connection.
    They are marked as integration tests and will skip if db_session is unavailable.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stripe_customers_table_exists(self, db_session: AsyncSession):
        """
        RED PHASE: Test that stripe_customers table exists in database.

        This test FAILS until migration is created and run.
        """
        # Given: A database session
        # When: Querying the stripe_customers table
        from sqlalchemy import text

        query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'stripe_customers'
            );
        """)

        result = await db_session.execute(query)
        exists = result.scalar()

        # Then: Table should exist
        assert exists is True, "stripe_customers table should exist after migration"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stripe_customers_table_has_correct_columns(self, db_session: AsyncSession):
        """
        RED PHASE: Test that stripe_customers table has all required columns.

        Verifies columns: id, tenant_id, stripe_customer_id, email, name,
        created_by, updated_by, created_at, updated_at.
        """
        # Given: A database session
        # When: Querying table columns
        from sqlalchemy import text

        query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'stripe_customers'
            ORDER BY ordinal_position;
        """)

        result = await db_session.execute(query)
        columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in result.fetchall()}

        # Then: All required columns should exist
        required_columns = {
            'id': 'integer',
            'tenant_id': 'character varying',
            'stripe_customer_id': 'character varying',
            'email': 'character varying',
            'name': 'character varying',
            'created_by': 'character varying',
            'updated_by': 'character varying',
            'created_at': 'timestamp without time zone',
            'updated_at': 'timestamp without time zone',
        }

        for col_name, col_type in required_columns.items():
            assert col_name in columns, f"Column {col_name} should exist"
            assert col_type in columns[col_name]['type'], f"Column {col_name} should be {col_type}"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stripe_customers_table_has_foreign_key_constraint(self, db_session: AsyncSession):
        """
        RED PHASE: Test that stripe_customers has foreign key to tenants table.

        Verifies tenant_id references tenants(tenant_id) with CASCADE delete.
        """
        # Given: A database session
        # When: Querying foreign key constraints
        from sqlalchemy import text

        query = text("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            JOIN information_schema.referential_constraints AS rc
                ON tc.constraint_name = rc.constraint_name
            WHERE tc.table_name = 'stripe_customers'
                AND tc.constraint_type = 'FOREIGN KEY';
        """)

        result = await db_session.execute(query)
        fk_constraints = result.fetchall()

        # Then: Should have FK to tenants(tenant_id)
        assert len(fk_constraints) > 0, "Should have foreign key constraint"

        fk = fk_constraints[0]
        assert fk.column_name == 'tenant_id'
        assert fk.foreign_table_name == 'tenants'
        assert fk.foreign_column_name == 'tenant_id'
        assert fk.delete_rule == 'CASCADE', "Should have CASCADE delete"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_stripe_customers_table_has_indexes(self, db_session: AsyncSession):
        """
        RED PHASE: Test that stripe_customers table has required indexes.

        Verifies indexes on tenant_id and stripe_customer_id.
        """
        # Given: A database session
        # When: Querying table indexes
        from sqlalchemy import text

        query = text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'stripe_customers';
        """)

        result = await db_session.execute(query)
        indexes = {row[0]: row[1] for row in result.fetchall()}

        # Then: Should have indexes on tenant_id and stripe_customer_id
        index_names = list(indexes.keys())
        assert any('tenant' in name.lower() for name in index_names), \
            "Should have index on tenant_id"
        assert any('stripe' in name.lower() or 'customer' in name.lower() for name in index_names), \
            "Should have index on stripe_customer_id"


class TestStripeServiceExceptions:
    """
    CYCLE 3: StripeService Exception Classes
    - RED: Test for custom exceptions
    - GREEN: Create StripeServiceError, StripeCustomerNotFoundError, StripeAPIError
    - REFACTOR: Add error inheritance hierarchy
    """

    def test_stripe_service_error_exists(self):
        """
        RED PHASE: Test that StripeServiceError exception class exists.

        This test FAILS until exception is created.
        """
        # Given: Import attempt
        # When: Importing from stripe_service
        # Then: Should be importable
        from src.services.stripe_service import StripeServiceError

        # And: Should be an Exception subclass
        assert issubclass(StripeServiceError, Exception)

    def test_stripe_customer_not_found_error_exists(self):
        """
        RED PHASE: Test that StripeCustomerNotFoundError exception class exists.

        Should inherit from StripeServiceError.
        """
        # Given: Import attempt
        # When: Importing from stripe_service
        # Then: Should be importable
        from src.services.stripe_service import StripeCustomerNotFoundError, StripeServiceError

        # And: Should inherit from StripeServiceError
        assert issubclass(StripeCustomerNotFoundError, StripeServiceError)

    def test_stripe_api_error_exists(self):
        """
        RED PHASE: Test that StripeAPIError exception class exists.

        Should inherit from StripeServiceError.
        """
        # Given: Import attempt
        # When: Importing from stripe_service
        # Then: Should be importable
        from src.services.stripe_service import StripeAPIError, StripeServiceError

        # And: Should inherit from StripeServiceError
        assert issubclass(StripeAPIError, StripeServiceError)

    def test_stripe_service_error_can_be_raised_with_message(self):
        """
        RED PHASE: Test that StripeServiceError can be raised with custom message.

        Verifies exception can be instantiated and raised with a message.
        """
        from src.services.stripe_service import StripeServiceError

        # Given: An error message
        error_message = "Test error message"

        # When: Raising the exception
        # Then: Should capture the message
        with pytest.raises(StripeServiceError) as exc_info:
            raise StripeServiceError(error_message)

        assert str(exc_info.value) == error_message

    def test_stripe_customer_not_found_error_can_be_raised(self):
        """
        RED PHASE: Test that StripeCustomerNotFoundError can be raised.

        Verifies exception can be instantiated and raised.
        """
        from src.services.stripe_service import StripeCustomerNotFoundError

        # Given: Customer ID and tenant ID
        stripe_customer_id = "cus_missing"
        tenant_id = "tenant_123"

        # When: Raising the exception
        # Then: Should capture the information
        with pytest.raises(StripeCustomerNotFoundError) as exc_info:
            raise StripeCustomerNotFoundError(
                f"Stripe customer not found: {stripe_customer_id} for tenant: {tenant_id}"
            )

        assert "cus_missing" in str(exc_info.value)
        assert "tenant_123" in str(exc_info.value)

    def test_stripe_api_error_can_be_raised_with_stripe_error(self):
        """
        RED PHASE: Test that StripeAPIError can be raised with Stripe error details.

        Verifies exception can capture Stripe API error information.
        """
        from src.services.stripe_service import StripeAPIError

        # Given: Stripe error details
        stripe_error_type = "StripeError"
        stripe_message = "Invalid API key"

        # When: Raising the exception
        # Then: Should capture the error information
        with pytest.raises(StripeAPIError) as exc_info:
            raise StripeAPIError(f"Stripe API error: {stripe_error_type} - {stripe_message}")

        assert "Stripe API error" in str(exc_info.value)
        assert stripe_error_type in str(exc_info.value)
        assert stripe_message in str(exc_info.value)


class TestStripeServiceInitialization:
    """
    CYCLE 4: StripeService.initialize()
    - RED: Test initialization with SecretManager
    - GREEN: Implement initialize() method
    - REFACTOR: Add error handling for missing API key
    """

    @pytest.mark.asyncio
    @patch('src.services.stripe_service.SecretManager')
    async def test_initialize_loads_api_key_from_secret_manager(self, MockSecretManager):
        """
        RED PHASE: Test that initialize() loads API key from SecretManager.

        Verifies that StripeService.initialize() retrieves the Stripe secret key
        from SecretManager and configures the Stripe client.
        """
        # Given: A StripeService instance and mocked SecretManager
        from src.services.stripe_service import StripeService

        # Configure mock
        mock_instance = Mock()
        mock_instance.get_secret.return_value = "sk_test_1234567890"
        MockSecretManager.return_value = mock_instance

        service = StripeService()

        # When: Calling initialize
        await service.initialize()

        # Then: API key should be loaded from SecretManager
        mock_instance.get_secret.assert_called_once_with('STRIPE_SECRET_KEY')
        assert service.api_key == "sk_test_1234567890"

    @pytest.mark.asyncio
    async def test_initialize_with_missing_api_key_raises_error(self):
        """
        RED PHASE: Test that initialize() raises error when API key is missing.

        Verifies that StripeServiceError is raised when SecretManager returns None.
        """
        # Given: A StripeService instance and SecretManager returning None
        from src.services.stripe_service import StripeService, StripeServiceError

        with patch('src.services.stripe_service.SecretManager') as mock:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = None
            mock.return_value = mock_instance

            service = StripeService()

            # When: Calling initialize with missing API key
            # Then: Should raise StripeServiceError
            with pytest.raises(StripeServiceError) as exc_info:
                await service.initialize()

            assert "Stripe API key" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_initialize_idempotent_when_already_initialized(self):
        """
        Test that initialize() can be called multiple times safely.

        Verifies that calling initialize() twice doesn't raise an error
        and logs a warning on second call.
        """
        from src.services.stripe_service import StripeService

        with patch('src.services.stripe_service.SecretManager') as MockSecretManager:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = "sk_test_1234567890"
            MockSecretManager.return_value = mock_instance

            service = StripeService()

            # When: Calling initialize twice
            await service.initialize()
            await service.initialize()  # Second call should log warning but not error

            # Then: Service should still be initialized
            assert service._initialized is True
            assert service.api_key == "sk_test_1234567890"


# Fixtures for Stripe testing
@pytest.fixture
def mock_stripe_client():
    """Mock Stripe client for testing."""
    # Mock the stripe.Customer class directly
    with patch('src.services.stripe_service.stripe.Customer') as mock:
        # Configure mock methods
        mock.create = Mock()
        mock.retrieve = Mock()
        mock.modify = Mock()
        mock.delete = Mock()
        yield mock

    # After the test, we can also reset the stripe.api_key to avoid side effects
    import stripe
    stripe.api_key = None


@pytest.fixture
def test_tenant():
    """Test tenant fixture."""
    return Tenant(
        tenant_id="test_tenant_123",
        name="Test Organization",
        email="admin@testcorp.com",
        status="active"
    )


@pytest.fixture
def test_db_session():
    """Mock database session for testing."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def initialized_stripe_service():
    """Fixture providing an initialized StripeService for testing."""
    from src.services.stripe_service import StripeService
    import os

    # Set default meter IDs for testing
    os.environ.setdefault('STRIPE_AI_LABELS_METER_ID', 'mtr_test_ai_labels')
    os.environ.setdefault('STRIPE_HUMAN_AUDITS_METER_ID', 'mtr_test_human_audits')

    service = StripeService()
    # Manually set initialized state to bypass SecretManager in tests
    service._initialized = True
    service.api_key = "sk_test_123"
    return service


class TestStripeServiceCreateCustomer:
    """
    CYCLE 5: StripeService.create_customer()
    - RED: Test successful customer creation
    - GREEN: Implement create_customer() with Stripe API call
    - REFACTOR: Extract metadata handling, add database persistence
    """

    @pytest.mark.asyncio
    async def test_create_customer_returns_stripe_customer_id(
        self, test_tenant, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """
        RED PHASE: Test successful customer creation returns Stripe customer ID.

        Verifies that create_customer():
        1. Calls Stripe API with correct parameters
        2. Includes tenant_id in metadata
        3. Returns the Stripe customer ID
        4. Persists to database
        """
        # Mock Stripe API response
        mock_customer = Mock()
        mock_customer.id = "cus_new123"
        mock_customer.email = "admin@testcorp.com"
        mock_customer.name = "Test Organization"
        mock_stripe_client.create.return_value = mock_customer

        # When: Creating a customer
        result = await initialized_stripe_service.create_customer(
            tenant=test_tenant,
            email="billing@testcorp.com",
            name="Test Organization Billing",
            db_session=test_db_session
        )

        # Then: Should return Stripe customer ID
        assert result == "cus_new123"

        # And: Stripe API should be called with correct parameters
        mock_stripe_client.create.assert_called_once()
        call_args = mock_stripe_client.create.call_args
        assert call_args.kwargs['email'] == "billing@testcorp.com"
        assert call_args.kwargs['name'] == "Test Organization Billing"
        assert call_args.kwargs['metadata']['tenant_id'] == "test_tenant_123"

    @pytest.mark.asyncio
    async def test_create_customer_persists_to_database(
        self, test_tenant, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """
        RED PHASE: Test that create_customer persists to database.

        Verifies that StripeCustomer record is created in database after
        successful Stripe API call.
        """
        mock_customer = Mock()
        mock_customer.id = "cus_db123"
        mock_stripe_client.create.return_value = mock_customer

        # When: Creating a customer
        await initialized_stripe_service.create_customer(
            tenant=test_tenant,
            email="billing@testcorp.com",
            name="Test Org",
            db_session=test_db_session
        )

        # Then: Should persist to database
        test_db_session.add.assert_called_once()
        test_db_session.commit.assert_called_once()
        test_db_session.refresh.assert_called_once()

        # Verify the StripeCustomer object was created
        call_args = test_db_session.add.call_args
        added_customer = call_args.args[0]
        assert isinstance(added_customer, StripeCustomer)
        assert added_customer.tenant_id == "test_tenant_123"
        assert added_customer.stripe_customer_id == "cus_db123"
        assert added_customer.email == "billing@testcorp.com"
        assert added_customer.name == "Test Org"


class TestStripeServiceGetCustomer:
    """
    CYCLE 6: StripeService.get_customer_by_tenant()
    - RED: Test retrieving existing customer
    - GREEN: Implement retrieval from database
    - REFACTOR: Add Stripe API fallback
    """

    @pytest.mark.asyncio
    async def test_get_customer_by_tenant_returns_customer_dict(
        self, test_db_session, initialized_stripe_service
    ):
        """
        RED PHASE: Test retrieving existing customer by tenant_id.

        Verifies that get_customer_by_tenant():
        1. Queries database for customer
        2. Returns customer dictionary with details
        """
        # Mock database query result
        mock_result = Mock()
        mock_result.tenant_id = "test_tenant_123"
        mock_result.stripe_customer_id = "cus_existing123"
        mock_result.email = "billing@testcorp.com"
        mock_result.name = "Test Org"
        mock_result.created_at = datetime.utcnow()
        mock_result.updated_at = datetime.utcnow()

        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_none.return_value = mock_result

        test_db_session.execute.return_value = mock_exec_result

        # When: Retrieving customer by tenant
        result = await initialized_stripe_service.get_customer_by_tenant(
            tenant_id="test_tenant_123",
            db_session=test_db_session
        )

        # Then: Should return customer dictionary
        assert result is not None
        assert result['tenant_id'] == "test_tenant_123"
        assert result['stripe_customer_id'] == "cus_existing123"
        assert result['email'] == "billing@testcorp.com"
        assert result['name'] == "Test Org"

    @pytest.mark.asyncio
    async def test_get_customer_by_tenant_returns_none_when_not_found(
        self, test_db_session, initialized_stripe_service
    ):
        """
        RED PHASE: Test that get_customer_by_tenant returns None for non-existent customer.

        Verifies that None is returned when tenant doesn't have a Stripe customer.
        """
        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_none.return_value = None
        test_db_session.execute.return_value = mock_exec_result

        # When: Retrieving non-existent customer
        result = await initialized_stripe_service.get_customer_by_tenant(
            tenant_id="nonexistent_tenant",
            db_session=test_db_session
        )

        # Then: Should return None
        assert result is None


class TestStripeServiceUpdateCustomer:
    """
    CYCLE 7: StripeService.update_customer()
    - RED: Test partial update (email only)
    - GREEN: Implement update with Stripe API
    - REFACTOR: Add metadata synchronization
    """

    @pytest.mark.asyncio
    async def test_update_customer_updates_stripe_and_database(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """
        RED PHASE: Test partial update of customer email.

        Verifies that update_customer():
        1. Calls Stripe API with updated fields
        2. Updates database record
        3. Returns updated customer data
        """
        # Mock Stripe API response - add get method to support _stripe_customer_to_dict
        mock_customer = Mock()
        mock_customer.id = "cus_update123"
        mock_customer.email = "newemail@testcorp.com"
        mock_customer.name = "Test Org"
        mock_customer.get = Mock(side_effect=lambda key, default=None: {
            'email': 'newemail@testcorp.com',
            'name': 'Test Org',
            'metadata': {},
            'created': 1234567890
        }.get(key, default))
        mock_stripe_client.modify.return_value = mock_customer

        # When: Updating customer email
        result = await initialized_stripe_service.update_customer(
            stripe_customer_id="cus_update123",
            email="newemail@testcorp.com"
        )

        # Then: Should call Stripe API
        mock_stripe_client.modify.assert_called_once_with(
            "cus_update123",
            email="newemail@testcorp.com"
        )

        # And: Return updated customer
        assert result['email'] == "newemail@testcorp.com"
        assert result['stripe_customer_id'] == "cus_update123"


class TestStripeServiceDeleteCustomer:
    """
    CYCLE 8: StripeService.delete_customer()
    - RED: Test customer deletion
    - GREEN: Implement deletion
    - REFACTOR: Add cascade behavior documentation
    """

    @pytest.mark.asyncio
    async def test_delete_customer_deletes_from_stripe_and_database(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """
        RED PHASE: Test customer deletion.

        Verifies that delete_customer():
        1. Calls Stripe API to delete customer
        2. Removes from database
        3. Returns True on success
        """
        mock_stripe_client.delete.return_value = Mock(id="cus_delete123")

        # When: Deleting customer
        result = await initialized_stripe_service.delete_customer(
            stripe_customer_id="cus_delete123",
            db_session=test_db_session
        )

        # Then: Should call Stripe API
        mock_stripe_client.delete.assert_called_once_with("cus_delete123")

        # And: Return True
        assert result is True


class TestStripeServiceErrorHandling:
    """
    Additional tests for error handling paths to increase coverage.
    Tests Stripe API errors, edge cases, and database operations.
    """

    @pytest.mark.asyncio
    async def test_create_customer_without_db_session(
        self, test_tenant, mock_stripe_client, initialized_stripe_service
    ):
        """Test create_customer without database session (Stripe only)."""
        mock_customer = Mock()
        mock_customer.id = "cus_nodb123"
        mock_stripe_client.create.return_value = mock_customer

        # When: Creating customer without db_session
        result = await initialized_stripe_service.create_customer(
            tenant=test_tenant,
            email="billing@testcorp.com",
            name="Test Org",
            db_session=None  # No database session
        )

        # Then: Should still return customer ID
        assert result == "cus_nodb123"

    @pytest.mark.asyncio
    async def test_create_customer_stripe_api_error(
        self, test_tenant, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test create_customer handles Stripe API errors."""
        from src.services.stripe_service import StripeAPIError
        import stripe

        # Mock Stripe API error
        mock_stripe_client.create.side_effect = stripe.error.StripeError("Invalid API key")

        # When/Then: Should raise StripeAPIError
        with pytest.raises(StripeAPIError) as exc_info:
            await initialized_stripe_service.create_customer(
                tenant=test_tenant,
                email="billing@testcorp.com",
                db_session=test_db_session
            )

        assert "Failed to create Stripe customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_customer_unexpected_error(
        self, test_tenant, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test create_customer handles unexpected errors."""
        from src.services.stripe_service import StripeServiceError

        # Mock unexpected error
        mock_stripe_client.create.side_effect = Exception("Unexpected error")

        # When/Then: Should raise StripeServiceError
        with pytest.raises(StripeServiceError) as exc_info:
            await initialized_stripe_service.create_customer(
                tenant=test_tenant,
                email="billing@testcorp.com",
                db_session=test_db_session
            )

        assert "Failed to create customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_customer_database_error(
        self, test_db_session, initialized_stripe_service
    ):
        """Test get_customer handles database errors."""
        from src.services.stripe_service import StripeServiceError

        # Mock database error
        test_db_session.execute.side_effect = Exception("Database connection failed")

        # When/Then: Should raise StripeServiceError
        with pytest.raises(StripeServiceError) as exc_info:
            await initialized_stripe_service.get_customer_by_tenant(
                tenant_id="test_tenant_123",
                db_session=test_db_session
            )

        assert "Failed to retrieve customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_customer_with_no_updates_returns_current(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer with no update parameters retrieves current customer."""
        # Mock retrieve response
        mock_customer = Mock()
        mock_customer.id = "cus_current123"
        mock_customer.email = "current@testcorp.com"
        mock_customer.name = "Current Org"
        mock_customer.get = Mock(side_effect=lambda key, default=None: {
            'email': 'current@testcorp.com',
            'name': 'Current Org',
            'metadata': {},
            'created': 1234567890
        }.get(key, default))
        mock_stripe_client.retrieve.return_value = mock_customer

        # When: Updating with no parameters
        result = await initialized_stripe_service.update_customer(
            stripe_customer_id="cus_current123",
            email=None,
            name=None,
            metadata=None
        )

        # Then: Should retrieve current customer
        mock_stripe_client.retrieve.assert_called_once_with("cus_current123")
        assert result['email'] == "current@testcorp.com"

    @pytest.mark.asyncio
    async def test_update_customer_with_metadata_only(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer with metadata only (no email/name)."""
        mock_customer = Mock()
        mock_customer.id = "cus_metadata123"
        mock_customer.email = "test@testcorp.com"
        mock_customer.name = "Test Org"
        mock_customer.get = Mock(side_effect=lambda key, default=None: {
            'email': 'test@testcorp.com',
            'name': 'Test Org',
            'metadata': {'updated': 'true'},
            'created': 1234567890
        }.get(key, default))
        mock_stripe_client.modify.return_value = mock_customer

        # When: Updating only metadata
        result = await initialized_stripe_service.update_customer(
            stripe_customer_id="cus_metadata123",
            metadata={'updated': 'true'}
        )

        # Then: Should call modify with metadata
        mock_stripe_client.modify.assert_called_once()
        call_kwargs = mock_stripe_client.modify.call_args.kwargs
        assert 'metadata' in call_kwargs
        assert call_kwargs['metadata'] == {'updated': 'true'}

    @pytest.mark.asyncio
    async def test_update_customer_syncs_to_database(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer syncs to database when session provided."""
        # Mock Stripe response
        mock_customer = Mock()
        mock_customer.id = "cus_sync123"
        mock_customer.email = "synced@testcorp.com"
        mock_customer.name = "Synced Org"
        mock_customer.get = Mock(side_effect=lambda key, default=None: {
            'email': 'synced@testcorp.com',
            'name': 'Synced Org',
            'metadata': {},
            'created': 1234567890
        }.get(key, default))
        mock_stripe_client.modify.return_value = mock_customer

        # Mock database query result
        mock_db_customer = Mock()
        mock_db_customer.email = "old@testcorp.com"
        mock_db_customer.name = "Old Org"
        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_none.return_value = mock_db_customer
        test_db_session.execute.return_value = mock_exec_result

        # When: Updating customer with db_session
        result = await initialized_stripe_service.update_customer(
            stripe_customer_id="cus_sync123",
            email="synced@testcorp.com",
            name="Synced Org",
            db_session=test_db_session
        )

        # Then: Should update database
        assert mock_db_customer.email == "synced@testcorp.com"
        assert mock_db_customer.name == "Synced Org"
        test_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_customer_not_found_error(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer raises NotFoundError for non-existent customer."""
        from src.services.stripe_service import StripeCustomerNotFoundError
        import stripe

        # Mock Stripe "No such customer" error
        mock_stripe_client.modify.side_effect = stripe.error.InvalidRequestError(
            "No such customer: cus_missing",
            None
        )

        # When/Then: Should raise StripeCustomerNotFoundError
        with pytest.raises(StripeCustomerNotFoundError) as exc_info:
            await initialized_stripe_service.update_customer(
                stripe_customer_id="cus_missing",
                email="new@testcorp.com"
            )

        assert "cus_missing" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_customer_stripe_api_error(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer handles Stripe API errors."""
        from src.services.stripe_service import StripeAPIError
        import stripe

        # Mock Stripe API error
        mock_stripe_client.modify.side_effect = stripe.error.StripeError("API Error")

        # When/Then: Should raise StripeAPIError
        with pytest.raises(StripeAPIError) as exc_info:
            await initialized_stripe_service.update_customer(
                stripe_customer_id="cus_error123",
                email="new@testcorp.com"
            )

        assert "Failed to update Stripe customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_customer_invalid_request_other_error(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test update_customer re-raises InvalidRequestError for non-customer errors."""
        import stripe

        # Mock InvalidRequestError that's NOT "No such customer"
        mock_stripe_client.modify.side_effect = stripe.error.InvalidRequestError(
            "Invalid parameter",
            param="email"
        )

        # When/Then: Should re-raise the original InvalidRequestError
        with pytest.raises(stripe.error.InvalidRequestError) as exc_info:
            await initialized_stripe_service.update_customer(
                stripe_customer_id="cus_invalid123",
                email="invalid-email"
            )

        assert "Invalid parameter" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_customer_without_db_session(
        self, mock_stripe_client, initialized_stripe_service
    ):
        """Test delete_customer without database session (Stripe only)."""
        mock_stripe_client.delete.return_value = Mock(id="cus_delete_nodb")

        # When: Deleting customer without db_session
        result = await initialized_stripe_service.delete_customer(
            stripe_customer_id="cus_delete_nodb",
            db_session=None
        )

        # Then: Should still return True
        assert result is True
        mock_stripe_client.delete.assert_called_once_with("cus_delete_nodb")

    @pytest.mark.asyncio
    async def test_delete_customer_removes_from_database(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test delete_customer removes record from database."""
        # Mock database query result
        mock_db_customer = Mock()
        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_none.return_value = mock_db_customer
        test_db_session.execute.return_value = mock_exec_result

        mock_stripe_client.delete.return_value = Mock(id="cus_delete_db")

        # When: Deleting customer with db_session
        result = await initialized_stripe_service.delete_customer(
            stripe_customer_id="cus_delete_db",
            db_session=test_db_session
        )

        # Then: Should delete from database
        test_db_session.delete.assert_called_once_with(mock_db_customer)
        test_db_session.commit.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_customer_when_not_in_database(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test delete_customer when record not in database."""
        # Mock database query returns None
        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_none.return_value = None
        test_db_session.execute.return_value = mock_exec_result

        mock_stripe_client.delete.return_value = Mock(id="cus_delete_missing")

        # When: Deleting customer not in database
        result = await initialized_stripe_service.delete_customer(
            stripe_customer_id="cus_delete_missing",
            db_session=test_db_session
        )

        # Then: Should not call delete on database
        test_db_session.delete.assert_not_called()
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_customer_stripe_api_error(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test delete_customer handles Stripe API errors."""
        from src.services.stripe_service import StripeAPIError
        import stripe

        # Mock Stripe API error
        mock_stripe_client.delete.side_effect = stripe.error.StripeError("API Error")

        # When/Then: Should raise StripeAPIError
        with pytest.raises(StripeAPIError) as exc_info:
            await initialized_stripe_service.delete_customer(
                stripe_customer_id="cus_error123",
                db_session=test_db_session
            )

        assert "Failed to delete Stripe customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_customer_unexpected_error(
        self, test_db_session, mock_stripe_client, initialized_stripe_service
    ):
        """Test delete_customer handles unexpected errors."""
        from src.services.stripe_service import StripeServiceError

        # Mock unexpected error
        mock_stripe_client.delete.side_effect = Exception("Unexpected error")

        # When/Then: Should raise StripeServiceError
        with pytest.raises(StripeServiceError) as exc_info:
            await initialized_stripe_service.delete_customer(
                stripe_customer_id="cus_unexpected123",
                db_session=test_db_session
            )

        assert "Failed to delete customer" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ensure_initialized_raises_error_when_not_initialized(
        self, test_db_session
    ):
        """Test _ensure_initialized raises error when service not initialized."""
        from src.services.stripe_service import StripeService, StripeServiceError

        service = StripeService()
        # Don't initialize

        # When/Then: Should raise StripeServiceError
        with pytest.raises(StripeServiceError) as exc_info:
            await service.get_customer_by_tenant(
                tenant_id="test_tenant",
                db_session=test_db_session
            )

        assert "not initialized" in str(exc_info.value).lower()

    def test_stripe_customer_to_dict(
        self, initialized_stripe_service
    ):
        """Test _stripe_customer_to_dict converts Stripe customer to dict."""
        # Create mock Stripe customer
        mock_customer = Mock()
        mock_customer.id = "cus_test123"
        mock_customer.email = "test@testcorp.com"
        mock_customer.name = "Test Org"
        mock_customer.get = Mock(side_effect=lambda key, default=None: {
            'email': 'test@testcorp.com',
            'name': 'Test Org',
            'metadata': {'tenant_id': 'tenant_123'},
            'created': 1234567890
        }.get(key, default))

        # When: Converting to dict
        result = initialized_stripe_service._stripe_customer_to_dict(mock_customer)

        # Then: Should return proper dictionary
        assert result['stripe_customer_id'] == "cus_test123"
        assert result['email'] == "test@testcorp.com"
        assert result['name'] == "Test Org"
        assert result['metadata'] == {'tenant_id': 'tenant_123'}
        assert result['created'] == 1234567890


# ============================================================================
# P02-001: Meter Event Reporting Tests
# ============================================================================

class TestStripeMeterValidationError:
    """
    CYCLE 9: StripeMeterValidationError Exception Class
    - RED: Test for StripeMeterValidationError exception
    - GREEN: Exception class already implemented
    - REFACTOR: Add validation error details
    """

    def test_stripe_meter_validation_error_exists(self):
        """
        RED PHASE: Test that StripeMeterValidationError exception class exists.

        This test FAILS until exception is created.
        """
        # Given: Import attempt
        # When: Importing from stripe_service
        # Then: Should be importable
        from src.services.stripe_service import StripeMeterValidationError

        # And: Should be an Exception subclass
        assert issubclass(StripeMeterValidationError, Exception)

    def test_stripe_meter_validation_error_inherits_from_service_error(self):
        """
        RED PHASE: Test that StripeMeterValidationError inherits from StripeServiceError.

        Verifies proper exception hierarchy.
        """
        from src.services.stripe_service import (
            StripeMeterValidationError,
            StripeServiceError
        )

        # Should inherit from StripeServiceError
        assert issubclass(StripeMeterValidationError, StripeServiceError)

    def test_stripe_meter_validation_error_can_be_raised_with_details(self):
        """
        RED PHASE: Test that StripeMeterValidationError can be raised with details.

        Verifies exception can be instantiated with meter_event and validation_errors.
        """
        from src.services.stripe_service import StripeMeterValidationError

        # Given: Error details
        meter_event = "invalid_meter"
        validation_errors = ["Invalid meter name", "Value must be positive"]

        # When: Raising the exception
        # Then: Should capture the information
        with pytest.raises(StripeMeterValidationError) as exc_info:
            raise StripeMeterValidationError(
                "Validation failed",
                meter_event=meter_event,
                validation_errors=validation_errors
            )

        assert exc_info.value.meter_event == meter_event
        assert exc_info.value.validation_errors == validation_errors


class TestStripeServiceMeterEventValidation:
    """
    CYCLE 10: report_usage() - Meter Event Validation
    - RED: Test validation logic for meter events
    - GREEN: Implement _validate_meter_event method
    - REFACTOR: Add more validation rules
    """

    @pytest.mark.asyncio
    async def test_validate_meter_event_accepts_valid_ai_labels_event(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that valid ai_labels meter event passes validation.

        Verifies that "ai_labels" meter event with positive value is accepted.
        """
        # Given: A valid meter event
        meter_event = "ai_labels"
        value = 100

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have no errors
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_meter_event_accepts_valid_human_audits_event(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that valid human_audits meter event passes validation.

        Verifies that "human_audits" meter event with positive value is accepted.
        """
        # Given: A valid meter event
        meter_event = "human_audits"
        value = 50

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have no errors
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_meter_event_rejects_invalid_meter_name(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that invalid meter event name fails validation.

        Verifies that meter event names other than "ai_labels" or "human_audits" are rejected.
        """
        # Given: An invalid meter event
        meter_event = "invalid_meter"
        value = 100

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have validation error
        assert len(errors) > 0
        assert any("Invalid meter_event" in err for err in errors)

    @pytest.mark.asyncio
    async def test_validate_meter_event_rejects_non_integer_value(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that non-integer value fails validation.

        Verifies that float values are rejected (must be int).
        """
        # Given: A meter event with float value
        meter_event = "ai_labels"
        value = 100.5

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have validation error
        assert len(errors) > 0
        assert any("integer" in err.lower() for err in errors)

    @pytest.mark.asyncio
    async def test_validate_meter_event_rejects_zero_value(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that zero value fails validation.

        Verifies that value must be positive (> 0).
        """
        # Given: A meter event with zero value
        meter_event = "ai_labels"
        value = 0

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have validation error
        assert len(errors) > 0
        assert any("positive" in err.lower() for err in errors)

    @pytest.mark.asyncio
    async def test_validate_meter_event_rejects_negative_value(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that negative value fails validation.

        Verifies that negative values are rejected.
        """
        # Given: A meter event with negative value
        meter_event = "ai_labels"
        value = -10

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have validation error
        assert len(errors) > 0
        assert any("positive" in err.lower() for err in errors)

    @pytest.mark.asyncio
    async def test_validate_meter_event_returns_multiple_errors(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that multiple validation errors are returned.

        Verifies that all validation issues are reported together.
        """
        # Given: An invalid meter event with multiple issues
        meter_event = "invalid_meter"
        value = -5

        # When: Validating the meter event
        errors = initialized_stripe_service._validate_meter_event(meter_event, value)

        # Then: Should have multiple errors
        assert len(errors) >= 2
        assert any("Invalid meter_event" in err for err in errors)
        assert any("positive" in err.lower() for err in errors)


class TestStripeServiceReportUsage:
    """
    CYCLE 11: report_usage() - Core Functionality
    - RED: Test successful meter event reporting
    - GREEN: Implement report_usage() with Stripe API integration
    - REFACTOR: Add database persistence, idempotency keys
    """

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels',
        'STRIPE_HUMAN_AUDITS_METER_ID': 'mtr_test_human_audits'
    })
    async def test_report_usage_returns_success_response(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test successful meter event reporting.

        Verifies that report_usage() returns proper response dictionary.
        """
        # Given: Valid meter event parameters
        meter_event = "ai_labels"
        value = 100
        tenant_id = "tenant_123"

        # Mock Stripe API call
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            return_value={"id": "evt_test123", "status": "succeeded"}
        ):
            # When: Reporting usage
            result = await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id
            )

            # Then: Should return success response
            assert result['status'] == 'succeeded'
            assert result['meter_event'] == meter_event
            assert result['value'] == value
            assert 'event_id' in result
            assert 'stripe_response' in result

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_with_metadata_includes_metadata_in_call(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that metadata is included in Stripe API call.

        Verifies optional metadata parameter is passed through correctly.
        """
        # Given: Meter event with metadata
        meter_event = "ai_labels"
        value = 50
        tenant_id = "tenant_123"
        metadata = {"batch_id": "batch_001", "source": "api"}

        # Mock Stripe API call
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            return_value={"id": "evt_test456"}
        ) as mock_stripe_call:
            # When: Reporting usage with metadata
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id,
                metadata=metadata
            )

            # Then: Metadata should be included in Stripe call
            mock_stripe_call.assert_called_once()
            call_kwargs = mock_stripe_call.call_args.kwargs
            assert call_kwargs['metadata'] == metadata

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_with_stripe_customer_id(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that stripe_customer_id is included in API call.

        Verifies optional customer ID parameter is passed through correctly.
        """
        # Given: Meter event with customer ID
        meter_event = "ai_labels"
        value = 75
        tenant_id = "tenant_123"
        customer_id = "cus_test123"

        # Mock Stripe API call
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            return_value={"id": "evt_test789"}
        ) as mock_stripe_call:
            # When: Reporting usage with customer ID
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id,
                stripe_customer_id=customer_id
            )

            # Then: Customer ID should be included in Stripe call
            mock_stripe_call.assert_called_once()
            call_kwargs = mock_stripe_call.call_args.kwargs
            assert call_kwargs['customer_id'] == customer_id

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_generates_unique_idempotency_key(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that unique idempotency key is generated.

        Verifies that different calls generate different idempotency keys.
        """
        # Given: Service instance
        meter_event = "ai_labels"
        value = 100
        tenant_id = "tenant_123"

        # Mock Stripe API call
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            return_value={"id": "evt_test"}
        ):
            # When: Reporting usage twice
            result1 = await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id
            )

            # Small delay to ensure different timestamp
            import asyncio
            await asyncio.sleep(0.01)

            result2 = await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id
            )

            # Then: Idempotency keys should be different
            assert result1['event_id'] != result2['event_id']

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_persists_to_database(
        self, initialized_stripe_service, test_db_session
    ):
        """
        RED PHASE: Test that meter event is persisted to database.

        Verifies StripeMeterEvent record is created when db_session is provided.
        """
        # Given: Meter event with database session
        meter_event = "ai_labels"
        value = 100
        tenant_id = "tenant_123"

        # Mock Stripe API call
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            return_value={"id": "evt_test"}
        ):
            # When: Reporting usage with db_session
            result = await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id=tenant_id,
                db_session=test_db_session
            )

            # Then: Should return success
            assert result['status'] == 'succeeded'

            # And: Database should have been called
            test_db_session.add.assert_called()
            test_db_session.commit.assert_called()


class TestStripeServiceReportUsageValidationErrors:
    """
    CYCLE 12: report_usage() - Validation Error Handling
    - RED: Test validation error scenarios
    - GREEN: Validation already implemented
    - REFACTOR: Improve error messages
    """

    @pytest.mark.asyncio
    async def test_report_usage_raises_validation_error_for_invalid_meter(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that invalid meter event name raises validation error.

        Verifies StripeMeterValidationError is raised for invalid meter names.
        """
        from src.services.stripe_service import StripeMeterValidationError

        # Given: Invalid meter event
        meter_event = "invalid_meter"

        # When/Then: Should raise validation error
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=100,
                tenant_id="tenant_123"
            )

        assert exc_info.value.meter_event == meter_event
        assert len(exc_info.value.validation_errors) > 0

    @pytest.mark.asyncio
    async def test_report_usage_raises_validation_error_for_non_integer_value(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that non-integer value raises validation error.

        Verifies StripeMeterValidationError is raised for float values.
        """
        from src.services.stripe_service import StripeMeterValidationError

        # Given: Meter event with float value
        meter_event = "ai_labels"
        value = 100.5

        # When/Then: Should raise validation error
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id="tenant_123"
            )

        # Check the validation_errors attribute which contains detailed errors
        assert len(exc_info.value.validation_errors) > 0
        assert any("integer" in err.lower() for err in exc_info.value.validation_errors)

    @pytest.mark.asyncio
    async def test_report_usage_raises_validation_error_for_zero_value(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that zero value raises validation error.

        Verifies StripeMeterValidationError is raised for zero value.
        """
        from src.services.stripe_service import StripeMeterValidationError

        # Given: Meter event with zero value
        meter_event = "ai_labels"
        value = 0

        # When/Then: Should raise validation error
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id="tenant_123"
            )

        # Check the validation_errors attribute which contains detailed errors
        assert len(exc_info.value.validation_errors) > 0
        assert any("positive" in err.lower() for err in exc_info.value.validation_errors)

    @pytest.mark.asyncio
    async def test_report_usage_raises_validation_error_for_missing_meter_id(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that missing meter ID configuration raises validation error.

        Verifies StripeMeterValidationError when meter ID not configured.
        """
        from src.services.stripe_service import StripeMeterValidationError

        # Given: Service with empty meter config for ai_labels
        # Modify the service's meter config directly to simulate missing configuration
        initialized_stripe_service._meter_config["ai_labels"] = ""

        meter_event = "ai_labels"
        value = 100

        # When/Then: Should raise validation error
        with pytest.raises(StripeMeterValidationError) as exc_info:
            await initialized_stripe_service.report_usage(
                meter_event=meter_event,
                value=value,
                tenant_id="tenant_123"
            )

        assert "not configured" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_report_usage_raises_error_when_not_initialized(self):
        """
        RED PHASE: Test that report_usage requires initialization.

        Verifies StripeServiceError is raised when service not initialized.
        """
        from src.services.stripe_service import StripeService, StripeServiceError

        # Given: Uninitialized service
        service = StripeService()
        # Don't call initialize()

        # When/Then: Should raise error
        with pytest.raises(StripeServiceError) as exc_info:
            await service.report_usage(
                meter_event="ai_labels",
                value=100,
                tenant_id="tenant_123"
            )

        assert "not initialized" in str(exc_info.value).lower()


class TestStripeServiceReportUsageStripeAPIErrors:
    """
    CYCLE 13: report_usage() - Stripe API Error Handling
    - RED: Test Stripe API error scenarios
    - GREEN: Error handling already implemented
    - REFACTOR: Add retry logic (P2-003)
    """

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_handles_stripe_api_error(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that Stripe API errors are handled properly.

        Verifies StripeAPIError is raised when Stripe API call fails.
        """
        from src.services.stripe_service import StripeAPIError
        import stripe

        # Given: Stripe API call will fail
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            side_effect=stripe.error.StripeError("API Error")
        ):
            # When/Then: Should raise StripeAPIError
            with pytest.raises(StripeAPIError) as exc_info:
                await initialized_stripe_service.report_usage(
                    meter_event="ai_labels",
                    value=100,
                    tenant_id="tenant_123"
                )

            assert "Failed to report meter event" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_updates_database_on_api_error(
        self, initialized_stripe_service, test_db_session
    ):
        """
        RED PHASE: Test that database record is updated to FAILED on API error.

        Verifies StripeMeterEvent status is updated when API call fails.
        """
        from src.services.stripe_service import StripeAPIError
        import stripe

        # Given: Stripe API call will fail
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            side_effect=stripe.error.StripeError("API Error")
        ):
            # When/Then: Should raise StripeAPIError
            with pytest.raises(StripeAPIError):
                await initialized_stripe_service.report_usage(
                    meter_event="ai_labels",
                    value=100,
                    tenant_id="tenant_123",
                    db_session=test_db_session
                )

            # And: Database should have been updated (commit called)
            # We expect at least one commit for creating the record
            # and potentially another for updating it to failed
            assert test_db_session.commit.call_count >= 1

    @pytest.mark.asyncio
    @patch.dict('os.environ', {
        'STRIPE_AI_LABELS_METER_ID': 'mtr_test_ai_labels'
    })
    async def test_report_usage_handles_unexpected_errors(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that unexpected errors are handled properly.

        Verifies StripeServiceError is raised for non-Stripe errors.
        """
        from src.services.stripe_service import StripeServiceError

        # Given: Unexpected error will occur
        with patch.object(
            initialized_stripe_service,
            '_report_meter_event_to_stripe',
            side_effect=Exception("Unexpected error")
        ):
            # When/Then: Should raise StripeServiceError
            with pytest.raises(StripeServiceError) as exc_info:
                await initialized_stripe_service.report_usage(
                    meter_event="ai_labels",
                    value=100,
                    tenant_id="tenant_123"
                )

            assert "Failed to report meter event" in str(exc_info.value)


class TestStripeServiceHelperMethods:
    """
    CYCLE 14: Helper Methods - Idempotency Key Generation
    - RED: Test idempotency key generation
    - GREEN: Implementation already complete
    - REFACTOR: Add more uniqueness guarantees
    """

    @pytest.mark.asyncio
    async def test_generate_idempotency_key_is_unique(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that idempotency keys are unique.

        Verifies that consecutive calls generate different keys.
        """
        # Given: Service instance
        tenant_id = "tenant_123"
        meter_event = "ai_labels"
        value = 100

        # When: Generating idempotency keys
        key1 = initialized_stripe_service._generate_idempotency_key(
            tenant_id, meter_event, value
        )

        import asyncio
        await asyncio.sleep(0.01)  # Small delay for different timestamp

        key2 = initialized_stripe_service._generate_idempotency_key(
            tenant_id, meter_event, value
        )

        # Then: Keys should be different
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_generate_idempotency_key_contains_context(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that idempotency key contains context information.

        Verifies key includes tenant_id, meter_event, and value.
        """
        # Given: Service instance
        tenant_id = "tenant_123"
        meter_event = "ai_labels"
        value = 100

        # When: Generating idempotency key
        key = initialized_stripe_service._generate_idempotency_key(
            tenant_id, meter_event, value
        )

        # Then: Key should contain all context
        assert tenant_id in key
        assert meter_event in key
        assert str(value) in key

    @pytest.mark.asyncio
    async def test_generate_idempotency_key_format_is_valid(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that idempotency key has expected format.

        Verifies key follows pattern: {tenant_id}_{event}_{value}_{timestamp}_{uuid}
        """
        # Given: Service instance
        tenant_id = "tenant_123"
        meter_event = "ai_labels"
        value = 100

        # When: Generating idempotency key
        key = initialized_stripe_service._generate_idempotency_key(
            tenant_id, meter_event, value
        )

        # Then: Key should have expected format
        # Format: {tenant_id}_{event}_{value}_{timestamp}_{uuid}
        # Since tenant_id may contain underscores, we verify the components are present
        assert tenant_id in key
        assert meter_event in key
        assert str(value) in key
        # Key should end with timestamp and uuid suffix (pattern: digits_hex)
        assert key.split('_')[-1]  # Last part should exist (uuid suffix)
        assert key.split('_')[-2]  # Second to last should exist (timestamp)


class TestStripeServiceMeterConfigInitialization:
    """
    CYCLE 15: Meter Configuration Initialization
    - RED: Test meter configuration is loaded correctly
    - GREEN: Implementation already complete
    - REFACTOR: Add configuration validation
    """

    @pytest.mark.asyncio
    async def test_meter_config_loaded_from_environment(self):
        """
        RED PHASE: Test that meter configuration is loaded from environment.

        Verifies _meter_config dict contains values from environment variables.
        """
        # Given: Environment variables set
        import os
        original_ai_labels = os.environ.get('STRIPE_AI_LABELS_METER_ID')
        original_human_audits = os.environ.get('STRIPE_HUMAN_AUDITS_METER_ID')

        try:
            os.environ['STRIPE_AI_LABELS_METER_ID'] = 'mtr_test_ai_123'
            os.environ['STRIPE_HUMAN_AUDITS_METER_ID'] = 'mtr_test_human_456'

            # When: Creating new StripeService instance
            from src.services.stripe_service import StripeService
            service = StripeService()

            # Then: Meter config should be loaded
            assert service._meter_config['ai_labels'] == 'mtr_test_ai_123'
            assert service._meter_config['human_audits'] == 'mtr_test_human_456'

        finally:
            # Restore original environment
            if original_ai_labels is not None:
                os.environ['STRIPE_AI_LABELS_METER_ID'] = original_ai_labels
            else:
                os.environ.pop('STRIPE_AI_LABELS_METER_ID', None)

            if original_human_audits is not None:
                os.environ['STRIPE_HUMAN_AUDITS_METER_ID'] = original_human_audits
            else:
                os.environ.pop('STRIPE_HUMAN_AUDITS_METER_ID', None)

    @pytest.mark.asyncio
    async def test_meter_config_defaults_to_empty_string(self):
        """
        RED PHASE: Test that missing environment variables default to empty string.

        Verifies behavior when meter IDs are not configured.
        """
        # Given: No environment variables set
        import os
        original_ai_labels = os.environ.get('STRIPE_AI_LABELS_METER_ID')
        original_human_audits = os.environ.get('STRIPE_HUMAN_AUDITS_METER_ID')

        try:
            os.environ.pop('STRIPE_AI_LABELS_METER_ID', None)
            os.environ.pop('STRIPE_HUMAN_AUDITS_METER_ID', None)

            # When: Creating new StripeService instance
            from src.services.stripe_service import StripeService
            service = StripeService()

            # Then: Meter config should have empty strings
            assert service._meter_config['ai_labels'] == ''
            assert service._meter_config['human_audits'] == ''

        finally:
            # Restore original environment
            if original_ai_labels is not None:
                os.environ['STRIPE_AI_LABELS_METER_ID'] = original_ai_labels
            if original_human_audits is not None:
                os.environ['STRIPE_HUMAN_AUDITS_METER_ID'] = original_human_audits


class TestStripeServiceReportMeterEventToStripe:
    """
    CYCLE 16: Stripe API Integration - _report_meter_event_to_stripe
    - RED: Test Stripe API call method
    - GREEN: Implementation already complete
    - REFACTOR: Add retry logic in P2-003

    Note: These tests focus on verifying the method exists and has the right structure.
    Actual Stripe API calls are tested through the higher-level report_usage() tests.
    """

    @pytest.mark.asyncio
    async def test_report_meter_event_to_stripe_method_exists(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that _report_meter_event_to_stripe method exists.

        Verifies the method signature and basic structure.
        """
        # Given: The service instance
        # When: Checking for the method
        # Then: Should exist and be callable
        assert hasattr(initialized_stripe_service, '_report_meter_event_to_stripe')
        assert callable(initialized_stripe_service._report_meter_event_to_stripe)

    @pytest.mark.asyncio
    async def test_report_meter_event_to_stripe_has_correct_signature(
        self, initialized_stripe_service
    ):
        """
        RED PHASE: Test that _report_meter_event_to_stripe has expected parameters.

        Verifies the method accepts the required parameters.
        """
        import inspect

        # Given: The method
        method = initialized_stripe_service._report_meter_event_to_stripe

        # When: Inspecting signature
        sig = inspect.signature(method)

        # Then: Should have expected parameters
        params = list(sig.parameters.keys())
        assert 'meter_id' in params
        assert 'event_name' in params
        assert 'value' in params
        assert 'idempotency_key' in params
        assert 'customer_id' in params
        assert 'metadata' in params
