"""
ABTestingWrapper - Data Foundry A/B Testing Validation Integration
====================================================================

Integrates A/B testing assignment with validation and metrics collection.
Provides a facade pattern for coordinating treatment assignment, validation,
and metrics tracking in A/B testing scenarios.

Components:
- ABTestingController: Deterministic treatment assignment
- BasicMetricsCollector: Metrics tracking and export
- ABValidationResult: Combined validation and treatment information

Author: Data Foundry
Version: 1.0.0
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Any, TypedDict

from src.core.ab_testing_controller import ABTestingController
from src.core.basic_metrics import BasicMetricsCollector
from src.core.data_quality import ValidationResult

logger = logging.getLogger(__name__)


class TreatmentStats(TypedDict):
    """
    Statistics from ABTestingController.get_stats().

    Attributes:
        total_samples: Total number of records assigned
        control_count: Number of records assigned to control
        variant_count: Number of records assigned to variant
    """
    total_samples: int
    control_count: int
    variant_count: int


@dataclass
class ABValidationResult:
    """
    Combines validation results with A/B testing treatment information.

    This result type provides both the validation outcome and the treatment
    assignment, allowing for analysis of validation effectiveness across
    different A/B testing branches.

    Attributes:
        validation_result: The ValidationResult from the validation process
        treatment: User-facing treatment name ("control" or "treatment")
        is_variant: True if assigned to treatment branch, False for control

    Example:
        >>> result = ABValidationResult(
        ...     validation_result=validation_result,
        ...     treatment="treatment",
        ...     is_variant=True
        ... )
        >>> print(f"Treatment: {result.treatment}")
        >>> print(f"Valid: {result.validation_result.is_valid}")
    """
    validation_result: ValidationResult
    treatment: str  # "control" or "treatment" (user-facing)
    is_variant: bool  # True if treatment="treatment"


class ABTestingWrapper:
    """
    Facade for integrating A/B testing with validation and metrics collection.

    This wrapper coordinates three components:
    1. ABTestingController - Deterministic treatment assignment
    2. Validator callables - Control and variant validation logic
    3. BasicMetricsCollector - Tracking validation results by treatment

    Thread Safety:
    - ABTestingController uses internal Lock for statistics
    - BasicMetricsCollector uses RLock for all operations
    - ABTestingWrapper adds no shared mutable state - thread-safe by composition

    Example:
        >>> from src.core.ab_testing_wrapper import ABTestingWrapper
        >>>
        >>> # Create wrapper
        >>> wrapper = ABTestingWrapper(test_name="validation_test", treatment_ratio=0.3)
        >>>
        >>> # Define validators
        >>> def control_validator(record):
        ...     return strict_validator.validate(record)
        >>>
        >>> def variant_validator(record):
        ...     return lenient_validator.validate(record)
        >>>
        >>> # Validate with A/B testing
        >>> result = wrapper.validate_with_ab_info(
        ...     record=my_record,
        ...     control_validator=control_validator,
        ...     variant_validator=variant_validator
        ... )
        >>>
        >>> print(f"Treatment: {result.treatment}")
        >>> print(f"Valid: {result.validation_result.is_valid}")
        >>>
        >>> # Export metrics
        >>> wrapper.export_metrics(Path("results/ab_metrics.json"))
    """

    def __init__(self, test_name: str, treatment_ratio: float = 0.5):
        """
        Initialize ABTestingWrapper with controller and metrics collector.

        Args:
            test_name: Name for this A/B test (used for identification)
            treatment_ratio: Fraction of traffic to route to treatment (0.0-1.0)
                Validation delegated to ABTestingController.

        Raises:
            ValueError: If treatment_ratio not between 0 and 1 (raised by
                ABTestingController)
        """
        self.test_name = test_name

        # Initialize A/B testing controller for deterministic assignment
        self.controller = ABTestingController(
            variant_ratio=treatment_ratio,
            control_name="control",
            variant_name="variant"
        )

        # Initialize metrics collector
        self.metrics_collector = BasicMetricsCollector()

        # Register treatments with metrics collector
        # Note: Uses "control" and "variant" internally (matching controller)
        self.metrics_collector.add_treatment("control")
        self.metrics_collector.add_treatment("variant")

        logger.info(
            f"ABTestingWrapper initialized: test_name={test_name}, "
            f"treatment_ratio={treatment_ratio:.1%}"
        )

    def validate_with_ab_info(
        self,
        record: Dict[str, Any],
        control_validator: Callable[[Dict[str, Any]], ValidationResult],
        variant_validator: Callable[[Dict[str, Any]], ValidationResult]
    ) -> ABValidationResult:
        """
        Validate record using appropriate validator based on A/B treatment assignment.

        Deterministically assigns treatment based on record_id, routes to the
        appropriate validator, records metrics, and returns combined result.

        Treatment Assignment:
        - Deterministic based on record_id (consistent hashing)
        - Same record_id always gets same treatment
        - Distribution controlled by treatment_ratio

        Args:
            record: Data record dict with 'record_id' field. Validators receive
                a reference to the original record and may mutate it.
            control_validator: Callable for control branch validation
                Signature: (record: Dict) -> ValidationResult
            variant_validator: Callable for treatment branch validation
                Signature: (record: Dict) -> ValidationResult

        Returns:
            ABValidationResult with validation outcome and treatment info

        Raises:
            TypeError: If record is not a dict or validators are not callable
            ValueError: If record missing 'record_id' field
            RuntimeError: If a validator raises an exception (with context)

        Example:
            >>> result = wrapper.validate_with_ab_info(
            ...     record={"record_id": "abc123", "value": 42},
            ...     control_validator=strict_validator.validate,
            ...     variant_validator=lenient_validator.validate
            ... )
            >>> if result.is_variant:
            ...     print("Used lenient validation")
        """
        # P0: Validate input types
        if not callable(control_validator):
            raise TypeError(
                f"control_validator must be callable, got {type(control_validator).__name__}"
            )
        if not callable(variant_validator):
            raise TypeError(
                f"variant_validator must be callable, got {type(variant_validator).__name__}"
            )
        if not isinstance(record, dict):
            raise TypeError(
                f"record must be a dict, got {type(record).__name__}"
            )

        # Extract record_id for treatment assignment
        record_id = record.get("record_id")
        if not record_id:
            raise ValueError("Record must have 'record_id' field")

        # Get deterministic treatment assignment
        assignment = self.controller.assign_treatment(record_id=record_id)
        controller_treatment = assignment.treatment  # "control" or "variant"

        # Route to appropriate validator based on treatment
        # P1: Exception handling with context about which treatment failed
        if controller_treatment == "variant":
            try:
                validation_result = variant_validator(record)
            except Exception as e:
                raise RuntimeError(
                    f"variant_validator failed for treatment '{controller_treatment}': {e}"
                ) from e
        else:  # controller_treatment == "control"
            try:
                validation_result = control_validator(record)
            except Exception as e:
                raise RuntimeError(
                    f"control_validator failed for treatment '{controller_treatment}': {e}"
                ) from e

        # Record prediction in metrics collector
        # Use controller treatment names ("control"/"variant")
        # P1: is_valid is used as prediction for metrics tracking (validation outcome)
        self.metrics_collector.record_prediction(
            sample_id=record_id,
            treatment=controller_treatment,
            prediction=validation_result.is_valid,  # Using is_valid as prediction
            score=validation_result.quality_score,
            ground_truth=None  # No ground truth in validation context
        )

        # Map to user-facing treatment names
        # Internal: "control"/"variant" → External: "control"/"treatment"
        user_treatment = "treatment" if controller_treatment == "variant" else "control"

        return ABValidationResult(
            validation_result=validation_result,
            treatment=user_treatment,
            is_variant=(controller_treatment == "variant")
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get all metrics from the metrics collector.

        Delegates to BasicMetricsCollector.get_all_metrics() and returns
        the complete metrics dictionary.

        Returns:
            Dictionary with metrics for all treatments and comparisons

        Example:
            >>> metrics = wrapper.get_metrics()
            >>> print(f"Control samples: {metrics['control']['total_samples']}")
            >>> print(f"Variant samples: {metrics['variant']['total_samples']}")
        """
        return self.metrics_collector.get_all_metrics()

    def export_metrics(self, output_path: Path) -> None:
        """
        Export metrics to JSON file.

        Delegates to BasicMetricsCollector.export_json() to write all
        collected metrics to the specified path.

        Args:
            output_path: Path where JSON file should be written

        Raises:
            IOError: If file write operation fails
            OSError: If directory doesn't exist or path is invalid

        Example:
            >>> from pathlib import Path
            >>> wrapper.export_metrics(Path("results/validation_ab_test.json"))
        """
        self.metrics_collector.export_json(output_path)

    def get_stats(self) -> TreatmentStats:
        """
        Get A/B testing controller statistics.

        Provides treatment distribution statistics from the controller,
        showing how many records were assigned to each treatment.

        Returns:
            TreatmentStats dict with total_samples, control_count, variant_count

        Example:
            >>> stats = wrapper.get_stats()
            >>> print(f"Total: {stats['total_samples']}")
            >>> print(f"Control: {stats['control_count']}")
            >>> print(f"Variant: {stats['variant_count']}")
        """
        return self.controller.get_stats()
