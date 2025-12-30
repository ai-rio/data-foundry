"""
Integration Tests for Data Ingestion Flow Modifications (P01-006)

Simplified test suite that tests the actual implementations without complex mocking.

Tests:
1. compute_inter_rater_agreement - Cohen's Kappa calculation
2. route_for_human_review - Modified with Cohen's Kappa threshold
3. generate_audit_report - AML audit report generation
"""

import pytest
import asyncio
from datetime import datetime
from typing import Any, Dict


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_ai_labels():
    """Sample AI-labeled AML data."""
    return [
        {"id": 1, "aml_risk_level": "HIGH", "tenant_id": "tenant_001"},
        {"id": 2, "aml_risk_level": "LOW", "tenant_id": "tenant_001"},
        {"id": 3, "aml_risk_level": "MEDIUM", "tenant_id": "tenant_001"},
        {"id": 4, "aml_risk_level": "HIGH", "tenant_id": "tenant_001"},
    ]


@pytest.fixture
def sample_expert_reviews():
    """Sample expert review data matching AI labels."""
    return [
        {"transaction_id": 1, "expert_risk_level": "HIGH"},
        {"transaction_id": 2, "expert_risk_level": "LOW"},
        {"transaction_id": 3, "expert_risk_level": "MEDIUM"},
        {"transaction_id": 4, "expert_risk_level": "HIGH"},
    ]


@pytest.fixture
def sample_disagreement_reviews():
    """Sample expert reviews with disagreements."""
    return [
        {"transaction_id": 1, "expert_risk_level": "LOW"},
        {"transaction_id": 2, "expert_risk_level": "HIGH"},
        {"transaction_id": 3, "expert_risk_level": "LOW"},
        {"transaction_id": 4, "expert_risk_level": "MEDIUM"},
    ]


# =============================================================================
# Test: compute_inter_rater_agreement (P01-006 Requirement #2)
# =============================================================================

class TestComputeInterRaterAgreementIntegration:
    """Integration tests for compute_inter_rater_agreement."""

    @pytest.mark.asyncio
    async def test_perfect_agreement(self, sample_ai_labels, sample_expert_reviews):
        """
        Test Cohen's Kappa with perfect agreement.

        GIVEN: AI and expert classifications are identical
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns kappa = 1.0 with PERFECT confidence level
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labels,
            expert_reviews=sample_expert_reviews
        )

        assert result["kappa"] == pytest.approx(1.0, abs=0.0001)
        assert result["confidence_level"] == "PERFECT"
        assert result["is_sufficient"] is True
        assert result["sample_size"] == 4

    @pytest.mark.asyncio
    async def test_partial_agreement(self, sample_ai_labels, sample_disagreement_reviews):
        """
        Test Cohen's Kappa with partial agreement.

        GIVEN: AI and expert classifications have disagreements
        WHEN: compute_inter_rater_agreement is called
        THEN: Returns kappa between 0.0 and 1.0
        """
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labels,
            expert_reviews=sample_disagreement_reviews
        )

        assert 0.0 <= result["kappa"] <= 1.0
        assert result["sample_size"] == 4
        assert "confidence_level" in result

    @pytest.mark.asyncio
    async def test_empty_inputs(self):
        """Test handling of empty inputs."""
        from src.tasks.ingestion import compute_inter_rater_agreement

        result = await compute_inter_rater_agreement(
            ai_labels=[],
            expert_reviews=[]
        )

        assert result["kappa"] is None
        assert result["sample_size"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mismatched_ids(self, sample_ai_labels):
        """Test handling of mismatched transaction IDs."""
        from src.tasks.ingestion import compute_inter_rater_agreement

        mismatched_reviews = [
            {"transaction_id": 999, "expert_risk_level": "HIGH"}
        ]

        result = await compute_inter_rater_agreement(
            ai_labels=sample_ai_labels,
            expert_reviews=mismatched_reviews
        )

        assert result["kappa"] is None
        assert result["sample_size"] == 0
        assert "error" in result


# =============================================================================
# Test: route_for_human_review with Cohen's Kappa (P01-006 Requirement #3)
# =============================================================================

class TestRouteForHumanReviewIntegration:
    """Integration tests for modified route_for_human_review."""

    @pytest.fixture
    def sample_data(self):
        """Sample data for routing."""
        return [
            {"id": 1, "aml_risk_level": "HIGH"},
            {"id": 2, "aml_risk_level": "LOW"},
        ]

    def test_high_kappa_auto_approves(self, sample_data):
        """
        Test routing with high Cohen's Kappa.

        GIVEN: kappa = 0.85 (above threshold)
        WHEN: route_for_human_review is called
        THEN: All records auto-approved
        """
        from src.tasks.ingestion import route_for_human_review

        auto_approved, human_review = route_for_human_review(
            data=sample_data,
            kappa_score=0.85,
            kappa_threshold=0.70
        )

        assert len(auto_approved) == 2
        assert len(human_review) == 0

    def test_low_kappa_routes_for_review(self, sample_data):
        """
        Test routing with low Cohen's Kappa.

        GIVEN: kappa = 0.50 (below threshold)
        WHEN: route_for_human_review is called
        THEN: All records routed for human review
        """
        from src.tasks.ingestion import route_for_human_review

        auto_approved, human_review = route_for_human_review(
            data=sample_data,
            kappa_score=0.50,
            kappa_threshold=0.70
        )

        assert len(auto_approved) == 0
        assert len(human_review) == 2

    def test_kappa_at_threshold(self, sample_data):
        """
        Test routing at threshold boundary.

        GIVEN: kappa = 0.70 (exactly at threshold)
        WHEN: route_for_human_review is called
        THEN: Auto-approves (inclusive boundary)
        """
        from src.tasks.ingestion import route_for_human_review

        auto_approved, human_review = route_for_human_review(
            data=sample_data,
            kappa_score=0.70,
            kappa_threshold=0.70
        )

        assert len(auto_approved) == 2
        assert len(human_review) == 0

    def test_no_kappa_uses_confidence(self, sample_data):
        """
        Test legacy mode without kappa.

        GIVEN: No kappa score provided
        WHEN: route_for_human_review is called
        THEN: Uses individual confidence scores
        """
        from src.tasks.ingestion import route_for_human_review

        # Add confidence scores
        data_with_conf = [
            {**rec, "aml_confidence_score": 0.90}
            for rec in sample_data
        ]

        auto_approved, human_review = route_for_human_review(
            data=data_with_conf,
            kappa_score=None
        )

        # Should use confidence threshold (0.85 by default)
        assert len(auto_approved) + len(human_review) == 2


# =============================================================================
# Test: generate_audit_report (P01-006 Requirement #4)
# =============================================================================

class TestGenerateAuditReportIntegration:
    """Integration tests for generate_audit_report."""

    @pytest.fixture
    def sample_labeled_data(self):
        """Sample AML-labeled data."""
        return [
            {"id": 1, "aml_risk_level": "HIGH"},
            {"id": 2, "aml_risk_level": "LOW"},
            {"id": 3, "aml_risk_level": "MEDIUM"},
            {"id": 4, "aml_risk_level": "CRITICAL"},
        ]

    @pytest.mark.asyncio
    async def test_report_structure(self, sample_labeled_data):
        """Test that report has required structure."""
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            job_id="test-job-123",
            tenant_id="test-tenant",
            labeled_data=sample_labeled_data,
            kappa_score=0.75
        )

        assert "total_transactions" in report
        assert "aml_risk_distribution" in report
        assert "inter_rater_agreement" in report
        assert "expert_review_queue_size" in report
        assert "report_generated_at" in report
        assert "report_id" in report

    @pytest.mark.asyncio
    async def test_risk_distribution(self, sample_labeled_data):
        """Test AML risk distribution calculation."""
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            job_id="test-job-123",
            tenant_id="test-tenant",
            labeled_data=sample_labeled_data,
            kappa_score=0.75
        )

        dist = report["aml_risk_distribution"]
        assert dist["HIGH"] == 1
        assert dist["LOW"] == 1
        assert dist["MEDIUM"] == 1
        assert dist["CRITICAL"] == 1

    @pytest.mark.asyncio
    async def test_kappa_included(self, sample_labeled_data):
        """Test that Cohen's Kappa is included in report."""
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            job_id="test-job-123",
            tenant_id="test-tenant",
            labeled_data=sample_labeled_data,
            kappa_score=0.85
        )

        assert report["inter_rater_agreement"]["kappa_score"] == 0.85
        assert report["inter_rater_agreement"]["available"] is True
        assert "confidence_level" in report["inter_rater_agreement"]

    @pytest.mark.asyncio
    async def test_empty_data(self):
        """Test handling of empty data."""
        from src.tasks.ingestion import generate_audit_report

        report = await generate_audit_report(
            job_id="test-job-123",
            tenant_id="test-tenant",
            labeled_data=[],
            kappa_score=None
        )

        assert report["total_transactions"] == 0
        assert report["inter_rater_agreement"]["kappa_score"] is None


# =============================================================================
# Test: Quality Gates (P01-006 Quality Requirements)
# =============================================================================

class TestQualityGates:
    """Quality gate tests from P01-006."""

    def test_all_tasks_exist(self):
        """Verify all required tasks exist and are callable."""
        from src.tasks.ingestion import (
            apply_aml_labeling,
            compute_inter_rater_agreement,
            route_for_human_review,
            generate_audit_report,
        )

        assert callable(apply_aml_labeling)
        assert callable(compute_inter_rater_agreement)
        assert callable(route_for_human_review)
        assert callable(generate_audit_report)

    def test_aml_config_exists(self):
        """Verify AML configuration exists."""
        from src.core.config import AML_CONFIG

        assert "kappa_threshold" in AML_CONFIG
        assert "kappa_interpretation" in AML_CONFIG
        assert AML_CONFIG["kappa_threshold"] == 0.70

    def test_agreement_calculator_exists(self):
        """Verify CohenKappaCalculator exists."""
        from src.core.agreement_calculator import CohenKappaCalculator

        calculator = CohenKappaCalculator()
        assert calculator.threshold == 0.70

    def test_aml_enums_exist(self):
        """Verify AML enums exist."""
        from src.models.aml_enums import (
            AMLRiskLevel,
            AMLTypology,
            AMLExpertReviewStatus,
        )

        assert AMLRiskLevel.HIGH in AMLRiskLevel
        assert AMLTypology.ML in AMLTypology
        assert AMLExpertReviewStatus.PENDING in AMLExpertReviewStatus


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
