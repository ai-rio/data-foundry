"""
Unit Tests for AML Test Harness Assertions (P01-021)

This test suite validates the AML-specific assertion functions added to
the Phase 2 API test harness. These assertions verify:

1. Records downloaded > 0 (CRITICAL FIX)
2. AML labels present in response
3. Confidence scores valid
4. Audit report generated

Reference: P01-021 (Update Test Harness)
Quality Gates: All assertions pass, records >0, report metrics verified
"""

import pytest
import pandas as pd
from typing import Dict, Any

# Import the assertion functions from the test harness
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from test_harness_phase2_api import (
    assert_records_downloaded,
    assert_aml_labels_present,
    assert_confidence_scores_present,
    assert_audit_report_generated,
    validate_aml_metrics,
    AML_RISK_LEVELS,
    AML_CONFIDENCE_THRESHOLD,
    AML_KAPPA_THRESHOLD,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_job_response():
    """
    Fixture providing a valid AML job response.

    Includes all required AML fields:
    - aml_risk_level_counts
    - aml_inter_rater_agreement
    - aml_expert_review_count
    - audit_report_url
    """
    return {
        "job_id": "test-job-123",
        "status": "completed",
        "aml_risk_level_counts": {
            "LOW": 50,
            "MEDIUM": 30,
            "HIGH": 15,
            "CRITICAL": 5
        },
        "aml_inter_rater_agreement": 0.75,
        "aml_expert_review_count": 20,
        "audit_report_url": "https://s3.amazonaws.com/bucket/audit-report-123.pdf",
        "metadata": {
            "generated_at": "2024-01-15T10:30:00Z"
        }
    }


@pytest.fixture
def sample_results_dataframe():
    """
    Fixture providing a valid AML results DataFrame.

    Contains labeled transactions with:
    - confidence_score (0.0 - 1.0)
    - aml_risk_level
    - Other AML fields
    """
    data = {
        "transaction_id": [1, 2, 3, 4, 5],
        "aml_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL", "LOW"],
        "aml_typology": ["FRAUD", "ML", "TF", "PEP", "FRAUD"],
        "confidence_score": [0.85, 0.72, 0.91, 0.68, 0.95],
        "aml_reasoning": [
            "Normal transaction pattern",
            "Suspicious cash deposit",
            "Matches terrorist financing pattern",
            "Politically exposed person involved",
            "Normal transaction pattern"
        ]
    }
    return pd.DataFrame(data)


@pytest.fixture
def invalid_results_dataframe():
    """
    Fixture providing an invalid AML results DataFrame.

    Contains invalid confidence scores for testing validation.
    """
    data = {
        "transaction_id": [1, 2, 3],
        "aml_risk_level": ["LOW", "MEDIUM", "HIGH"],
        "confidence_score": [0.85, -0.1, 1.5]  # Invalid: negative and >1.0
    }
    return pd.DataFrame(data)


# =============================================================================
# Test: assert_records_downloaded (CRITICAL FIX)
# =============================================================================

class TestAssertRecordsDownloaded:
    """
    Test suite for assert_records_downloaded function.

    This is the CRITICAL FIX for P01-021 - ensuring we actually
    downloaded records instead of getting 0.
    """

    def test_positive_record_count_passes(self):
        """
        Test that positive record count passes assertion.

        GIVEN: count = 100
        WHEN: assert_records_downloaded is called
        THEN: Returns (True, success_message)
        """
        passed, message = assert_records_downloaded(100)

        assert passed is True
        assert "✓" in message
        assert "100" in message
        assert ">0" in message

    def test_zero_record_count_fails(self):
        """
        Test that zero record count fails assertion.

        GIVEN: count = 0
        WHEN: assert_records_downloaded is called
        THEN: Returns (False, error_message with "CRITICAL")
        """
        passed, message = assert_records_downloaded(0)

        assert passed is False
        assert "CRITICAL" in message
        assert "Expected >0" in message
        assert "got 0" in message

    def test_negative_record_count_fails(self):
        """
        Test that negative record count fails assertion.

        GIVEN: count = -1
        WHEN: assert_records_downloaded is called
        THEN: Returns (False, error_message)
        """
        passed, message = assert_records_downloaded(-1)

        assert passed is False
        assert "CRITICAL" in message

    def test_large_record_count_passes(self):
        """
        Test that large record count passes assertion.

        GIVEN: count = 1000000
        WHEN: assert_records_downloaded is called
        THEN: Returns True
        """
        passed, message = assert_records_downloaded(1000000)

        assert passed is True


# =============================================================================
# Test: assert_aml_labels_present
# =============================================================================

class TestAssertAmlLabelsPresent:
    """
    Test suite for assert_aml_labels_present function.

    Validates that AML labels are present in job results.
    """

    def test_complete_aml_response_passes(self, sample_job_response):
        """
        Test that complete AML response passes all checks.

        GIVEN: Response with all AML fields present
        WHEN: assert_aml_labels_present is called
        THEN: Returns (True, success_message, extracted_data)
        """
        passed, message, extracted = assert_aml_labels_present(sample_job_response)

        assert passed is True
        assert "✓" in message
        assert "aml_risk_level_counts" in extracted
        assert "aml_inter_rater_agreement" in extracted
        assert "aml_expert_review_count" in extracted

    def test_missing_risk_level_counts_fails(self):
        """
        Test that missing risk_level_counts fails assertion.

        GIVEN: Response without aml_risk_level_counts
        WHEN: assert_aml_labels_present is called
        THEN: Returns (False, error_message, {})
        """
        response = {"job_id": "test-job-123"}
        passed, message, extracted = assert_aml_labels_present(response)

        assert passed is False
        assert "Missing aml_risk_level_counts" in message
        assert extracted == {}

    def test_incomplete_risk_levels_fail(self):
        """
        Test that incomplete risk levels fail assertion.

        GIVEN: Response with only some risk levels
        WHEN: assert_aml_labels_present is called
        THEN: Returns (False, error_message listing missing levels)
        """
        response = {
            "job_id": "test-job-123",
            "aml_risk_level_counts": {
                "LOW": 50,
                "MEDIUM": 30
                # Missing HIGH and CRITICAL
            },
            "aml_inter_rater_agreement": 0.75,
            "aml_expert_review_count": 20
        }
        passed, message, extracted = assert_aml_labels_present(response)

        assert passed is False
        assert "Missing risk level" in message

    def test_non_numeric_inter_rater_agreement_fails(self):
        """
        Test that non-numeric inter-rater agreement fails.

        GIVEN: Response with string instead of float for kappa
        WHEN: assert_aml_labels_present is called
        THEN: Returns (False, error_message)
        """
        response = {
            "job_id": "test-job-123",
            "aml_risk_level_counts": {level: 0 for level in AML_RISK_LEVELS},
            "aml_inter_rater_agreement": "high",  # Should be numeric
            "aml_expert_review_count": 20
        }
        passed, message, extracted = assert_aml_labels_present(response)

        assert passed is False
        assert "not numeric" in message.lower()

    def test_non_integer_expert_review_count_fails(self):
        """
        Test that non-integer expert review count fails.

        GIVEN: Response with float instead of int for count
        WHEN: assert_aml_labels_present is called
        THEN: Returns (False, error_message)
        """
        response = {
            "job_id": "test-job-123",
            "aml_risk_level_counts": {level: 0 for level in AML_RISK_LEVELS},
            "aml_inter_rater_agreement": 0.75,
            "aml_expert_review_count": 20.5  # Should be int
        }
        passed, message, extracted = assert_aml_labels_present(response)

        assert passed is False
        assert "not integer" in message.lower()


# =============================================================================
# Test: assert_confidence_scores_present
# =============================================================================

class TestAssertConfidenceScoresPresent:
    """
    Test suite for assert_confidence_scores_present function.

    Validates that confidence scores are included and valid.
    """

    def test_valid_confidence_scores_pass(self, sample_results_dataframe):
        """
        Test that valid confidence scores pass assertion.

        GIVEN: DataFrame with valid confidence scores (0.0-1.0)
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (True, success_message)
        """
        # Create DataFrame with all scores above threshold
        data = {
            "transaction_id": [1, 2, 3, 4, 5],
            "confidence_score": [0.85, 0.90, 0.95, 0.80, 0.88]
        }
        df = pd.DataFrame(data)

        passed, message = assert_confidence_scores_present(df)

        assert passed is True
        assert "✓" in message or "⚠" in message  # Both are valid pass indicators

    def test_empty_dataframe_fails(self):
        """
        Test that empty DataFrame fails assertion.

        GIVEN: Empty DataFrame
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (False, error_message)
        """
        df = pd.DataFrame()
        passed, message = assert_confidence_scores_present(df)

        assert passed is False
        assert "No results" in message

    def test_missing_confidence_column_fails(self):
        """
        Test that missing confidence_score column fails.

        GIVEN: DataFrame without confidence_score column
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (False, error_message)
        """
        df = pd.DataFrame({"transaction_id": [1, 2, 3]})
        passed, message = assert_confidence_scores_present(df)

        assert passed is False
        assert "Missing confidence_score" in message

    def test_invalid_confidence_scores_fail(self, invalid_results_dataframe):
        """
        Test that invalid confidence scores fail assertion.

        GIVEN: DataFrame with scores outside 0.0-1.0 range
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (False, error_message)
        """
        passed, message = assert_confidence_scores_present(invalid_results_dataframe)

        assert passed is False
        assert "invalid" in message.lower()
        assert "0.0-1.0" in message

    def test_scores_below_threshold_warn(self):
        """
        Test that scores below threshold generate warning.

        GIVEN: DataFrame with scores below AML_CONFIDENCE_THRESHOLD
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (True, warning_message) - still passes but warns
        """
        data = {
            "transaction_id": [1, 2],
            "confidence_score": [0.65, 0.68]  # Below default 0.70 threshold
        }
        df = pd.DataFrame(data)

        passed, message = assert_confidence_scores_present(df)

        # Should pass but with warning
        assert passed is True
        assert "⚠" in message  # Warning symbol
        assert "below threshold" in message.lower()

    def test_aml_confidence_column_accepted(self):
        """
        Test that aml_confidence_score column is accepted.

        GIVEN: DataFrame with aml_confidence_score column
        WHEN: assert_confidence_scores_present is called
        THEN: Returns (True, success_message)
        """
        data = {
            "transaction_id": [1, 2, 3],
            "aml_confidence_score": [0.85, 0.90, 0.95]
        }
        df = pd.DataFrame(data)

        passed, message = assert_confidence_scores_present(df)

        assert passed is True
        assert "✓" in message


# =============================================================================
# Test: assert_audit_report_generated
# =============================================================================

class TestAssertAuditReportGenerated:
    """
    Test suite for assert_audit_report_generated function.

    Validates that audit report URL is present in job metadata.
    """

    def test_audit_report_url_present_passes(self, sample_job_response):
        """
        Test that audit_report_url field passes assertion.

        GIVEN: Job data with audit_report_url field
        WHEN: assert_audit_report_generated is called
        THEN: Returns (True, success_message)
        """
        passed, message = assert_audit_report_generated(
            "test-job-123",
            sample_job_response
        )

        assert passed is True
        assert "✓" in message
        assert "Audit report generated" in message

    def test_report_url_in_metadata_passes(self):
        """
        Test that report_url in nested metadata passes.

        GIVEN: Job data with report_url in metadata object
        WHEN: assert_audit_report_generated is called
        THEN: Returns (True, success_message)
        """
        job_data = {
            "job_id": "test-job-123",
            "metadata": {
                "report_url": "https://s3.amazonaws.com/bucket/report.pdf"
            }
        }

        passed, message = assert_audit_report_generated("test-job-123", job_data)

        assert passed is True

    def test_missing_audit_report_fails(self):
        """
        Test that missing audit report URL fails assertion.

        GIVEN: Job data without audit report URL
        WHEN: assert_audit_report_generated is called
        THEN: Returns (False, error_message)
        """
        job_data = {"job_id": "test-job-123"}

        passed, message = assert_audit_report_generated("test-job-123", job_data)

        assert passed is False
        assert "not found" in message.lower()

    def test_empty_string_audit_url_fails(self):
        """
        Test that empty audit report URL fails assertion.

        GIVEN: Job data with empty audit_report_url
        WHEN: assert_audit_report_generated is called
        THEN: Returns (False, error_message)
        """
        job_data = {
            "job_id": "test-job-123",
            "audit_report_url": ""
        }

        passed, message = assert_audit_report_generated("test-job-123", job_data)

        assert passed is False
        # Empty string is treated as "not found" or "invalid"
        assert "Invalid" in message or "not found" in message.lower()

    def test_invalid_url_format_fails(self):
        """
        Test that invalid URL format fails assertion.

        GIVEN: Job data with malformed URL
        WHEN: assert_audit_report_generated is called
        THEN: Returns (False, error_message)
        """
        job_data = {
            "job_id": "test-job-123",
            "audit_report_url": "not-a-valid-url"
        }

        passed, message = assert_audit_report_generated("test-job-123", job_data)

        assert passed is False
        assert "invalid format" in message.lower()


# =============================================================================
# Test: validate_aml_metrics (Integration)
# =============================================================================

class TestValidateAmlMetrics:
    """
    Test suite for validate_aml_metrics integration function.

    Tests comprehensive AML metrics validation combining all assertions.
    """

    def test_complete_validation_passes(
        self,
        sample_job_response,
        sample_results_dataframe
    ):
        """
        Test that all validations pass with complete data.

        GIVEN: Valid job response and results DataFrame
        WHEN: validate_aml_metrics is called
        THEN: Returns validation with passed=True and no errors
        """
        validation = validate_aml_metrics(
            "test-job-123",
            sample_job_response,
            sample_results_dataframe
        )

        assert validation["passed"] is True
        assert len(validation["errors"]) == 0
        assert validation["assertions"]["records_downloaded_gt_zero"] is True
        assert validation["assertions"]["aml_labels_present"] is True
        assert validation["assertions"]["confidence_scores_valid"] is True
        assert validation["assertions"]["audit_report_generated"] is True

    def test_zero_records_fails_critical_gate(self, sample_job_response):
        """
        Test that zero records fails critical gate.

        GIVEN: Empty results DataFrame
        WHEN: validate_aml_metrics is called
        THEN: Validation fails with CRITICAL error
        """
        empty_df = pd.DataFrame()

        validation = validate_aml_metrics(
            "test-job-123",
            sample_job_response,
            empty_df
        )

        assert validation["passed"] is False
        assert validation["assertions"]["records_downloaded_gt_zero"] is False
        assert any("CRITICAL" in error for error in validation["errors"])

    def test_missing_aml_labels_fails(self, sample_results_dataframe):
        """
        Test that missing AML labels fails validation.

        GIVEN: Job response without AML fields
        WHEN: validate_aml_metrics is called
        THEN: Validation fails with appropriate error
        """
        incomplete_response = {"job_id": "test-job-123"}

        validation = validate_aml_metrics(
            "test-job-123",
            incomplete_response,
            sample_results_dataframe
        )

        assert validation["passed"] is False
        assert validation["assertions"]["aml_labels_present"] is False
        assert any("aml_risk_level_counts" in error for error in validation["errors"])

    def test_metrics_extracted_correctly(
        self,
        sample_job_response,
        sample_results_dataframe
    ):
        """
        Test that metrics are extracted correctly.

        GIVEN: Valid job response and results
        WHEN: validate_aml_metrics is called
        THEN: Metrics dictionary contains expected data
        """
        validation = validate_aml_metrics(
            "test-job-123",
            sample_job_response,
            sample_results_dataframe
        )

        metrics = validation["metrics"]

        assert "records_count" in metrics
        assert metrics["records_count"] == len(sample_results_dataframe)
        assert "aml_risk_level_counts" in metrics
        assert "aml_inter_rater_agreement" in metrics
        assert "aml_expert_review_count" in metrics


# =============================================================================
# Test: Quality Gates
# =============================================================================

class TestQualityGates:
    """
    Test suite validating quality gates from P01-021.

    Quality Gates:
    - AML assertions pass
    - >0 records downloaded
    - Report metrics verified
    """

    def test_quality_gate_critical_fix_records_gt_zero(self):
        """
        Quality Gate: Records downloaded > 0 (CRITICAL FIX).

        This is the critical fix for P01-021.
        """
        passed, _ = assert_records_downloaded(1)
        assert passed is True

        passed, message = assert_records_downloaded(0)
        assert passed is False
        assert "CRITICAL" in message

    def test_quality_gate_aml_assertions_pass(
        self,
        sample_job_response,
        sample_results_dataframe
    ):
        """
        Quality Gate: AML assertions pass.

        All individual assertions should pass.
        """
        # Each assertion should pass
        passed, _, _ = assert_aml_labels_present(sample_job_response)
        assert passed is True

        passed, _ = assert_confidence_scores_present(sample_results_dataframe)
        assert passed is True

        passed, _ = assert_audit_report_generated("test-job-123", sample_job_response)
        assert passed is True

    def test_quality_gate_report_metrics_verified(
        self,
        sample_job_response,
        sample_results_dataframe
    ):
        """
        Quality Gate: Report metrics are verified.

        Validation should extract and verify all required metrics.
        """
        validation = validate_aml_metrics(
            "test-job-123",
            sample_job_response,
            sample_results_dataframe
        )

        # Verify metrics are extracted
        assert "metrics" in validation
        assert "assertions" in validation

        # Verify all required metrics are present
        metrics = validation["metrics"]
        assert "records_count" in metrics
        assert "aml_risk_level_counts" in metrics
        assert "aml_inter_rater_agreement" in metrics
        assert "aml_expert_review_count" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
