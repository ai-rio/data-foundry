"""
Tests for CohenKappaCalculator - Cohen's Kappa Agreement Coefficient

This test suite follows TDD (Test-Driven Development) principles.
Tests are written first, before the implementation.

Cohen's Kappa Formula: k = (Po - Pe) / (1 - Pe)
- Po = observed agreement proportion
- Pe = expected agreement by chance

Landis & Koch (1977) interpretation scale:
- < 0.00: Poor
- 0.00 - 0.20: Slight
- 0.21 - 0.40: Fair
- 0.41 - 0.60: Moderate
- 0.61 - 0.80: Substantial
- 0.81 - 1.00: Almost Perfect/Perfect
"""

import pytest
import numpy as np
from typing import List
from unittest.mock import patch, MagicMock


class TestCohenKappaCalculatorBasic:
    """Basic Cohen's Kappa calculation tests."""

    def test_import_cohen_kappa_calculator(self):
        """Test that CohenKappaCalculator can be imported."""
        from src.core.agreement_calculator import CohenKappaCalculator
        assert CohenKappaCalculator is not None

    def test_instantiation(self):
        """Test that CohenKappaCalculator can be instantiated."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()
        assert calculator is not None

    def test_instantiation_with_custom_threshold(self):
        """Test that CohenKappaCalculator accepts custom threshold."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator(threshold=0.80)
        assert calculator.threshold == 0.80

    def test_default_threshold_from_config(self):
        """Test that default threshold is 0.70 from config."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()
        assert calculator.threshold == 0.70


class TestCohenKappaCalculation:
    """Tests for the calculate_agreement method."""

    def test_perfect_agreement(self):
        """Test Cohen's Kappa with perfect agreement (k = 1.0)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Both raters give identical decisions
        rater1 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        rater2 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_no_agreement_beyond_chance(self):
        """Test Cohen's Kappa with no agreement beyond chance (k = 0.0)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Decisions are independent - expected agreement equals observed
        # This is a theoretical case that's hard to construct perfectly
        # We use a pattern where observed equals expected by chance
        rater1 = ["HIGH", "HIGH", "LOW", "LOW"]
        rater2 = ["HIGH", "LOW", "HIGH", "LOW"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Kappa should be 0 when Po = Pe
        assert kappa == pytest.approx(0.0, abs=0.0001)

    def test_partial_agreement(self):
        """Test Cohen's Kappa with partial agreement."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Some agreement, some disagreement
        rater1 = ["HIGH", "HIGH", "LOW", "MEDIUM", "LOW"]
        rater2 = ["HIGH", "LOW", "LOW", "MEDIUM", "HIGH"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Kappa should be between 0 and 1
        assert 0.0 < kappa < 1.0

    def test_negative_kappa_worse_than_chance(self):
        """Test Cohen's Kappa with disagreement worse than chance (k < 0)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Systematic disagreement
        rater1 = ["HIGH", "HIGH", "HIGH", "LOW", "LOW", "LOW"]
        rater2 = ["LOW", "LOW", "LOW", "HIGH", "HIGH", "HIGH"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Kappa can be negative when there's systematic disagreement
        assert kappa < 0.0

    def test_binary_classification_agreement(self):
        """Test with binary classification decisions."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Binary decisions: SAR (Suspicious Activity Report) or NOT_SAR
        rater1 = ["SAR", "SAR", "NOT_SAR", "NOT_SAR", "SAR", "NOT_SAR"]
        rater2 = ["SAR", "NOT_SAR", "NOT_SAR", "NOT_SAR", "SAR", "SAR"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Should calculate correctly for binary categories
        assert -1.0 <= kappa <= 1.0

    def test_multi_category_agreement(self):
        """Test with multiple category decisions (AML risk levels)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # AML risk levels
        rater1 = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater2 = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "MEDIUM", "MEDIUM", "HIGH", "HIGH"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Should handle multiple categories correctly
        assert -1.0 <= kappa <= 1.0

    def test_known_kappa_value(self):
        """Test with known kappa value from academic example."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Example from statistical literature
        # 2 raters, 50 subjects, binary classification
        # Agreement matrix: [[20, 5], [10, 15]]
        # Po = (20 + 15) / 50 = 0.70
        # Pe = (25/50 * 30/50) + (25/50 * 20/50) = 0.30 + 0.20 = 0.50
        # K = (0.70 - 0.50) / (1 - 0.50) = 0.40

        rater1 = ["A"] * 25 + ["B"] * 25
        rater2 = ["A"] * 20 + ["B"] * 5 + ["A"] * 10 + ["B"] * 15

        kappa = calculator.calculate_agreement(rater1, rater2)

        assert kappa == pytest.approx(0.40, abs=0.01)

    def test_calculate_agreement_returns_float(self):
        """Test that calculate_agreement returns a float."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "MEDIUM"]
        rater2 = ["HIGH", "LOW", "HIGH"]

        result = calculator.calculate_agreement(rater1, rater2)

        assert isinstance(result, float)


class TestCohenKappaEdgeCases:
    """Edge case tests for Cohen's Kappa calculation."""

    def test_empty_lists(self):
        """Test handling of empty decision lists."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        with pytest.raises(ValueError, match="cannot be empty"):
            calculator.calculate_agreement([], [])

    def test_mismatched_list_lengths(self):
        """Test handling of mismatched list lengths."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "MEDIUM"]
        rater2 = ["HIGH", "LOW"]

        with pytest.raises(ValueError, match="same length"):
            calculator.calculate_agreement(rater1, rater2)

    def test_single_decision(self):
        """Test handling of single decision."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH"]
        rater2 = ["HIGH"]

        # With only one observation, kappa should still calculate
        kappa = calculator.calculate_agreement(rater1, rater2)

        # Perfect agreement with single decision
        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_all_same_category_both_raters(self):
        """Test when both raters always choose the same category."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # All decisions are "HIGH" for both raters
        rater1 = ["HIGH"] * 10
        rater2 = ["HIGH"] * 10

        # Perfect agreement but Pe = 1, so kappa is undefined (0/0)
        # The implementation should handle this gracefully
        kappa = calculator.calculate_agreement(rater1, rater2)

        # When Pe = 1, we typically return 1.0 for perfect agreement
        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_single_category_disagreement(self):
        """Test edge case where one rater only uses one category."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Rater 1 always says HIGH, Rater 2 varies
        rater1 = ["HIGH"] * 10
        rater2 = ["HIGH", "LOW", "HIGH", "MEDIUM", "HIGH", "LOW", "HIGH", "LOW", "HIGH", "MEDIUM"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Should still return a valid kappa value
        assert -1.0 <= kappa <= 1.0

    def test_handles_none_values(self):
        """Test handling of None values in decisions."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", None, "LOW"]
        rater2 = ["HIGH", "LOW", "LOW"]

        with pytest.raises(ValueError, match="None values"):
            calculator.calculate_agreement(rater1, rater2)

    def test_handles_numeric_decisions(self):
        """Test handling of numeric decisions (converted to strings)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Risk scores as numbers
        rater1 = [1, 2, 3, 4, 1, 2]
        rater2 = [1, 2, 3, 4, 2, 2]

        kappa = calculator.calculate_agreement(rater1, rater2)

        assert -1.0 <= kappa <= 1.0

    def test_case_insensitive_matching(self):
        """Test that decisions are case-insensitive."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "low", "Medium"]
        rater2 = ["high", "LOW", "MEDIUM"]

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Should be perfect agreement despite case differences
        assert kappa == pytest.approx(1.0, abs=0.0001)


class TestIsAgreementSufficient:
    """Tests for the is_agreement_sufficient method."""

    def test_sufficient_agreement_at_threshold(self):
        """Test that kappa at threshold (0.70) is sufficient."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.is_agreement_sufficient(0.70)

        assert result is True

    def test_sufficient_agreement_above_threshold(self):
        """Test that kappa above threshold is sufficient."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.is_agreement_sufficient(0.85)

        assert result is True

    def test_insufficient_agreement_below_threshold(self):
        """Test that kappa below threshold is insufficient."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.is_agreement_sufficient(0.65)

        assert result is False

    def test_insufficient_agreement_negative_kappa(self):
        """Test that negative kappa is insufficient."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.is_agreement_sufficient(-0.20)

        assert result is False

    def test_custom_threshold(self):
        """Test with custom threshold."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator(threshold=0.80)

        # 0.75 would be sufficient with default 0.70, but not with 0.80
        result = calculator.is_agreement_sufficient(0.75)

        assert result is False

    def test_returns_bool(self):
        """Test that is_agreement_sufficient returns a boolean."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.is_agreement_sufficient(0.80)

        assert isinstance(result, bool)


class TestGetConfidenceLevel:
    """Tests for the get_confidence_level method (using config interpretation)."""

    def test_poor_confidence_level(self):
        """Test POOR confidence level (0.0 - 0.20)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.15)

        assert result == "POOR"

    def test_fair_confidence_level(self):
        """Test FAIR confidence level (0.20 - 0.40)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.30)

        assert result == "FAIR"

    def test_moderate_confidence_level(self):
        """Test MODERATE confidence level (0.40 - 0.60)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.50)

        assert result == "MODERATE"

    def test_substantial_confidence_level(self):
        """Test SUBSTANTIAL confidence level (0.60 - 0.80)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.70)

        assert result == "SUBSTANTIAL"

    def test_perfect_confidence_level(self):
        """Test PERFECT confidence level (0.80 - 1.00)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.90)

        assert result == "PERFECT"

    def test_negative_kappa_returns_poor(self):
        """Test that negative kappa returns POOR."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(-0.20)

        assert result == "POOR"

    def test_boundary_values(self):
        """Test boundary values between levels."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # At boundary, should go to upper level (inclusive)
        assert calculator.get_confidence_level(0.20) == "FAIR"
        assert calculator.get_confidence_level(0.40) == "MODERATE"
        assert calculator.get_confidence_level(0.60) == "SUBSTANTIAL"
        assert calculator.get_confidence_level(0.80) == "PERFECT"

    def test_returns_string(self):
        """Test that get_confidence_level returns a string."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(0.50)

        assert isinstance(result, str)


class TestLandisKochInterpretation:
    """Tests for the interpret_landis_koch method (Landis & Koch 1977 scale)."""

    def test_poor_agreement(self):
        """Test interpretation for poor agreement (< 0.00)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(-0.10)

        assert "poor" in result.lower()

    def test_slight_agreement(self):
        """Test interpretation for slight agreement (0.00 - 0.20)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.15)

        assert "slight" in result.lower()

    def test_fair_agreement(self):
        """Test interpretation for fair agreement (0.21 - 0.40)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.35)

        assert "fair" in result.lower()

    def test_moderate_agreement(self):
        """Test interpretation for moderate agreement (0.41 - 0.60)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.55)

        assert "moderate" in result.lower()

    def test_substantial_agreement(self):
        """Test interpretation for substantial agreement (0.61 - 0.80)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.75)

        assert "substantial" in result.lower()

    def test_almost_perfect_agreement(self):
        """Test interpretation for almost perfect agreement (0.81 - 1.00)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.90)

        # "almost perfect" or "perfect" both acceptable
        assert "perfect" in result.lower()

    def test_perfect_agreement(self):
        """Test interpretation for perfect agreement (1.00)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(1.0)

        assert "perfect" in result.lower()

    def test_returns_descriptive_string(self):
        """Test that interpretation returns a descriptive string."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.interpret_landis_koch(0.65)

        assert isinstance(result, str)
        assert len(result) > 5  # More than just a label


class TestPerformanceWithLargeDatasets:
    """Performance tests for large datasets (1000+ expert reviews)."""

    def test_performance_1000_reviews(self):
        """Test performance with 1000 reviews."""
        import time
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Generate 1000 random decisions
        np.random.seed(42)
        categories = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater1 = np.random.choice(categories, 1000).tolist()
        rater2 = np.random.choice(categories, 1000).tolist()

        start_time = time.time()
        kappa = calculator.calculate_agreement(rater1, rater2)
        elapsed_time = time.time() - start_time

        # Should complete in less than 0.1 seconds
        assert elapsed_time < 0.1
        assert -1.0 <= kappa <= 1.0

    def test_performance_10000_reviews(self):
        """Test performance with 10000 reviews."""
        import time
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Generate 10000 random decisions
        np.random.seed(42)
        categories = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater1 = np.random.choice(categories, 10000).tolist()
        rater2 = np.random.choice(categories, 10000).tolist()

        start_time = time.time()
        kappa = calculator.calculate_agreement(rater1, rater2)
        elapsed_time = time.time() - start_time

        # Should complete in less than 0.5 seconds
        assert elapsed_time < 0.5
        assert -1.0 <= kappa <= 1.0

    def test_vectorized_calculation(self):
        """Test that calculation uses vectorized operations (no nested loops)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Large dataset
        np.random.seed(42)
        categories = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater1 = np.random.choice(categories, 5000).tolist()
        rater2 = np.random.choice(categories, 5000).tolist()

        # Time 3 executions to get average
        times = []
        for _ in range(3):
            import time
            start = time.time()
            calculator.calculate_agreement(rater1, rater2)
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)

        # Vectorized implementation should be fast
        assert avg_time < 0.2

    def test_memory_efficiency(self):
        """Test memory efficiency with large datasets."""
        import tracemalloc
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Generate large dataset
        np.random.seed(42)
        categories = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater1 = np.random.choice(categories, 10000).tolist()
        rater2 = np.random.choice(categories, 10000).tolist()

        tracemalloc.start()
        kappa = calculator.calculate_agreement(rater1, rater2)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable (less than 10 MB for calculation)
        assert peak < 10 * 1024 * 1024  # 10 MB


class TestConfigurationIntegration:
    """Tests for integration with AML configuration."""

    def test_uses_config_threshold(self):
        """Test that default threshold comes from AML_CONFIG."""
        from src.core.agreement_calculator import CohenKappaCalculator
        from src.core.config import AML_CONFIG

        calculator = CohenKappaCalculator()

        assert calculator.threshold == AML_CONFIG["kappa_threshold"]

    def test_uses_config_interpretation(self):
        """Test that interpretation uses AML_KAPPA_INTERPRETATION."""
        from src.core.agreement_calculator import CohenKappaCalculator
        from src.core.config import AML_CONFIG

        calculator = CohenKappaCalculator()

        # Get a confidence level and verify it matches config interpretation
        for level, (min_val, max_val) in AML_CONFIG["kappa_interpretation"].items():
            mid_val = (min_val + max_val) / 2
            result = calculator.get_confidence_level(mid_val)
            assert result == level


class TestMathematicalCorrectness:
    """Tests to verify mathematical correctness of Cohen's Kappa implementation."""

    def test_cohens_kappa_formula_manual_calculation(self):
        """Verify Cohen's Kappa formula: k = (Po - Pe) / (1 - Pe)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Manual calculation example
        # Confusion matrix:
        #           Rater2
        #           A    B
        # Rater1 A  10   5   = 15
        #        B   3  12   = 15
        #           13  17    = 30 total

        # Po = (10 + 12) / 30 = 0.7333
        # P1_A = 15/30 = 0.5, P2_A = 13/30 = 0.4333
        # P1_B = 15/30 = 0.5, P2_B = 17/30 = 0.5667
        # Pe = (0.5 * 0.4333) + (0.5 * 0.5667) = 0.2167 + 0.2833 = 0.5
        # K = (0.7333 - 0.5) / (1 - 0.5) = 0.4667

        rater1 = ["A"] * 15 + ["B"] * 15
        rater2 = ["A"] * 10 + ["B"] * 5 + ["A"] * 3 + ["B"] * 12

        kappa = calculator.calculate_agreement(rater1, rater2)

        # Expected kappa approximately 0.4667
        assert kappa == pytest.approx(0.4667, abs=0.01)

    def test_kappa_range_validation(self):
        """Test that kappa is always in valid range [-1, 1]."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Test various scenarios
        test_cases = [
            (["A", "A", "A"], ["A", "A", "A"]),  # Perfect agreement same cat
            (["A", "B", "C"], ["A", "B", "C"]),  # Perfect agreement multi
            (["A", "B", "A", "B"], ["B", "A", "B", "A"]),  # Systematic disagree
            (["A", "A", "B", "B"], ["A", "B", "A", "B"]),  # Mixed
        ]

        for rater1, rater2 in test_cases:
            kappa = calculator.calculate_agreement(rater1, rater2)
            assert -1.0 <= kappa <= 1.0, f"Kappa {kappa} out of range for {rater1}, {rater2}"

    def test_symmetric_property(self):
        """Test that kappa(rater1, rater2) == kappa(rater2, rater1)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        rater2 = ["HIGH", "MEDIUM", "MEDIUM", "LOW", "LOW"]

        kappa_12 = calculator.calculate_agreement(rater1, rater2)
        kappa_21 = calculator.calculate_agreement(rater2, rater1)

        assert kappa_12 == pytest.approx(kappa_21, abs=0.0001)


class TestInputValidation:
    """Tests for input validation."""

    def test_invalid_type_rater1(self):
        """Test handling of invalid type for rater1."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        with pytest.raises((ValueError, TypeError)):
            calculator.calculate_agreement("not a list", ["A", "B"])

    def test_invalid_type_rater2(self):
        """Test handling of invalid type for rater2."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        with pytest.raises((ValueError, TypeError)):
            calculator.calculate_agreement(["A", "B"], "not a list")

    def test_numpy_array_input(self):
        """Test handling of numpy array input."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = np.array(["HIGH", "LOW", "MEDIUM"])
        rater2 = np.array(["HIGH", "LOW", "HIGH"])

        # Should accept numpy arrays
        kappa = calculator.calculate_agreement(rater1, rater2)

        assert -1.0 <= kappa <= 1.0


class TestDocumentation:
    """Tests for proper documentation."""

    def test_class_has_docstring(self):
        """Test that CohenKappaCalculator has a docstring."""
        from src.core.agreement_calculator import CohenKappaCalculator

        assert CohenKappaCalculator.__doc__ is not None
        assert len(CohenKappaCalculator.__doc__) > 50

    def test_calculate_agreement_has_docstring(self):
        """Test that calculate_agreement has a docstring."""
        from src.core.agreement_calculator import CohenKappaCalculator

        assert CohenKappaCalculator.calculate_agreement.__doc__ is not None

    def test_module_has_docstring(self):
        """Test that the module has a docstring."""
        import src.core.agreement_calculator as module

        assert module.__doc__ is not None


class TestConfusionMatrix:
    """Tests for the calculate_confusion_matrix method."""

    def test_confusion_matrix_structure(self):
        """Test that confusion matrix has correct structure."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        rater2 = ["HIGH", "LOW", "HIGH", "HIGH", "MEDIUM"]

        result = calculator.calculate_confusion_matrix(rater1, rater2)

        assert "confusion_matrix" in result
        assert "categories" in result
        assert "total_observations" in result
        assert "observed_agreement" in result
        assert "expected_agreement" in result
        assert "kappa" in result
        assert "per_category_agreement" in result
        assert "interpretation" in result
        assert "is_sufficient" in result

    def test_confusion_matrix_counts(self):
        """Test that confusion matrix counts are correct."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Simple case: 3 A-A, 2 B-B
        rater1 = ["A", "A", "A", "B", "B"]
        rater2 = ["A", "A", "A", "B", "B"]

        result = calculator.calculate_confusion_matrix(rater1, rater2)

        assert result["confusion_matrix"]["a"]["a"] == 3
        assert result["confusion_matrix"]["b"]["b"] == 2
        assert result["total_observations"] == 5

    def test_confusion_matrix_kappa_matches(self):
        """Test that confusion matrix kappa matches calculate_agreement."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        rater2 = ["HIGH", "LOW", "HIGH", "HIGH", "MEDIUM"]

        kappa1 = calculator.calculate_agreement(rater1, rater2)
        result = calculator.calculate_confusion_matrix(rater1, rater2)

        assert kappa1 == pytest.approx(result["kappa"], abs=0.0001)

    def test_confusion_matrix_per_category_agreement(self):
        """Test per-category agreement statistics."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["A", "A", "B", "B"]
        rater2 = ["A", "B", "B", "B"]

        result = calculator.calculate_confusion_matrix(rater1, rater2)

        # Category A: 1 agreement out of (2 rater1 + 1 rater2 - 1 overlap) = 2 mentions
        # Category B: 2 agreements out of (2 rater1 + 3 rater2 - 2 overlap) = 3 mentions
        assert "a" in result["per_category_agreement"]
        assert "b" in result["per_category_agreement"]


class TestAMLWorkflowIntegration:
    """Tests simulating real AML workflow scenarios."""

    def test_typical_aml_review_scenario(self):
        """Test a typical AML expert review scenario."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Simulated AML risk assessments from two experts
        # Expert 1 and Expert 2 reviewing 20 transactions
        expert1 = [
            "LOW", "LOW", "MEDIUM", "HIGH", "LOW",
            "MEDIUM", "HIGH", "CRITICAL", "LOW", "MEDIUM",
            "HIGH", "HIGH", "MEDIUM", "LOW", "LOW",
            "CRITICAL", "HIGH", "MEDIUM", "LOW", "MEDIUM"
        ]
        expert2 = [
            "LOW", "LOW", "MEDIUM", "HIGH", "LOW",
            "MEDIUM", "MEDIUM", "CRITICAL", "LOW", "MEDIUM",
            "HIGH", "HIGH", "HIGH", "LOW", "LOW",
            "HIGH", "HIGH", "MEDIUM", "LOW", "MEDIUM"
        ]

        kappa = calculator.calculate_agreement(expert1, expert2)
        is_sufficient = calculator.is_agreement_sufficient(kappa)
        level = calculator.get_confidence_level(kappa)
        interpretation = calculator.interpret_landis_koch(kappa)

        # Verify the workflow produces valid results
        assert -1.0 <= kappa <= 1.0
        assert isinstance(is_sufficient, bool)
        assert level in ["POOR", "FAIR", "MODERATE", "SUBSTANTIAL", "PERFECT"]
        assert len(interpretation) > 20

    def test_high_agreement_sar_filing(self):
        """Test high agreement scenario for SAR filing decision."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Two experts mostly agree on SAR filing decisions
        expert1 = ["FILE_SAR", "FILE_SAR", "NO_SAR", "NO_SAR", "FILE_SAR",
                   "NO_SAR", "FILE_SAR", "NO_SAR", "FILE_SAR", "FILE_SAR"]
        expert2 = ["FILE_SAR", "FILE_SAR", "NO_SAR", "NO_SAR", "FILE_SAR",
                   "NO_SAR", "FILE_SAR", "FILE_SAR", "FILE_SAR", "FILE_SAR"]

        kappa = calculator.calculate_agreement(expert1, expert2)

        # High agreement should result in substantial kappa
        assert kappa >= 0.60
        assert calculator.is_agreement_sufficient(kappa)

    def test_disagreement_requires_third_reviewer(self):
        """Test scenario where disagreement would trigger third reviewer."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        # Two experts with significant disagreement
        expert1 = ["HIGH", "HIGH", "MEDIUM", "HIGH", "HIGH"]
        expert2 = ["LOW", "MEDIUM", "LOW", "MEDIUM", "LOW"]

        kappa = calculator.calculate_agreement(expert1, expert2)

        # Should not be sufficient for AML threshold
        assert not calculator.is_agreement_sufficient(kappa)
        assert calculator.get_confidence_level(kappa) in ["POOR", "FAIR", "MODERATE"]


class TestScikitLearnComparison:
    """Tests comparing results with scikit-learn's cohen_kappa_score."""

    def test_matches_sklearn_basic(self):
        """Test that results match scikit-learn for basic case."""
        try:
            from sklearn.metrics import cohen_kappa_score
        except ImportError:
            pytest.skip("scikit-learn not available")

        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["A", "A", "B", "B", "A", "B", "A", "B"]
        rater2 = ["A", "B", "B", "B", "A", "A", "A", "B"]

        our_kappa = calculator.calculate_agreement(rater1, rater2)
        sklearn_kappa = cohen_kappa_score(
            [x.lower() for x in rater1],
            [x.lower() for x in rater2]
        )

        assert our_kappa == pytest.approx(sklearn_kappa, abs=0.0001)

    def test_matches_sklearn_multi_category(self):
        """Test that results match scikit-learn for multi-category case."""
        try:
            from sklearn.metrics import cohen_kappa_score
        except ImportError:
            pytest.skip("scikit-learn not available")

        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        np.random.seed(123)
        categories = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        rater1 = np.random.choice(categories, 100).tolist()
        rater2 = np.random.choice(categories, 100).tolist()

        our_kappa = calculator.calculate_agreement(rater1, rater2)
        sklearn_kappa = cohen_kappa_score(
            [x.lower() for x in rater1],
            [x.lower() for x in rater2]
        )

        assert our_kappa == pytest.approx(sklearn_kappa, abs=0.0001)

    def test_matches_sklearn_perfect_agreement(self):
        """Test perfect agreement matches scikit-learn."""
        try:
            from sklearn.metrics import cohen_kappa_score
        except ImportError:
            pytest.skip("scikit-learn not available")

        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["A", "B", "C", "A", "B", "C"]
        rater2 = ["A", "B", "C", "A", "B", "C"]

        our_kappa = calculator.calculate_agreement(rater1, rater2)
        sklearn_kappa = cohen_kappa_score(
            [x.lower() for x in rater1],
            [x.lower() for x in rater2]
        )

        assert our_kappa == pytest.approx(sklearn_kappa, abs=0.0001)


class TestEdgeCasesExtended:
    """Extended edge case tests."""

    def test_two_items_same_category(self):
        """Test with just two items of the same category."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["A", "A"]
        rater2 = ["A", "A"]

        kappa = calculator.calculate_agreement(rater1, rater2)
        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_two_items_different_categories(self):
        """Test with two items of different categories, perfect agreement."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["A", "B"]
        rater2 = ["A", "B"]

        kappa = calculator.calculate_agreement(rater1, rater2)
        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_special_characters_in_categories(self):
        """Test categories with special characters."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH-RISK", "LOW-RISK", "HIGH-RISK"]
        rater2 = ["HIGH-RISK", "LOW-RISK", "LOW-RISK"]

        kappa = calculator.calculate_agreement(rater1, rater2)
        assert -1.0 <= kappa <= 1.0

    def test_unicode_categories(self):
        """Test categories with unicode characters."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["risque_eleve", "risque_faible", "risque_eleve"]
        rater2 = ["risque_eleve", "risque_faible", "risque_faible"]

        kappa = calculator.calculate_agreement(rater1, rater2)
        assert -1.0 <= kappa <= 1.0

    def test_boolean_decisions(self):
        """Test with boolean decisions."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = [True, False, True, False, True]
        rater2 = [True, False, True, True, True]

        kappa = calculator.calculate_agreement(rater1, rater2)
        assert -1.0 <= kappa <= 1.0

    def test_mixed_type_decisions(self):
        """Test with mixed type decisions (int and str)."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = [1, 2, 3, 1, 2]
        rater2 = ["1", "2", "3", "1", "2"]

        kappa = calculator.calculate_agreement(rater1, rater2)
        # After string normalization, these should be equal
        assert kappa == pytest.approx(1.0, abs=0.0001)

    def test_none_in_rater2(self):
        """Test handling of None values in rater2."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        rater1 = ["HIGH", "LOW", "LOW"]
        rater2 = ["HIGH", None, "LOW"]

        with pytest.raises(ValueError, match="None values"):
            calculator.calculate_agreement(rater1, rater2)

    def test_non_iterable_input(self):
        """Test handling of non-iterable inputs."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        with pytest.raises((ValueError, TypeError)):
            calculator.calculate_agreement(123, ["A", "B"])

    def test_custom_interpretation_ranges(self):
        """Test with custom interpretation ranges."""
        from src.core.agreement_calculator import CohenKappaCalculator

        custom_ranges = {
            "BAD": (0.0, 0.50),
            "OK": (0.50, 0.75),
            "GREAT": (0.75, 1.0)
        }
        calculator = CohenKappaCalculator(interpretation_ranges=custom_ranges)

        assert calculator.get_confidence_level(0.25) == "BAD"
        assert calculator.get_confidence_level(0.60) == "OK"
        assert calculator.get_confidence_level(0.85) == "GREAT"

    def test_kappa_exactly_1(self):
        """Test get_confidence_level with exactly 1.0."""
        from src.core.agreement_calculator import CohenKappaCalculator
        calculator = CohenKappaCalculator()

        result = calculator.get_confidence_level(1.0)
        assert result == "PERFECT"
