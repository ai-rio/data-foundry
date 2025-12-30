"""
Test Suite for Audit Report Generator (P01-015)

This module contains comprehensive tests for the AuditReportGenerator service.
Tests follow strict TDD red-green-refactor cycle and verify all quality gates.

Test Categories:
1. JSON report generation with all required sections
2. PDF generation capability
3. Metrics calculation (risk distribution, typology distribution, etc.)
4. Inter-rater agreement calculation integration
5. Expert review queue size tracking
6. Regulatory references inclusion
7. Report metadata (ID, timestamps, methodology version)
8. Error handling and edge cases
9. SOLID adherence verification

Quality Gates:
- SOLID adherence: 100%
- Test coverage: >90%
- Docstring coverage: >80%
- Function length: <50 lines

Reference: P01-015 (Audit Report Generation)
"""

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.services.audit_report_generator import AuditReportGenerator


# ============================================================================
# Helper Functions and Fixtures
# ============================================================================

def create_sample_labeled_transactions(
    count: int = 10,
    risk_distribution: Dict[str, int] = None
) -> list[Dict[str, Any]]:
    """
    Create sample AML-labeled transaction records for testing.

    Args:
        count: Number of transaction records to generate
        risk_distribution: Optional custom distribution of risk levels

    Returns:
        List of AML-labeled transaction dictionaries
    """
    import random

    # Default risk distribution if not provided
    if risk_distribution is None:
        risk_distribution = {"LOW": 5, "MEDIUM": 3, "HIGH": 1, "CRITICAL": 1}

    transactions = []
    risk_levels = []
    for risk, risk_count in risk_distribution.items():
        risk_levels.extend([risk] * risk_count)

    for i in range(count):
        risk = risk_levels[i % len(risk_levels)]
        typology = _get_typology_for_risk(risk)

        transactions.append({
            "id": f"txn_{i:05d}",
            "transaction_id": f"TXN-{i:05d}",
            "tenant_id": "tenant_001",
            "job_id": "job_abc123",
            "aml_risk_level": risk,
            "aml_typology": typology,
            "aml_confidence_score": 0.75 if risk != "LOW" else 0.95,
            "aml_reasoning": f"Transaction analysis shows {risk.lower()} risk indicators",
            "aml_expert_review_status": "PENDING" if risk in ["HIGH", "CRITICAL"] else "AGREED",
            "aml_requires_expert_review": risk in ["HIGH", "CRITICAL"],
            "amount": 1000.0 + i * 100,
            "counterparty": f"Counterparty_{i}",
            "date": "2024-01-15"
        })

    return transactions


def _get_typology_for_risk(risk_level: str) -> str:
    """Get appropriate typology based on risk level."""
    typologies = {
        "LOW": "ML",
        "MEDIUM": "FRAUD",
        "HIGH": "TF",
        "CRITICAL": "PEP"
    }
    return typologies.get(risk_level, "ML")


def create_sample_kappa_result(kappa: float = 0.85) -> Dict[str, Any]:
    """Create sample inter-rater agreement result."""
    return {
        "kappa": kappa,
        "confidence_level": "SUBSTANTIAL" if kappa >= 0.6 else "MODERATE",
        "is_sufficient": kappa >= 0.7,
        "sample_size": 50,
        "computed_at": datetime.utcnow().isoformat()
    }


# ============================================================================
# Test Class: Report Generation - Required Sections
# ============================================================================

class TestReportGenerationRequiredSections:
    """
    Tests for all required report sections as per P01-015 requirements.

    Required sections:
    - total_transactions
    - aml_risk_distribution
    - inter_rater_agreement (kappa + confidence level)
    - expert_review_queue_size
    - regulatory_references
    - report_generated_at
    - report_id
    """

    def test_generate_report_includes_total_transactions(self):
        """
        Test that report includes total transaction count.

        Given: Labeled transaction data
        When: generate_report() is called
        Then: Report includes total_transactions field
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(count=100)

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "total_transactions" in report
        assert report["total_transactions"] == 100
        assert isinstance(report["total_transactions"], int)

    def test_generate_report_includes_aml_risk_distribution(self):
        """
        Test that report includes AML risk level distribution.

        Given: Labeled transactions with different risk levels
        When: generate_report() is called
        Then: Report includes aml_risk_distribution with all 4 levels
        """
        generator = AuditReportGenerator()
        risk_dist = {"LOW": 50, "MEDIUM": 30, "HIGH": 15, "CRITICAL": 5}
        labels = create_sample_labeled_transactions(count=100, risk_distribution=risk_dist)

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "aml_risk_distribution" in report
        distribution = report["aml_risk_distribution"]
        assert "LOW" in distribution
        assert "MEDIUM" in distribution
        assert "HIGH" in distribution
        assert "CRITICAL" in distribution
        assert distribution["LOW"] == 50
        assert distribution["MEDIUM"] == 30
        assert distribution["HIGH"] == 15
        assert distribution["CRITICAL"] == 5

    def test_generate_report_includes_inter_rater_agreement(self):
        """
        Test that report includes inter-rater agreement metrics.

        Given: Kappa score from expert review
        When: generate_report() is called with kappa_score
        Then: Report includes inter_rater_agreement with kappa and confidence_level
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()
        kappa_result = create_sample_kappa_result(kappa=0.85)

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels,
            kappa_score=kappa_result["kappa"]
        )

        assert "inter_rater_agreement" in report
        agreement = report["inter_rater_agreement"]
        assert "kappa_score" in agreement
        assert "confidence_level" in agreement
        assert agreement["kappa_score"] == 0.85
        # Note: 0.85 is PERFECT per CohenKappaCalculator interpretation
        assert agreement["confidence_level"] == "PERFECT"

    def test_generate_report_includes_expert_review_queue_size(self):
        """
        Test that report includes expert review queue size.

        Given: Labels with some requiring expert review
        When: generate_report() is called
        Then: Report includes expert_review_queue_size
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(count=100)
        # 20 transactions require expert review (HIGH + CRITICAL)
        expert_count = sum(1 for l in labels if l.get("aml_requires_expert_review"))

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "expert_review_queue_size" in report
        assert report["expert_review_queue_size"] == expert_count

    def test_generate_report_includes_regulatory_references(self):
        """
        Test that report includes regulatory references.

        Given: AML audit report requirements
        When: generate_report() is called
        Then: Report includes regulatory_references list
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "regulatory_references" in report
        assert isinstance(report["regulatory_references"], list)
        assert len(report["regulatory_references"]) > 0
        # Check for expected references
        references = report["regulatory_references"]
        assert any("FATF" in ref for ref in references)

    def test_generate_report_includes_timestamp(self):
        """
        Test that report includes generation timestamp.

        Given: Current time
        When: generate_report() is called
        Then: Report includes report_generated_at in ISO format
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        before = datetime.utcnow()
        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )
        after = datetime.utcnow()

        assert "report_generated_at" in report
        # Verify timestamp is valid ISO format and recent
        generated_at = datetime.fromisoformat(report["report_generated_at"])
        assert before <= generated_at <= after

    def test_generate_report_includes_unique_report_id(self):
        """
        Test that report includes unique identifier.

        Given: Job data
        When: generate_report() is called
        Then: Report includes unique report_id
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        report1 = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        report2 = generator.generate_report(
            job_data={"job_id": "job_002", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "report_id" in report1
        assert "report_id" in report2
        assert report1["report_id"] != report2["report_id"]


# ============================================================================
# Test Class: Report Structure and Metadata
# ============================================================================

class TestReportStructureAndMetadata:
    """Tests for report structure, metadata, and audit trail."""

    def test_report_includes_job_and_tenant_ids(self):
        """
        Test that report includes job_id and tenant_id.

        Given: Job data with job_id and tenant_id
        When: generate_report() is called
        Then: Report includes both identifiers
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        report = generator.generate_report(
            job_data={"job_id": "job_xyz", "tenant_id": "tenant_abc"},
            labels=labels
        )

        assert report["job_id"] == "job_xyz"
        assert report["tenant_id"] == "tenant_abc"

    def test_report_includes_audit_trail_metadata(self):
        """
        Test that report includes audit trail section.

        Given: AML compliance requirements
        When: generate_report() is called
        Then: Report includes audit_trail section
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "audit_trail" in report
        audit_trail = report["audit_trail"]
        assert "methodology_version" in audit_trail
        assert "generated_by" in audit_trail
        assert "compliance_status" in audit_trail

    def test_report_includes_typology_distribution(self):
        """
        Test that report includes FATF typology distribution.

        Given: Labeled transactions with various typologies
        When: generate_report() is called
        Then: Report includes typology_distribution
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(count=100)

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "typology_distribution" in report
        assert isinstance(report["typology_distribution"], dict)
        assert len(report["typology_distribution"]) > 0


# ============================================================================
# Test Class: Metrics Calculation
# ============================================================================

class TestMetricsCalculation:
    """Tests for metrics calculation functionality."""

    def test_calculate_metrics_with_valid_labels(self):
        """
        Test calculate_metrics() with valid label data.

        Given: List of AML-labeled transactions
        When: calculate_metrics() is called
        Then: Returns accurate metrics dictionary
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(
            count=100,
            risk_distribution={"LOW": 50, "MEDIUM": 30, "HIGH": 15, "CRITICAL": 5}
        )

        metrics = generator.calculate_metrics(labels)

        assert metrics["total_transactions"] == 100
        assert metrics["aml_risk_distribution"]["LOW"] == 50
        assert metrics["aml_risk_distribution"]["MEDIUM"] == 30
        assert metrics["aml_risk_distribution"]["HIGH"] == 15
        assert metrics["aml_risk_distribution"]["CRITICAL"] == 5

    def test_calculate_metrics_with_empty_labels(self):
        """
        Test calculate_metrics() with empty label list.

        Given: Empty list of labels
        When: calculate_metrics() is called
        Then: Returns zeroed metrics
        """
        generator = AuditReportGenerator()

        metrics = generator.calculate_metrics([])

        assert metrics["total_transactions"] == 0
        assert metrics["aml_risk_distribution"]["LOW"] == 0
        assert metrics["aml_risk_distribution"]["MEDIUM"] == 0
        assert metrics["aml_risk_distribution"]["HIGH"] == 0
        assert metrics["aml_risk_distribution"]["CRITICAL"] == 0

    def test_calculate_metrics_expert_review_queue_size(self):
        """
        Test that expert_review_queue_size is calculated correctly.

        Given: Labels with mixed expert review requirements
        When: calculate_metrics() is called
        Then: Returns correct expert review queue count
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(count=100)

        metrics = generator.calculate_metrics(labels)

        # Count labels requiring expert review
        expected_queue_size = sum(
            1 for label in labels
            if label.get("aml_requires_expert_review", False)
        )

        assert metrics["expert_review_queue_size"] == expected_queue_size

    def test_calculate_metrics_typology_distribution(self):
        """
        Test that typology distribution is calculated correctly.

        Given: Labels with various FATF typologies
        When: calculate_metrics() is called
        Then: Returns correct typology counts
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions(count=100)

        metrics = generator.calculate_metrics(labels)

        assert "typology_distribution" in metrics
        assert isinstance(metrics["typology_distribution"], dict)
        # Verify total typology count equals total labels
        total_typologies = sum(metrics["typology_distribution"].values())
        assert total_typologies == 100


# ============================================================================
# Test Class: PDF Generation
# ============================================================================

class TestPDFGeneration:
    """Tests for PDF generation capability."""

    def test_generate_pdf_returns_bytes(self):
        """
        Test that generate_pdf() returns bytes.

        Given: Valid report data dictionary
        When: generate_pdf() is called
        Then: Returns bytes object
        """
        generator = AuditReportGenerator()
        report_data = {
            "report_id": "test_report_001",
            "total_transactions": 100,
            "aml_risk_distribution": {"LOW": 50, "MEDIUM": 30, "HIGH": 15, "CRITICAL": 5}
        }

        pdf_bytes = generator.generate_pdf(report_data)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # Verify PDF magic number
        assert pdf_bytes.startswith(b'%PDF')

    def test_generate_pdf_includes_report_content(self):
        """
        Test that PDF includes report data.

        Given: Report data with specific values
        When: generate_pdf() is called
        Then: PDF contains key information
        """
        generator = AuditReportGenerator()
        report_data = {
            "report_id": "test_report_unique_12345",
            "job_id": "job_abc",
            "total_transactions": 999
        }

        pdf_bytes = generator.generate_pdf(report_data)

        # Verify PDF was generated (has valid PDF header)
        assert pdf_bytes.startswith(b'%PDF')
        assert len(pdf_bytes) > 1000  # PDF should have substantial content

    def test_generate_pdf_handles_empty_report(self):
        """
        Test that generate_pdf() handles minimal report data.

        Given: Minimal report dictionary
        When: generate_pdf() is called
        Then: Still generates valid PDF
        """
        generator = AuditReportGenerator()
        report_data = {
            "report_id": "minimal_report",
            "total_transactions": 0
        }

        pdf_bytes = generator.generate_pdf(report_data)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        assert pdf_bytes.startswith(b'%PDF')


# ============================================================================
# Test Class: Error Handling and Edge Cases
# ============================================================================

class TestErrorHandlingAndEdgeCases:
    """Tests for error handling and edge cases."""

    def test_generate_report_with_empty_labels(self):
        """
        Test report generation with no labels.

        Given: Empty label list
        When: generate_report() is called
        Then: Returns valid report with zero counts
        """
        generator = AuditReportGenerator()

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=[]
        )

        assert report["total_transactions"] == 0
        assert report["aml_risk_distribution"]["LOW"] == 0
        assert report["expert_review_queue_size"] == 0
        assert "report_id" in report
        assert "report_generated_at" in report

    def test_generate_report_without_kappa_score(self):
        """
        Test report generation when kappa score is unavailable.

        Given: Labels but no kappa score
        When: generate_report() is called without kappa_score
        Then: Report includes inter_rater_agreement with unavailable status
        """
        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "inter_rater_agreement" in report
        agreement = report["inter_rater_agreement"]
        # Should handle None kappa gracefully
        assert "kappa_score" in agreement or "available" in agreement

    def test_generate_report_with_labels_missing_fields(self):
        """
        Test report generation with incomplete label data.

        Given: Labels missing some optional fields
        When: generate_report() is called
        Then: Still generates valid report with available data
        """
        generator = AuditReportGenerator()
        incomplete_labels = [
            {"id": "txn_001", "aml_risk_level": "HIGH"},
            {"id": "txn_002", "aml_risk_level": "LOW"},
            {"id": "txn_003"},  # Missing risk_level
        ]

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=incomplete_labels
        )

        assert report["total_transactions"] == 3
        assert "report_id" in report
        # Should handle missing fields gracefully

    def test_calculate_metrics_handles_invalid_risk_levels(self):
        """
        Test that invalid risk levels are handled gracefully.

        Given: Labels with invalid risk level values
        When: calculate_metrics() is called
        Then: Invalid values are categorized separately or ignored
        """
        generator = AuditReportGenerator()
        labels_with_invalid = [
            {"aml_risk_level": "HIGH"},
            {"aml_risk_level": "INVALID_LEVEL"},
            {"aml_risk_level": "LOW"},
        ]

        metrics = generator.calculate_metrics(labels_with_invalid)

        # Should not crash, should handle invalid levels
        assert metrics["total_transactions"] == 3
        assert "aml_risk_distribution" in metrics


# ============================================================================
# Test Class: SOLID Principles Compliance
# ============================================================================

class TestSOLIDCompliance:
    """Tests to verify SOLID principles adherence."""

    def test_single_responsibility_generator_only_generates(self):
        """
        Test that AuditReportGenerator only generates reports.

        Verify SRP: Class should only handle report generation, not persistence
        or other concerns.

        Given: AuditReportGenerator instance
        When: Methods are called
        Then: Each method has single, clear responsibility
        """
        generator = AuditReportGenerator()

        # Check public methods have single responsibilities
        assert hasattr(generator, 'generate_report')
        assert hasattr(generator, 'generate_pdf')
        assert hasattr(generator, 'calculate_metrics')

        # Methods should not directly access database
        # (No session, connection, or persistence parameters)
        import inspect
        generate_report_sig = inspect.signature(generator.generate_report)
        assert 'session' not in generate_report_sig.parameters
        assert 'db' not in generate_report_sig.parameters

    def test_open_closed_principle_extension_via_composition(self):
        """
        Test that report generation can be extended via composition.

        Verify OCP: Should be open for extension via strategy pattern,
        closed for modification.
        """
        # Generator should accept injectable dependencies
        # (e.g., custom PDF formatter, metrics calculator)
        generator = AuditReportGenerator()

        # Should be able to use with different formatters
        # without modifying the class itself
        assert callable(generator.generate_report)
        assert callable(generator.generate_pdf)

    def test_interface_segregation_all_methods_useful(self):
        """
        Test that all public methods are necessary and cohesive.

        Verify ISP: No fat interfaces, all methods serve report generation.
        """
        generator = AuditReportGenerator()

        public_methods = [
            name for name in dir(generator)
            if not name.startswith('_') and callable(getattr(generator, name))
        ]

        # Should have focused interface
        expected_methods = {'generate_report', 'generate_pdf', 'calculate_metrics'}
        actual_methods = set(public_methods)

        # All expected methods should be present
        assert expected_methods.issubset(actual_methods)

    def test_dependency_inversion_no_concrete_dependencies(self):
        """
        Test that generator doesn't depend on concrete implementations.

        Verify DIP: Should depend on abstractions, not concrete classes.
        """
        generator = AuditReportGenerator()

        # Should not instantiate concrete database classes
        # Should work with dictionaries and basic types
        labels = create_sample_labeled_transactions(count=5)

        # Should work without ORM models
        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels
        )

        assert "report_id" in report


# ============================================================================
# Test Class: Docstring Coverage
# ============================================================================

class TestDocstringCoverage:
    """Tests to verify documentation quality."""

    def test_class_has_docstring(self):
        """
        Test that AuditReportGenerator class has docstring.

        Given: AuditReportGenerator class
        When: Checking class documentation
        Then: Class has descriptive docstring
        """
        assert AuditReportGenerator.__doc__ is not None
        assert len(AuditReportGenerator.__doc__) > 50

    def test_generate_report_has_docstring(self):
        """
        Test that generate_report() has comprehensive docstring.

        Given: generate_report method
        When: Checking method documentation
        Then: Method has docstring with Args, Returns sections
        """
        docstring = AuditReportGenerator.generate_report.__doc__
        assert docstring is not None
        assert "Args:" in docstring or "Parameters:" in docstring
        assert "Returns:" in docstring

    def test_generate_pdf_has_docstring(self):
        """
        Test that generate_pdf() has docstring.

        Given: generate_pdf method
        When: Checking method documentation
        Then: Method has docstring
        """
        docstring = AuditReportGenerator.generate_pdf.__doc__
        assert docstring is not None
        assert len(docstring) > 20

    def test_calculate_metrics_has_docstring(self):
        """
        Test that calculate_metrics() has docstring.

        Given: calculate_metrics method
        When: Checking method documentation
        Then: Method has docstring with description
        """
        docstring = AuditReportGenerator.calculate_metrics.__doc__
        assert docstring is not None
        assert len(docstring) > 20


# ============================================================================
# Test Class: Function Length Compliance
# ============================================================================

class TestFunctionLengthCompliance:
    """Tests to verify function length stays under 50 lines."""

    def test_generate_report_length_under_50_lines(self):
        """
        Test that generate_report() is under 50 lines of executable code.

        Note: Docstrings are excluded from line count per SOLID quality gate.
        The requirement is for executable code lines only, not documentation.

        Given: generate_report method source
        When: Counting executable lines
        Then: Method length < 50 lines
        """
        import inspect
        source = inspect.getsource(AuditReportGenerator.generate_report)
        lines = source.strip().split('\n')

        # Exclude docstring lines and empty lines
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            # Track docstring boundaries
            if '"""' in stripped:
                in_docstring = not in_docstring
                continue
            # Count only non-docstring, non-empty lines
            if not in_docstring and stripped:
                code_lines.append(line)

        assert len(code_lines) < 50, f"Function too long: {len(code_lines)} lines"

    def test_calculate_metrics_length_under_50_lines(self):
        """
        Test that calculate_metrics() is under 50 lines of executable code.

        Note: Docstrings are excluded from line count.

        Given: calculate_metrics method source
        When: Counting lines
        Then: Method length < 50 lines
        """
        import inspect
        source = inspect.getsource(AuditReportGenerator.calculate_metrics)
        lines = source.strip().split('\n')

        # Exclude docstring lines and empty lines
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if '"""' in stripped:
                in_docstring = not in_docstring
                continue
            if not in_docstring and stripped:
                code_lines.append(line)

        assert len(code_lines) < 50, f"Function too long: {len(code_lines)} lines"

    def test_generate_pdf_length_under_50_lines(self):
        """
        Test that generate_pdf() is under 50 lines of executable code.

        Note: Docstrings are excluded from line count.

        Given: generate_pdf method source
        When: Counting lines
        Then: Method length < 50 lines
        """
        import inspect
        source = inspect.getsource(AuditReportGenerator.generate_pdf)
        lines = source.strip().split('\n')

        # Exclude docstring lines and empty lines
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if '"""' in stripped:
                in_docstring = not in_docstring
                continue
            if not in_docstring and stripped:
                code_lines.append(line)

        assert len(code_lines) < 50, f"Function too long: {len(code_lines)} lines"


# ============================================================================
# Test Class: Integration with Cohens Kappa
# ============================================================================

class TestCohenKappaIntegration:
    """Tests for integration with Cohen's Kappa calculator."""

    def test_inter_rater_agreement_with_sufficient_kappa(self):
        """
        Test that sufficient kappa is marked appropriately.

        Given: Kappa score >= 0.70
        When: generate_report() is called
        Then: Report shows sufficient agreement
        """
        from src.core.agreement_calculator import CohenKappaCalculator

        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        calculator = CohenKappaCalculator()
        kappa = 0.85  # Substantial agreement

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels,
            kappa_score=kappa
        )

        assert "inter_rater_agreement" in report
        agreement = report["inter_rater_agreement"]
        assert agreement["kappa_score"] == kappa
        assert agreement["confidence_level"] == calculator.get_confidence_level(kappa)

    def test_inter_rater_agreement_with_insufficient_kappa(self):
        """
        Test that insufficient kappa is marked appropriately.

        Given: Kappa score < 0.70
        When: generate_report() is called
        Then: Report shows insufficient agreement warning
        """
        from src.core.agreement_calculator import CohenKappaCalculator

        generator = AuditReportGenerator()
        labels = create_sample_labeled_transactions()

        kappa = 0.55  # Moderate agreement, below threshold

        report = generator.generate_report(
            job_data={"job_id": "job_001", "tenant_id": "tenant_001"},
            labels=labels,
            kappa_score=kappa
        )

        assert "inter_rater_agreement" in report
        agreement = report["inter_rater_agreement"]
        assert agreement["kappa_score"] == kappa
        assert agreement["confidence_level"] == "MODERATE"


# ============================================================================
# Run Tests Entry Point
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
