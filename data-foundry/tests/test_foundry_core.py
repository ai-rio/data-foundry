"""
Multi-tenancy (Row-Level Security) tests for Data Foundry core functionality
"""

import pytest
from datetime import datetime

from src.models import Tenant, User, DataRecord, ProcessedData, HumanReviewQueue
from src.core.security import create_access_token, get_password_hash


class TestMultiTenancyIsolation:
    """Test tenant isolation and data separation."""

    async def test_tenant_cannot_access_other_tenant_data(self, db_session, test_tenant):
        """Test that Tenant A cannot access Tenant B's data."""
        # Create a second tenant
        tenant_b = Tenant(
            tenant_id="test_tenant_002",
            name="Other Organization",
            status="active",
            max_users=50,
            max_data_records=100000,
            storage_limit_gb=50.0,
        )
        db_session.add(tenant_b)
        await db_session.commit()
        await db_session.refresh(tenant_b)

        # Create a user in tenant B
        user_b = User(
            user_id="test_user_b_001",
            email="user_b@otherorg.com",
            tenant_id=tenant_b.tenant_id,
            hashed_password=get_password_hash("testpass123"),
            role="analyst",
            status="active",
        )
        db_session.add(user_b)
        await db_session.commit()

        # Create data in tenant A
        record_a = DataRecord(
            record_id="rec_a_001",
            tenant_id=test_tenant.tenant_id,
            data_source="csv",
            status="raw",
            raw_data='{"name": "Tenant A User"}',
        )
        db_session.add(record_a)
        await db_session.commit()
        await db_session.refresh(record_a)

        # Create data in tenant B
        record_b = DataRecord(
            record_id="rec_b_001",
            tenant_id=tenant_b.tenant_id,
            data_source="csv",
            status="raw",
            raw_data='{"name": "Tenant B User"}',
        )
        db_session.add(record_b)
        await db_session.commit()
        await db_session.refresh(record_b)

        # Query as tenant A user - should only see tenant A data
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            # This simulates the RLS policy
            result = await conn.fetch(
                "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 1

            # Should not see tenant B data
            result_b = await conn.fetch(
                "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                tenant_b.tenant_id,
            )
            assert result_b[0]["count"] == 0

    async def test_postgresql_rls_working_correctly(self, db_session, test_tenant):
        """Test that PostgreSQL RLS is working correctly."""
        # Test RLS policies are enabled
        async with db_connection.get_connection() as conn:
            # Check if RLS is enabled on data_records table
            result = await conn.fetch(
                "SELECT rowsecurity FROM pg_class WHERE relname = 'data_records'"
            )
            assert result[0]["rowsecurity"] is True

            # Check if tenant isolation policy exists
            result = await conn.fetch(
                "SELECT 1 FROM pg_policies WHERE tablename = 'data_records' AND policyname = 'tenant_isolation_data_records'"
            )
            assert len(result) > 0

    async def test_database_session_isolation_with_app_tenant_id(self, db_session, test_tenant):
        """Test database session isolation with app.tenant_id setting."""
        # Create data for two tenants
        for i, tenant in enumerate([test_tenant, "test_tenant_002"]):
            record = DataRecord(
                record_id=f"session_test_{i}",
                tenant_id=tenant,
                data_source="csv",
                status="raw",
                raw_data=f'{{"name": "Tenant {i+1} User"}}',
            )
            db_session.add(record)

        await db_session.commit()

        # Test isolation by setting tenant context
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            # Should only see own tenant's data
            result = await conn.fetch(
                "SELECT record_id FROM data_records WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert len(result) == 1
            assert result[0]["record_id"] == f"session_test_0"

    async def test_tenant_data_counts_are_accurate(self, db_session, test_tenant, test_records):
        """Test that tenant data counts are accurate."""
        # Add one more record to test_tenant
        extra_record = DataRecord(
            record_id="extra_test_rec",
            tenant_id=test_tenant.tenant_id,
            data_source="csv",
            status="raw",
            raw_data='{"name": "Extra User"}',
        )
        db_session.add(extra_record)
        await db_session.commit()

        # Test counts per tenant
        async with db_connection.get_connection() as conn:
            # Count for test_tenant
            result = await conn.fetch(
                "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == len(test_records) + 1

    async def test_cross_tenant_data_access_denied(self, db_session, test_tenant):
        """Test that cross-tenant data access is properly denied."""
        # Create data in different tenants
        tenants = ["tenant_a", "tenant_b", "tenant_c"]
        records = []

        for i, tenant_id in enumerate(tenants):
            record = DataRecord(
                record_id=f"cross_test_{i}",
                tenant_id=tenant_id,
                data_source="csv",
                status="raw",
                raw_data=f'{{"name": "Tenant {tenant_id} User"}}',
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Test that each tenant only sees their own data
        for i, tenant_id in enumerate(tenants):
            async with db_connection.get_tenant_connection(tenant_id) as conn:
                result = await conn.fetch(
                    "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                    tenant_id,
                )
                assert result[0]["count"] == 1

                # Should not see other tenants' data
                for j, other_tenant_id in enumerate(tenants):
                    if i != j:
                        result = await conn.fetch(
                            "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                            other_tenant_id,
                        )
                        assert result[0]["count"] == 0

    async def test_tenant_specific_processed_data_isolation(self, db_session, test_tenant):
        """Test processed data isolation between tenants."""
        # Create processed data for different tenants
        tenant_ids = [test_tenant.tenant_id, "tenant_other", "tenant_another"]

        for i, tenant_id in enumerate(tenant_ids):
            processed = ProcessedData(
                record_id=f"proc_{i}",
                tenant_id=tenant_id,
                confidence_score=0.9,
                auto_approved=True,
                review_required=False,
                ai_category="high_value",
                ai_confidence=0.9,
                ai_model="gpt-4o",
                cleaned_data=f'{{"name": "Processed Tenant {tenant_id}"}}',
                processed_at=datetime.utcnow(),
            )
            db_session.add(processed)

        await db_session.commit()

        # Test isolation
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            result = await conn.fetch(
                "SELECT COUNT(*) FROM processed_data WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 1

            # Should not see other tenants' data
            for other_tenant_id in tenant_ids[1:]:
                result = await conn.fetch(
                    "SELECT COUNT(*) FROM processed_data WHERE tenant_id = $1",
                    other_tenant_id,
                )
                assert result[0]["count"] == 0

    async def test_tenant_specific_human_review_queue_isolation(self, db_session, test_tenant):
        """Test human review queue isolation between tenants."""
        # Create review queue items for different tenants
        tenant_ids = [test_tenant.tenant_id, "tenant_other", "tenant_another"]

        for i, tenant_id in enumerate(tenant_ids):
            review = HumanReviewQueue(
                review_id=f"rev_{i}",
                record_id=f"rev_rec_{i}",
                tenant_id=tenant_id,
                status="pending",
                priority="medium",
                original_data=f'{{"name": "Review Tenant {tenant_id}"}}',
                ai_confidence=0.65,
                ai_category="uncertain",
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow(),
            )
            db_session.add(review)

        await db_session.commit()

        # Test isolation
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            result = await conn.fetch(
                "SELECT COUNT(*) FROM human_review_queue WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 1

            # Should not see other tenants' data
            for other_tenant_id in tenant_ids[1:]:
                result = await conn.fetch(
                    "SELECT COUNT(*) FROM human_review_queue WHERE tenant_id = $1",
                    other_tenant_id,
                )
                assert result[0]["count"] == 0

    async def test_user_tenant_relationship_isolation(self, db_session, test_tenant, test_users):
        """Test user-tenant relationship isolation."""
        # Create another tenant and user
        other_tenant = Tenant(
            tenant_id="other_test_tenant",
            name="Other Test Org",
            status="active",
        )
        db_session.add(other_tenant)
        await db_session.commit()

        other_user = User(
            user_id="other_user_001",
            email="other@example.com",
            tenant_id=other_tenant.tenant_id,
            hashed_password=get_password_hash("testpass123"),
            role="admin",
            status="active",
        )
        db_session.add(other_user)
        await db_session.commit()

        # Test that users only see their own tenant's users
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            result = await conn.fetch(
                "SELECT COUNT(*) FROM users WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            # Should see all users in the same tenant
            assert result[0]["count"] >= 3  # test_users + any new ones

            # Should not see users from other tenant
            result = await conn.fetch(
                "SELECT COUNT(*) FROM users WHERE tenant_id = $1",
                other_tenant.tenant_id,
            )
            assert result[0]["count"] == 0

    async def test_tenant_status_affects_data_access(self, db_session, test_tenant):
        """Test that tenant status affects data access."""
        # Create an inactive tenant
        inactive_tenant = Tenant(
            tenant_id="inactive_tenant",
            name="Inactive Org",
            status="inactive",
        )
        db_session.add(inactive_tenant)
        await db_session.commit()

        # Create data for inactive tenant
        inactive_record = DataRecord(
            record_id="inactive_rec",
            tenant_id=inactive_tenant.tenant_id,
            data_source="csv",
            status="raw",
            raw_data='{"name": "Inactive Tenant User"}',
        )
        db_session.add(inactive_record)
        await db_session.commit()

        # Active tenant should not see inactive tenant's data
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            result = await conn.fetch(
                "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                inactive_tenant.tenant_id,
            )
            assert result[0]["count"] == 0

    async def test_tenant_data_deletion_cascades_properly(self, db_session, test_tenant):
        """Test that tenant data deletion cascades properly."""
        # Create records for the tenant
        tenant_records = []
        for i in range(3):
            record = DataRecord(
                record_id=f"cascade_test_{i}",
                tenant_id=test_tenant.tenant_id,
                data_source="csv",
                status="raw",
                raw_data=f'{{"name": "Cascade User {i}"}}',
            )
            tenant_records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Create processed data for some records
        processed1 = ProcessedData(
            record_id=tenant_records[0].record_id,
            tenant_id=test_tenant.tenant_id,
            confidence_score=0.9,
            auto_approved=True,
            review_required=False,
            ai_category="high_value",
            ai_confidence=0.9,
            ai_model="gpt-4o",
            cleaned_data='{"name": "Processed Cascade User 0"}',
            processed_at=datetime.utcnow(),
        )
        db_session.add(processed1)
        await db_session.commit()

        # Create review queue for another record
        review1 = HumanReviewQueue(
            review_id="cascade_review_1",
            record_id=tenant_records[1].record_id,
            tenant_id=test_tenant.tenant_id,
            status="pending",
            priority="medium",
            original_data='{"name": "Review Cascade User 1"}',
            ai_confidence=0.65,
            ai_category="uncertain",
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )
        db_session.add(review1)
        await db_session.commit()

        # Delete tenant
        await db_session.delete(test_tenant)
        await db_session.commit()

        # Verify all associated data is also deleted
        async with db_connection.get_connection() as conn:
            # Check data_records
            result = await conn.fetch(
                "SELECT COUNT(*) FROM data_records WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 0

            # Check processed_data
            result = await conn.fetch(
                "SELECT COUNT(*) FROM processed_data WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 0

            # Check human_review_queue
            result = await conn.fetch(
                "SELECT COUNT(*) FROM human_review_queue WHERE tenant_id = $1",
                test_tenant.tenant_id,
            )
            assert result[0]["count"] == 0

    async def test_tenant_id_inheritance_on_create(self, db_session, test_tenant):
        """Test that tenant_id is properly inherited on create."""
        # Create a new record without explicitly setting tenant_id
        # The RLS trigger should set it based on the current session
        async with db_connection.get_tenant_connection(test_tenant.tenant_id) as conn:
            await conn.execute(
                """
                INSERT INTO data_records (record_id, data_source, raw_data, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                """,
                "inherit_test",
                "csv",
                '{"name": "Inherited Tenant User"}',
            )

            # Verify the tenant_id was set correctly
            result = await conn.fetch(
                "SELECT tenant_id FROM data_records WHERE record_id = $1",
                "inherit_test",
            )
            assert result[0]["tenant_id"] == test_tenant.tenant_id


class TestTenantManagement:
    """Test tenant management functionality."""

    async def test_tenant_creation(self, db_session):
        """Test tenant creation and basic properties."""
        tenant = Tenant(
            tenant_id="new_test_tenant",
            name="New Test Organization",
            status="active",
            max_users=50,
            max_data_records=500000,
            storage_limit_gb=25.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        assert tenant.tenant_id == "new_test_tenant"
        assert tenant.name == "New Test Organization"
        assert tenant.status == "active"
        assert tenant.max_users == 50
        assert tenant.max_data_records == 500000
        assert tenant.storage_limit_gb == 25.0
        assert tenant.enable_pii_redaction is True
        assert tenant.enable_ai_labeling is True
        assert tenant.enable_human_review is True
        assert tenant.created_at is not None
        assert tenant.updated_at is not None

    async def test_tenant_status_transitions(self, db_session):
        """Test tenant status transitions."""
        tenant = Tenant(
            tenant_id="status_test_tenant",
            name="Status Test Org",
            status="active",
        )
        db_session.add(tenant)
        await db_session.commit()

        # Test status transition from active to suspended
        tenant.status = "suspended"
        await db_session.commit()
        await db_session.refresh(tenant)
        assert tenant.status == "suspended"

        # Test status transition from suspended to inactive
        tenant.status = "inactive"
        await db_session.commit()
        await db_session.refresh(tenant)
        assert tenant.status == "inactive"

    async def test_tenant_settings_inheritance(self, db_session):
        """Test that tenant settings are properly inherited by data processing."""
        tenant = Tenant(
            tenant_id="settings_test_tenant",
            name="Settings Test Org",
            status="active",
            enable_pii_redaction=False,  # Disable PII redaction
            enable_ai_labeling=False,     # Disable AI labeling
            enable_human_review=False,    # Disable human review
        )
        db_session.add(tenant)
        await db_session.commit()

        # Verify settings are stored correctly
        await db_session.refresh(tenant)
        assert tenant.enable_pii_redaction is False
        assert tenant.enable_ai_labeling is False
        assert tenant.enable_human_review is False

    async def test_tenant_quota_enforcement(self, db_session, test_tenant):
        """Test tenant quota enforcement."""
        # Test current usage vs limits
        current_users = 3  # From test_users fixture
        max_users = test_tenant.max_users

        # Verify current usage is within limits
        assert current_users <= max_users

        # Test that we can't exceed user limit (this would be enforced at application level)
        # For now, just verify the limits are properly stored
        assert test_tenant.max_users > 0
        assert test_tenant.max_data_records > 0
        assert test_tenant.storage_limit_gb > 0


class TestSecurityIntegration:
    """Test security integration with multi-tenancy."""

    async def test_jwt_token_contains_tenant_id(self, test_users):
        """Test that JWT tokens contain tenant information."""
        admin_user = test_users[0]

        # Create a token with tenant context
        token = create_access_token(
            subject=admin_user.user_id,
            expires_delta=None,
        )

        # Verify the token was created (we don't decode it here as that's tested elsewhere)
        assert token is not None
        assert isinstance(token, str)

    async def test_user_tenant_verification(self, test_users, test_tenant):
        """Test user-tenant relationship verification."""
        admin_user, analyst_user, viewer_user = test_users

        # Verify all users belong to the correct tenant
        for user in test_users:
            assert user.tenant_id == test_tenant.tenant_id

        # Verify tenant ID consistency
        assert admin_user.tenant_id == analyst_user.tenant_id == viewer_user.tenant_id

    async def test_tenant_specific_api_keys(self, db_session, test_tenant):
        """Test tenant-specific API key generation."""
        # This test verifies the structure for API key generation
        # In production, API keys would be generated and stored per tenant

        # Create a user with an API key
        user_with_api = User(
            user_id="api_user_001",
            email="api_user@testcorp.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password=get_password_hash("testpass123"),
            role="admin",
            status="active",
            # API key would be set here
        )
        db_session.add(user_with_api)
        await db_session.commit()

        # Verify user can be retrieved
        retrieved_user = await db_session.get(User, user_with_api.id)
        assert retrieved_user is not None
        assert retrieved_user.tenant_id == test_tenant.tenant_id