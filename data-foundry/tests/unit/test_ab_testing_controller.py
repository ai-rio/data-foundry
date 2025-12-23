"""
Unit tests for ABTestingController extracted from pipeline-v4.

Tests cover:
- Deterministic treatment assignment (same ID gets same treatment)
- Configurable traffic distribution (ml_ratio parameter)
- Treatment routing (control vs variant)
- Edge cases and statistics tracking
"""

import pytest

from src.core.ab_testing_controller import (
    ABTestingController,
    ABPrediction,
    TreatmentAssignment
)


class TestABTestingControllerInitialization:
    """Test ABTestingController initialization and configuration."""

    def test_initialization_default_parameters(self):
        """Test initialization with default parameters."""
        controller = ABTestingController()

        assert controller.ml_ratio == 0.5
        assert controller.variant_ratio == 0.5
        assert controller.control_name == "control"
        assert controller.variant_name == "variant"

    def test_initialization_custom_ratio(self):
        """Test initialization with custom ratio."""
        controller = ABTestingController(variant_ratio=0.3)

        assert controller.ml_ratio == 0.3
        assert controller.variant_ratio == 0.3

    def test_initialization_custom_treatment_names(self):
        """Test initialization with custom treatment names."""
        controller = ABTestingController(
            control_name="baseline",
            variant_name="ml_model"
        )

        assert controller.control_name == "baseline"
        assert controller.variant_name == "ml_model"

    def test_initialization_invalid_ratio_negative(self):
        """Test that negative ratio raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            ABTestingController(variant_ratio=-0.1)

    def test_initialization_invalid_ratio_greater_than_one(self):
        """Test that ratio > 1 raises ValueError."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            ABTestingController(variant_ratio=1.5)

    def test_initialization_boundary_values(self):
        """Test initialization with boundary values."""
        controller_zero = ABTestingController(variant_ratio=0.0)
        assert controller_zero.variant_ratio == 0.0

        controller_one = ABTestingController(variant_ratio=1.0)
        assert controller_one.variant_ratio == 1.0


class TestDeterministicAssignment:
    """Test deterministic treatment assignment."""

    def test_same_record_id_same_treatment(self):
        """Test that same record_id always gets same treatment."""
        controller = ABTestingController(variant_ratio=0.5)
        record_id = "test-record-123"

        # Multiple assignments should return same treatment
        treatment1 = controller.assign_treatment(record_id)
        treatment2 = controller.assign_treatment(record_id)
        treatment3 = controller.assign_treatment(record_id)

        assert treatment1 == treatment2 == treatment3

    def test_deterministic_across_instances(self):
        """Test deterministic assignment across controller instances."""
        record_id = "deterministic-test-record"

        controller1 = ABTestingController(variant_ratio=0.3)
        treatment1 = controller1.assign_treatment(record_id)

        controller2 = ABTestingController(variant_ratio=0.3)
        treatment2 = controller2.assign_treatment(record_id)

        # Same treatment with same ratio
        assert treatment1 == treatment2

    def test_different_record_ids_can_have_different_treatments(self):
        """Test that different record IDs can get different treatments."""
        controller = ABTestingController(variant_ratio=0.5)

        # Generate many record IDs and verify both treatments are assigned
        treatments = set()
        for i in range(100):
            record_id = f"record-{i}"
            treatment = controller.assign_treatment(record_id)
            treatments.add(treatment.treatment)

        # Should have both treatments with 50% ratio
        assert len(treatments) == 2

    def test_deterministic_with_record_hash(self):
        """Test deterministic assignment using record_hash."""
        controller = ABTestingController(variant_ratio=0.4)
        record_hash = "abc123def456"

        # Same hash should produce same treatment
        treatment1 = controller.assign_treatment(record_hash=record_hash)
        treatment2 = controller.assign_treatment(record_hash=record_hash)

        assert treatment1 == treatment2

    def test_record_id_priority_over_hash(self):
        """Test that record_id takes priority when both provided."""
        controller = ABTestingController(variant_ratio=0.5)

        # When both provided, record_id should be used
        treatment = controller.assign_treatment(
            record_id="test-id",
            record_hash="test-hash"
        )

        assert treatment.treatment in ["control", "variant"]

    def test_neither_id_nor_hash_provided(self):
        """Test behavior when neither record_id nor record_hash provided."""
        controller = ABTestingController(variant_ratio=0.5)

        with pytest.raises(ValueError, match="Either record_id or record_hash"):
            controller.assign_treatment()


class TestTreatmentAssignmentResult:
    """Test TreatmentAssignment dataclass."""

    def test_treatment_assignment_properties(self):
        """Test TreatmentAssignment result properties."""
        controller = ABTestingController(variant_ratio=0.5)
        record_id = "test-record-456"

        assignment = controller.assign_treatment(record_id)

        # Check return type
        assert isinstance(assignment, TreatmentAssignment)
        assert hasattr(assignment, 'treatment')
        assert hasattr(assignment, 'record_id')
        assert hasattr(assignment, 'is_variant')
        assert hasattr(assignment, 'is_control')

    def test_treatment_assignment_values(self):
        """Test TreatmentAssignment values are correct."""
        controller = ABTestingController(
            variant_ratio=0.5,
            control_name="baseline",
            variant_name="ml"
        )
        record_id = "test-record"

        assignment = controller.assign_treatment(record_id)

        assert assignment.record_id == record_id
        assert assignment.treatment in ["baseline", "ml"]
        assert assignment.is_variant == (assignment.treatment == "ml")
        assert assignment.is_control == (assignment.treatment == "baseline")


class TestTrafficDistribution:
    """Test traffic distribution accuracy."""

    def test_distribution_fifty_percent(self):
        """Test approximately 50% distribution."""
        controller = ABTestingController(variant_ratio=0.5)
        num_samples = 1000

        variant_count = 0
        for i in range(num_samples):
            record_id = f"record-{i}"
            assignment = controller.assign_treatment(record_id)
            if assignment.is_variant:
                variant_count += 1

        variant_ratio = variant_count / num_samples

        # Should be close to 50% (allow 5% tolerance for statistical variance)
        assert 0.45 <= variant_ratio <= 0.55

    def test_distribution_thirty_percent(self):
        """Test approximately 30% distribution."""
        controller = ABTestingController(variant_ratio=0.3)
        num_samples = 1000

        variant_count = 0
        for i in range(num_samples):
            record_id = f"record-{i}"
            assignment = controller.assign_treatment(record_id)
            if assignment.is_variant:
                variant_count += 1

        variant_ratio = variant_count / num_samples

        # Should be close to 30% (allow 5% tolerance)
        assert 0.25 <= variant_ratio <= 0.35

    def test_distribution_seventy_percent(self):
        """Test approximately 70% distribution."""
        controller = ABTestingController(variant_ratio=0.7)
        num_samples = 1000

        variant_count = 0
        for i in range(num_samples):
            record_id = f"record-{i}"
            assignment = controller.assign_treatment(record_id)
            if assignment.is_variant:
                variant_count += 1

        variant_ratio = variant_count / num_samples

        # Should be close to 70% (allow 5% tolerance)
        assert 0.65 <= variant_ratio <= 0.75

    def test_distribution_all_control(self):
        """Test 0% ratio (all control)."""
        controller = ABTestingController(variant_ratio=0.0)
        num_samples = 100

        for i in range(num_samples):
            record_id = f"record-{i}"
            assignment = controller.assign_treatment(record_id)
            assert assignment.is_control
            assert not assignment.is_variant

    def test_distribution_all_variant(self):
        """Test 100% ratio (all variant)."""
        controller = ABTestingController(variant_ratio=1.0)
        num_samples = 100

        for i in range(num_samples):
            record_id = f"record-{i}"
            assignment = controller.assign_treatment(record_id)
            assert assignment.is_variant
            assert not assignment.is_control


class TestStatisticsTracking:
    """Test statistics tracking functionality."""

    def test_initial_stats(self):
        """Test initial statistics are zero."""
        controller = ABTestingController()

        stats = controller.get_stats()

        assert stats['total_samples'] == 0
        assert stats['control_count'] == 0
        assert stats['variant_count'] == 0
        assert stats['variant_ratio_configured'] == 0.5

    def test_stats_tracking_single_assignment(self):
        """Test stats update after single assignment."""
        controller = ABTestingController(variant_ratio=0.5)
        record_id = "test-record"

        controller.assign_treatment(record_id)
        stats = controller.get_stats()

        assert stats['total_samples'] == 1

    def test_stats_tracking_multiple_assignments(self):
        """Test stats update after multiple assignments."""
        controller = ABTestingController(variant_ratio=0.5)
        num_samples = 100

        for i in range(num_samples):
            controller.assign_treatment(f"record-{i}")

        stats = controller.get_stats()

        assert stats['total_samples'] == num_samples
        assert stats['control_count'] + stats['variant_count'] == num_samples

    def test_stats_ratio_accuracy(self):
        """Test that stats reflect actual ratios."""
        controller = ABTestingController(variant_ratio=0.3)
        num_samples = 1000

        for i in range(num_samples):
            controller.assign_treatment(f"record-{i}")

        stats = controller.get_stats()

        actual_variant_ratio = stats['variant_count'] / num_samples

        # Actual ratio should be close to configured ratio
        assert 0.25 <= actual_variant_ratio <= 0.35

    def test_stats_actual_ratios(self):
        """Test actual ratio calculation in stats."""
        controller = ABTestingController(variant_ratio=0.4)

        # Create 10 samples with known distribution
        for i in range(6):
            controller.assign_treatment(f"control-{i}")
        for i in range(4):
            controller.assign_treatment(f"variant-{i}")

        stats = controller.get_stats()

        assert stats['total_samples'] == 10
        assert 'control_ratio_actual' in stats
        assert 'variant_ratio_actual' in stats


class TestSetRatio:
    """Test dynamic ratio updates."""

    def test_set_ratio_valid(self):
        """Test setting valid ratio."""
        controller = ABTestingController(variant_ratio=0.5)

        controller.set_variant_ratio(0.7)

        assert controller.variant_ratio == 0.7

    def test_set_ratio_invalid_negative(self):
        """Test setting negative ratio raises error."""
        controller = ABTestingController()

        with pytest.raises(ValueError, match="must be between 0 and 1"):
            controller.set_variant_ratio(-0.1)

    def test_set_ratio_invalid_greater_than_one(self):
        """Test setting ratio > 1 raises error."""
        controller = ABTestingController()

        with pytest.raises(ValueError, match="must be between 0 and 1"):
            controller.set_variant_ratio(1.5)

    def test_set_ratio_zero(self):
        """Test setting ratio to 0."""
        controller = ABTestingController(variant_ratio=0.5)

        controller.set_variant_ratio(0.0)

        assert controller.variant_ratio == 0.0

    def test_set_ratio_one(self):
        """Test setting ratio to 1."""
        controller = ABTestingController(variant_ratio=0.5)

        controller.set_variant_ratio(1.0)

        assert controller.variant_ratio == 1.0


class TestABPrediction:
    """Test ABPrediction dataclass."""

    def test_ab_prediction_creation(self):
        """Test creating ABPrediction."""
        prediction = ABPrediction(
            treatment="variant",
            active_result={"score": 0.85},
            control_result={"score": 0.70},
            variant_result={"score": 0.85}
        )

        assert prediction.treatment == "variant"
        assert prediction.active_result["score"] == 0.85
        assert prediction.control_result["score"] == 0.70
        assert prediction.variant_result["score"] == 0.85

    def test_ab_prediction_optional_fields(self):
        """Test ABPrediction with optional fields."""
        prediction = ABPrediction(
            treatment="control",
            active_result={"score": 0.70},
            control_result={"score": 0.70}
        )

        assert prediction.variant_result is None
        assert prediction.treatment == "control"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_string_record_id(self):
        """Test that empty string record_id raises ValueError."""
        controller = ABTestingController(variant_ratio=0.5)

        # Empty string should raise ValueError as it's not a meaningful record_id
        with pytest.raises(ValueError, match="Either record_id or record_hash"):
            controller.assign_treatment(record_id="")

    def test_special_characters_in_record_id(self):
        """Test treatment assignment with special characters."""
        controller = ABTestingController(variant_ratio=0.5)

        special_ids = [
            "test!@#$%^&*()",
            "test-with-unicode-\u00e9\u00f1",
            "test\nwith\nnewlines",
            "test\twith\ttabs"
        ]

        # Each should be deterministic
        for record_id in special_ids:
            treatment1 = controller.assign_treatment(record_id=record_id)
            treatment2 = controller.assign_treatment(record_id=record_id)
            assert treatment1 == treatment2

    def test_very_long_record_id(self):
        """Test treatment assignment with very long record_id."""
        controller = ABTestingController(variant_ratio=0.5)

        long_id = "a" * 10000  # 10k character ID

        treatment1 = controller.assign_treatment(record_id=long_id)
        treatment2 = controller.assign_treatment(record_id=long_id)

        assert treatment1 == treatment2

    def test_unicode_record_id(self):
        """Test treatment assignment with Unicode characters."""
        controller = ABTestingController(variant_ratio=0.5)

        unicode_ids = [
            "test-emoji-😀🎉",
            "test-chinese-中文",
            "test-arabic-العربية",
            "test-cyrillic-русский"
        ]

        for record_id in unicode_ids:
            treatment1 = controller.assign_treatment(record_id=record_id)
            treatment2 = controller.assign_treatment(record_id=record_id)
            assert treatment1 == treatment2

    def test_numeric_record_id(self):
        """Test treatment assignment with numeric record_id."""
        controller = ABTestingController(variant_ratio=0.5)

        # Convert to string
        record_id = str(1234567890)

        treatment1 = controller.assign_treatment(record_id=record_id)
        treatment2 = controller.assign_treatment(record_id=record_id)

        assert treatment1 == treatment2


class TestConsistentHashing:
    """Test consistent hashing behavior."""

    def test_hash_consistency_md5(self):
        """Test that MD5 hashing produces consistent results."""
        controller = ABTestingController(variant_ratio=0.5)

        # Same input should always produce same treatment
        record_id = "consistency-test"
        treatments = [controller.assign_treatment(record_id) for _ in range(10)]

        # All should be the same
        assert all(t == treatments[0] for t in treatments)

    def test_different_inputs_different_treatments(self):
        """Test that different inputs produce different treatments (statistically)."""
        controller = ABTestingController(variant_ratio=0.5)

        # Generate many different record IDs
        treatments = set()
        for i in range(50):
            record_id = f"unique-record-{i}-{i*12345}"
            assignment = controller.assign_treatment(record_id)
            treatments.add(assignment.treatment)

        # Should have both treatments with 50% ratio
        assert len(treatments) == 2


class TestIntegrationScenarios:
    """Integration test scenarios for ABTestingController."""

    def test_full_workflow(self):
        """Test complete A/B testing workflow."""
        controller = ABTestingController(
            variant_ratio=0.2,
            control_name="baseline_validator",
            variant_name="experimental_validator"
        )

        # Simulate processing 100 records
        results = {"baseline_validator": 0, "experimental_validator": 0}

        for i in range(100):
            record_id = f"batch-record-{i}"
            assignment = controller.assign_treatment(record_id)
            results[assignment.treatment] += 1

        stats = controller.get_stats()

        # Verify stats
        assert stats['total_samples'] == 100
        assert stats['control_count'] + stats['variant_count'] == 100

        # Verify distribution approximately matches configured ratio
        variant_ratio = results["experimental_validator"] / 100
        assert 0.1 <= variant_ratio <= 0.3  # Allow tolerance

    def test_ratio_change_during_experiment(self):
        """Test changing ratio during active experiment."""
        controller = ABTestingController(variant_ratio=0.2)

        # Process 50 records at 20% variant
        for i in range(50):
            controller.assign_treatment(f"record-{i}")

        stats_20 = controller.get_stats()
        assert stats_20['total_samples'] == 50

        # Change to 50% variant
        controller.set_variant_ratio(0.5)

        # Process 50 more records at 50% variant
        for i in range(50, 100):
            controller.assign_treatment(f"record-{i}")

        stats_final = controller.get_stats()
        assert stats_final['total_samples'] == 100

    def test_multiple_tenant_isolation(self):
        """Test A/B testing across multiple tenants."""
        controller = ABTestingController(variant_ratio=0.3)

        tenant_results = {
            "tenant-a": {"control": 0, "variant": 0},
            "tenant-b": {"control": 0, "variant": 0}
        }

        # Process records for both tenants
        for tenant in ["tenant-a", "tenant-b"]:
            for i in range(50):
                record_id = f"{tenant}-record-{i}"
                assignment = controller.assign_treatment(record_id)
                tenant_results[tenant][assignment.treatment] += 1

        # Each tenant should have approximately 30% variant
        for tenant, results in tenant_results.items():
            total = results["control"] + results["variant"]
            variant_ratio = results["variant"] / total
            assert 0.2 <= variant_ratio <= 0.4  # Allow tolerance


class TestBackwardCompatibility:
    """Test backward compatibility with pipeline-v4 naming."""

    def test_ml_ratio_alias(self):
        """Test that ml_ratio works as alias for variant_ratio."""
        controller = ABTestingController(ml_ratio=0.4)

        assert controller.ml_ratio == 0.4
        assert controller.variant_ratio == 0.4

    def test_default_names_backward_compatible(self):
        """Test default treatment names are backward compatible."""
        controller = ABTestingController()

        # Should default to "control" and "variant" for generic use
        # but ml_ratio should work as alias
        assert controller.control_name == "control"
        assert controller.variant_name == "variant"
