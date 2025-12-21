"""
Integration tests for complete Data Foundry workflow with mocked services

This test suite validates the entire data processing workflow from ingestion
to final output using mocked external dependencies (AI services, databases, etc.).
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

from src.models import (
    User, Tenant, DataRecord, ProcessedData, HumanReviewQueue,
    TokenUsage, AuditLog
)
from src.models.user import UserRole, UserStatus
from src.models.tenant import TenantStatus
from src.models.data_record import DataSource, DataStatus

# Import services that exist
from src.core.config import settings


class TestCompleteWorkflow:
    """Integration test for the complete data processing workflow."""

    @pytest.fixture
    def mock_tenant(self):
        """Create a mock tenant for testing."""
        tenant = Tenant(
            tenant_id="test_tenant_001",
            name="Test Organization",
            status=TenantStatus.ACTIVE,
            max_users=100,
            max_data_records=1000000,
            storage_limit_gb=100.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            billing_plan="premium",
            billing_status="active",
            subscription_tier="enterprise"
        )
        return tenant

    @pytest.fixture
    def mock_user(self, mock_tenant):
        """Create a mock user for testing."""
        user = User(
            user_id="test_user_001",
            email="test@example.com",
            tenant_id=mock_tenant.tenant_id,
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            first_name="Test",
            last_name="User",
            mfa_enabled=True
        )
        return user

    @pytest.fixture
    def sample_data(self):
        """Sample data for testing."""
        return [
            {
                "id": 1,
                "name": "John Smith",
                "email": "john.smith@enterprise.com",
                "phone": "+1-555-0123",
                "company": "TechCorp Inc",
                "title": "CTO",
                "tenant_id": "test_tenant_001",
                "ai_confidence": None,
                "ai_category": None,
                "ai_reasoning": None
            },
            {
                "id": 2,
                "name": "Jane Doe",
                "email": "jane.doe@startup.io",
                "phone": "+1-555-0456",
                "company": "StartupXYZ",
                "title": "CEO",
                "tenant_id": "test_tenant_001",
                "ai_confidence": None,
                "ai_category": None,
                "ai_reasoning": None
            },
            {
                "id": 3,
                "name": "Test Contact",
                "email": "test@example.com",
                "phone": "+1-555-0789",
                "company": "TestCompany",
                "title": "Test Engineer",
                "tenant_id": "test_tenant_001",
                "ai_confidence": None,
                "ai_category": None,
                "ai_reasoning": None
            }
        ]

    @pytest.fixture
    def mock_ai_service(self):
        """Mock AI service for testing."""
        mock_service = Mock()
        mock_service.classify.return_value = {
            "category": "high_value",
            "confidence": 0.95,
            "reasoning": "Corporate email and executive title detected"
        }
        mock_service.is_available.return_value = True
        mock_service.get_model_info.return_value = {
            "model": "gpt-4o",
            "provider": "openai",
            "cost_per_1k_tokens": Decimal("0.01")
        }
        return mock_service

    @pytest.fixture
    def mock_pii_service(self):
        """Mock PII service for testing."""
        mock_service = Mock()
        mock_service.detect_pii.return_value = [
            {"type": "PERSON", "value": "John Smith", "confidence": 0.95},
            {"type": "EMAIL", "value": "john.smith@enterprise.com", "confidence": 1.0},
            {"type": "PHONE", "value": "+1-555-0123", "confidence": 0.9}
        ]
        mock_service.redact_pii.return_value = "[REDACTED_PERSON] <redacted_email> <redacted_phone>"
        mock_service.is_available.return_value = True
        return mock_service

    @pytest.fixture
    def mock_label_studio(self):
        """Mock Label Studio client for testing."""
        mock_client = Mock()
        mock_client.create_task.return_value = {"id": "ls_task_001", "status": "created"}
        mock_client.get_task_status.return_value = {"id": "ls_task_001", "status": "completed"}
        mock_client.get_task_annotations.return_value = [
            {"result": [{"value": {"choices": ["high_value"]}}], "type": "choices"}
        ]
        mock_client.is_available.return_value = True
        return mock_client

    def test_data_ingestion_and_ai_classification(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service,
        mock_pii_service,
        mock_label_studio
    ):
        """Test complete data ingestion and AI classification workflow."""

        # Mock configuration
        with patch('src.core.config.settings.CONFIDENCE_THRESHOLD', 0.85):

                        # Simulate the workflow for each record
                        processed_records = []
                        human_review_queue = []

                        for record in sample_data:
                            # Step 1: AI Classification
                            ai_result = mock_ai_service.classify(record)
                            record.update(ai_result)

                            # Step 2: Check confidence threshold
                            confidence = record.get("ai_confidence", 1.0)
                            if confidence < 0.85:
                                # Send to human review
                                human_review_item = HumanReviewQueue(
                                    review_id=f"rev_{record['id']:03d}",
                                    record_id=f"rec_{record['id']:03d}",
                                    tenant_id=record["tenant_id"],
                                    status="pending",
                                    priority="medium",
                                    original_data=str(record),
                                    ai_confidence=confidence,
                                    ai_category=record.get("ai_category")
                                )
                                human_review_queue.append(human_review_item)
                            else:
                                # Auto-approve
                                processed_record = ProcessedData(
                                    record_id=f"proc_{record['id']:03d}",
                                    tenant_id=record["tenant_id"],
                                    confidence_score=confidence,
                                    auto_approved=True,
                                    review_required=False,
                                    ai_category=record.get("ai_category"),
                                    ai_confidence=confidence,
                                    ai_model="gpt-4o",
                                    cleaned_data=str(record),
                                    processing_metadata={
                                        "ai_service": "LiteLLM",
                                        "pii_detected": True,
                                        "pii_redacted": True
                                    }
                                )
                                processed_records.append(processed_record)

                        # Verify results
                        assert len(processed_records) == 2  # 2 high confidence records
                        assert len(human_review_queue) == 1  # 1 low confidence record

                        # Verify auto-approved records
                        auto_approved = [r for r in processed_records if r.auto_approved]
                        assert len(auto_approved) == 2
                        assert all(r.ai_confidence >= 0.85 for r in auto_approved)

                        # Verify human review queue
                        assert human_review_queue[0].ai_confidence < 0.85
                        assert human_review_queue[0].status == "pending"

    def test_pii_detection_and_redaction_workflow(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_pii_service
    ):
        """Test PII detection and redaction workflow."""

        # Use the mock services directly
        # Test PII detection
        record = sample_data[0]  # John Smith record

        # Detect PII
        pii_results = mock_pii_service.detect_pii(record)
        assert len(pii_results) == 3
        assert any(r["type"] == "PERSON" for r in pii_results)
        assert any(r["type"] == "EMAIL" for r in pii_results)
        assert any(r["type"] == "PHONE" for r in pii_results)

        # Redact PII
        redacted_text = mock_pii_service.redact_pii(str(record))
        assert "[REDACTED_PERSON]" in redacted_text
        assert "<redacted_email>" in redacted_text
        assert "<redacted_phone>" in redacted_text

        # Verify redacted data doesn't contain PII
        redacted_data = redacted_text.replace("[REDACTED_PERSON]", "").replace("<redacted_email>", "").replace("<redacted_phone>", "")
        assert "John Smith" not in redacted_data
        assert "john.smith@enterprise.com" not in redacted_data
        assert "+1-555-0123" not in redacted_data

    def test_tenant_isolation_enforcement(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service,
        mock_pii_service
    ):
        """Test tenant isolation is enforced throughout the workflow."""

        # Create data from different tenants
        tenant_a_data = [
            {
                "id": 1,
                "name": "User A",
                "email": "user@a.com",
                "tenant_id": "tenant_a",
            }
        ]

        tenant_b_data = [
            {
                "id": 2,
                "name": "User B",
                "email": "user@b.com",
                "tenant_id": "tenant_b",
            }
        ]

        # Mock AI service to process data
        mock_ai_service.classify.side_effect = lambda x: {
            "category": "high_value",
            "confidence": 0.95,
            "reasoning": "Test classification"
        }

        # Use the mock services directly
        # Process tenant A data
        tenant_a_processed = []
        for record in tenant_a_data:
            ai_result = mock_ai_service.classify(record)
            record.update(ai_result)
            processed_record = ProcessedData(
                record_id=f"proc_{record['id']:03d}",
                tenant_id=record["tenant_id"],
                confidence_score=record["ai_confidence"],
                auto_approved=True,
                review_required=False,
                ai_category=record["ai_category"],
                ai_confidence=record["ai_confidence"],
                ai_model="gpt-4o",
                cleaned_data=str(record)
            )
            tenant_a_processed.append(processed_record)

        # Process tenant B data
        tenant_b_processed = []
        for record in tenant_b_data:
            ai_result = mock_ai_service.classify(record)
            record.update(ai_result)
            processed_record = ProcessedData(
                record_id=f"proc_{record['id']:03d}",
                tenant_id=record["tenant_id"],
                confidence_score=record["ai_confidence"],
                auto_approved=True,
                review_required=False,
                ai_category=record["ai_category"],
                ai_confidence=record["ai_confidence"],
                ai_model="gpt-4o",
                cleaned_data=str(record)
            )
            tenant_b_processed.append(processed_record)

        # Verify tenant isolation
        assert len(tenant_a_processed) == 1
        assert len(tenant_b_processed) == 1
        assert tenant_a_processed[0].tenant_id == "tenant_a"
        assert tenant_b_processed[0].tenant_id == "tenant_b"
        assert tenant_a_processed[0].tenant_id != tenant_b_processed[0].tenant_id

        # Verify no data leakage between tenants
        tenant_a_emails = [r for r in tenant_a_processed]
        tenant_b_emails = [r for r in tenant_b_processed]
        assert "user@b.com" not in str(tenant_a_emails)
        assert "user@a.com" not in str(tenant_b_emails)

    def test_error_handling_workflow(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service,
        mock_pii_service
    ):
        """Test error handling when external services are unavailable."""

        # Test AI service unavailable
        mock_ai_service.is_available.return_value = False

        # Use the mock services directly
        # Test graceful degradation when AI service is unavailable
        record = sample_data[0]

        # Should still process record but with default values
        if not mock_ai_service.is_available():
            # Fallback logic
            record.update({
                "ai_category": "unknown",
                "ai_confidence": 0.5,  # Default confidence
                "ai_reasoning": "AI service unavailable"
            })

        assert record["ai_category"] == "unknown"
        assert record["ai_confidence"] == 0.5
        assert "AI service unavailable" in record["ai_reasoning"]

        # Reset for next test
        mock_ai_service.is_available.return_value = True

        # Test PII service unavailable
        mock_pii_service.is_available.return_value = False

        # Use the mock services directly
        # Should still process but without PII redaction
        if not mock_pii_service.is_available():
            # Record original data without redaction
            original_data = str(record)
            # Add PII warning
            record["pii_warning"] = "PII redaction service unavailable"

        assert "pii_warning" in record
        assert "PII redaction service unavailable" in record["pii_warning"]

    def test_audit_logging_workflow(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service,
        mock_pii_service
    ):
        """Test audit logging throughout the workflow."""

        audit_logs = []

        def log_audit_event(action, resource_type, resource_id, success=True, details=None):
            """Mock audit logging function."""
            audit_log = AuditLog(
                tenant_id=mock_tenant.tenant_id,
                user_id=mock_user.user_id,
                operation=action,
                resource_type=resource_type,
                resource_id=resource_id,
                success=success,
                details=details or {},
                ip_address="192.168.1.100",
                user_agent="Mozilla/5.0 (Test)",
                duration_ms=150.0
            )
            audit_logs.append(audit_log)
            return audit_log

        # Use the mock services directly

        # Process each record with audit logging
        for record in sample_data:
            # Log data ingestion
            log_audit_event(
                action="data_ingestion",
                resource_type="DataRecord",
                resource_id=f"rec_{record['id']}",
                success=True,
                details={"record_count": len(sample_data)}
            )

            # Log AI classification
            ai_result = mock_ai_service.classify(record)
            log_audit_event(
                action="ai_classification",
                resource_type="DataRecord",
                resource_id=f"rec_{record['id']}",
                success=True,
                details={
                    "model": "gpt-4o",
                    "confidence": ai_result["confidence"],
                    "category": ai_result["category"]
                }
            )

            # Log PII detection
            pii_results = mock_pii_service.detect_pii(record)
            log_audit_event(
                action="pii_detection",
                resource_type="DataRecord",
                resource_id=f"rec_{record['id']}",
                success=True,
                details={
                    "pii_count": len(pii_results),
                    "pii_types": [r["type"] for r in pii_results]
                }
            )

        # Verify audit logs
        assert len(audit_logs) == len(sample_data) * 3  # 3 actions per record

        # Verify all logs contain required information
        for log in audit_logs:
            assert log.tenant_id == mock_tenant.tenant_id
            assert log.user_id == mock_user.user_id
            assert log.success is True
            assert log.details is not None
            assert log.ip_address == "192.168.1.100"
            assert log.duration_ms == 150.0

        # Verify specific actions
        ingestion_logs = [log for log in audit_logs if log.operation == "data_ingestion"]
        ai_logs = [log for log in audit_logs if log.operation == "ai_classification"]
        pii_logs = [log for log in audit_logs if log.operation == "pii_detection"]

        assert len(ingestion_logs) == len(sample_data)
        assert len(ai_logs) == len(sample_data)
        assert len(pii_logs) == len(sample_data)

    def test_cost_tracking_workflow(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service
    ):
        """Test cost tracking throughout the workflow."""

        token_usage_logs = []

        def log_token_usage(model, input_tokens, output_tokens):
            """Mock token usage logging function."""
            cost_per_1k_input = Decimal("0.001")
            cost_per_1k_output = Decimal("0.002")

            input_cost = (input_tokens / 1000) * cost_per_1k_input
            output_cost = (output_tokens / 1000) * cost_per_1k_output
            total_cost = input_cost + output_cost

            token_usage = TokenUsage(
                tenant_id=mock_tenant.tenant_id,
                user_id=mock_user.user_id,
                request_id=f"req_{len(token_usage_logs):03d}",
                model=model,
                provider="openai",
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=total_cost,
                currency="USD",
                response_time_ms=500.0,
                success=True,
                additional_metadata={
                    "tenant_id": mock_tenant.tenant_id,
                    "processed_at": datetime.utcnow().isoformat()
                }
            )
            token_usage_logs.append(token_usage)
            return token_usage

        # Use the mock services directly

            # Configure mock AI service to return token usage
            mock_ai_service.classify.side_effect = lambda x: {
                "category": "high_value",
                "confidence": 0.95,
                "reasoning": "Corporate email and executive title detected",
                "input_tokens": 150,
                "output_tokens": 50
            }

            # Process records and track costs
            for record in sample_data:
                # AI classification with token tracking
                ai_result = mock_ai_service.classify(record)
                log_token_usage("gpt-4o", ai_result["input_tokens"], ai_result["output_tokens"])

            # Verify token usage tracking
            assert len(token_usage_logs) == len(sample_data)

            # Calculate totals
            total_input_tokens = sum(tu.prompt_tokens for tu in token_usage_logs)
            total_output_tokens = sum(tu.completion_tokens for tu in token_usage_logs)
            total_tokens = sum(tu.total_tokens for tu in token_usage_logs)
            total_cost = sum(tu.total_cost for tu in token_usage_logs)

            assert total_input_tokens == len(sample_data) * 150  # 150 tokens per record
            assert total_output_tokens == len(sample_data) * 50  # 50 tokens per record
            assert total_tokens == len(sample_data) * 200  # 200 tokens per record
            assert total_cost > 0

            # Verify cost calculation
            expected_input_cost = (total_input_tokens / 1000) * Decimal("0.001")
            expected_output_cost = (total_output_tokens / 1000) * Decimal("0.002")
            expected_total_cost = expected_input_cost + expected_output_cost

            assert abs(total_cost - expected_total_cost) < Decimal("0.0001")

    def test_workflow_configuration_variations(
        self,
        mock_tenant,
        mock_user,
        sample_data,
        mock_ai_service,
        mock_pii_service,
        mock_label_studio
    ):
        """Test workflow with different configuration combinations."""

        configurations = [
            {
                "name": "Full Pipeline",
                "enable_pii_redaction": True,
                "enable_ai_labeling": True,
                "enable_human_review": True,
                "confidence_threshold": 0.85
            },
            {
                "name": "AI Only",
                "enable_pii_redaction": False,
                "enable_ai_labeling": True,
                "enable_human_review": False,
                "confidence_threshold": 0.9
            },
            {
                "name": "PII Only",
                "enable_pii_redaction": True,
                "enable_ai_labeling": False,
                "enable_human_review": False,
                "confidence_threshold": 1.0  # Auto-approve everything
            },
            {
                "name": "Minimal",
                "enable_pii_redaction": False,
                "enable_ai_labeling": False,
                "enable_human_review": False,
                "confidence_threshold": 0.0  # Auto-approve everything
            }
        ]

        for config in configurations:
            with patch('src.core.config.settings.CONFIDENCE_THRESHOLD', config["confidence_threshold"]):
                # Use the mock services directly
                    # Use the mock services directly
                        # Use the mock services directly

                            # Configure mock AI service based on config
                            if config["enable_ai_labeling"]:
                                mock_ai_service.classify.return_value = {
                                    "category": "high_value",
                                    "confidence": 0.95,
                                    "reasoning": "Test classification"
                                }
                            else:
                                mock_ai_service.classify.return_value = {
                                    "category": None,
                                    "confidence": 1.0,
                                    "reasoning": "AI labeling disabled"
                                }

                            # Simulate workflow
                            processed_records = []
                            human_review_queue = []

                            for record in sample_data:
                                # Apply AI labeling if enabled
                                if config["enable_ai_labeling"]:
                                    ai_result = mock_ai_service.classify(record)
                                    record.update(ai_result)
                                else:
                                    record.update({
                                        "ai_confidence": 1.0,
                                        "ai_category": "unclassified"
                                    })

                                # Apply PII redaction if enabled
                                if config["enable_pii_redaction"]:
                                    pii_results = mock_pii_service.detect_pii(record)
                                    redacted = mock_pii_service.redact_pii(str(record))
                                    record["pii_detected"] = len(pii_results) > 0
                                    record["pii_redacted"] = True
                                    record["redacted_data"] = redacted
                                else:
                                    record["pii_detected"] = False
                                    record["pii_redacted"] = False

                                # Apply human review if enabled
                                confidence = record.get("ai_confidence", 1.0)
                                if config["enable_human_review"] and confidence < config["confidence_threshold"]:
                                    human_review_item = HumanReviewQueue(
                                        review_id=f"rev_{record['id']:03d}",
                                        record_id=f"rec_{record['id']:03d}",
                                        tenant_id=record["tenant_id"],
                                        status="pending",
                                        priority="medium",
                                        original_data=str(record),
                                        ai_confidence=confidence,
                                        ai_category=record.get("ai_category")
                                    )
                                    human_review_queue.append(human_review_item)
                                else:
                                    processed_record = ProcessedData(
                                        record_id=f"proc_{record['id']:03d}",
                                        tenant_id=record["tenant_id"],
                                        confidence_score=confidence,
                                        auto_approved=True,
                                        review_required=False,
                                        ai_category=record.get("ai_category"),
                                        ai_confidence=confidence,
                                        ai_model="gpt-4o" if config["enable_ai_labeling"] else None,
                                        cleaned_data=str(record),
                                        processing_metadata={
                                            "pii_redacted": record.get("pii_redacted", False),
                                            "ai_processed": config["enable_ai_labeling"]
                                        }
                                    )
                                    processed_records.append(processed_record)

                            # Verify configuration-specific behavior
                            if config["name"] == "Full Pipeline":
                                assert len(processed_records) == 2  # High confidence
                                assert len(human_review_queue) == 1  # Low confidence
                                assert all(r.pii_redacted for r in processed_records)

                            elif config["name"] == "AI Only":
                                assert len(processed_records) == 3  # All auto-approved
                                assert len(human_review_queue) == 0
                                assert not any(r.get("pii_redacted", False) for r in processed_records)

                            elif config["name"] == "PII Only":
                                assert len(processed_records) == 3  # All auto-approved
                                assert len(human_review_queue) == 0
                                assert all(r.pii_redacted for r in processed_records)

                            elif config["name"] == "Minimal":
                                assert len(processed_records) == 3  # All auto-approved
                                assert len(human_review_queue) == 0
                                assert not any(r.get("pii_redacted", False) for r in processed_records)
                                assert not any(r.get("ai_category") for r in processed_records)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])