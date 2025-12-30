"""
Test for AML Typology Validation Fix (P01-009)

This test verifies that the typology validation correctly validates
against FATF_TYPOLOGIES from the AML labeling prompt.
"""

import pytest
from pydantic import ValidationError

from src.services.ai_service import AMLLabelResponse


class TestAMLTypologyValidation:
    """Test suite for AML typology validation."""

    def test_valid_fatf_typologies(self):
        """Test that all valid FATF typologies pass validation."""
        valid_typologies = [
            "ML",  # Money Laundering
            "TF",  # Terrorist Financing
            "PEP",  # Politically Exposed Persons
            "FRAUD",  # Financial Fraud
            "SANCTIONS",  # Sanctions Evasion
            "TAX_EVASION",  # Tax Evasion
            "BRIBERY",  # Bribery and Corruption
            "SMUGGLING",  # Trade-based ML
            "DRUG_TRAFFICKING",  # Drug proceeds
            "HUMAN_TRAFFICKING",  # Human trafficking proceeds
            "PROLIFERATION",  # WMD financing
            "CYBERCRIME",  # Cybercrime proceeds
            "ENVIRONMENTAL"  # Environmental crimes
        ]

        for typology in valid_typologies:
            # Test with uppercase
            response = AMLLabelResponse(
                risk_level="LOW",
                typology=typology,
                confidence_score=0.8,
                reasoning="Test reasoning"
            )
            assert response.typology == typology

            # Test with lowercase (should be converted to uppercase)
            response = AMLLabelResponse(
                risk_level="LOW",
                typology=typology.lower(),
                confidence_score=0.8,
                reasoning="Test reasoning"
            )
            assert response.typology == typology

            # Test with mixed case (should be converted to uppercase)
            response = AMLLabelResponse(
                risk_level="LOW",
                typology=typology.capitalize(),
                confidence_score=0.8,
                reasoning="Test reasoning"
            )
            assert response.typology == typology

    def test_invalid_typology_raises_error(self):
        """Test that invalid typologies raise ValidationError."""
        invalid_typologies = [
            "INVALID",
            "MONEY_LAUNDERING",  # Wrong format
            "ML_TEST",  # Not a valid code
            "123",  # Numeric
            "",  # Empty string
            "   ",  # Whitespace only
        ]

        for typology in invalid_typologies:
            with pytest.raises(ValidationError) as exc_info:
                AMLLabelResponse(
                    risk_level="LOW",
                    typology=typology,
                    confidence_score=0.8,
                    reasoning="Test reasoning"
                )

            # Verify error message mentions valid typologies
            error_str = str(exc_info.value)
            assert "typology must be one of" in error_str

    def test_confidence_score_rounding(self):
        """Test that confidence scores are rounded to 4 decimal places."""
        test_cases = [
            (0.123456789, 0.1235),  # Rounds up
            (0.123449999, 0.1234),  # Rounds down
            (0.99995, 1.0),  # Edge case - rounds to 1.0
            (0.00001, 0.0),  # Edge case - rounds to 0.0
            (0.5, 0.5),  # Already at good precision
        ]

        for input_score, expected_score in test_cases:
            response = AMLLabelResponse(
                risk_level="LOW",
                typology="ML",
                confidence_score=input_score,
                reasoning="Test reasoning"
            )
            assert response.confidence_score == expected_score

    def test_confidence_score_out_of_range(self):
        """Test that out-of-range confidence scores raise ValidationError."""
        invalid_scores = [
            -0.1,  # Negative
            1.1,  # Greater than 1.0
            2.0,  # Way too high
            -1.0,  # Way too low
        ]

        for score in invalid_scores:
            with pytest.raises(ValidationError) as exc_info:
                AMLLabelResponse(
                    risk_level="LOW",
                    typology="ML",
                    confidence_score=score,
                    reasoning="Test reasoning"
                )

            error_str = str(exc_info.value)
            assert "confidence_score must be between 0.0 and 1.0" in error_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
