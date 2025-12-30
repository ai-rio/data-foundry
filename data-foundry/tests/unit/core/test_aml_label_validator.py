"""
Test suite for AML Label Validator - Comprehensive validation testing

This test suite validates:
1. Valid data passes validation
2. Invalid data fails with clear error messages
3. All field types are validated (string, enum, list, json, etc.)
4. Edge cases (null values, empty strings, boundaries)
5. Regulatory flags JSON validation
6. Transaction ID and Tenant ID validation

Reference: P01-023 - Critical Database Fixes
Target Coverage: >95% of validator code
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.core.aml_label_validator import AMLLabelValidator, ValidationError, ValidationResult
from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus


class TestAMLLabelValidatorRequiredFields:
    """Test validation of required fields."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_valid_data_passes(self):
        """Test that valid AML label data passes all validation checks."""
        valid_data = {
            "transaction_id": "txn_12345",
            "tenant_id": "tenant_001",
            "job_id": "job_abc123",
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": 0.85,
            "ai_reasoning": "Transaction shows multiple red flags including structuring behavior"
        }

        result = self.validator.validate(valid_data)

        assert result.is_valid is True, "Valid data should pass validation"
        assert len(result.errors) == 0, "Valid data should have no errors"
        assert result.validated_data is not None, "Valid data should return validated_data"
        assert result.validated_data["transaction_id"] == "txn_12345"
        assert result.validated_data["risk_level"] == AMLRiskLevel.HIGH

    def test_missing_transaction_id(self):
        """Test validation fails when transaction_id is missing."""
        invalid_data = {
            # "transaction_id": missing
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "TF",
            "confidence_score": 0.75,
            "ai_reasoning": "Test reasoning"
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "transaction_id" for err in result.errors)
        assert any(err.error_code == "MISSING_REQUIRED_FIELD" for err in result.errors)

    def test_missing_tenant_id(self):
        """Test validation fails when tenant_id is missing."""
        invalid_data = {
            "transaction_id": "txn_001",
            # "tenant_id": missing
            "job_id": "job_001",
            "risk_level": "LOW",
            "typology": "FRAUD",
            "confidence_score": 0.60,
            "ai_reasoning": "Test reasoning"
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "tenant_id" for err in result.errors)

    def test_missing_job_id(self):
        """Test validation fails when job_id is missing."""
        invalid_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            # "job_id": missing
            "risk_level": "CRITICAL",
            "typology": "ML",
            "confidence_score": 0.95,
            "ai_reasoning": "Test reasoning"
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "job_id" for err in result.errors)

    def test_missing_risk_level(self):
        """Test validation fails when risk_level is missing."""
        invalid_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            # "risk_level": missing
            "typology": "TF",
            "confidence_score": 0.80,
            "ai_reasoning": "Test reasoning"
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "risk_level" for err in result.errors)

    def test_missing_confidence_score(self):
        """Test validation fails when confidence_score is missing."""
        invalid_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "ML",
            # "confidence_score": missing
            "ai_reasoning": "Test reasoning"
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "confidence_score" for err in result.errors)

    def test_missing_ai_reasoning(self):
        """Test validation fails when ai_reasoning is missing."""
        invalid_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "FRAUD",
            "confidence_score": 0.70
            # "ai_reasoning": missing
        }

        result = self.validator.validate(invalid_data)

        assert result.is_valid is False
        assert any(err.field == "ai_reasoning" for err in result.errors)


class TestAMLLabelValidatorFieldTypes:
    """Test validation of field types and formats."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_empty_transaction_id(self):
        """Test validation fails for empty transaction_id."""
        data = {
            "transaction_id": "",  # Empty string
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "LOW",
            "typology": "ML",
            "confidence_score": 0.65,
            "ai_reasoning": "Test reasoning for empty transaction validation"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "EMPTY_TRANSACTION_ID" for err in result.errors)

    def test_empty_tenant_id(self):
        """Test validation fails for empty tenant_id."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "   ",  # Whitespace only
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "TF",
            "confidence_score": 0.75,
            "ai_reasoning": "Test reasoning for empty tenant validation"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "EMPTY_TENANT_ID" for err in result.errors)

    def test_empty_job_id(self):
        """Test validation fails for empty job_id."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "",  # Empty
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": 0.85,
            "ai_reasoning": "Test reasoning for empty job_id validation"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "EMPTY_JOB_ID" for err in result.errors)

    def test_invalid_risk_level(self):
        """Test validation fails for invalid risk_level enum."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "SUPER_HIGH",  # Invalid enum value
            "typology": "ML",
            "confidence_score": 0.80,
            "ai_reasoning": "Test reasoning for invalid risk level"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.field == "risk_level" for err in result.errors)
        assert any(err.error_code == "INVALID_RISK_LEVEL" for err in result.errors)
        assert any("LOW, MEDIUM, HIGH, CRITICAL" in err.message for err in result.errors)

    def test_valid_risk_levels(self):
        """Test all valid risk level enums are accepted."""
        base_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "typology": "ML",
            "confidence_score": 0.80,
            "ai_reasoning": "Test reasoning for valid risk levels"
        }

        for risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            data = {**base_data, "risk_level": risk_level}
            result = self.validator.validate(data)
            assert result.is_valid is True, f"Risk level {risk_level} should be valid"

    def test_empty_typology(self):
        """Test validation fails for empty typology."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "",  # Empty
            "confidence_score": 0.70,
            "ai_reasoning": "Test reasoning for empty typology validation"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "EMPTY_TYPOLOGY" for err in result.errors)

    def test_valid_fatf_typologies(self):
        """Test all valid FATF typologies are accepted."""
        base_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "confidence_score": 0.85,
            "ai_reasoning": "Test reasoning for valid FATF typologies"
        }

        valid_typologies = [
            "ML", "TF", "PEP", "FRAUD", "SANCTIONS", "TAX_EVASION",
            "BRIBERY", "SMUGGLING", "DRUG_TRAFFICKING", "HUMAN_TRAFFICKING",
            "PROLIFERATION", "CYBERCRIME", "ENVIRONMENTAL"
        ]

        for typology in valid_typologies:
            data = {**base_data, "typology": typology}
            result = self.validator.validate(data)
            assert result.is_valid is True, f"Typology {typology} should be valid"
            assert result.validated_data["typology"] == typology

    def test_non_standard_typology_warning(self):
        """Test non-standard typology triggers warning but passes validation."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "CUSTOM_TYPE",  # Non-standard
            "confidence_score": 0.75,
            "ai_reasoning": "Test reasoning for non-standard typology"
        }

        result = self.validator.validate(data)

        assert result.is_valid is True, "Non-standard typology should pass with warning"
        assert len(result.warnings) > 0, "Should have warning"
        assert any(warn.error_code == "NON_STANDARD_TYPOLOGY" for warn in result.warnings)

    def test_typology_normalized_to_uppercase(self):
        """Test typology is normalized to uppercase."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "ml",  # Lowercase
            "confidence_score": 0.85,
            "ai_reasoning": "Test reasoning for typology normalization"
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert result.validated_data["typology"] == "ML", "Typology should be uppercase"


class TestAMLLabelValidatorConfidenceScore:
    """Test validation of confidence_score field."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_confidence_score_valid_range(self):
        """Test confidence scores in valid range (0.0 to 1.0) are accepted."""
        base_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "ML",
            "ai_reasoning": "Test reasoning for confidence score validation"
        }

        valid_scores = [0.0, 0.1, 0.5, 0.75, 0.99, 1.0]

        for score in valid_scores:
            data = {**base_data, "confidence_score": score}
            result = self.validator.validate(data)
            assert result.is_valid is True, f"Confidence score {score} should be valid"
            assert result.validated_data["confidence_score"] == Decimal(str(score))

    def test_confidence_score_below_range(self):
        """Test confidence score below 0.0 is rejected."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "LOW",
            "typology": "FRAUD",
            "confidence_score": -0.5,  # Below 0
            "ai_reasoning": "Test reasoning for negative confidence"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "CONFIDENCE_OUT_OF_RANGE" for err in result.errors)

    def test_confidence_score_above_range(self):
        """Test confidence score above 1.0 is rejected."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "TF",
            "confidence_score": 1.5,  # Above 1.0
            "ai_reasoning": "Test reasoning for high confidence"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "CONFIDENCE_OUT_OF_RANGE" for err in result.errors)

    def test_confidence_score_invalid_type(self):
        """Test invalid confidence score type is rejected."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "ML",
            "confidence_score": "not_a_number",  # Invalid type
            "ai_reasoning": "Test reasoning for invalid confidence type"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "INVALID_CONFIDENCE_SCORE" for err in result.errors)

    def test_confidence_score_accepts_decimal(self):
        """Test confidence score accepts Decimal type."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": Decimal("0.8546"),
            "ai_reasoning": "Test reasoning for decimal confidence"
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert isinstance(result.validated_data["confidence_score"], Decimal)


class TestAMLLabelValidatorReasoning:
    """Test validation of ai_reasoning field."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_empty_reasoning(self):
        """Test empty ai_reasoning is rejected."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "FRAUD",
            "confidence_score": 0.70,
            "ai_reasoning": ""  # Empty
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "EMPTY_REASONING" for err in result.errors)

    def test_short_reasoning_warning(self):
        """Test short reasoning triggers warning but passes validation."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "LOW",
            "typology": "ML",
            "confidence_score": 0.60,
            "ai_reasoning": "Too short"  # Less than 20 chars
        }

        result = self.validator.validate(data)

        assert result.is_valid is True, "Short reasoning should pass with warning"
        assert len(result.warnings) > 0, "Should have warning"
        assert any(warn.error_code == "SHORT_REASONING" for warn in result.warnings)

    def test_adequate_reasoning_length(self):
        """Test adequate reasoning length passes without warnings."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "TF",
            "confidence_score": 0.85,
            "ai_reasoning": "This transaction shows multiple suspicious patterns including large cash deposits and rapid movement of funds across multiple jurisdictions."
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert len([w for w in result.warnings if w.field == "ai_reasoning"]) == 0, \
            "Adequate reasoning should not trigger warnings"


class TestAMLLabelValidatorOptionalFields:
    """Test validation of optional fields."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_valid_expert_review_status(self):
        """Test valid expert_review_status values are accepted."""
        base_data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "ML",
            "confidence_score": 0.75,
            "ai_reasoning": "Test reasoning for expert review status"
        }

        valid_statuses = ["PENDING", "AGREED", "DISAGREED", "ESCALATED", "RESOLVED"]

        for status in valid_statuses:
            data = {**base_data, "expert_review_status": status}
            result = self.validator.validate(data)
            assert result.is_valid is True, f"Status {status} should be valid"

    def test_invalid_expert_review_status(self):
        """Test invalid expert_review_status is rejected."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "TF",
            "confidence_score": 0.85,
            "ai_reasoning": "Test reasoning for invalid status",
            "expert_review_status": "INVALID_STATUS"
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert any(err.error_code == "INVALID_REVIEW_STATUS" for err in result.errors)

    def test_regulatory_flags_list(self):
        """Test regulatory_flags accepts list format."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "CRITICAL",
            "typology": "SANCTIONS",
            "confidence_score": 0.95,
            "ai_reasoning": "Test reasoning for regulatory flags list",
            "regulatory_flags": ["OFAC", "FATF_GREYLIST", "HIGH_RISK_JURISDICTION"]
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert isinstance(result.validated_data["regulatory_flags"], list)

    def test_regulatory_flags_dict(self):
        """Test regulatory_flags accepts dict format."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "HIGH",
            "typology": "ML",
            "confidence_score": 0.88,
            "ai_reasoning": "Test reasoning for regulatory flags dict",
            "regulatory_flags": {
                "sanctions": ["OFAC", "EU"],
                "pep_status": "confirmed",
                "risk_jurisdiction": "high"
            }
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert isinstance(result.validated_data["regulatory_flags"], dict)

    def test_regulatory_flags_none(self):
        """Test regulatory_flags defaults to empty list when None."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "LOW",
            "typology": "FRAUD",
            "confidence_score": 0.65,
            "ai_reasoning": "Test reasoning for None regulatory flags",
            "regulatory_flags": None
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert result.validated_data["regulatory_flags"] == []


class TestAMLLabelValidatorCompleteScenarios:
    """Test complete validation scenarios."""

    def setup_method(self):
        """Initialize validator for each test."""
        self.validator = AMLLabelValidator()

    def test_complete_valid_record(self):
        """Test complete valid record with all fields."""
        data = {
            "transaction_id": "txn_abc123",
            "tenant_id": "tenant_fintech_001",
            "job_id": "job_batch_20250130",
            "risk_level": "CRITICAL",
            "typology": "ML",
            "confidence_score": Decimal("0.9547"),
            "ai_reasoning": "Transaction exhibits multiple red flags: (1) Structuring behavior with amounts just below reporting thresholds, (2) Rapid movement of funds across multiple jurisdictions, (3) Involvement of shell companies, (4) Unusual transaction patterns inconsistent with business profile.",
            "expert_review_status": "ESCALATED",
            "regulatory_flags": {
                "sanctions": ["OFAC"],
                "pep": False,
                "high_risk_country": True,
                "fatf_greylist": False
            },
            "version_id": "v1.2.3",
            "is_audit_ready": False
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.validated_data is not None
        assert result.validated_data["transaction_id"] == "txn_abc123"
        assert result.validated_data["risk_level"] == AMLRiskLevel.CRITICAL
        assert result.validated_data["confidence_score"] == Decimal("0.9547")

    def test_multiple_validation_errors(self):
        """Test record with multiple validation errors."""
        data = {
            "transaction_id": "",  # Empty
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "INVALID_LEVEL",  # Invalid enum
            "typology": "ML",
            "confidence_score": 1.5,  # Out of range
            "ai_reasoning": "Short"  # Too short (warning)
        }

        result = self.validator.validate(data)

        assert result.is_valid is False
        assert len(result.errors) >= 3, "Should have multiple errors"

        error_codes = [err.error_code for err in result.errors]
        assert "EMPTY_TRANSACTION_ID" in error_codes
        assert "INVALID_RISK_LEVEL" in error_codes
        assert "CONFIDENCE_OUT_OF_RANGE" in error_codes

    def test_validator_adds_timestamps(self):
        """Test validator adds created_at and updated_at timestamps."""
        data = {
            "transaction_id": "txn_001",
            "tenant_id": "tenant_001",
            "job_id": "job_001",
            "risk_level": "MEDIUM",
            "typology": "FRAUD",
            "confidence_score": 0.72,
            "ai_reasoning": "Test reasoning for timestamp validation"
        }

        result = self.validator.validate(data)

        assert result.is_valid is True
        assert "created_at" in result.validated_data
        assert "updated_at" in result.validated_data
        assert isinstance(result.validated_data["created_at"], datetime)
        assert isinstance(result.validated_data["updated_at"], datetime)
