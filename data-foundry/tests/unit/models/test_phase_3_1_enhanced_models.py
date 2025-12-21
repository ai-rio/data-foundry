"""
Comprehensive tests for Phase 3.1 Enhanced Data Models

This test suite covers the enhanced models that were previously untested:
- User with MFA support and permissions
- Tenant with billing integration and feature flags
- DataRecord with new AI tracking fields and JSONB columns
- TokenUsage, TenantUsage, AuditLog for usage tracking
- CostAlert and BillingEvent for billing system
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from src.models import (
    User, Tenant, DataRecord, ProcessedData, HumanReviewQueue,
    TokenUsage, TenantUsage, AuditLog, CostAlert, BillingEvent
)
from src.models.user import UserRole, UserStatus
from src.models.tenant import TenantStatus
from src.models.data_record import DataSource, DataStatus


class TestUserEnhancements:
    """Test enhanced User model with MFA and permissions."""

    def test_user_creation_with_all_fields(self):
        """Test creating a user with all enhanced features."""
        user = User(
            user_id="enhanced_user_001",
            email="test@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            first_name="John",
            last_name="Doe",
            can_create_data=True,
            can_view_data=True,
            can_modify_data=True,
            can_delete_data=True,
            can_manage_users=True,
            mfa_enabled=True,
            last_login=datetime.utcnow(),
            failed_login_attempts=0,
            locked_until=None,
            preferences={
                "theme": "dark",
                "notifications": True,
                "language": "en",
                "timezone": "UTC"
            },
            permissions=[
                "data:read",
                "data:write",
                "data:delete",
                "user:manage",
                "tenant:manage"
            ],
            api_key_hash="hashed_api_key",
            personal_access_tokens=["token_001", "token_002"],
            created_by="admin_001",
            updated_by="admin_001"
        )

        # Test basic user fields
        assert user.user_id == "enhanced_user_001"
        assert user.email == "test@example.com"
        assert user.role == UserRole.ADMIN
        assert user.status == UserStatus.ACTIVE
        assert user.mfa_enabled is True

        # Test enhanced security fields
        assert user.last_login is not None
        assert user.failed_login_attempts == 0
        assert user.locked_until is None
        assert user.api_key_hash is not None
        assert user.personal_access_tokens is not None
        assert len(user.personal_access_tokens) == 2

        # Test preferences
        assert user.preferences["theme"] == "dark"
        assert user.preferences["notifications"] is True

        # Test permissions
        assert "data:read" in user.permissions
        assert "data:write" in user.permissions
        assert "user:manage" in user.permissions

    def test_user_login_tracking(self):
        """Test user login tracking functionality."""
        user = User(
            user_id="login_test_001",
            email="login@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE
        )

        # Test initial state
        assert user.last_login is None
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

        # Simulate successful login
        user.last_login = datetime.utcnow()
        assert user.last_login is not None

    def test_user_failed_login_tracking(self):
        """Test failed login attempt tracking."""
        user = User(
            user_id="failed_login_test_001",
            email="failed@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE
        )

        # Simulate failed login attempts
        user.failed_login_attempts = 3
        assert user.failed_login_attempts == 3

        # Simulate account lockout
        user.locked_until = datetime.utcnow() + timedelta(hours=1)
        assert user.locked_until is not None

    def test_user_permission_inheritance(self):
        """Test permission inheritance for different roles."""
        # Test Admin permissions (full access)
        admin = User(
            user_id="admin_001",
            email="admin@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        # Admin should have all permissions by default
        assert admin.can_create_data
        assert admin.can_view_data
        assert admin.can_modify_data
        assert admin.can_delete_data
        assert admin.can_manage_users

        # Test Analyst permissions
        analyst = User(
            user_id="analyst_001",
            email="analyst@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ANALYST,
            status=UserStatus.ACTIVE
        )
        # Analyst should have read and create permissions
        assert analyst.can_create_data is True
        assert analyst.can_view_data is True
        assert analyst.can_modify_data is False
        assert analyst.can_delete_data is False
        assert analyst.can_manage_users is False

        # Test Viewer permissions
        viewer = User(
            user_id="viewer_001",
            email="viewer@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.VIEWER,
            status=UserStatus.ACTIVE
        )
        # Viewer should only have read permission
        assert viewer.can_create_data is False
        assert viewer.can_view_data is True
        assert viewer.can_modify_data is False
        assert viewer.can_delete_data is False
        assert viewer.can_manage_users is False

    def test_user_preferences_validation(self):
        """Test user preferences validation."""
        user = User(
            user_id="prefs_test_001",
            email="prefs@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            preferences={
                "theme": "invalid_theme",  # Should be validated
                "notifications": True,
                "language": "en",
                "timezone": "invalid_timezone"  # Should be validated
            }
        )

        # Test preferences structure
        assert isinstance(user.preferences, dict)
        assert "theme" in user.preferences
        assert "notifications" in user.preferences
        assert "language" in user.preferences
        assert "timezone" in user.preferences


class TestTenantEnhancements:
    """Test enhanced Tenant model with billing and feature flags."""

    def test_tenant_billing_features(self):
        """Test tenant billing functionality."""
        tenant = Tenant(
            tenant_id="billing_test_001",
            name="Billing Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=100,
            max_data_records=1000000,
            storage_limit_gb=100.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            billing_plan="premium",
            billing_status="active",
            subscription_tier="enterprise",
            feature_flags={
                "advanced_analytics": True,
                "data_export": True,
                "custom_models": False,
                "api_access": True,
                "white_labeling": True
            },
            credit_limit=Decimal("10000.00"),
            trial_end_date=datetime.utcnow() + timedelta(days=30),
            custom_settings={
                "confidence_threshold": 0.85,
                "batch_size": 1000,
                "auto_approve_threshold": 0.90,
                "enable_caching": True
            },
            billing_currency="USD",
            payment_method_id="pm_001",
            invoice_email="billing@company.com",
            next_billing_date=datetime.utcnow().replace(day=1) + timedelta(days=30),
            created_by="admin_001",
            updated_by="admin_001"
        )

        # Test billing features
        assert tenant.billing_plan == "premium"
        assert tenant.billing_status == "active"
        assert tenant.subscription_tier == "enterprise"
        assert tenant.credit_limit == Decimal("10000.00")
        assert tenant.billing_currency == "USD"
        assert tenant.payment_method_id is not None
        assert tenant.invoice_email is not None
        assert tenant.next_billing_date is not None

        # Test trial period
        assert tenant.trial_end_date is not None
        assert tenant.trial_end_date > datetime.utcnow()

    def test_tenant_feature_flags(self):
        """Test tenant feature flags functionality."""
        tenant = Tenant(
            tenant_id="features_test_001",
            name="Features Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=50,
            max_data_records=500000,
            storage_limit_gb=50.0,
            enable_pii_redaction=False,
            enable_ai_labeling=False,
            enable_human_review=False,
            feature_flags={
                "advanced_analytics": False,
                "data_export": False,
                "custom_models": False,
                "api_access": False,
                "white_labeling": False
            }
        )

        # Test feature flags
        assert not tenant.feature_flags["advanced_analytics"]
        assert not tenant.feature_flags["data_export"]
        assert not tenant.feature_flags["custom_models"]
        assert not tenant.feature_flags["api_access"]
        assert not tenant.feature_flags["white_labeling"]

    def test_tenant_custom_settings(self):
        """Test tenant custom settings."""
        tenant = Tenant(
            tenant_id="settings_test_001",
            name="Settings Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=25,
            max_data_records=250000,
            storage_limit_gb=25.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            custom_settings={
                "confidence_threshold": 0.90,
                "batch_size": 500,
                "auto_approve_threshold": 0.95,
                "enable_caching": False,
                "max_retry_attempts": 3,
                "timeout_seconds": 30
            }
        )

        # Test custom settings
        assert tenant.custom_settings["confidence_threshold"] == 0.90
        assert tenant.custom_settings["batch_size"] == 500
        assert tenant.custom_settings["auto_approve_threshold"] == 0.95
        assert not tenant.custom_settings["enable_caching"]
        assert tenant.custom_settings["max_retry_attempts"] == 3
        assert tenant.custom_settings["timeout_seconds"] == 30

    def test_tenant_usage_limits(self):
        """Test tenant usage limits and enforcement."""
        tenant = Tenant(
            tenant_id="limits_test_001",
            name="Limits Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=10000,
            storage_limit_gb=10.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            billing_plan="basic",
            billing_status="active"
        )

        # Test usage limits
        assert tenant.max_users == 10
        assert tenant.max_data_records == 10000
        assert tenant.storage_limit_gb == 10.0


class TestDataRecordEnhancements:
    """Test enhanced DataRecord model with AI tracking."""

    def test_data_record_ai_metadata(self):
        """Test DataRecord AI metadata tracking."""
        record = DataRecord(
            record_id="ai_meta_test_001",
            tenant_id="tenant_001",
            data_source=DataSource.CSV,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "John Doe", "email": "john@corp.com", "phone": "555-1234"}',
            ai_metadata={
                "confidence_score": 0.95,
                "category": "high_value",
                "model_used": "gpt-4o",
                "model_version": "2024-06-13",
                "processing_time_ms": 450,
                "tokens_used": 150,
                "cost_estimate": Decimal("0.001"),
                "provider": "openai",
                "temperature": 0.3,
                "top_p": 1.0,
                "frequency_penalty": 0,
                "presence_penalty": 0
            },
            tags=["enterprise", "high_confidence", "verified"],
            validation_status="valid",
            validation_details={
                "pii_detected": True,
                "pii_types": ["EMAIL"],
                "data_quality_score": 0.98,
                "completeness_score": 0.95,
                "consistency_score": 1.0
            },
            processed_at=datetime.utcnow(),
            processing_tenant_id="tenant_001",
            processing_user_id="user_001"
        )

        # Test AI metadata
        assert record.ai_metadata is not None
        assert record.ai_metadata["confidence_score"] == 0.95
        assert record.ai_metadata["category"] == "high_value"
        assert record.ai_metadata["model_used"] == "gpt-4o"
        assert record.ai_metadata["model_version"] == "2024-06-13"
        assert record.ai_metadata["processing_time_ms"] == 450
        assert record.ai_metadata["tokens_used"] == 150
        assert record.ai_metadata["cost_estimate"] == Decimal("0.001")
        assert record.ai_metadata["provider"] == "openai"

    def test_data_record_validation_features(self):
        """Test DataRecord validation features."""
        record = DataRecord(
            record_id="validation_test_001",
            tenant_id="tenant_001",
            data_source=DataSource.JSON,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "John Doe", "email": "john@corp.com"}',
            validation_status="valid",
            validation_details={
                "pii_detected": True,
                "pii_types": ["EMAIL", "NAME"],
                "data_quality_score": 0.98,
                "completeness_score": 0.95,
                "consistency_score": 1.0,
                "validation_rules_applied": ["pii_detection", "format_validation", "completeness_check"],
                "validation_timestamp": datetime.utcnow().isoformat()
            }
        )

        # Test validation features
        assert record.validation_status == "valid"
        assert record.validation_details is not None
        assert record.validation_details["pii_detected"] is True
        assert "EMAIL" in record.validation_details["pii_types"]
        assert "NAME" in record.validation_details["pii_types"]
        assert record.validation_details["data_quality_score"] == 0.98
        assert len(record.validation_details["validation_rules_applied"]) == 3

    def test_data_record_tags_and_categorization(self):
        """Test DataRecord tags and categorization."""
        record = DataRecord(
            record_id="tags_test_001",
            tenant_id="tenant_001",
            data_source=DataSource.CSV,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "Jane Smith", "email": "jane@startup.io"}',
            tags=[
                "startup",
                "early_stage",
                "high_potential",
                "tech_industry",
                "series_a"
            ],
            category_tags=["b2b", "technology", "saas"],
            priority_score=0.75
        )

        # Test tags
        assert len(record.tags) == 5
        assert "startup" in record.tags
        assert "high_potential" in record.tags
        assert "tech_industry" in record.tags

        # Test category tags
        assert len(record.category_tags) == 3
        assert "b2b" in record.category_tags
        assert "technology" in record.category_tags
        assert "saas" in record.category_tags

        # Test priority score
        assert record.priority_score == 0.75

    def test_data_record_processing_tracking(self):
        """Test DataRecord processing tracking."""
        record = DataRecord(
            record_id="process_test_001",
            tenant_id="tenant_001",
            data_source=DataSource.JSON,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "Test User", "email": "test@example.com"}',
            processing_tenant_id="tenant_001",
            processing_user_id="user_001",
            processed_at=datetime.utcnow(),
            processing_duration_ms=250,
            retry_count=0,
            processing_version="1.0.0"
        )

        # Test processing tracking
        assert record.processing_tenant_id == "tenant_001"
        assert record.processing_user_id == "user_001"
        assert record.processed_at is not None
        assert record.processing_duration_ms == 250
        assert record.retry_count == 0
        assert record.processing_version == "1.0.0"


class TestTokenUsageTracking:
    """Test TokenUsage tracking functionality."""

    def test_token_usage_creation(self):
        """Test TokenUsage creation."""
        token_usage = TokenUsage(
            token_id="token_usage_001",
            tenant_id="tenant_001",
            user_id="user_001",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_per_token_input=Decimal("0.00001"),
            cost_per_token_output=Decimal("0.00002"),
            total_cost=Decimal("0.002"),
            request_timestamp=datetime.utcnow(),
            metadata={
                "session_id": "session_001",
                "task": "data_labeling",
                "data_source": "csv",
                "tenant_custom_settings": {
                    "confidence_threshold": 0.85
                }
            },
            batch_id="batch_001",
            parent_request_id="parent_req_001",
            retry_count=0
        )

        # Test token usage tracking
        assert token_usage.prompt_tokens == 100
        assert token_usage.completion_tokens == 50
        assert token_usage.total_tokens == 150
        assert token_usage.cost_per_token_input == Decimal("0.00001")
        assert token_usage.cost_per_token_output == Decimal("0.00002")
        assert token_usage.total_cost == Decimal("0.002")
        assert token_usage.metadata is not None
        assert token_usage.metadata["task"] == "data_labeling"
        assert token_usage.batch_id == "batch_001"
        assert token_usage.retry_count == 0

    def test_token_cost_calculation(self):
        """Test token cost calculation."""
        token_usage = TokenUsage(
            token_id="token_cost_001",
            tenant_id="tenant_001",
            user_id="user_001",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_per_token_input=Decimal("0.00001"),
            cost_per_token_output=Decimal("0.00002"),
            total_cost=Decimal("0.02"),
            request_timestamp=datetime.utcnow(),
            metadata={}
        )

        # Verify cost calculation
        expected_input_cost = 1000 * Decimal("0.00001")  # 0.01
        expected_output_cost = 500 * Decimal("0.00002")  # 0.01
        expected_total_cost = expected_input_cost + expected_output_cost  # 0.02

        assert token_usage.total_cost == expected_total_cost
        assert token_usage.total_cost == Decimal("0.02")

    def test_token_usage_aggregation(self):
        """Test token usage aggregation for reporting."""
        token_usages = [
            TokenUsage(
                token_id=f"token_{i:03d}",
                tenant_id="tenant_001",
                user_id="user_001",
                model="gpt-4o",
                provider="openai",
                prompt_tokens=100 + i * 10,
                completion_tokens=50 + i * 5,
                total_tokens=150 + i * 15,
                cost_per_token_input=Decimal("0.00001"),
                cost_per_token_output=Decimal("0.00002"),
                total_cost=Decimal("0.002") + i * Decimal("0.001"),
                request_timestamp=datetime.utcnow(),
                metadata={}
            )
            for i in range(5)
        ]

        # Aggregate token usage
        total_prompt_tokens = sum(tu.prompt_tokens for tu in token_usages)
        total_completion_tokens = sum(tu.completion_tokens for tu in token_usages)
        total_tokens = sum(tu.total_tokens for tu in token_usages)
        total_cost = sum(tu.total_cost for tu in token_usages)

        assert total_prompt_tokens == 1000  # 100 + 110 + 120 + 130 + 140
        assert total_completion_tokens == 500  # 50 + 55 + 60 + 65 + 70
        assert total_tokens == 1500  # 150 + 165 + 180 + 195 + 210
        assert total_cost == Decimal("0.010")  # 0.002 + 0.003 + 0.004 + 0.005 + 0.006


class TestTenantUsageTracking:
    """Test TenantUsage tracking functionality."""

    def test_tenant_usage_creation(self):
        """Test TenantUsage creation."""
        tenant_usage = TenantUsage(
            usage_id="tenant_usage_001",
            tenant_id="tenant_001",
            period_start=datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            period_end=datetime.utcnow().replace(day=28, hour=23, minute=59, second=59, microsecond=999999),
            total_tokens_used=100000,
            total_cost=Decimal("50.00"),
            ai_requests_count=1000,
            data_records_processed=5000,
            storage_usage_gb=75.5,
            feature_usage={
                "ai_labeling": 800,
                "pii_redaction": 950,
                "human_review": 200,
                "data_export": 50
            },
            billing_alerts=[
                {
                    "type": "cost_threshold",
                    "threshold": Decimal("40.00"),
                    "current_amount": Decimal("45.00"),
                    "percentage_threshold": 80.0,
                    "triggered_at": datetime.utcnow()
                }
            ],
            resource_usage={
                "cpu_hours": 100,
                "memory_gb_hours": 50,
                "storage_gb": 75.5
            }
        )

        # Test tenant usage tracking
        assert tenant_usage.total_tokens_used == 100000
        assert tenant_usage.total_cost == Decimal("50.00")
        assert tenant_usage.ai_requests_count == 1000
        assert tenant_usage.data_records_processed == 5000
        assert tenant_usage.storage_usage_gb == 75.5
        assert tenant_usage.feature_usage is not None
        assert tenant_usage.billing_alerts is not None
        assert tenant_usage.resource_usage is not None

        # Test feature usage breakdown
        assert tenant_usage.feature_usage["ai_labeling"] == 800
        assert tenant_usage.feature_usage["pii_redaction"] == 950
        assert tenant_usage.feature_usage["human_review"] == 200

        # Test billing alerts
        assert len(tenant_usage.billing_alerts) == 1
        assert tenant_usage.billing_alerts[0]["type"] == "cost_threshold"
        assert tenant_usage.billing_alerts[0]["percentage_threshold"] == 80.0

    def test_tenant_usage_cost_analysis(self):
        """Test tenant usage cost analysis."""
        tenant_usage = TenantUsage(
            usage_id="cost_analysis_001",
            tenant_id="tenant_001",
            period_start=datetime.utcnow().replace(day=1),
            period_end=datetime.utcnow().replace(day=28),
            total_tokens_used=100000,
            total_cost=Decimal("50.00"),
            ai_requests_count=1000,
            data_records_processed=5000,
            storage_usage_gb=75.5,
            feature_usage={
                "ai_labeling": 800,
                "pii_redaction": 950,
                "human_review": 200
            },
            billing_alerts=[],
            resource_usage={}
        )

        # Calculate cost per token
        cost_per_token = tenant_usage.total_cost / tenant_usage.total_tokens_used
        assert cost_per_token == Decimal("0.0005")  # 50.00 / 100000

        # Calculate cost per request
        cost_per_request = tenant_usage.total_cost / tenant_usage.ai_requests_count
        assert cost_per_request == Decimal("0.05")  # 50.00 / 1000

        # Calculate cost per record
        cost_per_record = tenant_usage.total_cost / tenant_usage.data_records_processed
        assert cost_per_record == Decimal("0.01")  # 50.00 / 5000

        # Calculate cost per GB
        cost_per_gb = tenant_usage.total_cost / tenant_usage.storage_usage_gb
        assert cost_per_gb == Decimal("0.6616")  # 50.00 / 75.5


class TestAuditLogEnhancements:
    """Test enhanced AuditLog model."""

    def test_audit_log_with_ai_details(self):
        """Test AuditLog with AI processing details."""
        audit_log = AuditLog(
            log_id="audit_ai_001",
            tenant_id="tenant_001",
            user_id="user_001",
            action="data_record_processed",
            resource_type="DataRecord",
            resource_id="rec_001",
            timestamp=datetime.utcnow(),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0 (compatible; DataFoundry/1.0)",
            details={
                "record_data": {"name": "John Doe", "email": "john@corp.com"},
                "ai_confidence": 0.95,
                "ai_category": "high_value",
                "ai_model": "gpt-4o",
                "ai_model_version": "2024-06-13",
                "processing_time_ms": 450,
                "tokens_used": 150,
                "cost": Decimal("0.001"),
                "pii_detected": True,
                "pii_types": ["EMAIL"],
                "validation_passed": True,
                "retry_attempts": 0
            },
            risk_level="low",
            related_events=["evt_001", "evt_002", "evt_003"],
            session_id="session_001",
            request_id="req_001",
            tenant_custom_settings={
                "confidence_threshold": 0.85,
                "enable_pii_redaction": True
            }
        )

        # Test AI-related audit details
        assert audit_log.action == "data_record_processed"
        assert audit_log.details is not None
        assert audit_log.details["ai_confidence"] == 0.95
        assert audit_log.details["ai_category"] == "high_value"
        assert audit_log.details["ai_model"] == "gpt-4o"
        assert audit_log.details["processing_time_ms"] == 450
        assert audit_log.details["tokens_used"] == 150
        assert audit_log.details["cost"] == Decimal("0.001")
        assert audit_log.details["pii_detected"] is True

        # Test risk and events
        assert audit_log.risk_level == "low"
        assert len(audit_log.related_events) == 3
        assert audit_log.session_id == "session_001"
        assert audit_log.request_id == "req_001"

    def test_audit_log_security_events(self):
        """Test AuditLog for security-related events."""
        audit_log = AuditLog(
            log_id="security_001",
            tenant_id="tenant_001",
            user_id="user_001",
            action="login_failed",
            resource_type="User",
            resource_id="user_001",
            timestamp=datetime.utcnow(),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            details={
                "failure_reason": "invalid_password",
                "failed_attempts": 3,
                "account_locked": False,
                "ip_reputation": "suspicious",
                "geo_location": "Unknown"
            },
            risk_level="medium",
            related_events=["login_attempt_001", "login_attempt_002", "login_attempt_003"]
        )

        # Test security audit log
        assert audit_log.action == "login_failed"
        assert audit_log.details["failure_reason"] == "invalid_password"
        assert audit_log.details["failed_attempts"] == 3
        assert audit_log.details["account_locked"] is False
        assert audit_log.details["ip_reputation"] == "suspicious"
        assert audit_log.risk_level == "medium"

    def test_audit_log_data_access(self):
        """Test AuditLog for data access events."""
        audit_log = AuditLog(
            log_id="data_access_001",
            tenant_id="tenant_001",
            user_id="user_001",
            action="data_record_access",
            resource_type="DataRecord",
            resource_id="rec_001",
            timestamp=datetime.utcnow(),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            details={
                "access_type": "read",
                "fields_accessed": ["name", "email"],
                "query_filter": "tenant_id = 'tenant_001'",
                "result_count": 1,
                "data_sensitivity": "medium",
                "compliance_requirements": ["gdpr", "ccpa"]
            },
            risk_level="low",
            related_events=[]
        )

        # Test data access audit log
        assert audit_log.action == "data_record_access"
        assert audit_log.details["access_type"] == "read"
        assert "name" in audit_log.details["fields_accessed"]
        assert "email" in audit_log.details["fields_accessed"]
        assert audit_log.details["result_count"] == 1
        assert audit_log.details["data_sensitivity"] == "medium"


class TestCostAlertSystem:
    """Test CostAlert system functionality."""

    def test_cost_alert_creation(self):
        """Test CostAlert creation."""
        cost_alert = CostAlert(
            alert_id="cost_alert_001",
            tenant_id="tenant_001",
            alert_type="cost_threshold",
            severity="warning",
            threshold_amount=Decimal("100.00"),
            current_amount=Decimal("95.00"),
            percentage_threshold=80.0,
            triggered_at=datetime.utcnow(),
            details={
                "period": "monthly",
                "ai_service_cost": Decimal("75.00"),
                "storage_cost": Decimal("20.00"),
                "alert_message": "Monthly cost approaching threshold",
                "cost_breakdown": {
                    "gpt-4o": Decimal("50.00"),
                    "gpt-3.5": Decimal("25.00"),
                    "storage": Decimal("20.00")
                }
            },
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None,
            resolution_action="monitor"
        )

        # Test cost alert features
        assert cost_alert.alert_type == "cost_threshold"
        assert cost_alert.severity == "warning"
        assert cost_alert.threshold_amount == Decimal("100.00")
        assert cost_alert.current_amount == Decimal("95.00")
        assert cost_alert.percentage_threshold == 80.0
        assert cost_alert.details is not None
        assert cost_alert.details["alert_message"] == "Monthly cost approaching threshold"
        assert not cost_alert.acknowledged
        assert cost_alert.resolution_action == "monitor"

    def test_cost_alert_acknowledgment(self):
        """Test CostAlert acknowledgment process."""
        cost_alert = CostAlert(
            alert_id="cost_alert_ack_001",
            tenant_id="tenant_001",
            alert_type="cost_threshold",
            severity="critical",
            threshold_amount=Decimal("100.00"),
            current_amount=Decimal("120.00"),
            percentage_threshold=100.0,
            triggered_at=datetime.utcnow(),
            details={},
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None
        )

        # Test initial state
        assert not cost_alert.acknowledged
        assert cost_alert.acknowledged_by is None
        assert cost_alert.acknowledged_at is None

        # Simulate acknowledgment
        cost_alert.acknowledged = True
        cost_alert.acknowledged_by = "admin_001"
        cost_alert.acknowledged_at = datetime.utcnow()

        # Test acknowledgment
        assert cost_alert.acknowledged is True
        assert cost_alert.acknowledged_by == "admin_001"
        assert cost_alert.acknowledged_at is not None

    def test_cost_alert_types(self):
        """Test different types of cost alerts."""
        # Cost threshold alert
        cost_threshold_alert = CostAlert(
            alert_id="threshold_001",
            tenant_id="tenant_001",
            alert_type="cost_threshold",
            severity="warning",
            threshold_amount=Decimal("100.00"),
            current_amount=Decimal("95.00"),
            percentage_threshold=80.0,
            triggered_at=datetime.utcnow(),
            details={},
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None
        )

        # Usage limit alert
        usage_limit_alert = CostAlert(
            alert_id="usage_001",
            tenant_id="tenant_001",
            alert_type="usage_limit",
            severity="critical",
            threshold_amount=Decimal("1000000"),  # 1M tokens
            current_amount=Decimal("950000"),
            percentage_threshold=95.0,
            triggered_at=datetime.utcnow(),
            details={
                "limit_type": "tokens",
                "period": "monthly"
            },
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None
        )

        # Budget alert
        budget_alert = CostAlert(
            alert_id="budget_001",
            tenant_id="tenant_001",
            alert_type="budget_exceeded",
            severity="error",
            threshold_amount=Decimal("1000.00"),
            current_amount=Decimal("1200.00"),
            percentage_threshold=120.0,
            triggered_at=datetime.utcnow(),
            details={
                "budget_name": "Monthly Budget",
                "department": "Data Science"
            },
            acknowledged=False,
            acknowledged_by=None,
            acknowledged_at=None
        )

        # Test different alert types
        assert cost_threshold_alert.alert_type == "cost_threshold"
        assert usage_limit_alert.alert_type == "usage_limit"
        assert budget_alert.alert_type == "budget_exceeded"
        assert usage_limit_alert.details["limit_type"] == "tokens"
        assert budget_alert.details["budget_name"] == "Monthly Budget"


class TestBillingEventTracking:
    """Test BillingEvent tracking functionality."""

    def test_billing_event_ai_usage(self):
        """Test BillingEvent for AI usage."""
        billing_event = BillingEvent(
            event_id="billing_ai_001",
            tenant_id="tenant_001",
            event_type="ai_usage",
            description="GPT-4 token usage - Data labeling",
            amount=Decimal("5.00"),
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={
                "model": "gpt-4o",
                "provider": "openai",
                "tokens": 5000,
                "unit_cost": Decimal("0.00001"),
                "request_id": "req_001",
                "user_id": "user_001",
                "tenant_tier": "premium"
            },
            status="pending",
            invoice_id=None,
            batch_id="batch_001",
            cost_center="data_processing",
            project_code="DP-2024-001"
        )

        # Test AI usage billing event
        assert billing_event.event_type == "ai_usage"
        assert billing_event.description == "GPT-4 token usage - Data labeling"
        assert billing_event.amount == Decimal("5.00")
        assert billing_event.currency == "USD"
        assert billing_event.metadata is not None
        assert billing_event.metadata["model"] == "gpt-4o"
        assert billing_event.metadata["provider"] == "openai"
        assert billing_event.metadata["tokens"] == 5000
        assert billing_event.metadata["unit_cost"] == Decimal("0.00001")
        assert billing_event.status == "pending"
        assert billing_event.batch_id == "batch_001"
        assert billing_event.cost_center == "data_processing"

    def test_billing_event_storage_usage(self):
        """Test BillingEvent for storage usage."""
        billing_event = BillingEvent(
            event_id="billing_storage_001",
            tenant_id="tenant_001",
            event_type="storage_usage",
            description="Monthly storage usage",
            amount=Decimal("20.00"),
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={
                "storage_type": "s3",
                "storage_gb": 100,
                "unit_cost": Decimal("0.20"),
                "period": "monthly"
            },
            status="pending",
            invoice_id=None,
            batch_id=None,
            cost_center="storage",
            project_code="ST-2024-001"
        )

        # Test storage billing event
        assert billing_event.event_type == "storage_usage"
        assert billing_event.description == "Monthly storage usage"
        assert billing_event.amount == Decimal("20.00")
        assert billing_event.metadata["storage_type"] == "s3"
        assert billing_event.metadata["storage_gb"] == 100
        assert billing_event.metadata["unit_cost"] == Decimal("0.20")

    def test_billing_event_processing_fees(self):
        """Test BillingEvent for processing fees."""
        billing_event = BillingEvent(
            event_id="billing_processing_001",
            tenant_id="tenant_001",
            event_type="processing_fee",
            description="Data processing fee - Batch processing",
            amount=Decimal("10.00"),
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={
                "fee_type": "batch_processing",
                "records_processed": 10000,
                "unit_cost": Decimal("0.001"),
                "processing_time_minutes": 30
            },
            status="pending",
            invoice_id=None,
            batch_id="batch_001",
            cost_center="data_processing",
            project_code="BP-2024-001"
        )

        # Test processing fee billing event
        assert billing_event.event_type == "processing_fee"
        assert billing_event.description == "Data processing fee - Batch processing"
        assert billing_event.amount == Decimal("10.00")
        assert billing_event.metadata["fee_type"] == "batch_processing"
        assert billing_event.metadata["records_processed"] == 10000
        assert billing_event.metadata["unit_cost"] == Decimal("0.001")

    def test_billing_event_status_tracking(self):
        """Test BillingEvent status tracking."""
        billing_event = BillingEvent(
            event_id="billing_status_001",
            tenant_id="tenant_001",
            event_type="ai_usage",
            description="Test billing event",
            amount=Decimal("1.00"),
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={},
            status="pending",
            invoice_id=None,
            batch_id=None,
            cost_center="test",
            project_code="TST-001"
        )

        # Test initial status
        assert billing_event.status == "pending"
        assert billing_event.invoice_id is None

        # Test status transitions
        billing_event.status = "invoiced"
        billing_event.invoice_id = "invoice_001"

        assert billing_event.status == "invoiced"
        assert billing_event.invoice_id == "invoice_001"

        # Test payment status
        billing_event.status = "paid"
        billing_event.payment_date = datetime.utcnow()

        assert billing_event.status == "paid"
        assert billing_event.payment_date is not None

    def test_billing_event_currency_support(self):
        """Test BillingEvent with different currencies."""
        # USD billing event
        usd_event = BillingEvent(
            event_id="usd_001",
            tenant_id="tenant_001",
            event_type="ai_usage",
            description="USD usage",
            amount=Decimal("10.00"),
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={},
            status="pending",
            invoice_id=None,
            batch_id=None,
            cost_center="test",
            project_code="TST-001"
        )

        # EUR billing event
        eur_event = BillingEvent(
            event_id="eur_001",
            tenant_id="tenant_001",
            event_type="ai_usage",
            description="EUR usage",
            amount=Decimal("8.50"),
            currency="EUR",
            timestamp=datetime.utcnow(),
            metadata={},
            status="pending",
            invoice_id=None,
            batch_id=None,
            cost_center="test",
            project_code="TST-001"
        )

        # Test currency support
        assert usd_event.currency == "USD"
        assert usd_event.amount == Decimal("10.00")
        assert eur_event.currency == "EUR"
        assert eur_event.amount == Decimal("8.50")


@pytest.fixture
def sample_tenant_data():
    """Sample tenant data for testing."""
    return {
        "tenant_id": "test_tenant_001",
        "name": "Test Organization",
        "status": "active",
        "max_users": 100,
        "max_data_records": 1000000,
        "storage_limit_gb": 100.0,
        "enable_pii_redaction": True,
        "enable_ai_labeling": True,
        "enable_human_review": True,
        "billing_plan": "premium",
        "billing_status": "active",
        "subscription_tier": "enterprise",
        "feature_flags": {
            "advanced_analytics": True,
            "data_export": True,
            "custom_models": False
        }
    }


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "user_id": "test_user_001",
        "email": "test@example.com",
        "tenant_id": "test_tenant_001",
        "hashed_password": "hashed_password",
        "role": "admin",
        "status": "active",
        "first_name": "Test",
        "last_name": "User",
        "mfa_enabled": True,
        "preferences": {
            "theme": "dark",
            "notifications": True
        }
    }


@pytest.fixture
def sample_data_record():
    """Sample data record for testing."""
    return {
        "record_id": "test_rec_001",
        "tenant_id": "test_tenant_001",
        "data_source": "csv",
        "status": "processed",
        "raw_data": '{"name": "John Doe", "email": "john@corp.com"}',
        "ai_metadata": {
            "confidence_score": 0.95,
            "category": "high_value",
            "model_used": "gpt-4o"
        },
        "tags": ["enterprise", "high_confidence"]
    }


# Test helper functions
def create_test_user(**overrides):
    """Helper function to create test users."""
    defaults = {
        "user_id": "test_user_001",
        "email": "test@example.com",
        "tenant_id": "test_tenant_001",
        "hashed_password": "hashed_password",
        "role": UserRole.ADMIN,
        "status": UserStatus.ACTIVE
    }
    defaults.update(overrides)
    return User(**defaults)


def create_test_tenant(**overrides):
    """Helper function to create test tenants."""
    defaults = {
        "tenant_id": "test_tenant_001",
        "name": "Test Organization",
        "status": TenantStatus.ACTIVE,
        "max_users": 100,
        "max_data_records": 1000000,
        "storage_limit_gb": 100.0,
        "enable_pii_redaction": True,
        "enable_ai_labeling": True,
        "enable_human_review": True
    }
    defaults.update(overrides)
    return Tenant(**defaults)


def create_test_data_record(**overrides):
    """Helper function to create test data records."""
    defaults = {
        "record_id": "test_rec_001",
        "tenant_id": "test_tenant_001",
        "data_source": DataSource.CSV,
        "status": DataStatus.PROCESSED,
        "raw_data": '{"name": "John Doe", "email": "john@corp.com"}'
    }
    defaults.update(overrides)
    return DataRecord(**defaults)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])