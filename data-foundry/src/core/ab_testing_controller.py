"""
A/B Testing Controller for Data Foundry
========================================

Provides deterministic traffic routing between control and variant treatments
with consistent hashing to ensure the same record always gets the same treatment.

Extracted and adapted from pipeline-v4 ABTestingController for use in
Data Foundry's validation and processing workflows.

Features:
- Deterministic assignment (record_id -> treatment)
- Configurable variant traffic percentage (0%, 20%, 50%, 100%)
- Treatment tracking for metrics and analysis
- Generic framework for any A/B testing scenario

Use Cases in Data Foundry:
- Test different validation strategies
- Compare AI model performance
- Test new features safely
- Roll out changes gradually

Author: Data Foundry (adapted from RedditHarbor ML Pipeline)
Version: 1.0.0
"""

import hashlib
import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TreatmentAssignment:
    """
    Result of treatment assignment for a single record.

    Attributes:
        treatment: The assigned treatment ("control" or "variant" by default)
        record_id: The record identifier used for assignment
        variant_name: The name of the variant treatment (for comparison)
        is_variant: True if assigned to variant treatment
        is_control: True if assigned to control treatment
    """
    treatment: str
    record_id: str
    variant_name: str = "variant"
    is_variant: bool = field(init=False)
    is_control: bool = field(init=False)

    def __post_init__(self):
        """Set boolean flags based on treatment."""
        self.is_variant = self.treatment == self.variant_name
        self.is_control = not self.is_variant


@dataclass
class ABPrediction:
    """
    Result from A/B testing with both predictions.

    This generic result type can hold predictions from any A/B testing scenario:
    - Validation results (control vs variant validation)
    - AI model predictions (baseline vs ML model)
    - Processing strategies (old vs new implementation)

    Attributes:
        treatment: The treatment that was active ("control" or "variant")
        active_result: The result that was used (based on treatment)
        control_result: The control/baseline prediction (always computed)
        variant_result: The variant/experimental prediction (if available)
        record_id: Record identifier for tracking
        metadata: Additional metadata about the prediction
    """
    treatment: str
    active_result: Any
    control_result: Any
    variant_result: Optional[Any] = None
    record_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ABTestingController:
    """
    Controls A/B traffic routing between control and variant treatments.

    Uses consistent hashing (MD5) to ensure deterministic assignment - the same
    record_id will always get the same treatment across multiple runs and instances.

    This controller is generic and can be used for any A/B testing scenario:
    - Validation strategies (strict vs lenient)
    - AI models (baseline vs experimental)
    - Processing methods (old vs new)
    - Feature flags (off vs on)

    Attributes:
        variant_ratio: Fraction of traffic routed to variant (0.0-1.0)
        control_name: Name for control treatment (default: "control")
        variant_name: Name for variant treatment (default: "variant")
        stats: Statistics tracking for treatment distribution

    Example:
        >>> controller = ABTestingController(variant_ratio=0.3)
        >>> assignment = controller.assign_treatment(record_id="record-123")
        >>> if assignment.is_variant:
        ...     result = experimental_validator.validate(record)
        ... else:
        ...     result = baseline_validator.validate(record)
    """

    def __init__(
        self,
        variant_ratio: float = 0.5,
        control_name: str = "control",
        variant_name: str = "variant",
        ml_ratio: Optional[float] = None
    ):
        """
        Initialize A/B testing controller.

        Args:
            variant_ratio: Fraction of traffic to route to variant (0.0-1.0)
            control_name: Name for the control treatment
            variant_name: Name for the variant treatment
            ml_ratio: Backward compatibility alias for variant_ratio

        Raises:
            ValueError: If ratio is not between 0 and 1
        """
        # Handle backward compatibility: ml_ratio is alias for variant_ratio
        if ml_ratio is not None:
            variant_ratio = ml_ratio

        if not 0.0 <= variant_ratio <= 1.0:
            raise ValueError(
                f"variant_ratio must be between 0 and 1, got {variant_ratio}"
            )

        self.variant_ratio = variant_ratio
        self.ml_ratio = variant_ratio  # Alias for backward compatibility
        self.control_name = control_name
        self.variant_name = variant_name

        # Thread-safe statistics tracking
        self._stats_lock = Lock()
        self.stats = {
            'total_samples': 0,
            'control_count': 0,
            'variant_count': 0
        }

        logger.info(
            f"ABTestingController initialized: {control_name}={1-variant_ratio:.1%}, "
            f"{variant_name}={variant_ratio:.1%}"
        )

    def assign_treatment(
        self,
        record_id: Optional[str] = None,
        record_hash: Optional[str] = None
    ) -> TreatmentAssignment:
        """
        Deterministically assign treatment based on record_id or record_hash.

        Uses MD5 hash to create consistent assignment. The same record_id will
        always get the same treatment, even across different controller instances
        with the same variant_ratio.

        Args:
            record_id: Unique record identifier (takes priority over record_hash)
            record_hash: Hash of the record for deduplication

        Returns:
            TreatmentAssignment with treatment and metadata

        Raises:
            ValueError: If neither record_id nor record_hash is provided

        Example:
            >>> controller = ABTestingController(variant_ratio=0.3)
            >>> assignment = controller.assign_treatment(record_id="record-123")
            >>> print(assignment.treatment)  # "control" or "variant"
        """
        # Validate input
        if (record_id is None or record_id == "") and record_hash is None:
            raise ValueError(
                "Either record_id or record_hash must be provided"
            )

        # Use record_id if provided, otherwise use record_hash
        identifier = record_id if record_id is not None else record_hash

        # Get treatment assignment (deterministic)
        treatment = self._assign_treatment(identifier)

        # Thread-safe stats update
        with self._stats_lock:
            self.stats['total_samples'] += 1
            if treatment == self.variant_name:
                self.stats['variant_count'] += 1
            else:
                self.stats['control_count'] += 1

        # Create and return assignment
        return TreatmentAssignment(
            treatment=treatment,
            record_id=identifier,
            variant_name=self.variant_name
        )

    def _assign_treatment(self, identifier: str) -> str:
        """
        Deterministically assign treatment based on identifier.

        Uses MD5 hash of identifier to create consistent assignment.
        Same identifier always gets same treatment.

        Args:
            identifier: Unique identifier (record_id or record_hash)

        Returns:
            Control or variant treatment name
        """
        # Edge cases
        if self.variant_ratio == 0.0:
            return self.control_name

        if self.variant_ratio == 1.0:
            return self.variant_name

        # Hash identifier to get deterministic value
        hash_value = int(hashlib.md5(identifier.encode()).hexdigest(), 16)

        # Convert to 0-1 range
        # Use modulo 1,000,000 for fine-grained distribution
        normalized_hash = (hash_value % 1_000_000) / 1_000_000

        # Assign to variant if hash falls below variant_ratio threshold
        if normalized_hash < self.variant_ratio:
            return self.variant_name
        else:
            return self.control_name

    def get_stats(self) -> Dict[str, Any]:
        """
        Get A/B testing statistics.

        Returns:
            Dictionary with treatment distribution:
            - total_samples: Total number of assignments
            - control_count: Number assigned to control
            - variant_count: Number assigned to variant
            - variant_ratio_configured: The configured variant ratio
            - control_ratio_actual: Actual control ratio
            - variant_ratio_actual: Actual variant ratio

        Example:
            >>> stats = controller.get_stats()
            >>> print(f"Variant: {stats['variant_ratio_actual']:.1%}")
        """
        total = self.stats['total_samples']

        if total == 0:
            return {
                'total_samples': 0,
                'control_count': 0,
                'variant_count': 0,
                'variant_ratio_configured': self.variant_ratio,
                'control_ratio_actual': 0.0,
                'variant_ratio_actual': 0.0
            }

        return {
            'total_samples': total,
            'control_count': self.stats['control_count'],
            'variant_count': self.stats['variant_count'],
            'variant_ratio_configured': self.variant_ratio,
            'control_ratio_actual': self.stats['control_count'] / total,
            'variant_ratio_actual': self.stats['variant_count'] / total
        }

    def set_variant_ratio(self, new_ratio: float) -> None:
        """
        Update variant traffic ratio.

        Allows dynamic adjustment of traffic distribution during experiments.
        Useful for gradual rollouts or rollback scenarios.

        Args:
            new_ratio: New variant ratio (0.0-1.0)

        Raises:
            ValueError: If ratio not in valid range

        Example:
            >>> controller.set_variant_ratio(0.7)  # Increase to 70%
        """
        if not 0.0 <= new_ratio <= 1.0:
            raise ValueError(
                f"variant_ratio must be between 0 and 1, got {new_ratio}"
            )

        old_ratio = self.variant_ratio
        self.variant_ratio = new_ratio
        self.ml_ratio = new_ratio  # Keep alias in sync

        logger.info(
            f"Variant ratio updated: {old_ratio:.1%} -> {new_ratio:.1%}"
        )

    def reset_stats(self) -> None:
        """
        Reset statistics tracking.

        Useful for starting a new experiment phase or clearing test data.

        Example:
            >>> controller.reset_stats()
            >>> stats = controller.get_stats()
            >>> assert stats['total_samples'] == 0
        """
        self.stats = {
            'total_samples': 0,
            'control_count': 0,
            'variant_count': 0
        }

        logger.info("Statistics reset")

    def create_prediction(
        self,
        treatment: str,
        active_result: Any,
        control_result: Any,
        variant_result: Optional[Any] = None,
        record_id: str = ""
    ) -> ABPrediction:
        """
        Create an ABPrediction result object.

        Helper method for creating prediction results with proper structure.

        Args:
            treatment: The treatment that was active
            active_result: The result that was used
            control_result: The control/baseline result
            variant_result: The variant/experimental result (optional)
            record_id: Record identifier for tracking

        Returns:
            ABPrediction with all results

        Example:
            >>> prediction = controller.create_prediction(
            ...     treatment="variant",
            ...     active_result=ml_result,
            ...     control_result=baseline_result,
            ...     variant_result=ml_result,
            ...     record_id="record-123"
            ... )
        """
        return ABPrediction(
            treatment=treatment,
            active_result=active_result,
            control_result=control_result,
            variant_result=variant_result,
            record_id=record_id
        )


# Convenience functions for common A/B testing patterns

def create_ab_controller(
    variant_percentage: int = 50,
    control_name: str = "control",
    variant_name: str = "variant"
) -> ABTestingController:
    """
    Convenience function to create ABTestingController with percentage.

    Args:
        variant_percentage: Percentage for variant (0-100)
        control_name: Name for control treatment
        variant_name: Name for variant treatment

    Returns:
        Configured ABTestingController

    Example:
        >>> controller = create_ab_controller(variant_percentage=30)
        >>> # 30% variant, 70% control
    """
    return ABTestingController(
        variant_ratio=variant_percentage / 100.0,
        control_name=control_name,
        variant_name=variant_name
    )
