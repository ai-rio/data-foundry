#!/usr/bin/env python3
"""
A/B Testing Framework Validation Script
=========================================

Quick validation script to verify A/B testing framework works correctly.

Tests:
1. Deterministic assignment
2. Traffic distribution
3. Metrics collection
4. Wrapper interface

Author: Data Foundry (adapted from RedditHarbor ML Pipeline)
Version: 1.0.0
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.core.ab_testing_controller import ABTestingController
from src.core.basic_metrics import BasicMetricsCollector
from src.core.ab_testing_wrapper import ABTestingWrapper
from src.core.data_quality import DataQualityValidator, ValidationResult


def test_deterministic_assignment():
    """Test that same record_id gets same treatment"""
    print("\n" + "=" * 60)
    print("TEST 1: Deterministic Assignment")
    print("=" * 60)

    controller = ABTestingController(variant_ratio=0.5)

    # Test 10 samples, 3 times each
    test_ids = [f"test_{i:03d}" for i in range(10)]

    assignments = {}
    for round_num in range(3):
        for test_id in test_ids:
            assignment = controller.assign_treatment(test_id)
            treatment = assignment.treatment

            if test_id not in assignments:
                assignments[test_id] = []

            assignments[test_id].append(treatment)

    # Verify consistency
    failures = 0
    for test_id, treatments in assignments.items():
        if len(set(treatments)) != 1:
            print(f"  ✗ FAIL: {test_id} got different treatments: {treatments}")
            failures += 1

    if failures == 0:
        print(f"  ✓ PASS: All {len(test_ids)} samples consistently assigned")
        return True
    else:
        print(f"  ✗ FAIL: {failures} samples had inconsistent assignments")
        return False


def test_traffic_distribution():
    """Test that traffic distribution matches configured ratio"""
    print("\n" + "=" * 60)
    print("TEST 2: Traffic Distribution")
    print("=" * 60)

    # Test with different ratios
    test_cases = [
        (0.0, "0% variant (control only)"),
        (0.2, "20% variant"),
        (0.5, "50% variant"),
        (1.0, "100% variant"),
    ]

    all_passed = True

    for variant_ratio, description in test_cases:
        controller = ABTestingController(variant_ratio=variant_ratio)

        # Assign 1000 samples
        variant_count = 0
        control_count = 0

        for i in range(10000):
            # Use different ID pattern for better distribution
            assignment = controller.assign_treatment(f"sample_uuid_{i:08d}")
            treatment = assignment.treatment
            if treatment == 'variant':  # variant_name is "variant" by default
                variant_count += 1
            else:
                control_count += 1

        actual_ratio = variant_count / 10000
        error = abs(actual_ratio - variant_ratio)

        # Allow 5% error margin for random distribution
        passed = error < 0.05

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {description}")
        print(f"    Expected: {variant_ratio:.1%}, Actual: {actual_ratio:.1%}, Error: {error:.1%}")

        all_passed = all_passed and passed

    return all_passed


def test_metrics_collection():
    """Test metrics collection and calculation"""
    print("\n" + "=" * 60)
    print("TEST 3: Metrics Collection")
    print("=" * 60)

    metrics = BasicMetricsCollector()

    # Register treatments
    metrics.add_treatment("control")
    metrics.add_treatment("variant")

    # Add test predictions with known ground truth
    test_data = [
        # (sample_id, treatment, prediction, ground_truth)
        ('s1', 'variant', True, True),       # TP
        ('s2', 'variant', True, False),      # FP
        ('s3', 'variant', False, True),      # FN
        ('s4', 'variant', False, False),     # TN
        ('s5', 'control', True, True),       # TP
        ('s6', 'control', False, False),     # TN
    ]

    for sample_id, treatment, pred, truth in test_data:
        metrics.record_prediction(sample_id, treatment, pred, ground_truth=truth)

    # Get metrics
    variant_metrics = metrics.get_treatment_metrics('variant')
    control_metrics = metrics.get_treatment_metrics('control')

    # Verify variant metrics
    variant_passed = (
        variant_metrics.true_positive == 1 and
        variant_metrics.false_positive == 1 and
        variant_metrics.false_negative == 1 and
        variant_metrics.true_negative == 1 and
        variant_metrics.precision == 0.5 and
        variant_metrics.recall == 0.5
    )

    # Verify control metrics
    control_passed = (
        control_metrics.true_positive == 1 and
        control_metrics.true_negative == 1 and
        control_metrics.precision == 1.0 and
        control_metrics.recall == 1.0
    )

    if variant_passed and control_passed:
        print("  ✓ PASS: Metrics calculated correctly")
        print(f"    Variant: Precision={variant_metrics.precision:.2f}, Recall={variant_metrics.recall:.2f}")
        print(f"    Control: Precision={control_metrics.precision:.2f}, Recall={control_metrics.recall:.2f}")
        return True
    else:
        print("  ✗ FAIL: Metrics calculation incorrect")
        return False


def test_wrapper_interface():
    """Test ABTestingWrapper maintains interface with validation"""
    print("\n" + "=" * 60)
    print("TEST 4: Wrapper Interface")
    print("=" * 60)

    # Create wrapper
    wrapper = ABTestingWrapper("test_wrapper", treatment_ratio=0.5)

    # Create validators
    validator = DataQualityValidator()

    # Control validator (standard validation)
    def control_validator(record: dict) -> ValidationResult:
        return validator.validate_record(record)

    # Variant validator (stricter validation - higher quality threshold)
    def variant_validator(record: dict) -> ValidationResult:
        result = validator.validate_record(record)
        # Variant requires higher quality score
        if result.quality_score < 0.8:
            result = ValidationResult(
                is_valid=False,
                completeness_score=result.completeness_score,
                validity_score=result.validity_score,
                quality_score=result.quality_score,
                errors=result.errors + ["Variant requires quality_score >= 0.8"],
                warnings=result.warnings
            )
        return result

    # Test record
    test_record = {
        "record_id": "test_wrapper_001",
        "tenant_id": "tenant_001",
        "data_source": "test_source",
        "raw_data": {"name": "Test", "email": "test@example.com"},
        "file_name": "test.csv",
        "mime_type": "text/csv",
        "created_at": "2025-01-01T00:00:00Z"
    }

    # Test wrapper interface
    result = wrapper.validate_with_ab_info(
        record=test_record,
        control_validator=control_validator,
        variant_validator=variant_validator
    )

    # Verify result structure
    interface_passed = (
        hasattr(result, 'validation_result') and
        hasattr(result, 'treatment') and
        hasattr(result, 'is_variant') and
        isinstance(result.validation_result, ValidationResult) and
        result.treatment in ['control', 'treatment'] and
        isinstance(result.is_variant, bool)
    )

    # Verify treatment assignment
    treatment_ok = result.treatment in ['control', 'treatment']

    # Verify validation result
    validation_ok = (
        hasattr(result.validation_result, 'is_valid') and
        hasattr(result.validation_result, 'quality_score')
    )

    if interface_passed and treatment_ok and validation_ok:
        print("  ✓ PASS: Wrapper interface compatible")
        print(f"    Treatment: {result.treatment}")
        print(f"    Is Variant: {result.is_variant}")
        print(f"    Valid: {result.validation_result.is_valid}")
        print(f"    Quality Score: {result.validation_result.quality_score:.2f}")
        return True
    else:
        print("  ✗ FAIL: Wrapper interface incompatible")
        return False


def run_all_tests():
    """Run all validation tests"""
    print("\n" + "=" * 80)
    print("A/B TESTING FRAMEWORK VALIDATION")
    print("=" * 80)

    results = {
        'Deterministic Assignment': test_deterministic_assignment(),
        'Traffic Distribution': test_traffic_distribution(),
        'Metrics Collection': test_metrics_collection(),
        'Wrapper Interface': test_wrapper_interface(),
    }

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
        all_passed = all_passed and passed

    print("\n" + "=" * 80)

    if all_passed:
        print("✓ ALL TESTS PASSED - A/B framework ready for deployment")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Review A/B testing documentation: docs/ab_testing_*.md")
        print("2. Run examples: python examples/ab_testing_demo.py")
        print("3. Configure feature flags: ENABLE_AB_TESTING=true in .env")
        return 0
    else:
        print("✗ SOME TESTS FAILED - Fix issues before deployment")
        print("=" * 80)
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
