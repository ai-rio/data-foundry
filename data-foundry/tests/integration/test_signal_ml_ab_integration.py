"""
A/B Test Integration: Rule-Based Signal Detection vs ML Quality Prediction
=========================================================================

Integration test for Week 3 A/B testing framework.
Compares rule-based SignalDetector against ML-based QualityPredictor.

This test demonstrates:
1. Using ABTestingWrapper for treatment assignment
2. Collecting metrics with BasicMetricsCollector
3. Comparing rule-based vs ML prediction approaches
"""

from datetime import datetime, UTC
import pytest

from src.core.signal_detector import SignalDetector
from src.ml.quality_predictor import QualityPredictor
from src.ml.feature_engineering import FeatureEngineering
from src.core.ab_testing_wrapper import ABTestingWrapper
from src.core.basic_metrics import BasicMetricsCollector
from src.models.data_record import DataRecord, DataSource, DataStatus


def create_test_record(
    record_id: str,
    data_preview: str,
    raw_data: str,
    data_quality_score: float = 0.8,
    access_count: int = 10,
) -> DataRecord:
    """Helper to create test DataRecord instances"""
    return DataRecord(
        id=1,
        record_id=record_id,
        tenant_id="test_tenant",
        data_source=DataSource.MANUAL,
        status=DataStatus.RAW,
        data_preview=data_preview,
        raw_data=raw_data,
        data_quality_score=data_quality_score,
        access_count=access_count,
        created_at=datetime.now(UTC),
    )


class TestSignalMLABIntegration:
    """A/B test integration for rule-based vs ML approaches"""

    def test_ab_testing_wrapper_assigns_treatments(self):
        """Test that A/B testing wrapper assigns treatments correctly"""
        # Create A/B testing wrapper with 50/50 split
        wrapper = ABTestingWrapper(
            test_name="signal_vs_ml",
            treatment_ratio=0.5
        )

        # Create test records
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview="Looking for a tool that helps with automation",
                raw_data='{"text": "I need help with this problem"}',
            )
            for i in range(100)
        ]

        # Assign treatments
        control_count = 0
        variant_count = 0

        for record in records:
            treatment = wrapper.controller.assign_treatment(record.record_id).treatment
            if treatment == "control":
                control_count += 1
            else:
                variant_count += 1

        # Should have roughly 50/50 split
        assert control_count > 30  # Allow some variance
        assert variant_count > 30
        assert control_count + variant_count == 100

    def test_signal_detector_rule_based_approach(self):
        """Test rule-based signal detection approach"""
        detector = SignalDetector(threshold=70)

        record = create_test_record(
            record_id="test1",
            data_preview="Looking for a tool to automate my workflow",
            raw_data='{"text": "I need help with task management"}',
            data_quality_score=0.85,
            access_count=50,
        )

        result = detector.detect_signals(record)

        assert result.signal_type in ["TOOL_REQUEST", "PAIN_COMPLAINT", "NONE"]
        assert result.signal_strength >= 0
        assert result.should_analyze is True  # High signal content

    def test_ml_quality_predictor_approach(self):
        """Test ML-based quality prediction approach"""
        # Create feature engineering
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Tool software help {i}",
                raw_data=f'{{"text": "Problem solution need {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        # Create quality predictor with mock fallback for testing
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        # Test record
        test_record = create_test_record(
            record_id="test1",
            data_preview="Looking for recommendations software",
            raw_data='{"text": "Tool help automation problem"}',
        )

        # Extract features and predict
        features = fe.extract_features(test_record)
        if len(features) < 111:
            padded = [0.0] * 111
            padded[:len(features)] = features
            features = padded

        quality_proba = qp.predict_proba(features)

        assert 0 <= quality_proba <= 1
        assert isinstance(quality_proba, float)

    def test_collect_metrics_for_both_approaches(self):
        """Test collecting metrics for both rule-based and ML approaches"""
        # Create metrics collector
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")
        metrics.add_treatment("treatment")

        # Create test records
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Looking for tool {i}" if i % 2 == 0 else "Just random content",
                raw_data='{"text": "Need help with solution"}',
            )
            for i in range(50)
        ]

        # Process with rule-based approach
        detector = SignalDetector(threshold=70)

        for record in records:
            result = detector.detect_signals(record)
            metrics.record_prediction(
                sample_id=record.record_id,
                treatment="control",
                prediction=result.should_analyze,
                score=result.signal_strength / 100,
                ground_truth=True  # Assume high-quality data
            )

        # Process with ML approach (with mock fallback for testing)
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        for record in records:
            # Use mock features
            mock_features = [0.7] * 111
            proba = qp.predict_proba(mock_features)
            metrics.record_prediction(
                sample_id=record.record_id,
                treatment="treatment",
                prediction=proba > 0.5,
                score=proba,
                ground_truth=True
            )

        # Export metrics
        metrics_dict = metrics.get_all_metrics()

        assert "control" in metrics_dict
        assert "treatment" in metrics_dict
        # performance is nested inside the treatment dict
        assert "performance" in metrics_dict["control"]
        assert "precision" in metrics_dict["control"]["performance"]

    def test_end_to_end_ab_test_workflow(self):
        """Test end-to-end A/B test workflow for signal vs ML"""
        # Create A/B testing wrapper
        wrapper = ABTestingWrapper(
            test_name="signal_vs_ml",
            treatment_ratio=0.5
        )

        # Create metrics collector
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")
        metrics.add_treatment("variant")  # ABTestingController uses "variant" not "treatment"

        # Create components
        detector = SignalDetector(threshold=70)
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        # Test records
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Looking for tool {i}" if i % 3 == 0 else "Regular content about testing",
                raw_data='{"text": "Need help with solution"}',
            )
            for i in range(30)
        ]

        # Process each record with appropriate treatment
        for record in records:
            # Get treatment assignment
            treatment = wrapper.controller.assign_treatment(record.record_id).treatment

            if treatment == "control":
                # Rule-based approach
                result = detector.detect_signals(record)
                prediction = int(result.should_analyze)
                score = result.signal_strength / 100
            else:
                # ML approach
                mock_features = [0.7] * 111
                proba = qp.predict_proba(mock_features)
                prediction = int(proba > 0.5)
                score = proba

            # Collect metrics
            metrics.record_prediction(
                sample_id=record.record_id,
                treatment=treatment,
                prediction=bool(prediction),
                score=score,
                ground_truth=True  # Assume all valid for this test
            )

        # Export and verify metrics
        metrics_dict = metrics.get_all_metrics()

        # Both treatments should have results
        assert "control" in metrics_dict
        assert "variant" in metrics_dict

        # Get stats
        stats = wrapper.controller.get_stats()
        assert stats["total_samples"] == 30


class TestABTestMetricsComparison:
    """Test comparing metrics between rule-based and ML approaches"""

    def test_compare_precision_both_approaches(self):
        """Test comparing precision between rule-based and ML"""
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")
        metrics.add_treatment("treatment")

        # Simulate control (rule-based) results
        for i in range(50):
            # Rule-based: 80% precision
            y_pred = i % 5 != 0
            metrics.record_prediction(f"control_{i}", "control", y_pred, ground_truth=True)

        # Simulate variant (ML) results
        for i in range(50):
            # ML: 85% precision
            y_pred = i % 7 != 0
            metrics.record_prediction(f"treatment_{i}", "treatment", y_pred, ground_truth=True)

        metrics_dict = metrics.get_all_metrics()

        # Both should have precision metrics (nested under "performance")
        control_precision = metrics_dict["control"].get("performance", {}).get("precision", 0)
        treatment_precision = metrics_dict["treatment"].get("performance", {}).get("precision", 0)
        assert 0 <= control_precision <= 1
        assert 0 <= treatment_precision <= 1

    def test_export_metrics_to_json(self, tmp_path):
        """Test exporting metrics to JSON file"""
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")
        metrics.add_treatment("treatment")

        # Add some results
        for i in range(20):
            metrics.record_prediction(f"c_{i}", "control", True, ground_truth=True)
            metrics.record_prediction(f"t_{i}", "treatment", True, ground_truth=True)

        # Export to file
        output_path = tmp_path / "metrics.json"
        metrics.export_json(output_path)

        # File should exist
        assert output_path.exists()

        # Load and verify
        import json
        with open(output_path) as f:
            loaded = json.load(f)

        # Structure has nested 'metrics' key
        assert "metrics" in loaded
        assert "control" in loaded["metrics"]
        assert "treatment" in loaded["metrics"]
