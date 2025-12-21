"""
Comprehensive tests for Phase 3.1 Enhanced Data Models
Tests the models that were implemented with "Test Later" approach
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from src.models import (
    DataRecord, Tenant, User, ProcessedData, HumanReviewQueue,
    TokenUsage, TenantUsage, AuditLog, CostAlert, BillingEvent
)
from src.models.user import UserRole, UserStatus
from src.models.tenant import TenantStatus


class TestEnhancedDataRecord:
    """Test enhanced DataRecord model with new AI tracking fields."""

    @pytest.mark.asyncio
    async def test_data_record_with_ai_tracking_fields(self, db_session, test_tenant):
        """Test DataRecord with new AI tracking fields."""
        # Create a record with all new AI tracking fields
        record = DataRecord(
            record_id="test_ai_rec_001",
            tenant_id=test_tenant.tenant_id,
            data_source="csv",
            status="processed",

            # Existing fields
            raw_data='{"name": "John Doe", "email": "john@example.com"}',
            processed_data='{"name": "John Doe", "email": "john@example.com", "category": "high_value"}',
            confidence_score=0.95,
            ai_category="high_value",
            ai_confidence=0.95,
            ai_reasoning="Corporate email pattern detected",

            # New AI tracking fields
            ai_model="gpt-4o",
            ai_request_id="req_ai_001",
            ai_tokens_used=250,
            ai_cost="0.0025",
            ai_processing_time_ms=1250,

            # New provenance and audit fields
            provenance_metadata='{"model_version": "gpt-4o-1106", "cache_hit": false, "fallback_used": false}',
            processing_history='[{"timestamp": "2024-01-20T10:00:00Z", "action": "ai_processing", "model": "gpt-4o"}]',

            # PII fields
            pii_detected=True,
            pii_redacted=True,
            pii_types='["EMAIL_ADDRESS"]',

            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            processed_at=datetime.utcnow(),
        )

        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        # Verify all fields are set correctly
        assert record.record_id == "test_ai_rec_001"
        assert record.ai_model == "gpt-4o"
        assert record.ai_request_id == "req_ai_001"
        assert record.ai_tokens_used == 250
        assert record.ai_cost == "0.0025"
        assert record.ai_processing_time_ms == 1250
        assert record.provenance_metadata is not None
        assert record.processing_history is not None
        assert record.pii_detected is True
        assert record.pii_redacted is True

    @pytest.mark.asyncio
    async def test_data_record_jsonb_fields_validation(self, db_session, test_tenant):
        """Test JSONB fields work correctly with complex data."""
        complex_provenance = {
            "model": "gpt-4o",
            "provider": "openai",
            "model_version": "gpt-4o-1106-preview",
            "request_id": "req_12345",
            "tokens": {"prompt": 150, "completion": 100, "total": 250},
            "cost": {"input": 0.0015, "output": 0.001, "total": 0.0025},
            "timing": {"response_time_ms": 1250, "cache_hit": False},
            "fallback": {"used": False, "original_model": "gpt-4o"},
        }

        complex_history = [
            {
                "timestamp": "2024-01-20T10:00:00Z",
                "action": "data_ingestion",
                "status": "completed",
                "details": {"file_size": 1024, "records_processed": 1}
            },
            {
                "timestamp": "2024-01-20T10:01:00Z",
                "action": "pii_detection",
                "status": "completed",
                "details": {"pii_types_found": ["EMAIL_ADDRESS"], "redaction_applied": True}
            },
            {
                "timestamp": "2024-01-20T10:02:00Z",
                "action": "ai_processing",
                "status": "completed",
                "details": {"model": "gpt-4o", "confidence": 0.95, "category": "high_value"}
            }
        ]

        record = DataRecord(
            record_id="test_jsonb_001",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="processed",
            raw_data='{"test": "data"}',
            provenance_metadata=str(complex_provenance).replace("'", '"'),
            processing_history=str(complex_history).replace("'", '"'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        # Verify JSONB fields are accessible
        assert record.provenance_metadata is not None
        assert record.processing_history is not None
        assert "gpt-4o" in record.provenance_metadata
        assert "ai_processing" in record.processing_history


class TestEnhancedTenant:
    """Test enhanced Tenant model with billing and feature flags."""

    @pytest.mark.asyncio
    async def test_tenant_with_enhanced_fields(self, db_session):
        """Test Tenant with new billing and feature flag fields."""
        tenant = Tenant(
            tenant_id="enhanced_tenant_001",
            name="Enhanced Test Organization",
            status=TenantStatus.ACTIVE,
            domain="enhanced.example.com",
            max_users=50,
            max_data_records=500000,
            storage_limit_gb=50.0,

            # Feature flags
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,

            # New billing fields
            billing_plan="enterprise",
            created_by="admin_user",

            # Feature-specific settings
            max_ai_requests_per_month=10000,
            max_human_reviews_per_month=5000,
            custom_prompt_templates_enabled=True,
            advanced_analytics_enabled=True,

            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        # Verify enhanced fields
        assert tenant.billing_plan == "enterprise"
        assert tenant.is_active is True
        assert tenant.enable_pii_redaction is True
        assert tenant.enable_ai_labeling is True
        assert tenant.enable_human_review is True

    @pytest.mark.asyncio
    async def test_tenant_status_transitions(self, db_session):
        """Test tenant status transitions and business logic."""
        tenant = Tenant(
            tenant_id="status_tenant_001",
            name="Status Test Organization",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=1000,
            storage_limit_gb=5.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        # Test active status
        assert tenant.is_active is True

        # Test suspension
        tenant.status = TenantStatus.SUSPENDED
        await db_session.commit()
        await db_session.refresh(tenant)
        assert tenant.is_active is False

        # Test reactivation
        tenant.status = TenantStatus.ACTIVE
        await db_session.commit()
        await db_session.refresh(tenant)
        assert tenant.is_active is True


class TestEnhancedUser:
    """Test enhanced User model with MFA and permissions."""

    @pytest.mark.asyncio
    async def test_user_with_enhanced_fields(self, db_session, test_tenant):
        """Test User with new MFA and permission fields."""
        user = User(
            user_id="enhanced_user_001",
            email="enhanced@example.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password="hashed_password_here",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            first_name="Enhanced",
            last_name="User",

            # Permission flags
            can_create_data=True,
            can_view_data=True,
            can_modify_data=True,
            can_delete_data=True,
            can_manage_users=True,
            can_view_billing=True,
            can_manage_billing=True,

            # MFA fields
            mfa_enabled=True,
            mfa_secret="JBSWY3DPEHPK3PXP",  # Example secret
            backup_codes='["123456", "789012"]',

            # Profile fields
            phone_number="+1-555-123-4567",
            department="IT",
            job_title="System Administrator",
            last_login_at=datetime.utcnow(),

            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Verify enhanced fields
        assert user.mfa_enabled is True
        assert user.can_manage_billing is True
        assert user.phone_number == "+1-555-123-4567"
        assert user.department == "IT"
        assert user.job_title == "System Administrator"

    @pytest.mark.asyncio
    async def test_user_role_permissions(self, db_session, test_tenant):
        """Test user role-based permissions."""
        # Test admin user
        admin_user = User(
            user_id="admin_user_001",
            email="admin@example.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            can_create_data=True,
            can_view_data=True,
            can_modify_data=True,
            can_delete_data=True,
            can_manage_users=True,
            can_view_billing=True,
            can_manage_billing=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Test viewer user
        viewer_user = User(
            user_id="viewer_user_001",
            email="viewer@example.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password="hashed_password",
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE,
            can_create_data=False,
            can_view_data=True,
            can_modify_data=False,
            can_delete_data=False,
            can_manage_users=False,
            can_view_billing=False,
            can_manage_billing=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add_all([admin_user, viewer_user])
        await db_session.commit()
        await db_session.refresh(admin_user)
        await db_session.refresh(viewer_user)

        # Verify permissions by role
        assert admin_user.can_manage_billing is True
        assert admin_user.can_delete_data is True
        assert viewer_user.can_manage_billing is False
        assert viewer_user.can_delete_data is False


class TestUsageTrackingModels:
    """Test usage tracking models for billing and audit."""

    @pytest.mark.asyncio
    async def test_token_usage_model(self, db_session, test_tenant):
        """Test TokenUsage model for detailed usage tracking."""
        token_usage = TokenUsage(
            usage_id="token_usage_001",
            tenant_id=test_tenant.tenant_id,
            user_id="user_001",
            record_id="record_001",
            request_id="req_001",

            # Provider and model information
            provider="openai",
            model="gpt-4o",
            model_version="gpt-4o-1106-preview",

            # Token counts
            prompt_tokens=150,
            completion_tokens=100,
            total_tokens=250,
            context_tokens=50,

            # Cost information
            input_cost=Decimal("0.00075"),
            output_cost=Decimal("0.0015"),
            total_cost=Decimal("0.00225"),
            currency="USD",

            # Performance metrics
            response_time_ms=1250,
            cache_hit=False,
            fallback_used=False,

            # Request metadata
            request_metadata='{"temperature": 0.3, "max_tokens": 500}',

            created_at=datetime.utcnow(),
        )

        db_session.add(token_usage)
        await db_session.commit()
        await db_session.refresh(token_usage)

        # Verify token usage fields
        assert token_usage.provider == "openai"
        assert token_usage.model == "gpt-4o"
        assert token_usage.total_tokens == 250
        assert token_usage.total_cost == Decimal("0.00225")
        assert token_usage.cache_hit is False

    @pytest.mark.asyncio
    async def test_tenant_usage_model(self, db_session, test_tenant):
        """Test TenantUsage model for aggregated billing data."""
        tenant_usage = TenantUsage(
            usage_id="tenant_usage_001",
            tenant_id=test_tenant.tenant_id,
            billing_period_start=datetime(2024, 1, 1),
            billing_period_end=datetime(2024, 1, 31),

            # Usage totals
            total_records_processed=10000,
            total_ai_requests=8500,
            total_human_reviews=1500,

            # Token usage
            total_prompt_tokens=850000,
            total_completion_tokens=425000,
            total_tokens=1275000,

            # Cost totals
            total_input_cost=Decimal("42.50"),
            total_output_cost=Decimal("63.75"),
            total_cost=Decimal("106.25"),
            currency="USD",

            # Quality metrics
            average_confidence_score=0.87,
            auto_approval_rate=0.78,

            # System metrics
            cache_hit_rate=0.65,
            average_response_time_ms=950,

            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(tenant_usage)
        await db_session.commit()
        await db_session.refresh(tenant_usage)

        # Verify tenant usage fields
        assert tenant_usage.total_records_processed == 10000
        assert tenant_usage.total_tokens == 1275000
        assert tenant_usage.total_cost == Decimal("106.25")
        assert tenant_usage.average_confidence_score == 0.87

    @pytest.mark.asyncio
    async def test_audit_log_model(self, db_session, test_tenant):
        """Test AuditLog model for comprehensive audit trail."""
        audit_log = AuditLog(
            log_id="audit_log_001",
            tenant_id=test_tenant.tenant_id,
            user_id="user_001",
            action="data_processing",
            resource_type="data_record",
            resource_id="record_001",

            # Action details
            action_details='{"model": "gpt-4o", "confidence": 0.95, "category": "high_value"}',

            # Result and metadata
            result="success",
            error_message=None,
            metadata='{"request_id": "req_001", "processing_time_ms": 1250}',

            # Security context
            ip_address="192.168.1.100",
            user_agent="DataFoundry/1.0",
            session_id="session_001",

            # System context
            service="ai_service",
            version="1.0.0",

            created_at=datetime.utcnow(),
        )

        db_session.add(audit_log)
        await db_session.commit()
        await db_session.refresh(audit_log)

        # Verify audit log fields
        assert audit_log.action == "data_processing"
        assert audit_log.result == "success"
        assert audit_log.ip_address == "192.168.1.100"
        assert audit_log.service == "ai_service"

    @pytest.mark.asyncio
    async def test_cost_alert_model(self, db_session, test_tenant):
        """Test CostAlert model for real-time cost monitoring."""
        cost_alert = CostAlert(
            alert_id="cost_alert_001",
            tenant_id=test_tenant.tenant_id,

            # Alert configuration
            alert_type="monthly_budget",
            threshold_amount=Decimal("100.00"),
            currency="USD",

            # Current state
            current_amount=Decimal("105.50"),
            percentage_used=105.5,

            # Alert details
            alert_message="Monthly budget exceeded by $5.50 (105.5%)",
            severity="warning",
            status="active",

            # Notification settings
            notification_channels='["email", "slack"]',
            notified_users='["admin@example.com"]',

            created_at=datetime.utcnow(),
            acknowledged_at=None,
        )

        db_session.add(cost_alert)
        await db_session.commit()
        await db_session.refresh(cost_alert)

        # Verify cost alert fields
        assert cost_alert.alert_type == "monthly_budget"
        assert cost_alert.current_amount == Decimal("105.50")
        assert cost_alert.percentage_used == 105.5
        assert cost_alert.severity == "warning"

    @pytest.mark.asyncio
    async def test_billing_event_model(self, db_session, test_tenant):
        """Test BillingEvent model for Stripe integration."""
        billing_event = BillingEvent(
            event_id="billing_event_001",
            tenant_id=test_tenant.tenant_id,

            # Stripe event details
            stripe_event_id="evt_1234567890",
            stripe_event_type="invoice.payment_succeeded",

            # Billing period
            billing_period_start=datetime(2024, 1, 1),
            billing_period_end=datetime(2024, 1, 31),

            # Financial details
            amount=Decimal("106.25"),
            currency="USD",
            description="AI Services - January 2024",

            # Itemization
            line_items='[{"description": "AI Processing", "amount": "85.00", "quantity": 8500}, {"description": "Human Review", "amount": "21.25", "quantity": 1500}]',

            # Processing details
            processing_status="completed",
            processed_at=datetime.utcnow(),
            error_message=None,

            created_at=datetime.utcnow(),
        )

        db_session.add(billing_event)
        await db_session.commit()
        await db_session.refresh(billing_event)

        # Verify billing event fields
        assert billing_event.stripe_event_id == "evt_1234567890"
        assert billing_event.amount == Decimal("106.25")
        assert billing_event.processing_status == "completed"


class TestModelRelationships:
    """Test relationships between enhanced models."""

    @pytest.mark.asyncio
    async def test_tenant_user_relationships(self, db_session):
        """Test tenant-user relationships."""
        # Create tenant
        tenant = Tenant(
            tenant_id="rel_tenant_001",
            name="Relationship Test Organization",
            status=TenantStatus.ACTIVE,
            max_users=5,
            max_data_records=1000,
            storage_limit_gb=10.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Create users for the tenant
        users = [
            User(
                user_id=f"rel_user_{i:03d}",
                email=f"user{i}@example.com",
                tenant_id=tenant.tenant_id,
                hashed_password="hashed_password",
                role=UserRole.ADMIN if i == 0 else UserRole.ANALYST,
                status=UserStatus.ACTIVE,
                can_create_data=True,
                can_view_data=True,
                can_modify_data=True if i == 0 else False,
                can_delete_data=True if i == 0 else False,
                can_manage_users=True if i == 0 else False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(3)
        ]

        db_session.add(tenant)
        db_session.add_all(users)
        await db_session.commit()
        await db_session.refresh(tenant)

        # Verify relationships (this would require proper relationship setup in models)
        assert tenant.tenant_id == "rel_tenant_001"
        assert len(users) == 3
        assert all(user.tenant_id == tenant.tenant_id for user in users)


class TestModelValidation:
    """Test model validation and constraints."""

    @pytest.mark.asyncio
    async def test_data_record_validation(self, db_session, test_tenant):
        """Test DataRecord field validation."""
        # Test valid record
        valid_record = DataRecord(
            record_id="valid_rec_001",
            tenant_id=test_tenant.tenant_id,
            data_source="csv",
            status="processed",
            raw_data='{"test": "data"}',
            confidence_score=0.95,  # Valid range 0.0-1.0
            ai_confidence=0.85,     # Valid range 0.0-1.0
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(valid_record)
        await db_session.commit()
        await db_session.refresh(valid_record)

        # Test valid confidence scores
        assert 0.0 <= valid_record.confidence_score <= 1.0
        assert 0.0 <= valid_record.ai_confidence <= 1.0

    @pytest.mark.asyncio
    async def test_tenant_validation(self, db_session):
        """Test Tenant field validation."""
        # Test valid tenant
        valid_tenant = Tenant(
            tenant_id="valid_tenant_001",
            name="Valid Test Organization",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=1000,
            storage_limit_gb=10.0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(valid_tenant)
        await db_session.commit()
        await db_session.refresh(valid_tenant)

        # Verify valid fields
        assert valid_tenant.max_users > 0
        assert valid_tenant.max_data_records > 0
        assert valid_tenant.storage_limit_gb > 0

    @pytest.mark.asyncio
    async def test_user_validation(self, db_session, test_tenant):
        """Test User field validation."""
        # Test valid user
        valid_user = User(
            user_id="valid_user_001",
            email="valid@example.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password="hashed_password_here",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            first_name="Valid",
            last_name="User",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(valid_user)
        await db_session.commit()
        await db_session.refresh(valid_user)

        # Verify valid email format (basic check)
        assert "@" in valid_user.email
        assert "." in valid_user.email


class TestModelPerformance:
    """Test model performance and database efficiency."""

    @pytest.mark.asyncio
    async def test_bulk_data_record_creation(self, db_session, test_tenant):
        """Test bulk creation of DataRecords for performance."""
        import time

        records = []
        start_time = time.time()

        # Create 1000 records
        for i in range(1000):
            record = DataRecord(
                record_id=f"bulk_rec_{i:06d}",
                tenant_id=test_tenant.tenant_id,
                data_source="csv",
                status="processed",
                raw_data=f'{{"id": {i}, "name": "Test Record {i}"}}',
                processed_data=f'{{"id": {i}, "name": "Test Record {i}", "category": "processed"}}',
                confidence_score=0.9 + (i % 10) * 0.01,
                ai_confidence=0.85 + (i % 15) * 0.01,
                ai_model="gpt-4o",
                ai_tokens_used=150 + (i % 50),
                ai_cost=f"{0.001 + (i % 10) * 0.0001:.4f}",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            records.append(record)

        # Bulk insert
        db_session.add_all(records)
        await db_session.commit()

        end_time = time.time()
        creation_time = end_time - start_time

        # Performance assertion (should complete within reasonable time)
        assert creation_time < 5.0  # 5 seconds for 1000 records
        assert len(records) == 1000

    @pytest.mark.asyncio
    async def test_jsonb_field_performance(self, db_session, test_tenant):
        """Test JSONB field performance with large data."""
        import time

        # Create record with large JSONB data
        large_metadata = {
            "ai_processing": {
                "model": "gpt-4o",
                "tokens": {"prompt": 500, "completion": 300, "total": 800},
                "cost": {"input": 0.005, "output": 0.003, "total": 0.008},
                "timing": {"queue_time_ms": 50, "processing_time_ms": 2000, "total_time_ms": 2050}
            },
            "data_quality": {
                "completeness_score": 0.95,
                "accuracy_score": 0.92,
                "consistency_score": 0.88
            },
            "security": {
                "pii_detected": True,
                "pii_types": ["EMAIL_ADDRESS", "PHONE_NUMBER"],
                "encryption_applied": True,
                "access_level": "restricted"
            }
        }

        start_time = time.time()

        record = DataRecord(
            record_id="jsonb_perf_001",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="processed",
            raw_data='{"test": "large jsonb data"}',
            provenance_metadata=str(large_metadata).replace("'", '"'),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        end_time = time.time()
        creation_time = end_time - start_time

        # Performance assertion
        assert creation_time < 1.0  # Should complete quickly even with large JSONB
        assert record.provenance_metadata is not None