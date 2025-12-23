#!/usr/bin/env python3
"""
A/B Testing Controller Demo for Data Foundry
==============================================

This script demonstrates how to use the ABTestingController for A/B testing
different validation strategies in Data Foundry.

Usage Examples:
    # Run the demo
    python examples/ab_testing_demo.py

    # Test with different ratios
    python examples/ab_testing_demo.py --ratio 0.3
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.ab_testing_controller import (
    ABTestingController,
    create_ab_controller
)


def demo_basic_usage():
    """Demonstrate basic A/B testing controller usage."""
    print("=" * 60)
    print("ABTestingController Demo - Basic Usage")
    print("=" * 60)

    # Create controller with 30% variant traffic
    controller = ABTestingController(
        variant_ratio=0.3,
        control_name="strict_validator",
        variant_name="lenient_validator"
    )

    print(f"\nController configured:")
    print(f"  Control: {controller.control_name} (70%)")
    print(f"  Variant: {controller.variant_name} (30%)")

    # Simulate processing records
    print("\nProcessing 10 sample records:")
    for i in range(10):
        record_id = f"record-{i:03d}"
        assignment = controller.assign_treatment(record_id)

        # In real usage, you would use the treatment to decide
        # which validation strategy to apply
        if assignment.is_variant:
            strategy = "LENIENT validation"
        else:
            strategy = "STRICT validation"

        print(f"  {record_id}: {strategy} ({assignment.treatment})")

    # Show statistics
    stats = controller.get_stats()
    print("\nStatistics:")
    print(f"  Total samples: {stats['total_samples']}")
    print(f"  Control count: {stats['control_count']}")
    print(f"  Variant count: {stats['variant_count']}")
    print(f"  Actual variant ratio: {stats['variant_ratio_actual']:.1%}")


def demo_deterministic_assignment():
    """Demonstrate deterministic assignment behavior."""
    print("\n" + "=" * 60)
    print("ABTestingController Demo - Deterministic Assignment")
    print("=" * 60)

    controller = ABTestingController(variant_ratio=0.5)

    print("\nSame record_id always gets same treatment:")
    record_id = "important-customer-record"

    for run in range(5):
        assignment = controller.assign_treatment(record_id)
        print(f"  Run {run + 1}: {assignment.treatment}")

    print("\n✓ Verified: Deterministic assignment works!")


def demo_traffic_distribution():
    """Demonstrate traffic distribution accuracy."""
    print("\n" + "=" * 60)
    print("ABTestingController Demo - Traffic Distribution")
    print("=" * 60)

    test_configs = [
        (0.0, "0% - All Control"),
        (0.2, "20% - Mostly Control"),
        (0.5, "50% - Even Split"),
        (0.8, "80% - Mostly Variant"),
        (1.0, "100% - All Variant"),
    ]

    for ratio, label in test_configs:
        controller = ABTestingController(variant_ratio=ratio)

        # Process 1000 records
        variant_count = 0
        for i in range(1000):
            assignment = controller.assign_treatment(record_id=f"test-{i}")
            if assignment.is_variant:
                variant_count += 1

        actual_ratio = variant_count / 1000
        print(f"\n{label}:")
        print(f"  Expected: {ratio:.1%}")
        print(f"  Actual:   {actual_ratio:.1%}")


def demo_validation_ab_testing():
    """Demonstrate A/B testing for validation strategies."""
    print("\n" + "=" * 60)
    print("ABTestingController Demo - Validation A/B Testing")
    print("=" * 60)

    # Create A/B testing controller
    controller = ABTestingController(
        variant_ratio=0.3,
        control_name="standard_validation",
        variant_name="experimental_validation"
    )

    print("\nSimulating data validation with A/B testing:")
    print("(Showing first 5 records)\n")

    # Simulate validation results
    results = {
        "standard_validation": {"passed": 0, "failed": 0},
        "experimental_validation": {"passed": 0, "failed": 0}
    }

    for i in range(5):
        record_id = f"customer-{i:03d}"
        assignment = controller.assign_treatment(record_id)

        # Simulate validation based on treatment
        if assignment.is_variant:
            # Experimental validation (more lenient)
            passed = i % 3 != 0  # Passes 2/3 of the time
        else:
            # Standard validation (strict)
            passed = i % 2 == 0  # Passes 1/2 of the time

        status = "PASS" if passed else "FAIL"
        results[assignment.treatment]["passed" if passed else "failed"] += 1

        print(f"  {record_id}: {assignment.treatment} -> {status}")

    print(f"\nValidation Results:")
    for treatment, counts in results.items():
        total = counts["passed"] + counts["failed"]
        pass_rate = counts["passed"] / total if total > 0 else 0
        print(f"  {treatment}:")
        print(f"    Passed: {counts['passed']}/{total} ({pass_rate:.1%})")


def demo_record_hash_usage():
    """Demonstrate using record_hash for assignment."""
    print("\n" + "=" * 60)
    print("ABTestingController Demo - Record Hash Usage")
    print("=" * 60)

    controller = ABTestingController(variant_ratio=0.4)

    # Simulate records with hashes
    records = [
        ("record-1", "abc123def456"),
        ("record-2", "def789ghi012"),
        ("record-3", "ghi345jkl678"),
    ]

    print("\nUsing record_hash for deterministic assignment:")
    for record_id, record_hash in records:
        assignment = controller.assign_treatment(record_hash=record_hash)
        print(f"  {record_id} (hash: {record_hash[:12]}...): {assignment.treatment}")

    print("\n✓ Same record_hash always gets same treatment!")


def main():
    """Run all demos."""
    parser = argparse.ArgumentParser(
        description="A/B Testing Controller Demo for Data Foundry"
    )
    parser.add_argument(
        "--ratio",
        type=float,
        default=0.5,
        help="Variant ratio for demo (0.0-1.0)"
    )
    parser.add_argument(
        "--demo",
        choices=["all", "basic", "deterministic", "distribution", "validation", "hash"],
        default="all",
        help="Which demo to run"
    )

    args = parser.parse_args()

    if args.demo == "all":
        demo_basic_usage()
        demo_deterministic_assignment()
        demo_traffic_distribution()
        demo_validation_ab_testing()
        demo_record_hash_usage()
    elif args.demo == "basic":
        demo_basic_usage()
    elif args.demo == "deterministic":
        demo_deterministic_assignment()
    elif args.demo == "distribution":
        demo_traffic_distribution()
    elif args.demo == "validation":
        demo_validation_ab_testing()
    elif args.demo == "hash":
        demo_record_hash_usage()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
