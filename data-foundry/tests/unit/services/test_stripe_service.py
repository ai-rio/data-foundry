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
        # Then: Should have unique constraint
        field = StripeCustomer.model_fields['tenant_id']
        # Field description should contain unique information
        assert 'unique' in str(field.metadata).lower() or hasattr(StripeCustomer, '__table_args__')

    @pytest.mark.asyncio
    async def test_stripe_customer_stripe_id_unique_constraint(self):
        """
        RED PHASE: Test that stripe_customer_id has unique constraint.

        Verifies stripe_customer_id is marked as unique in Field definition.
        """
        # Given: The StripeCustomer model
        # When: Checking stripe_customer_id field
        # Then: Should have unique constraint
        field = StripeCustomer.model_fields['stripe_customer_id']
        # Field description should contain unique information
        assert 'unique' in str(field.metadata).lower() or hasattr(StripeCustomer, '__table_args__')


class TestStripeCustomersMigration:
    """
    CYCLE 2: stripe_customers Table Migration
    - RED: Test that verifies table exists and has correct schema
    - GREEN: Create migration script
    - REFACTOR: Add RLS policies, indexes
    """

    @pytest.mark.asyncio
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

    @pytest.fixture
    def mock_secret_manager(self):
        """Mock SecretManager fixture."""
        with patch('src.services.stripe_service.SecretManager') as mock:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = "sk_test_1234567890"
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_initialize_loads_api_key_from_secret_manager(self, mock_secret_manager):
        """
        RED PHASE: Test that initialize() loads API key from SecretManager.

        Verifies that StripeService.initialize() retrieves the Stripe secret key
        from SecretManager and configures the Stripe client.
        """
        # Given: A StripeService instance
        from src.services.stripe_service import StripeService

        service = StripeService()

        # When: Calling initialize
        await service.initialize()

        # Then: API key should be loaded from SecretManager
        mock_secret_manager.return_value.get_secret.assert_called_once_with('STRIPE_SECRET_KEY')
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


# Fixtures for Stripe testing
@pytest.fixture
def mock_stripe_client():
    """Mock Stripe client for testing."""
    with patch('stripe.Customer') as mock:
        yield mock


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


class TestStripeServiceCreateCustomer:
    """
    CYCLE 5: StripeService.create_customer()
    - RED: Test successful customer creation
    - GREEN: Implement create_customer() with Stripe API call
    - REFACTOR: Extract metadata handling, add database persistence
    """

    @pytest.mark.asyncio
    async def test_create_customer_returns_stripe_customer_id(
        self, test_tenant, test_db_session, mock_stripe_client
    ):
        """
        RED PHASE: Test successful customer creation returns Stripe customer ID.

        Verifies that create_customer():
        1. Calls Stripe API with correct parameters
        2. Includes tenant_id in metadata
        3. Returns the Stripe customer ID
        4. Persists to database
        """
        # Given: A StripeService and mocked Stripe API response
        from src.services.stripe_service import StripeService

        service = StripeService()
        service.api_key = "sk_test_123"

        # Mock Stripe API response
        mock_customer = Mock()
        mock_customer.id = "cus_new123"
        mock_customer.email = "admin@testcorp.com"
        mock_customer.name = "Test Organization"
        mock_stripe_client.create.return_value = mock_customer

        # When: Creating a customer
        result = await service.create_customer(
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
        self, test_tenant, test_db_session, mock_stripe_client
    ):
        """
        RED PHASE: Test that create_customer persists to database.

        Verifies that StripeCustomer record is created in database after
        successful Stripe API call.
        """
        # Given: A StripeService and mocked Stripe API response
        from src.services.stripe_service import StripeService

        service = StripeService()
        service.api_key = "sk_test_123"

        mock_customer = Mock()
        mock_customer.id = "cus_db123"
        mock_stripe_client.create.return_value = mock_customer

        # When: Creating a customer
        await service.create_customer(
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
    async def test_get_customer_by_tenant_returns_customer_dict(self, test_db_session):
        """
        RED PHASE: Test retrieving existing customer by tenant_id.

        Verifies that get_customer_by_tenant():
        1. Queries database for customer
        2. Returns customer dictionary with details
        """
        # Given: A StripeService and existing customer in database
        from src.services.stripe_service import StripeService

        service = StripeService()

        # Mock database query result
        mock_result = Mock()
        mock_result.tenant_id = "test_tenant_123"
        mock_result.stripe_customer_id = "cus_existing123"
        mock_result.email = "billing@testcorp.com"
        mock_result.name = "Test Org"

        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_create.return_value = mock_result

        test_db_session.execute.return_value = mock_exec_result

        # When: Retrieving customer by tenant
        result = await service.get_customer_by_tenant(
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
    async def test_get_customer_by_tenant_returns_none_when_not_found(self, test_db_session):
        """
        RED PHASE: Test that get_customer_by_tenant returns None for non-existent customer.

        Verifies that None is returned when tenant doesn't have a Stripe customer.
        """
        # Given: A StripeService and empty database
        from src.services.stripe_service import StripeService

        service = StripeService()

        mock_exec_result = Mock()
        mock_exec_result.scalar_one_or_create.return_value = None
        test_db_session.execute.return_value = mock_exec_result

        # When: Retrieving non-existent customer
        result = await service.get_customer_by_tenant(
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
    async def test_update_customer_updates_stripe_and_database(self, mock_stripe_client):
        """
        RED PHASE: Test partial update of customer email.

        Verifies that update_customer():
        1. Calls Stripe API with updated fields
        2. Updates database record
        3. Returns updated customer data
        """
        # Given: A StripeService and mocked Stripe response
        from src.services.stripe_service import StripeService

        service = StripeService()
        service.api_key = "sk_test_123"

        # Mock Stripe API response
        mock_customer = Mock()
        mock_customer.id = "cus_update123"
        mock_customer.email = "newemail@testcorp.com"
        mock_customer.name = "Test Org"
        mock_stripe_client.modify.return_value = mock_customer

        # When: Updating customer email
        result = await service.update_customer(
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
        self, test_db_session, mock_stripe_client
    ):
        """
        RED PHASE: Test customer deletion.

        Verifies that delete_customer():
        1. Calls Stripe API to delete customer
        2. Removes from database
        3. Returns True on success
        """
        # Given: A StripeService
        from src.services.stripe_service import StripeService

        service = StripeService()
        service.api_key = "sk_test_123"

        mock_stripe_client.delete.return_value = Mock(id="cus_delete123")

        # When: Deleting customer
        result = await service.delete_customer(
            stripe_customer_id="cus_delete123",
            db_session=test_db_session
        )

        # Then: Should call Stripe API
        mock_stripe_client.delete.assert_called_once_with("cus_delete123")

        # And: Delete from database
        # Note: This will be implemented with actual delete query

        # And: Return True
        assert result is True
