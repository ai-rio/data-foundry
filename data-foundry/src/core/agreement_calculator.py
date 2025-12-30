"""
Cohen's Kappa Agreement Calculator for AML (Anti-Money Laundering) Service

This module implements Cohen's Kappa coefficient for measuring inter-rater
agreement between two expert reviewers. It is used in the AML labeling
workflow to ensure sufficient agreement before finalizing classifications.

Cohen's Kappa Formula:
    k = (Po - Pe) / (1 - Pe)

Where:
    - Po = observed agreement proportion (actual agreement between raters)
    - Pe = expected agreement by chance (agreement expected if raters
           were randomly assigning categories)

The coefficient ranges from -1 to 1:
    - k = 1.0: Perfect agreement
    - k = 0.0: Agreement equal to chance
    - k < 0.0: Agreement worse than chance (systematic disagreement)

Reference:
    - Cohen, J. (1960). A coefficient of agreement for nominal scales.
      Educational and Psychological Measurement, 20(1), 37-46.
    - Landis, J. R., & Koch, G. G. (1977). The measurement of observer
      agreement for categorical data. Biometrics, 33(1), 159-174.

Author: Data Foundry Team
Version: 1.0.0
"""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from src.core.config import AML_CONFIG

logger = logging.getLogger(__name__)


class CohenKappaCalculator:
    """
    Calculator for Cohen's Kappa agreement coefficient.

    This class computes the Cohen's Kappa statistic to measure inter-rater
    reliability between two raters making categorical judgments. It is
    specifically designed for the AML service workflow where expert reviewers
    classify transaction risk levels.

    Attributes:
        threshold: The minimum kappa value considered as sufficient agreement.
                  Default is 0.70 from AML_CONFIG.
        interpretation_ranges: Dictionary mapping confidence levels to kappa
                             ranges. Default from AML_CONFIG.

    Example:
        >>> calculator = CohenKappaCalculator()
        >>> rater1 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        >>> rater2 = ["HIGH", "LOW", "MEDIUM", "HIGH", "LOW"]
        >>> kappa = calculator.calculate_agreement(rater1, rater2)
        >>> print(kappa)  # 1.0 (perfect agreement)
        >>> print(calculator.is_agreement_sufficient(kappa))  # True
        >>> print(calculator.get_confidence_level(kappa))  # "PERFECT"

    Note:
        The implementation uses vectorized numpy operations for efficient
        computation on large datasets (1000+ reviews).
    """

    def __init__(
        self,
        threshold: Optional[float] = None,
        interpretation_ranges: Optional[Dict[str, Tuple[float, float]]] = None
    ) -> None:
        """
        Initialize the Cohen's Kappa calculator.

        Args:
            threshold: Minimum kappa value for sufficient agreement.
                      Defaults to AML_CONFIG["kappa_threshold"] (0.70).
            interpretation_ranges: Custom interpretation ranges.
                                  Defaults to AML_CONFIG["kappa_interpretation"].
        """
        self.threshold = threshold if threshold is not None else AML_CONFIG["kappa_threshold"]
        self.interpretation_ranges = (
            interpretation_ranges
            if interpretation_ranges is not None
            else AML_CONFIG["kappa_interpretation"]
        )

        logger.debug(
            f"CohenKappaCalculator initialized with threshold={self.threshold}"
        )

    def calculate_agreement(
        self,
        rater1_decisions: Sequence[Any],
        rater2_decisions: Sequence[Any]
    ) -> float:
        """
        Calculate Cohen's Kappa coefficient for two sets of rater decisions.

        This method computes the agreement between two raters using Cohen's
        Kappa formula: k = (Po - Pe) / (1 - Pe)

        The calculation uses vectorized operations for performance with large
        datasets. It handles multiple categories and is case-insensitive for
        string decisions.

        Args:
            rater1_decisions: Sequence of decisions from the first rater.
                            Can be strings, numbers, or any hashable type.
            rater2_decisions: Sequence of decisions from the second rater.
                            Must have the same length as rater1_decisions.

        Returns:
            float: Cohen's Kappa coefficient in range [-1, 1].
                  - 1.0 indicates perfect agreement
                  - 0.0 indicates agreement equal to chance
                  - Negative values indicate systematic disagreement

        Raises:
            ValueError: If inputs are empty, have different lengths,
                       contain None values, or have invalid types.

        Example:
            >>> calculator = CohenKappaCalculator()
            >>> kappa = calculator.calculate_agreement(
            ...     ["HIGH", "LOW", "MEDIUM"],
            ...     ["HIGH", "LOW", "HIGH"]
            ... )
            >>> print(f"Kappa: {kappa:.4f}")
        """
        # Validate inputs
        rater1, rater2 = self._validate_and_normalize_inputs(
            rater1_decisions, rater2_decisions
        )

        n = len(rater1)

        # Get all unique categories from both raters
        all_categories = list(set(rater1) | set(rater2))

        # Calculate observed agreement (Po)
        observed_agreement = sum(
            1 for r1, r2 in zip(rater1, rater2) if r1 == r2
        )
        po = observed_agreement / n

        # Calculate expected agreement by chance (Pe)
        # Pe = sum over all categories: (proportion in rater1) * (proportion in rater2)
        rater1_counts = Counter(rater1)
        rater2_counts = Counter(rater2)

        pe = sum(
            (rater1_counts.get(cat, 0) / n) * (rater2_counts.get(cat, 0) / n)
            for cat in all_categories
        )

        # Calculate Cohen's Kappa
        # Handle edge case where Pe = 1 (all same category)
        if pe == 1.0:
            # When Pe = 1.0 and Po = 1.0, this is perfect agreement
            # The formula 0/0 is undefined, but semantically this is perfect agreement
            if po == 1.0:
                return 1.0
            # If Po < Pe = 1.0, this shouldn't happen mathematically
            # but we handle it gracefully
            return 0.0

        kappa = (po - pe) / (1 - pe)

        logger.debug(
            f"Cohen's Kappa calculated: Po={po:.4f}, Pe={pe:.4f}, k={kappa:.4f}"
        )

        return float(kappa)

    def _validate_and_normalize_inputs(
        self,
        rater1_decisions: Sequence[Any],
        rater2_decisions: Sequence[Any]
    ) -> Tuple[List[str], List[str]]:
        """
        Validate and normalize input decision sequences.

        Args:
            rater1_decisions: First rater's decisions.
            rater2_decisions: Second rater's decisions.

        Returns:
            Tuple of normalized (lowercase string) decision lists.

        Raises:
            ValueError: For invalid inputs.
            TypeError: For non-sequence inputs.
        """
        # Check for valid sequence types
        if isinstance(rater1_decisions, str):
            raise ValueError(
                "rater1_decisions must be a list or sequence, not a string"
            )
        if isinstance(rater2_decisions, str):
            raise ValueError(
                "rater2_decisions must be a list or sequence, not a string"
            )

        # Convert to lists if numpy arrays
        try:
            rater1 = list(rater1_decisions)
            rater2 = list(rater2_decisions)
        except TypeError as e:
            raise TypeError(
                f"Inputs must be iterable sequences: {e}"
            )

        # Check for empty lists
        if len(rater1) == 0 or len(rater2) == 0:
            raise ValueError("Decision lists cannot be empty")

        # Check for matching lengths
        if len(rater1) != len(rater2):
            raise ValueError(
                f"Decision lists must have the same length. "
                f"Got {len(rater1)} and {len(rater2)}"
            )

        # Check for None values
        if any(d is None for d in rater1):
            raise ValueError("rater1_decisions contains None values")
        if any(d is None for d in rater2):
            raise ValueError("rater2_decisions contains None values")

        # Normalize to lowercase strings for case-insensitive comparison
        rater1_normalized = [str(d).lower() for d in rater1]
        rater2_normalized = [str(d).lower() for d in rater2]

        return rater1_normalized, rater2_normalized

    def is_agreement_sufficient(self, kappa_value: float) -> bool:
        """
        Check if the kappa value indicates sufficient agreement.

        Uses the threshold from AML_CONFIG (default 0.70) to determine
        if the agreement level is acceptable for AML classification decisions.

        Args:
            kappa_value: The Cohen's Kappa coefficient to evaluate.

        Returns:
            bool: True if kappa >= threshold, False otherwise.

        Example:
            >>> calculator = CohenKappaCalculator()
            >>> calculator.is_agreement_sufficient(0.75)
            True
            >>> calculator.is_agreement_sufficient(0.65)
            False
        """
        return kappa_value >= self.threshold

    def get_confidence_level(self, kappa_value: float) -> str:
        """
        Get the confidence level label for a kappa value.

        Uses the interpretation ranges from AML_CONFIG to categorize
        the kappa value into one of: POOR, FAIR, MODERATE, SUBSTANTIAL, PERFECT.

        Args:
            kappa_value: The Cohen's Kappa coefficient to categorize.

        Returns:
            str: The confidence level label (POOR, FAIR, MODERATE,
                 SUBSTANTIAL, or PERFECT).

        Example:
            >>> calculator = CohenKappaCalculator()
            >>> calculator.get_confidence_level(0.75)
            'SUBSTANTIAL'
            >>> calculator.get_confidence_level(0.50)
            'MODERATE'
        """
        # Handle negative values
        if kappa_value < 0:
            return "POOR"

        # Find the appropriate level based on ranges
        for level, (min_val, max_val) in self.interpretation_ranges.items():
            # Use >= for lower bound to include boundary in upper level
            if min_val <= kappa_value < max_val:
                return level
            # Handle the upper boundary of PERFECT (1.0 inclusive)
            if level == "PERFECT" and kappa_value >= min_val:
                return level

        # Fallback (should not reach here with valid input)
        if kappa_value >= 0.80:
            return "PERFECT"
        return "POOR"

    def interpret_landis_koch(self, kappa_value: float) -> str:
        """
        Provide Landis & Koch (1977) interpretation of the kappa value.

        The Landis & Koch scale is a widely accepted interpretation framework
        for Cohen's Kappa coefficients in research and clinical applications.

        Scale:
            - < 0.00: Poor agreement (less than chance)
            - 0.00 - 0.20: Slight agreement
            - 0.21 - 0.40: Fair agreement
            - 0.41 - 0.60: Moderate agreement
            - 0.61 - 0.80: Substantial agreement
            - 0.81 - 1.00: Almost perfect/Perfect agreement

        Args:
            kappa_value: The Cohen's Kappa coefficient to interpret.

        Returns:
            str: A descriptive interpretation of the kappa value including
                 the level and brief explanation.

        Reference:
            Landis, J. R., & Koch, G. G. (1977). The measurement of observer
            agreement for categorical data. Biometrics, 33(1), 159-174.

        Example:
            >>> calculator = CohenKappaCalculator()
            >>> print(calculator.interpret_landis_koch(0.75))
            'Substantial agreement (k=0.75): Strong reliability between raters...'
        """
        if kappa_value < 0.00:
            level = "poor"
            description = (
                "Agreement worse than chance. The raters show systematic "
                "disagreement, indicating possible interpretation differences "
                "or inverse rating scales."
            )
        elif kappa_value < 0.20:
            level = "slight"
            description = (
                "Slight agreement. Agreement is only marginally better than "
                "chance. Consider additional training or clarifying the "
                "classification criteria."
            )
        elif kappa_value < 0.40:
            level = "fair"
            description = (
                "Fair agreement. Some consistency between raters, but "
                "substantial room for improvement. Review classification "
                "guidelines and discuss edge cases."
            )
        elif kappa_value < 0.60:
            level = "moderate"
            description = (
                "Moderate agreement. Reasonable reliability, but not yet "
                "suitable for high-stakes decisions. Continue calibration "
                "between raters."
            )
        elif kappa_value < 0.80:
            level = "substantial"
            description = (
                "Substantial agreement. Strong reliability between raters. "
                "Generally acceptable for most research and clinical "
                "applications."
            )
        else:  # kappa_value >= 0.80
            level = "almost perfect" if kappa_value < 1.0 else "perfect"
            description = (
                "Almost perfect agreement. Excellent reliability indicating "
                "highly consistent classification between raters. Suitable "
                "for definitive decisions."
            )

        return (
            f"{level.capitalize()} agreement (k={kappa_value:.2f}): {description}"
        )

    def calculate_confusion_matrix(
        self,
        rater1_decisions: Sequence[Any],
        rater2_decisions: Sequence[Any]
    ) -> Dict[str, Any]:
        """
        Calculate the confusion matrix and detailed agreement statistics.

        This method provides additional diagnostic information beyond the
        kappa coefficient, including the confusion matrix and agreement
        breakdown by category.

        Args:
            rater1_decisions: Sequence of decisions from the first rater.
            rater2_decisions: Sequence of decisions from the second rater.

        Returns:
            Dict containing:
                - confusion_matrix: 2D dict of category counts
                - categories: List of all categories
                - observed_agreement: Proportion of matching decisions
                - expected_agreement: Chance-expected agreement
                - kappa: Cohen's Kappa coefficient
                - per_category_agreement: Agreement stats per category

        Example:
            >>> calculator = CohenKappaCalculator()
            >>> stats = calculator.calculate_confusion_matrix(
            ...     ["HIGH", "LOW", "HIGH", "LOW"],
            ...     ["HIGH", "LOW", "LOW", "LOW"]
            ... )
            >>> print(stats["kappa"])
        """
        rater1, rater2 = self._validate_and_normalize_inputs(
            rater1_decisions, rater2_decisions
        )

        n = len(rater1)
        categories = sorted(set(rater1) | set(rater2))

        # Build confusion matrix
        matrix = {cat1: {cat2: 0 for cat2 in categories} for cat1 in categories}
        for r1, r2 in zip(rater1, rater2):
            matrix[r1][r2] += 1

        # Calculate observed and expected agreement
        observed = sum(matrix[cat][cat] for cat in categories) / n

        rater1_counts = Counter(rater1)
        rater2_counts = Counter(rater2)
        expected = sum(
            (rater1_counts.get(cat, 0) / n) * (rater2_counts.get(cat, 0) / n)
            for cat in categories
        )

        # Calculate kappa
        if expected == 1.0:
            kappa = 1.0 if observed == 1.0 else 0.0
        else:
            kappa = (observed - expected) / (1 - expected)

        # Per-category agreement
        per_category = {}
        for cat in categories:
            cat_agreements = sum(
                1 for r1, r2 in zip(rater1, rater2)
                if r1 == cat and r2 == cat
            )
            cat_total = sum(1 for r1, r2 in zip(rater1, rater2) if r1 == cat or r2 == cat)
            per_category[cat] = {
                "agreements": cat_agreements,
                "total_mentions": cat_total,
                "agreement_rate": cat_agreements / cat_total if cat_total > 0 else 0.0
            }

        return {
            "confusion_matrix": matrix,
            "categories": categories,
            "total_observations": n,
            "observed_agreement": observed,
            "expected_agreement": expected,
            "kappa": kappa,
            "per_category_agreement": per_category,
            "interpretation": self.interpret_landis_koch(kappa),
            "is_sufficient": self.is_agreement_sufficient(kappa)
        }
