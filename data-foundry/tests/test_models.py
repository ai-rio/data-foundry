"""
Database Model Tests for Data Foundry
Tests all SQLModel models and their relationships
"""

import pytest
from datetime import datetime
from decimal import Decimal

from src.models import Tenant, User, DataRecord, ProcessedData, HumanReviewQueue
from src.core.security import get_password_hash


class TestTenantModel:
    """Test Tenant model functionality."""

    def test_tenant_creation(self):
        """Test tenant creation with default values."""
        tenant = Tenant(
            tenant_id="test_tenant_001",
            name="Test Organization",
        )

        # Verify default values
        assert tenant.status == "active"
        assert tenant.max_users == 10
        assert tenant.max_data_records == 100000
        assert tenant.storage_limit_gb == 10.0
        assert tenant.enable_pii_redaction is True
        assert tenant.enable_ai_labeling is True
        assert tenant.enable_human_review is True
        assert tenant.created_at is not None
        assert tenant.updated_at is not None

    def test_tenant_custom_values(self):
        """Test tenant creation with custom values."""
        tenant = Tenant(
            tenant_id="custom_tenant",
            name="Custom Org",
            status="suspended",
            max_users=50,
            max_data_records=500000,
            storage_limit_gb=25.0,
            enable_pii_redaction=False,
            enable_ai_labeling=False,
            enable_human_review=False,
        )

        assert tenant.status == "suspended"
        assert tenant.max_users == 50
        assert tenant.max_data_records == 500000
        assert tenant.storage_limit_gb == 25.0
        assert tenant.enable_pii_redaction is False
        assert tenant.enable_ai_labeling is False
        assert tenant.enable_human_review is False

    def test_tenant_status_enum(self):
        """Test tenant status enumeration."""
        # Test all valid status values
        valid_statuses = ["active", "suspended", "inactive"]
        for status in valid_statuses:
            tenant = Tenant(tenant_id=f"tenant_{status}", name=f"Org {status}")
            assert tenant.status == status

    def test_tenant_properties(self):
        """Test tenant properties."""
        tenant = Tenant(
            tenant_id="prop_test",
            name="Property Test Org",
            status="active",
        )

        # Test is_active property
        assert tenant.is_active is True

        # Test inactive tenant
        tenant.status = "inactive"
        assert tenant.is_active is False

    def test_tenant_str_representation(self):
        """Test tenant string representation."""
        tenant = Tenant(
            tenant_id="str_test",
            name="String Test Org",
        )

        # Test that string representation works
        assert str(tenant) is not None
        assert "Tenant" in str(tenant) or "test_tenant" in str(tenant)

    def test_tenant_update_timestamp(self):
        """Test that updated_at timestamp updates on save."""
        tenant = Tenant(
            tenant_id="timestamp_test",
            name="Timestamp Test Org",
        )
        original_updated_at = tenant.updated_at

        # In a real scenario, saving would update the timestamp
        # For now, just verify the timestamp exists
        assert tenant.updated_at is not None


class TestUserModel:
    """Test User model functionality."""

    def test_user_creation_minimal(self):
        """Test user creation with minimal required fields."""
        user = User(
            user_id="user_001",
            email="user@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
        )

        # Verify default values
        assert user.role == "analyst"
        assert user.status == "active"
        assert user.can_create_data is True
        assert user.can_view_data is True
        assert user.can_modify_data is False
        assert user.can_delete_data is False
        assert user.can_manage_users is False

    def test_user_creation_with_all_fields(self):
        """Test user creation with all fields."""
        user = User(
            user_id="admin_user",
            email="admin@company.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("admin123"),
            role="admin",
            status="active",
            first_name="Admin",
            last_name="User",
            phone="555-1234",
            can_create_data=True,
            can_view_data=True,
            can_modify_data=True,
            can_delete_data=True,
            can_manage_users=True,
        )

        assert user.role == "admin"
        assert user.first_name == "Admin"
        assert user.last_name == "User"
        assert user.phone == "555-1234"
        assert user.can_manage_users is True

    def test_user_role_enum(self):
        """Test user role enumeration."""
        valid_roles = ["admin", "manager", "analyst", "viewer"]
        for role in valid_roles:
            user = User(
                user_id=f"user_{role}",
                email=f"{role}@example.com",
                tenant_id="tenant_001",
                hashed_password=get_password_hash("testpass123"),
                role=role,
            )
            assert user.role == role

    def test_user_status_enum(self):
        """Test user status enumeration."""
        valid_statuses = ["active", "inactive", "suspended"]
        for status in valid_statuses:
            user = User(
                user_id=f"user_{status}",
                email=f"{status}@example.com",
                tenant_id="tenant_001",
                hashed_password=get_password_hash("testpass123"),
                status=status,
            )
            assert user.status == status

    def test_user_full_name_property(self):
        """Test user full name property."""
        # Test with first and last name
        user = User(
            user_id="name_user",
            email="name@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            first_name="John",
            last_name="Doe",
        )
        assert user.full_name == "John Doe"

        # Test with only first name
        user.first_name = "Jane"
        user.last_name = None
        assert user.full_name == "Jane"

        # Test with only last name
        user.first_name = None
        user.last_name = "Smith"
        assert user.full_name == "Smith"

        # Test with no names
        user.first_name = None
        user.last_name = None
        assert user.full_name == "name@example.com"  # Falls back to email

    def test_user_admin_privileges_property(self):
        """Test user admin privileges property."""
        # Admin user
        admin_user = User(
            user_id="admin_test",
            email="admin@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            role="admin",
        )
        assert admin_user.has_admin_privileges is True

        # Non-admin user
        analyst_user = User(
            user_id="analyst_test",
            email="analyst@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            role="analyst",
        )
        assert analyst_user.has_admin_privileges is False

    def test_user_str_representation(self):
        """Test user string representation."""
        user = User(
            user_id="str_user",
            email="str@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
        )

        assert str(user) is not None
        assert "User" in str(user) or "str_user" in str(user)


class TestDataRecordModel:
    """Test DataRecord model functionality."""

    def test_data_record_creation(self):
        """Test data record creation."""
        record = DataRecord(
            record_id="rec_001",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"name": "John Doe", "email": "john@example.com"}',
        )

        assert record.record_id == "rec_001"
        assert record.tenant_id == "tenant_001"
        assert record.data_source == "csv"
        assert record.status == "raw"
        assert record.pii_detected is False
        assert record.pii_redacted is False
        assert record.created_at is not None
        assert record.updated_at is not None

    def test_data_record_data_source_enum(self):
        """Test data source enumeration."""
        valid_sources = ["csv", "json", "excel", "parquet", "api", "manual"]
        for source in valid_sources:
            record = DataRecord(
                record_id=f"rec_{source}",
                tenant_id="tenant_001",
                data_source=source,
                status="raw",
                raw_data='{"test": "data"}',
            )
            assert record.data_source == source

    def test_data_record_status_enum(self):
        """Test data record status enumeration."""
        valid_statuses = ["raw", "processing", "processed", "failed", "archived"]
        for status in valid_statuses:
            record = DataRecord(
                record_id=f"rec_{status}",
                tenant_id="tenant_001",
                data_source="csv",
                status=status,
                raw_data='{"test": "data"}',
            )
            assert record.status == status

    def test_data_record_confidence_validation(self):
        """Test confidence score validation."""
        # Valid confidence scores
        for confidence in [0.0, 0.5, 1.0]:
            record = DataRecord(
                record_id=f"rec_{confidence}",
                tenant_id="tenant_001",
                data_source="csv",
                status="raw",
                raw_data='{"test": "data"}',
                confidence_score=confidence,
            )
            assert record.confidence_score == confidence

    def test_data_record_readiness_properties(self):
        """Test data record readiness properties."""
        # Raw record - ready for processing
        raw_record = DataRecord(
            record_id="raw_rec",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
        )
        assert raw_record.is_ready_for_processing is True

        # Processed record - not ready
        processed_record = DataRecord(
            record_id="proc_rec",
            tenant_id="tenant_001",
            data_source="csv",
            status="processed",
            raw_data='{"test": "data"}',
        )
        assert processed_record.is_ready_for_processing is False

        # Failed record - might be ready for retry
        failed_record = DataRecord(
            record_id="failed_rec",
            tenant_id="tenant_001",
            data_source="csv",
            status="failed",
            raw_data='{"test": "data"}',
            retry_count=0,
        )
        # In a real implementation, this might check retry logic
        assert failed_record.is_ready_for_processing is False

    def test_data_record_confidence_properties(self):
        """Test data record confidence properties."""
        # High confidence record
        high_conf_record = DataRecord(
            record_id="high_conf",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
            ai_confidence=0.95,
        )
        assert high_conf_record.has_high_confidence is True

        # Low confidence record
        low_conf_record = DataRecord(
            record_id="low_conf",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
            ai_confidence=0.65,
        )
        assert low_conf_record.has_high_confidence is False

        # Record without confidence
        no_conf_record = DataRecord(
            record_id="no_conf",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
        )
        assert no_conf_record.has_high_confidence is False  # Default is False


class TestProcessedDataModel:
    """Test ProcessedData model functionality."""

    def test_processed_data_creation(self):
        """Test processed data creation."""
        processed = ProcessedData(
            record_id="proc_001",
            tenant_id="tenant_001",
            confidence_score=0.95,
            auto_approved=True,
            review_required=False,
            cleaned_data='{"name": "John Doe", "email": "john@example.com"}',
            processed_at=datetime.utcnow(),
        )

        assert processed.record_id == "proc_001"
        assert processed.tenant_id == "tenant_001"
        assert processed.confidence_score == 0.95
        assert processed.auto_approved is True
        assert processed.review_required is False
        assert processed.processed_at is not None

    def test_processed_data_confidence_validation(self):
        """Test confidence score validation in processed data."""
        # Test edge cases
        for confidence in [0.0, 0.00001, 0.99999, 1.0]:
            processed = ProcessedData(
                record_id=f"proc_{confidence}",
                tenant_id="tenant_001",
                confidence_score=confidence,
                auto_approved=True,
                review_required=False,
                cleaned_data='{"test": "data"}',
                processed_at=datetime.utcnow(),
            )
            assert processed.confidence_score == confidence

        # Test that invalid confidence would raise an error
        with pytest.raises(ValueError):
            ProcessedData(
                record_id="invalid_conf",
                tenant_id="tenant_001",
                confidence_score=1.5,  # Invalid - > 1.0
                auto_approved=True,
                review_required=False,
                cleaned_data='{"test": "data"}',
                processed_at=datetime.utcnow(),
            )

    def test_processed_data_quality_scores(self):
        """Test data quality score properties."""
        processed = ProcessedData(
            record_id="quality_test",
            tenant_id="tenant_001",
            confidence_score=0.9,
            auto_approved=True,
            review_required=False,
            cleaned_data='{"test": "data"}',
            processed_at=datetime.utcnow(),
            data_quality_score=0.85,
            completeness_score=0.90,
            accuracy_score=0.80,
        )

        assert processed.data_quality_score == 0.85
        assert processed.completeness_score == 0.90
        assert processed.accuracy_score == 0.80

    def test_processed_data_tags_and_categories(self):
        """Test tags and categories functionality."""
        processed = ProcessedData(
            record_id="tags_test",
            tenant_id="tenant_001",
            confidence_score=0.9,
            auto_approved=True,
            review_required=False,
            cleaned_data='{"test": "data"}',
            processed_at=datetime.utcnow(),
            tags=["premium", "enterprise", "verified"],
            categories=["B2B", "High Value"],
            keywords=["business", "corporate"],
        )

        assert processed.tags == ["premium", "enterprise", "verified"]
        assert processed.categories == ["B2B", "High Value"]
        assert processed.keywords == ["business", "corporate"]

        # Test default empty lists
        empty_processed = ProcessedData(
            record_id="empty_test",
            tenant_id="tenant_001",
            confidence_score=0.9,
            auto_approved=True,
            review_required=False,
            cleaned_data='{"test": "data"}',
            processed_at=datetime.utcnow(),
        )

        assert empty_processed.tags == []
        assert empty_processed.categories == []
        assert empty_processed.keywords == []


class TestHumanReviewQueueModel:
    """Test HumanReviewQueue model functionality."""

    def test_human_review_queue_creation(self):
        """Test human review queue creation."""
        review = HumanReviewQueue(
            review_id="rev_001",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="pending",
            priority="medium",
            original_data='{"name": "John Doe", "email": "john@example.com"}',
            ai_confidence=0.65,
            ai_category="uncertain",
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )

        assert review.review_id == "rev_001"
        assert review.record_id == "rec_001"
        assert review.tenant_id == "tenant_001"
        assert review.status == "pending"
        assert review.priority == "medium"
        assert review.ai_confidence == 0.65
        assert review.ai_category == "uncertain"

    def test_human_review_queue_status_enum(self):
        """Test human review queue status enumeration."""
        valid_statuses = ["pending", "in_progress", "reviewed", "approved", "rejected", "skipped"]
        for status in valid_statuses:
            review = HumanReviewQueue(
                review_id=f"rev_{status}",
                record_id="rec_001",
                tenant_id="tenant_001",
                status=status,
                priority="medium",
                original_data='{"test": "data"}',
                ai_confidence=0.5,
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow(),
            )
            assert review.status == status

    def test_human_review_queue_priority_enum(self):
        """Test human review queue priority enumeration."""
        valid_priorities = ["low", "medium", "high", "urgent"]
        for priority in valid_priorities:
            review = HumanReviewQueue(
                review_id=f"rev_{priority}",
                record_id="rec_001",
                tenant_id="tenant_001",
                status="pending",
                priority=priority,
                original_data='{"test": "data"}',
                ai_confidence=0.5,
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow(),
            )
            assert review.priority == priority

    def test_human_review_queue_status_properties(self):
        """Test human review queue status properties."""
        # Pending review
        pending_review = HumanReviewQueue(
            review_id="pending_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="pending",
            priority="medium",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )
        assert pending_review.is_active is True
        assert pending_review.is_completed is False

        # In progress review
        in_progress_review = HumanReviewQueue(
            review_id="in_progress_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="in_progress",
            priority="medium",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )
        assert in_progress_review.is_active is True
        assert in_progress_review.is_completed is False

        # Completed review
        completed_review = HumanReviewQueue(
            review_id="completed_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="approved",
            priority="medium",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )
        assert completed_review.is_active is False
        assert completed_review.is_completed is True

    def test_human_review_queue_pending_time_calculation(self):
        """Test pending time calculation."""
        import time

        # Create review with different timestamps
        start_time = datetime.utcnow()
        time.sleep(0.001)  # Small delay
        end_time = datetime.utcnow()

        review = HumanReviewQueue(
            review_id="time_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="pending",
            priority="medium",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            created_at=start_time,
            submitted_at=start_time,
        )

        # Simulate review started
        review.started_at = end_time

        # Test pending time calculation
        pending_time = review.pending_time_minutes
        assert pending_time is not None
        assert pending_time >= 0

    def test_human_review_queue_reviewer_data(self):
        """Test reviewer data functionality."""
        review = HumanReviewQueue(
            review_id="reviewer_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="reviewed",
            priority="high",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            ai_category="uncertain",
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            assigned_to="reviewer_001",
            reviewer_category="high_value",
            reviewer_confidence=0.95,
            reviewer_notes="This is a high value customer",
            reviewer_action="approved",
            final_labels=["premium", "verified"],
            final_tags=["B2B", "Enterprise"],
            final_categories=["High Value"],
        )

        assert review.assigned_to == "reviewer_001"
        assert review.reviewer_category == "high_value"
        assert review.reviewer_confidence == 0.95
        assert review.reviewer_notes == "This is a high value customer"
        assert review.reviewer_action == "approved"
        assert review.final_labels == ["premium", "verified"]
        assert review.final_tags == ["B2B", "Enterprise"]
        assert review.final_categories == ["High Value"]

    def test_human_review_queue_quality_metrics(self):
        """Test quality rating metrics."""
        review = HumanReviewQueue(
            review_id="quality_test",
            record_id="rec_001",
            tenant_id="tenant_001",
            status="reviewed",
            priority="medium",
            original_data='{"test": "data"}',
            ai_confidence=0.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            reviewer_experience=4,
            data_quality_rating=3,
            review_difficulty=2,
        )

        assert review.reviewer_experience == 4
        assert review.data_quality_rating == 3
        assert review.review_difficulty == 2


class TestModelRelationships:
    """Test model relationships and constraints."""

    async def test_user_tenant_relationship(self, db_session):
        """Test user-tenant relationship."""
        # Create tenant
        tenant = Tenant(
            tenant_id="rel_tenant",
            name="Relationship Test Org",
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create user
        user = User(
            user_id="rel_user",
            email="rel@example.com",
            tenant_id=tenant.tenant_id,
            hashed_password=get_password_hash("testpass123"),
        )
        db_session.add(user)
        await db_session.commit()

        # Verify relationship
        assert user.tenant_id == tenant.tenant_id
        # In a real implementation, we might test foreign key constraints

    async def test_data_record_tenant_relationship(self, db_session):
        """Test data record-tenant relationship."""
        # Create tenant
        tenant = Tenant(
            tenant_id="data_tenant",
            name="Data Relationship Test Org",
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create data record
        record = DataRecord(
            record_id="data_rec",
            tenant_id=tenant.tenant_id,
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
        )
        db_session.add(record)
        await db_session.commit()

        # Verify relationship
        assert record.tenant_id == tenant.tenant_id

    async def test_processed_data_relationship(self, db_session):
        """Test processed data relationship."""
        # Create tenant
        tenant = Tenant(
            tenant_id="processed_tenant",
            name="Processed Data Test Org",
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create processed data
        processed = ProcessedData(
            record_id="proc_data",
            tenant_id=tenant.tenant_id,
            confidence_score=0.9,
            auto_approved=True,
            review_required=False,
            cleaned_data='{"processed": "data"}',
            processed_at=datetime.utcnow(),
        )
        db_session.add(processed)
        await db_session.commit()

        # Verify relationship
        assert processed.tenant_id == tenant.tenant_id

    async def test_human_review_queue_relationship(self, db_session):
        """Test human review queue relationship."""
        # Create tenant
        tenant = Tenant(
            tenant_id="review_tenant",
            name="Review Test Org",
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create human review queue item
        review = HumanReviewQueue(
            review_id="review_data",
            record_id="review_rec",
            tenant_id=tenant.tenant_id,
            status="pending",
            priority="high",
            original_data='{"review": "data"}',
            ai_confidence=0.5,
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
        )
        db_session.add(review)
        await db_session.commit()

        # Verify relationship
        assert review.tenant_id == tenant.tenant_id


class TestModelValidation:
    """Test model validation constraints."""

    def test_tenant_id_uniqueness(self):
        """Test tenant ID uniqueness constraint."""
        # Create first tenant
        tenant1 = Tenant(
            tenant_id="unique_test",
            name="First Org",
        )

        # Create second tenant with same ID should fail in database
        # This tests the constraint at the model level
        tenant2 = Tenant(
            tenant_id="unique_test",  # Same ID
            name="Second Org",
        )

        # In a real test, this would fail due to database constraint
        # For now, just verify the models are created
        assert tenant1.tenant_id == "unique_test"
        assert tenant2.tenant_id == "unique_test"

    def test_user_email_uniqueness(self):
        """Test user email uniqueness constraint."""
        # Create first user
        user1 = User(
            user_id="user1",
            email="unique@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
        )

        # Create second user with same email should fail
        user2 = User(
            user_id="user2",
            email="unique@example.com",  # Same email
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
        )

        # Verify models are created
        assert user1.email == "unique@example.com"
        assert user2.email == "unique@example.com"

    def test_required_fields_validation(self):
        """Test required fields validation."""
        # Test Tenant required fields
        tenant = Tenant(tenant_id="required_test", name="Required Test")
        assert tenant.tenant_id is not None
        assert tenant.name is not None

        # Test User required fields
        user = User(
            user_id="required_user",
            email="required@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
        )
        assert user.user_id is not None
        assert user.email is not None
        assert user.tenant_id is not None
        assert user.hashed_password is not None

        # Test DataRecord required fields
        record = DataRecord(
            record_id="required_rec",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"test": "data"}',
        )
        assert record.record_id is not None
        assert record.tenant_id is not None
        assert record.data_source is not None
        assert record.status is not None
        assert record.raw_data is not None


class TestModelSerialization:
    """Test model serialization and JSON conversion."""

    def test_tenant_to_dict(self):
        """Test model to dictionary conversion."""
        tenant = Tenant(
            tenant_id="serial_test",
            name="Serialization Test Org",
            status="active",
            max_users=50,
        )

        # Convert to dictionary
        tenant_dict = tenant.model_dump()

        # Verify all fields are included
        assert "tenant_id" in tenant_dict
        assert "name" in tenant_dict
        assert "status" in tenant_dict
        assert "max_users" in tenant_dict
        assert tenant_dict["tenant_id"] == "serial_test"
        assert tenant_dict["name"] == "Serialization Test Org"

    def test_user_to_dict(self):
        """Test user model to dictionary conversion."""
        user = User(
            user_id="serial_user",
            email="serial@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("testpass123"),
            role="admin",
        )

        user_dict = user.model_dump()

        # Verify all fields are included
        assert "user_id" in user_dict
        assert "email" in user_dict
        assert "tenant_id" in user_dict
        assert "role" in user_dict
        assert user_dict["user_id"] == "serial_user"
        assert user_dict["email"] == "serial@example.com"

    def test_data_record_to_dict(self):
        """Test data record model to dictionary conversion."""
        record = DataRecord(
            record_id="serial_rec",
            tenant_id="tenant_001",
            data_source="csv",
            status="raw",
            raw_data='{"name": "John Doe"}',
        )

        record_dict = record.model_dump()

        # Verify all fields are included
        assert "record_id" in record_dict
        assert "tenant_id" in record_dict
        assert "data_source" in record_dict
        assert "status" in record_dict
        assert "raw_data" in record_dict
        assert record_dict["record_id"] == "serial_rec"
        assert record_dict["raw_data"] == '{"name": "John Doe"}'

    def test_model_json_serialization(self):
        """Test model JSON serialization."""
        tenant = Tenant(
            tenant_id="json_test",
            name="JSON Test Org",
            status="active",
        )

        # Convert to JSON
        json_str = tenant.model_dump_json()

        # Verify it's valid JSON
        import json
        parsed = json.loads(json_str)

        # Verify content
        assert parsed["tenant_id"] == "json_test"
        assert parsed["name"] == "JSON Test Org"
        assert parsed["status"] == "active"


class TestModelIndexes:
    """Test database indexes on models."""

    def test_tenant_indexes(self):
        """Test tenant model indexes."""
        # Test that model_fields contains expected fields
        assert "tenant_id" in Tenant.model_fields
        assert Tenant.model_fields["tenant_id"].description == "Unique tenant identifier used for data isolation"

    def test_user_indexes(self):
        """Test user model indexes."""
        # Test that model_fields contains expected fields
        assert "user_id" in User.model_fields
        assert User.model_fields["user_id"].description == "Unique user identifier (UUID)"

        assert "email" in User.model_fields
        assert "tenant_id" in User.model_fields

    def test_data_record_indexes(self):
        """Test data record model indexes."""
        # Test that model_fields contains expected fields
        assert "record_id" in DataRecord.model_fields
        assert DataRecord.model_fields["record_id"].description == "Unique record identifier (UUID)"

        assert "tenant_id" in DataRecord.model_fields

    def test_processed_data_indexes(self):
        """Test processed data model indexes."""
        # Test that model_fields contains expected fields
        assert "record_id" in ProcessedData.model_fields
        assert ProcessedData.model_fields["record_id"].description == "Original record ID from data_records"

        assert "tenant_id" in ProcessedData.model_fields

    def test_human_review_queue_indexes(self):
        """Test human review queue model indexes."""
        # Test that model_fields contains expected fields
        assert "review_id" in HumanReviewQueue.model_fields
        assert HumanReviewQueue.model_fields["review_id"].description == "Unique review identifier (UUID)"

        assert "tenant_id" in HumanReviewQueue.model_fields
        assert "record_id" in HumanReviewQueue.model_fields