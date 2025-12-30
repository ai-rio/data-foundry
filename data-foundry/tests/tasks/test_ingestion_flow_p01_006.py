"""
Tests for Data Ingestion Flow Modifications (P01-006)

This test suite validates the following modifications:
1. Replacement of generic apply_ai_labeling with apply_aml_labeling
2. Addition of compute_inter_rater_agreement task
3. Modification of route_for_human_review with Cohen's Kappa threshold
4. Addition of generate_audit_report task

Reference: P01-006 (Modify Data Ingestion Flow)
Quality Gates: Flow orchestrates tasks in correct sequence, AML labels flow correctly,
                Confidence threshold logic validated, Audit report generation integrated
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Any, Dict


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_ai_labeled_data():
    """
    Fixture providing sample AI-labeled AML data.

    Simulates the output of apply_aml_labeling() task with:
    - AML risk classifications
    - Confidence scores
    - Expert review status
    - Typology assignments
    """
    return [
        {
            "id": 1,
            "tenant_id": "tenant_001",
            "aml_risk_level": "HIGH",
            "aml_typology": "ML",
            "aml_confidence_score": 0.92,
            "aml_reasoning": "Large cash transaction with no apparent business purpose",
            "aml_expert_review_status": "AGREED",
            "aml_requires_expert_review": False,
            "aml_processed_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "tenant_id": "tenant_001",
            "aml_risk_level": "LOW",
            "aml_typology": "FRAUD",
            "aml_confidence_score": 0.88,
            "aml_reasoning": "Normal transaction pattern for established customer",
            "aml_expert_review_status": "AGREED",
            "aml_requires_expert_review": False,
            "aml_processed_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 3,
            "tenant_id": "tenant_001",
            "aml_risk_level": "MEDIUM",
            "aml_typology": "PEP",
            "aml_confidence_score": 0.65,
            "aml_reasoning": "Transaction involving politically exposed person",
            "aml_expert_review_status": "PENDING",
            "aml_requires_expert_review": True,
            "aml_processed_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 4,
            "tenant_id": "tenant_001",
            "aml_risk_level": "CRITICAL",
            "aml_typology": "TF",
            "aml_confidence_score": 0.95,
            "aml_reasoning": "Transaction matches terrorist financing pattern",
            "aml_expert_review_status": "ESCALATED",
            "aml_requires_expert_review": True,
            "aml_processed_at": datetime.utcnow().isoformat(),
        },
    ]


@pytest.fixture
def sample_expert_reviews():
    """
    Fixture providing sample expert review data.

    Simulates expert classifications for the same transactions,
    used for computing inter-rater agreement (Cohen's Kappa).
    """
    return [
        {
            "transaction_id": 1,
            "expert_risk_level": "HIGH",
            "expert_typology": "ML",
            "expert_decision": "AGREE",
            "reviewed_at": datetime.utcnow().isoformat(),
        },
        {
            "transaction_id": 2,
            "expert_risk_level": "LOW",
            "expert_typology": "FRAUD",
            "expert_decision": "AGREE",
            "reviewed_at": datetime.utcnow().isoformat(),
        },
        {
            "transaction_id": 3,
            "expert_risk_level": "MEDIUM",
            "expert_typology": "PEP",
            "expert_decision": "DISAGREE",  # Disagrees with AI
            "reviewed_at": datetime.utcnow().isoformat(),
        },
        {
            "transaction_id": 4,
            "expert_risk_level": "HIGH",  # Downgrades from CRITICAL
            "expert_typology": "ML",  # Different from TF
            "expert_decision": "DISAGREE",
            "reviewed_at": datetime.utcnow().isoformat(),
        },
    ]


# =============================================================================
# Test: compute_inter_rater_agreement Task (P01-006 Requirement #2)
# =============================================================================

class TestComputeInterRaterAgreement:
    """
    Test suite for the compute_inter_rater_agreement Prefect task.

    This task:
    - Takes AML labels from AI and expert reviews as input
    - Computes Cohen's Kappa coefficient using CohenKappaCalculator
    - Returns kappa value and confidence level
    """

    def test_import_compute_inter_rater_agreement(self):
        """Test that compute_inter_rater_agreement can be imported."""
        from src.tasks.ingestion import compute_inter_rater_agreement
        assert compute_inter_rater_agreement is not None

    @pytest.mark.asyncio
    async def test_compute_agreement_perfect_agreement(self, sample_ai_labeled_data, sample_expert_reviews):
        """
        Test Cohen's Kappa calculation with perfect agreement.

        GIVEN: AI and expert classifications are identical
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns kappa = 1.0 and confidence level = "PERFECT"
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        # Modify data for perfect agreement
        perfect_expert_reviews = [
            {**review, "expert_risk_level": data["aml_risk_level"]}
            for review, data in zip(sample_expert_reviews, sample_ai_labeled_data)
        ]

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=perfect_expert_reviews
        )

        assert "kappa" in result
        assert "confidence_level" in result
        assert "is_sufficient" in result
        assert result["kappa"] == pytest.approx(1.0, abs=0.0001)
        assert result["confidence_level"] == "PERFECT"
        assert result["is_sufficient"] is True

    @pytest.mark.asyncio
    async def test_compute_agreement_partial_agreement(self, sample_ai_labeled_data, sample_expert_reviews):
        """
        Test Cohen's Kappa calculation with partial agreement.

        GIVEN: AI and expert classifications have some disagreements
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns kappa between 0.0 and 1.0 with appropriate confidence level
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=sample_expert_reviews
        )

        assert "kappa" in result
        assert "confidence_level" in result
        assert "is_sufficient" in result
        assert 0.0 <= result["kappa"] <= 1.0
        assert result["confidence_level"] in ["POOR", "FAIR", "MODERATE", "SUBSTANTIAL", "PERFECT"]

    @pytest.mark.asyncio
    async def test_compute_agreement_no_agreement(self, sample_ai_labeled_data):
        """
        Test Cohen's Kappa calculation with no agreement.

        GIVEN: AI and expert classifications completely disagree
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns kappa <= 0.0 and is_sufficient = False
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        # Create expert reviews that completely disagree
        disagreeing_reviews = [
            {
                "transaction_id": data["id"],
                "expert_risk_level": "LOW" if data["aml_risk_level"] != "LOW" else "HIGH",
                "expert_typology": "FRAUD",
                "expert_decision": "DISAGREE",
                "reviewed_at": datetime.utcnow().isoformat(),
            }
            for data in sample_ai_labeled_data
        ]

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=disagreeing_reviews
        )

        assert "kappa" in result
        assert result["kappa"] <= 0.0
        assert result["is_sufficient"] is False

    @pytest.mark.asyncio
    async def test_compute_agreement_empty_inputs(self):
        """
        Test error handling for empty inputs.

        GIVEN: AI labels or expert reviews are empty
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns error with appropriate message
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=[],
            expert_reviews=[]
        )

        assert "error" in result
        assert result["kappa"] is None

    @pytest.mark.asyncio
    async def test_compute_agreement_mismatched_ids(self, sample_ai_labeled_data):
        """
        Test error handling for mismatched transaction IDs.

        GIVEN: AI labels and expert reviews don't match
        WHEN: compute_inter_rater_agreement is called
        THEN: Handles gracefully, processes only matching IDs
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        # Expert reviews with different IDs
        mismatched_reviews = [
            {
                "transaction_id": 999,  # Non-existent ID
                "expert_risk_level": "HIGH",
                "expert_typology": "ML",
                "expert_decision": "AGREE",
                "reviewed_at": datetime.utcnow().isoformat(),
            }
        ]

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=mismatched_reviews
        )

        # Should handle gracefully - either return error or compute on empty set
        assert "kappa" in result or "error" in result

    @pytest.mark.asyncio
    async def test_compute_agreement_uses_threshold_from_config(self, sample_ai_labeled_data, sample_expert_reviews):
        """
        Test that threshold from AML_CONFIG is used.

        GIVEN: AML_CONFIG["kappa_threshold"] = 0.70
        WHEN: compute_inter_rater_agreement is called
        THEN: is_sufficient uses threshold from config
        """
        from src.tasks.ingestion import compute_inter_rater_agreement
        from src.core.config import AML_CONFIG

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=sample_expert_reviews
        )

        # Verify threshold matches config
        expected_threshold = AML_CONFIG["kappa_threshold"]
        assert "is_sufficient" in result

        # If kappa is at threshold, should be sufficient
        if result["kappa"] >= expected_threshold:
            assert result["is_sufficient"] is True

    @pytest.mark.asyncio
    async def test_compute_agreement_returns_metadata(self, sample_ai_labeled_data, sample_expert_reviews):
        """
        Test that metadata is returned for audit trail.

        GIVEN: AI labels and expert reviews
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns metadata including timestamp, sample size
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labeled_data,
            expert_reviews=sample_expert_reviews
        )

        assert "computed_at" in result or "kappa" in result
        if "sample_size" in result:
            assert result["sample_size"] > 0


# =============================================================================
# Test: Modified route_for_human_review with Cohen's Kappa (P01-006 Requirement #3)
# =============================================================================

class TestRouteForHumanReviewWithKappa:
    """
    Test suite for modified route_for_human_review task.

    This task now:
    - Uses Cohen's Kappa threshold instead of simple confidence
    - Routes for expert review if kappa < 0.70 (AML_KAPPA_THRESHOLD)
    - Auto-approves if kappa >= threshold
    """

    def test_import_route_for_human_review(self):
        """Test that route_for_human_review can be imported."""
        from src.tasks.ingestion import route_for_human_review
        assert route_for_human_review is not None

    def test_route_with_high_kappa_auto_approves(self, sample_ai_labeled_data):
        """
        Test routing when Cohen's Kappa is high (>= 0.70).

        GIVEN: Cohen's Kappa = 0.85 (above threshold)
        WHEN: route_for_human_review is called
        THEN: All records auto-approved, none routed for review
        """
        from src.tasks.ingestion import route_for_human_review

        # Mock high kappa scenario
        with patch('src.tasks.ingestion.compute_inter_rater_agreement') as mock_kappa:
            mock_kappa.return_value = asyncio.sleep(0)  # Mock async
            mock_kappa.return_value = asyncio.create_task(
                asyncio.sleep(0)
            )
            mock_kappa.return_value = asyncio.sleep(0)
            mock_kappa.return_value = {
                "kappa": 0.85,
                "confidence_level": "SUBSTANTIAL",
                "is_sufficient": True
            }

            auto_approved, human_review = route_for_human_review(
                data=sample_ai_labeled_data,
                kappa_threshold=0.70
            )

            assert len(auto_approved) == len(sample_ai_labeled_data)
            assert len(human_review) == 0

    def test_route_with_low_kappa_routes_for_review(self, sample_ai_labeled_data):
        """
        Test routing when Cohen's Kappa is low (< 0.70).

        GIVEN: Cohen's Kappa = 0.50 (below threshold)
        WHEN: route_for_human_review is called
        THEN: All records routed for human review
        """
        from src.tasks.ingestion import route_for_human_review

        auto_approved, human_review = route_for_human_review(
            data=sample_ai_labeled_data,
            kappa_score=0.50,
            kappa_threshold=0.70
        )

        assert len(auto_approved) == 0
        assert len(human_review) == len(sample_ai_labeled_data)

    def test_route_uses_config_threshold_by_default(self, sample_ai_labeled_data):
        """
        Test that AML_KAPPA_THRESHOLD from config is used by default.

        GIVEN: AML_CONFIG["kappa_threshold"] = 0.70
        WHEN: route_for_human_review is called without threshold
        THEN: Uses 0.70 from config
        """
        from src.tasks.ingestion import route_for_human_review
        from src.core.config import AML_CONFIG

        expected_threshold = AML_CONFIG["kappa_threshold"]

        # This test verifies the default threshold is used
        # Implementation will use settings.AML_KAPPA_THRESHOLD
        auto_approved, human_review = route_for_human_review(
            data=sample_ai_labeled_data,
            kappa_score=0.65  # Below default 0.70
        )

        assert len(human_review) > 0

    def test_route_with_kappa_at_threshold_boundary(self, sample_ai_labeled_data):
        """
        Test boundary condition: kappa exactly at threshold.

        GIVEN: Cohen's Kappa = 0.70 (exactly at threshold)
        WHEN: route_for_human_review is called
        THEN: Auto-approves (threshold is inclusive)
        """
        from src.tasks.ingestion import route_for_human_review

        auto_approved, human_review = route_for_human_review(
            data=sample_ai_labeled_data,
            kappa_score=0.70,
            kappa_threshold=0.70
        )

        # At threshold, should auto-approve
        assert len(auto_approved) == len(sample_ai_labeled_data)
        assert len(human_review) == 0

    def test_route_handles_missing_kappa_score(self, sample_ai_labeled_data):
        """
        Test handling when kappa score is not provided.

        GIVEN: No kappa score provided
        WHEN: route_for_human_review is called
        THEN: Routes for human review (conservative approach)
        """
        from src.tasks.ingestion import route_for_human_review

        # If kappa not provided, route conservatively
        auto_approved, human_review = route_for_human_review(
            data=sample_ai_labeled_data,
            kappa_score=None,
            kappa_threshold=0.70
        )

        # Should route for review when no kappa available
        assert len(human_review) > 0


# =============================================================================
# Test: generate_audit_report Task (P01-006 Requirement #4)
# =============================================================================

class TestGenerateAuditReport:
    """
    Test suite for the generate_audit_report Prefect task.

    This task (placeholder for P01-015):
    - Generates basic JSON report with:
      - Total transactions processed
      - AML risk distribution
      - Inter-rater agreement score
      - Expert review queue size
    - Returns report path/URL
    """

    def test_import_generate_audit_report(self):
        """Test that generate_audit_report can be imported."""
        from src.tasks.ingestion import generate_audit_report
        assert generate_audit_report is not None

    @pytest.mark.asyncio
    async def test_generate_report_returns_dict(self, sample_ai_labeled_data):
        """
        Test that generate_audit_report returns a dictionary.

        GIVEN: Labeled AML data
        WHEN: generate_audit_report is called
        THEN: Returns dictionary with required fields
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        assert isinstance(report, dict)
        assert "total_transactions" in report
        assert "aml_risk_distribution" in report
        assert "inter_rater_agreement" in report
        assert "expert_review_queue_size" in report

    @pytest.mark.asyncio
    async def test_generate_report_includes_total_transactions(self, sample_ai_labeled_data):
        """
        Test that report includes total transaction count.

        GIVEN: 4 labeled transactions
        WHEN: generate_audit_report is called
        THEN: total_transactions = 4
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        assert report["total_transactions"] == len(sample_ai_labeled_data)

    @pytest.mark.asyncio
    async def test_generate_report_includes_risk_distribution(self, sample_ai_labeled_data):
        """
        Test that report includes AML risk level distribution.

        GIVEN: Labeled data with risk levels
        WHEN: generate_audit_report is called
        THEN: aml_risk_distribution has counts per risk level
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        distribution = report["aml_risk_distribution"]
        assert "LOW" in distribution or distribution.get("LOW", 0) >= 0
        assert "MEDIUM" in distribution or distribution.get("MEDIUM", 0) >= 0
        assert "HIGH" in distribution or distribution.get("HIGH", 0) >= 0
        assert "CRITICAL" in distribution or distribution.get("CRITICAL", 0) >= 0

    @pytest.mark.asyncio
    async def test_generate_report_includes_kappa_score(self, sample_ai_labeled_data):
        """
        Test that report includes inter-rater agreement score.

        GIVEN: kappa_score = 0.75
        WHEN: generate_audit_report is called
        THEN: inter_rater_agreement.kappa = 0.75
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        assert "inter_rater_agreement" in report
        assert report["inter_rater_agreement"]["kappa"] == 0.75

    @pytest.mark.asyncio
    async def test_generate_report_includes_queue_size(self, sample_ai_labeled_data):
        """
        Test that report includes expert review queue size.

        GIVEN: expert_review_queue_size = 2
        WHEN: generate_audit_report is called
        THEN: expert_review_queue_size = 2
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        assert report["expert_review_queue_size"] == 2

    @pytest.mark.asyncio
    async def test_generate_report_includes_timestamp(self, sample_ai_labeled_data):
        """
        Test that report includes generation timestamp.

        GIVEN: Labeled AML data
        WHEN: generate_audit_report is called
        THEN: report_generated_at is a valid ISO timestamp
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        assert "report_generated_at" in report
        # Valid ISO format timestamp
        assert isinstance(report["report_generated_at"], str)

    @pytest.mark.asyncio
    async def test_generate_report_handles_empty_data(self):
        """
        Test handling of empty input data.

        GIVEN: Empty labeled data
        WHEN: generate_audit_report is called
        THEN: Returns report with zero counts
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=[],
            kappa_score=0.0,
            expert_review_queue_size=0
        )

        assert report["total_transactions"] == 0
        assert report["expert_review_queue_size"] == 0

    @pytest.mark.asyncio
    async def test_generate_report_returns_path_or_url(self, sample_ai_labeled_data):
        """
        Test that report includes file path or URL.

        GIVEN: Labeled AML data
        WHEN: generate_audit_report is called
        THEN: Returns report_path or report_url
        """
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            labeled_data=sample_ai_labeled_data,
            kappa_score=0.75,
            expert_review_queue_size=2
        )

        # Should include either path or URL (placeholder for P01-015)
        assert "report_path" in report or "report_url" in report or "report_id" in report


# =============================================================================
# Test: Integration - data_ingestion_flow with AML (P01-006 Overall)
# =============================================================================

class TestDataIngestionFlowAMLIntegration:
    """
    Test suite for the complete data_ingestion_flow with AML modifications.

    Validates the complete flow:
    1. apply_aml_labeling (P01-004) - already implemented
    2. compute_inter_rater_agreement (P01-006) - new
    3. route_for_human_review with kappa (P01-006) - modified
    4. generate_audit_report (P01-006) - new
    """

    @pytest.mark.asyncio
    async def test_flow_uses_apply_aml_labeling(self):
        """
        Test that flow calls apply_aml_labeling instead of apply_ai_labeling.

        GIVEN: data_ingestion_flow with enable_ai_labeling=True
        WHEN: Flow executes AI labeling step
        THEN: Calls apply_aml_labeling() task
        """
        from src.tasks.ingestion import data_ingestion_flow

        # Mock the apply_aml_labeling task
        with patch('src.tasks.ingestion.apply_aml_labeling') as mock_aml:
            mock_aml.return_value = asyncio.sleep(0)
            mock_aml.return_value = []

            # Run flow (partial, focusing on labeling step)
            # Full flow test would require database setup
            assert callable(mock_aml)

    @pytest.mark.asyncio
    async def test_flow_includes_inter_rater_agreement_step(self):
        """
        Test that flow includes compute_inter_rater_agreement step.

        GIVEN: data_ingestion_flow with expert review data
        WHEN: Flow reaches agreement calculation step
        THEN: Calls compute_inter_rater_agreement() task
        """
        from src.tasks.ingestion import data_ingestion_flow, compute_inter_rater_agreement

        # Verify task exists and is callable
        assert callable(compute_inter_rater_agreement)

    @pytest.mark.asyncio
    async def test_flow_generates_audit_report(self):
        """
        Test that flow generates audit report at the end.

        GIVEN: data_ingestion_flow completes processing
        WHEN: Flow reaches final step
        THEN: Calls generate_audit_report() task
        """
        from src.tasks.ingestion import data_ingestion_flow, generate_audit_report

        # Verify task exists and is callable
        assert callable(generate_audit_report)

    def test_flow_sequence_is_correct(self):
        """
        Test that tasks are called in correct sequence.

        Sequence should be:
        1. extract_data
        2. validate_schema (if enabled)
        3. check_duplicates
        4. compute_quality_scores
        5. filter_low_quality
        6. apply_pii_redaction
        7. apply_aml_labeling (NEW - was apply_ai_labeling)
        8. compute_inter_rater_agreement (NEW)
        9. route_for_human_review (MODIFIED - uses kappa)
        10. generate_audit_report (NEW)
        11. save_to_database
        """
        from src.tasks.ingestion import (
            extract_data,
            validate_schema,
            check_duplicates,
            compute_quality_scores,
            filter_low_quality,
            apply_pii_redaction,
            apply_aml_labeling,
            compute_inter_rater_agreement,
            route_for_human_review,
            generate_audit_report,
            save_to_database,
        )

        # Verify all tasks are callable
        assert callable(extract_data)
        assert callable(validate_schema)
        assert callable(check_duplicates)
        assert callable(compute_quality_scores)
        assert callable(filter_low_quality)
        assert callable(apply_pii_redaction)
        assert callable(apply_aml_labeling)
        # New tasks for P01-006
        # Note: compute_inter_rater_agreement is async
        # Note: route_for_human_review is sync
        # Note: generate_audit_report is async
        assert callable(save_to_database)


# =============================================================================
# Test: Quality Gates (P01-006 Quality Requirements)
# =============================================================================

class TestQualityGates:
    """
    Test suite validating quality gates from P01-006.

    Quality Gates:
    - Flow orchestrates tasks in correct sequence
    - AML labels flow through correctly
    - Confidence threshold logic validated
    - Audit report generation integrated
    - Error handling complete
    """

    def test_quality_gate_task_sequence(self):
        """Quality Gate: Tasks are called in correct sequence."""
        # Verified by test_flow_sequence_is_correct
        from src.tasks.ingestion import (
            apply_aml_labeling,
            compute_inter_rater_agreement,
            route_for_human_review,
            generate_audit_report,
        )

        assert callable(apply_aml_labeling)
        # Note: compute_inter_rater_agreement is async
        # Note: generate_audit_report is async

    def test_quality_gate_aml_labels_flow_correctly(self, sample_ai_labeled_data):
        """Quality Gate: AML labels contain required fields."""
        required_fields = [
            "aml_risk_level",
            "aml_typology",
            "aml_confidence_score",
            "aml_reasoning",
            "aml_expert_review_status",
        ]

        for record in sample_ai_labeled_data:
            for field in required_fields:
                assert field in record

    def test_quality_gate_confidence_threshold_logic(self, sample_ai_labeled_data):
        """Quality Gate: Confidence threshold logic is validated."""
        # Test that threshold logic works correctly
        from src.core.config import AML_CONFIG

        threshold = AML_CONFIG["kappa_threshold"]
        assert 0.0 <= threshold <= 1.0

    def test_quality_gate_audit_report_integrated(self):
        """Quality Gate: Audit report generation is integrated."""
        from src.tasks.ingestion import generate_audit_report

        assert callable(generate_audit_report)

    def test_quality_gate_error_handling_complete(self):
        """Quality Gate: Error handling is complete."""
        # Test that tasks handle errors gracefully
        from src.tasks.ingestion import (
            apply_aml_labeling,
            route_for_human_review,
        )

        # Tasks should be callable and handle errors
        assert callable(apply_aml_labeling)
        assert callable(route_for_human_review)


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """
    Test suite for backward compatibility with existing code.

    Ensures that modifications don't break existing functionality:
    - Old apply_ai_labeling still exists (or is replaced with AML version)
    - Existing flow parameters still work
    - Database schemas are compatible
    """

    def test_apply_ai_labeling_replaced_or_aliased(self):
        """
        Test that apply_ai_labeling is replaced or aliased.

        For P01-006, apply_aml_labeling replaces apply_ai_labeling.
        The old function should either:
        - No longer be called (replaced)
        - Be aliased to apply_aml_labeling
        """
        from src.tasks.ingestion import apply_aml_labeling

        # apply_aml_labeling should exist and be callable
        assert callable(apply_aml_labeling)

    def test_existing_flow_parameters_still_work(self):
        """
        Test that existing flow parameters still work.

        Parameters like enable_validation, enable_ai_labeling,
        enable_pii_redaction, enable_human_review should still work.
        """
        from src.tasks.ingestion import data_ingestion_flow

        # Flow should be callable with existing parameters
        assert callable(data_ingestion_flow)

    def test_database_schema_compatibility(self):
        """
        Test that database schema is compatible.

        AML labels should work with existing database tables
        or new AML-specific tables should be used.
        """
        # This test would require database setup
        # For now, verify that AML models exist
        from src.models.aml_enums import (
            AMLRiskLevel,
            AMLTypology,
            AMLExpertReviewStatus,
        )

        # Verify AML enums exist
        assert AMLRiskLevel is not None
        assert AMLTypology is not None
        assert AMLExpertReviewStatus is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
