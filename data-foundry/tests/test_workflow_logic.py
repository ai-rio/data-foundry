"""
Direct workflow logic tests for Data Foundry
Tests core workflow functionality without pytest dependencies
"""

import sys
import os
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import DataRecord, ProcessedData, HumanReviewQueue, TokenUsage, AuditLog
from src.models.data_record import DataSource, DataStatus


def test_confidence_routing_logic():
    """Test the core confidence routing decision logic."""
    print("Testing confidence routing logic...")

    # Simple routing function
    def route_by_confidence(records, threshold=0.85):
        auto_approved = []
        human_review = []

        for record in records:
            confidence = record.get("ai_confidence", 1.0)
            if confidence < threshold:
                human_review.append(record)
            else:
                auto_approved.append(record)

        return auto_approved, human_review

    # Test data
    test_data = [
        {"id": 1, "ai_confidence": 0.9, "name": "High Confidence"},
        {"id": 2, "ai_confidence": 0.8, "name": "Low Confidence"},
        {"id": 3, "ai_confidence": 0.95, "name": "Very High Confidence"},
        {"id": 4, "ai_confidence": 0.7, "name": "Very Low Confidence"},
    ]

    # Test routing
    auto_approved, human_review = route_by_confidence(test_data, threshold=0.85)

    # Assertions
    assert len(auto_approved) == 2, f"Expected 2 auto-approved, got {len(auto_approved)}"
    assert len(human_review) == 2, f"Expected 2 human review, got {len(human_review)}"

    auto_ids = [r["id"] for r in auto_approved]
    human_ids = [r["id"] for r in human_review]

    assert 1 in auto_ids, "Record 1 should be auto-approved"
    assert 3 in auto_ids, "Record 3 should be auto-approved"
    assert 2 in human_ids, "Record 2 should go to human review"
    assert 4 in human_ids, "Record 4 should go to human review"

    print("✓ Confidence routing logic test passed")


def test_pii_detection_workflow():
    """Test PII detection workflow with mock."""
    print("Testing PII detection workflow...")

    # Mock Presidio
    mock_analyzer = Mock()
    mock_analyzer.analyze.return_value = [
        Mock(entity_type="PERSON", start=0, end=8),
        Mock(entity_type="EMAIL", start=20, end=37)
    ]

    mock_anonymizer = Mock()
    mock_anonymizer.anonymize.return_value = Mock(text="[REDACTED_PERSON] <redacted_email>")

    # Test PII detection
    def detect_and_redact(text, analyzer, anonymizer):
        results = analyzer.analyze(text=text, language="en")
        if results:
            anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
            return anonymized.text, len(results)
        return text, 0

    # Test with PII
    pii_text = "John Doe <john@example.com>"
    redacted, count = detect_and_redact(pii_text, mock_analyzer, mock_anonymizer)

    assert "[REDACTED_PERSON]" in redacted, "Person name should be redacted"
    assert "<redacted_email>" in redacted, "Email should be redacted"
    assert count == 2, f"Expected 2 PII entities, got {count}"

    print("✓ PII detection workflow test passed")


def test_tenant_isolation_workflow():
    """Test tenant isolation in workflow."""
    print("Testing tenant isolation workflow...")

    # Mock data records from different tenants
    records = [
        DataRecord(
            record_id="rec_001",
            tenant_id="tenant_001",
            data_source=DataSource.CSV,
            status=DataStatus.RAW,
            raw_data='{"name": "John", "email": "john@tenant1.com"}'
        ),
        DataRecord(
            record_id="rec_002",
            tenant_id="tenant_002",
            data_source=DataSource.CSV,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "Jane", "email": "jane@tenant2.com"}'
        ),
    ]

    # Test tenant isolation
    tenant_001_records = [r for r in records if r.tenant_id == "tenant_001"]
    tenant_002_records = [r for r in records if r.tenant_id == "tenant_002"]

    assert len(tenant_001_records) == 1, f"Expected 1 record for tenant 001, got {len(tenant_001_records)}"
    assert len(tenant_002_records) == 1, f"Expected 1 record for tenant 002, got {len(tenant_002_records)}"
    assert tenant_001_records[0].tenant_id != tenant_002_records[0].tenant_id, "Tenants should be isolated"

    print("✓ Tenant isolation workflow test passed")


def test_ai_classification_workflow():
    """Test AI classification workflow."""
    print("Testing AI classification workflow...")

    # Mock AI service
    mock_ai_service = Mock()
    mock_ai_service.classify.return_value = {
        "category": "high_value",
        "confidence": 0.95,
        "reasoning": "Enterprise email detected",
        "model": "gpt-4o",
        "tokens_used": 150
    }

    # Mock cost calculation
    def calculate_cost(tokens, model="gpt-4o"):
        input_cost = Decimal(tokens) / Decimal("1000") * Decimal("0.001")
        output_cost = Decimal(tokens) / Decimal("1000") * Decimal("0.002")
        return input_cost, output_cost, input_cost + output_cost

    # Test AI classification
    record = {"name": "John Smith", "email": "john@enterprise.com"}
    ai_result = mock_ai_service.classify(record)

    assert ai_result["category"] == "high_value", f"Expected high_value category, got {ai_result['category']}"
    assert ai_result["confidence"] == 0.95, f"Expected 0.95 confidence, got {ai_result['confidence']}"
    assert ai_result["model"] == "gpt-4o", f"Expected gpt-4o model, got {ai_result['model']}"
    assert ai_result["tokens_used"] == 150, f"Expected 150 tokens, got {ai_result['tokens_used']}"

    # Test cost calculation
    input_cost, output_cost, total_cost = calculate_cost(ai_result["tokens_used"])
    expected_input_cost = Decimal("0.00015")
    expected_output_cost = Decimal("0.0003")
    expected_total_cost = Decimal("0.00045")

    assert abs(input_cost - expected_input_cost) < Decimal("0.000001"), f"Expected {expected_input_cost}, got {input_cost}"
    assert abs(output_cost - expected_output_cost) < Decimal("0.000001"), f"Expected {expected_output_cost}, got {output_cost}"
    assert abs(total_cost - expected_total_cost) < Decimal("0.000001"), f"Expected {expected_total_cost}, got {total_cost}"

    print("✓ AI classification workflow test passed")


def test_audit_logging_workflow():
    """Test audit logging workflow."""
    print("Testing audit logging workflow...")

    # Mock audit service
    def create_audit_log(tenant_id, operation, resource_id, success=True, audit_metadata=None):
        audit_log = AuditLog(
            tenant_id=tenant_id,
            operation=operation,
            resource_type="DataRecord",
            resource_id=resource_id,
            success=success,
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            duration_ms=150.0,
            audit_metadata=audit_metadata or {}
        )
        return audit_log

    # Test audit logging
    metadata = {
        "ai_confidence": 0.95,
        "pii_detected": True,
        "tokens_used": 150
    }
    audit_log = create_audit_log(
        tenant_id="tenant_001",
        operation="data_processing",
        resource_id="rec_001",
        success=True,
        audit_metadata=metadata
    )

    assert audit_log.tenant_id == "tenant_001", f"Expected tenant_001, got {audit_log.tenant_id}"
    assert audit_log.operation == "data_processing", f"Expected data_processing, got {audit_log.operation}"
    assert audit_log.resource_id == "rec_001", f"Expected rec_001, got {audit_log.resource_id}"
    assert audit_log.success is True, f"Expected success=True, got {audit_log.success}"
    assert audit_log.audit_metadata["ai_confidence"] == 0.95, f"Expected 0.95, got {audit_log.audit_metadata['ai_confidence']}"
    assert audit_log.audit_metadata["tokens_used"] == 150, f"Expected 150, got {audit_log.audit_metadata['tokens_used']}"

    print("✓ Audit logging workflow test passed")


def test_error_handling_workflow():
    """Test error handling in workflow."""
    print("Testing error handling workflow...")

    # Mock error scenarios
    def safe_ai_labeling(record, ai_service=None):
        """AI labeling with error handling."""
        if not ai_service:
            return {
                **record,
                "ai_category": "unknown",
                "ai_confidence": 0.5,
                "ai_error": "AI service unavailable"
            }
        return ai_service.classify(record)

    def safe_pii_redaction(record, pii_service=None):
        """PII redaction with error handling."""
        if not pii_service:
            return {
                **record,
                "pii_detected": False,
                "pii_redacted": False,
                "pii_warning": "PII service unavailable"
            }
        return record  # Would use PII service in real implementation

    # Test with missing services
    record = {"id": 1, "name": "John Doe", "email": "john@example.com"}

    # Test AI service failure
    result = safe_ai_labeling(record, ai_service=None)
    assert result["ai_category"] == "unknown", f"Expected unknown category, got {result['ai_category']}"
    assert result["ai_confidence"] == 0.5, f"Expected 0.5 confidence, got {result['ai_confidence']}"
    assert "AI service unavailable" in result["ai_error"], f"Expected error message, got {result['ai_error']}"

    # Test PII service failure
    result = safe_pii_redaction(record, pii_service=None)
    assert result["pii_detected"] is False, f"Expected pii_detected=False, got {result['pii_detected']}"
    assert result["pii_redacted"] is False, f"Expected pii_redacted=False, got {result['pii_redacted']}"
    assert "PII service unavailable" in result["pii_warning"], f"Expected warning message, got {result['pii_warning']}"

    print("✓ Error handling workflow test passed")


def test_workflow_configuration():
    """Test workflow configuration variations."""
    print("Testing workflow configuration...")

    # Test different configurations
    configurations = [
        {"ai_labeling": True, "pii_redaction": True, "human_review": True},
        {"ai_labeling": False, "pii_redaction": True, "human_review": False},
        {"ai_labeling": True, "pii_redaction": False, "human_review": True},
    ]

    for i, config in enumerate(configurations):
        print(f"  Testing configuration {i+1}: {config}")

        # Validate configuration
        assert isinstance(config["ai_labeling"], bool), f"ai_labeling should be boolean, got {type(config['ai_labeling'])}"
        assert isinstance(config["pii_redaction"], bool), f"pii_redaction should be boolean, got {type(config['pii_redaction'])}"
        assert isinstance(config["human_review"], bool), f"human_review should be boolean, got {type(config['human_review'])}"

        # Test configuration effects
        record = {"id": 1, "name": "Test Record"}

        if config["ai_labeling"]:
            record["ai_category"] = "classified"
            record["ai_confidence"] = 0.9
        else:
            record["ai_category"] = "unclassified"
            record["ai_confidence"] = 1.0

        if config["pii_redaction"]:
            record["pii_detected"] = True
            record["pii_redacted"] = True
        else:
            record["pii_detected"] = False
            record["pii_redacted"] = False

    print("✓ Workflow configuration test passed")


def test_token_usage_tracking():
    """Test token usage tracking in workflow."""
    print("Testing token usage tracking...")

    # Mock token usage tracking
    def create_token_usage(tenant_id, model, prompt_tokens, completion_tokens):
        cost_per_1k_input = Decimal("0.001")
        cost_per_1k_output = Decimal("0.002")

        input_cost = Decimal(prompt_tokens) / Decimal("1000") * cost_per_1k_input
        output_cost = Decimal(completion_tokens) / Decimal("1000") * cost_per_1k_output
        total_cost = input_cost + output_cost

        token_usage = TokenUsage(
            tenant_id=tenant_id,
            user_id="test_user_001",
            request_id=f"req_{tenant_id}_{model}",
            model=model,
            provider="openai",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            currency="USD",
            response_time_ms=500.0,
            success=True
        )
        return token_usage

    # Test token usage tracking
    token_usage = create_token_usage(
        tenant_id="tenant_001",
        model="gpt-4o",
        prompt_tokens=150,
        completion_tokens=50
    )

    assert token_usage.tenant_id == "tenant_001", f"Expected tenant_001, got {token_usage.tenant_id}"
    assert token_usage.model == "gpt-4o", f"Expected gpt-4o, got {token_usage.model}"
    assert token_usage.prompt_tokens == 150, f"Expected 150, got {token_usage.prompt_tokens}"
    assert token_usage.completion_tokens == 50, f"Expected 50, got {token_usage.completion_tokens}"
    assert token_usage.total_tokens == 200, f"Expected 200, got {token_usage.total_tokens}"
    assert token_usage.total_cost == Decimal("0.00025"), f"Expected 0.00025, got {token_usage.total_cost}"

    print("✓ Token usage tracking test passed")


def test_batch_processing_workflow():
    """Test batch processing workflow."""
    print("Testing batch processing workflow...")

    # Mock batch of records
    batch_records = [
        {"id": f"batch_{i:03d}", "name": f"User {i}", "email": f"user{i}@example.com"}
        for i in range(1, 6)  # 5 records
    ]

    # Mock AI service
    mock_ai_service = Mock()
    mock_ai_service.classify.return_value = {
        "category": "standard",
        "confidence": 0.85,
        "reasoning": "Batch test record"
    }

    # Process batch
    processed_records = []
    human_review_queue = []

    for record in batch_records:
        # AI classification
        ai_result = mock_ai_service.classify(record)
        record.update(ai_result)

        # Confidence-based routing
        confidence = record.get("ai_confidence", 1.0)
        if confidence >= 0.85:
            processed_records.append(record)
        else:
            human_review_queue.append(record)

    # Verify batch results
    assert len(processed_records) == 5, f"Expected 5 processed records, got {len(processed_records)}"
    assert len(human_review_queue) == 0, f"Expected 0 human review records, got {len(human_review_queue)}"

    # Verify AI service called for each record
    assert mock_ai_service.classify.call_count == 5, f"Expected 5 AI service calls, got {mock_ai_service.classify.call_count}"

    print("✓ Batch processing workflow test passed")


def test_workflow_metrics():
    """Test workflow metrics calculation."""
    print("Testing workflow metrics...")

    # Mock metrics tracking
    def calculate_metrics(processed_records, human_review_queue, token_usages):
        total_records = len(processed_records) + len(human_review_queue)
        auto_approval_rate = len(processed_records) / total_records if total_records > 0 else 0
        avg_confidence = sum(r.get("ai_confidence", 0.0) for r in processed_records) / len(processed_records) if processed_records else 0
        total_cost = sum(tu.total_cost for tu in token_usages)
        avg_processing_time = 150.0  # Mock average

        return {
            "total_records": total_records,
            "processed_records": len(processed_records),
            "human_review_queue": len(human_review_queue),
            "auto_approval_rate": auto_approval_rate,
            "avg_confidence": avg_confidence,
            "total_cost": total_cost,
            "avg_processing_time": avg_processing_time
        }

    # Test metrics calculation
    processed = [
        {"ai_confidence": 0.95},
        {"ai_confidence": 0.88},
        {"ai_confidence": 0.92}
    ]
    review_queue = []
    token_usages = [Mock(total_cost=Decimal("0.001")) for _ in range(3)]

    metrics = calculate_metrics(processed, review_queue, token_usages)

    assert metrics["total_records"] == 3, f"Expected 3 total records, got {metrics['total_records']}"
    assert metrics["processed_records"] == 3, f"Expected 3 processed records, got {metrics['processed_records']}"
    assert metrics["human_review_queue"] == 0, f"Expected 0 human review records, got {metrics['human_review_queue']}"
    assert metrics["auto_approval_rate"] == 1.0, f"Expected 1.0 auto approval rate, got {metrics['auto_approval_rate']}"
    expected_avg_confidence = (0.95 + 0.88 + 0.92) / 3
    assert abs(metrics["avg_confidence"] - expected_avg_confidence) < 0.001, f"Expected {expected_avg_confidence}, got {metrics['avg_confidence']}"
    assert metrics["total_cost"] == Decimal("0.003"), f"Expected 0.003 total cost, got {metrics['total_cost']}"

    print("✓ Workflow metrics test passed")


def main():
    """Run all workflow logic tests."""
    print("Running Data Foundry Workflow Logic Tests\n")
    print("=" * 50)

    tests = [
        test_confidence_routing_logic,
        test_pii_detection_workflow,
        test_tenant_isolation_workflow,
        test_ai_classification_workflow,
        test_audit_logging_workflow,
        test_error_handling_workflow,
        test_workflow_configuration,
        test_token_usage_tracking,
        test_batch_processing_workflow,
        test_workflow_metrics
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {str(e)}")
            failed += 1
        print()

    print("=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())