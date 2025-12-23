"""
Integration Tests for Complete Signal Detection Pipeline
========================================================

Comprehensive integration tests for Week 3 Signal Detection components.
Tests the complete workflow from data ingestion through quality prediction.

Pipeline Components:
1. DataRecord creation and validation
2. FeatureEngineering for feature extraction
3. SignalDetector for rule-based signal detection
4. QualityPredictor for ML-based quality prediction
5. A/B testing framework for comparing approaches

Author: Data Foundry v4-df-migration Week 3
Version: 1.0.0
"""

from datetime import datetime, UTC
import pytest
import time
import numpy as np

from src.models.data_record import DataRecord, DataSource, DataStatus
from src.ml.feature_engineering import FeatureEngineering
from src.ml.quality_predictor import QualityPredictor
from src.core.signal_detector import SignalDetector
from src.core.ab_testing_wrapper import ABTestingWrapper
from src.core.basic_metrics import BasicMetricsCollector


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


class TestEndToEndPipeline:
    """Test complete end-to-end signal detection pipeline"""

    def test_pipeline_from_record_to_prediction(self):
        """Test complete pipeline from DataRecord to quality prediction"""
        # Step 1: Create DataRecord
        record = create_test_record(
            record_id="pipeline_test_1",
            data_preview="Looking for a tool to automate my workflow",
            raw_data='{"text": "I need help with task management and automation"}',
            data_quality_score=0.85,
            access_count=50,
        )

        # Step 2: Feature Engineering - Fit on training data
        fe = FeatureEngineering()
        train_records = [
            create_test_record(
                record_id=f"train{i}",
                data_preview=f"Tool software help {i}",
                raw_data=f'{{"text": "Problem solution need {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(train_records)

        # Step 3: Extract features from test record
        features = fe.extract_features(record)
        assert features is not None
        assert len(features) > 0

        # Step 4: Rule-based signal detection
        detector = SignalDetector(threshold=70)
        signal_result = detector.detect_signals(record)

        assert signal_result.signal_type in ["TOOL_REQUEST", "PAIN_COMPLAINT", "NONE"]
        assert isinstance(signal_result.signal_strength, (int, float))
        assert isinstance(signal_result.should_analyze, bool)

        # Step 5: ML-based quality prediction
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        # Pad features if needed
        if len(features) < 111:
            padded = np.zeros(111)
            padded[:len(features)] = features
            features = padded

        quality_proba = qp.predict_proba(features)
        assert 0 <= quality_proba <= 1

        # Step 6: Compare results
        # Both approaches should agree this is high-quality content
        assert signal_result.signal_strength > 50 or quality_proba > 0.3

    def test_pipeline_with_low_quality_record(self):
        """Test pipeline correctly handles low-quality records"""
        # Create low-quality record
        record = create_test_record(
            record_id="low_quality_1",
            data_preview="just some text",
            raw_data='{"text": "random content here"}',
            data_quality_score=0.1,  # Low quality
            access_count=0,  # No engagement
        )

        # Feature extraction should work
        fe = FeatureEngineering()
        fe.fit([record])  # Fit on single record
        features = fe.extract_features(record)
        assert features is not None

        # Signal detector should filter this out
        detector = SignalDetector(threshold=70)
        signal_result = detector.detect_signals(record)

        assert signal_result.signal_type == "NONE"
        assert signal_result.signal_strength == 0
        assert signal_result.should_analyze is False

    def test_pipeline_batch_processing(self):
        """Test pipeline processes multiple records efficiently"""
        # Create batch of records
        records = [
            create_test_record(
                record_id=f"batch{i}",
                data_preview=f"Looking for tool {i}" if i % 3 == 0 else "Regular content",
                raw_data=f'{{"text": "Need help with solution {i}"}}',
                data_quality_score=0.7 + (i % 3) * 0.1,
                access_count=10 + i * 5,
            )
            for i in range(30)
        ]

        # Feature engineering batch processing
        fe = FeatureEngineering()
        fe.fit(records)

        features_batch = fe.extract_features_batch(records)
        assert features_batch.shape[0] == 30

        # Process with signal detector
        detector = SignalDetector(threshold=70)
        signal_results = [detector.detect_signals(r) for r in records]

        # Verify results
        assert len(signal_results) == 30
        signal_types = [r.signal_type for r in signal_results]
        assert all(st in ["TOOL_REQUEST", "PAIN_COMPLAINT", "PRICE_MENTION", "PROBLEM_SOLUTION", "COMPARISON", "NONE"] for st in signal_types)

        # ML prediction batch
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        # Pad features for batch prediction
        if features_batch.shape[1] < 111:
            padded = np.zeros((features_batch.shape[0], 111))
            padded[:, :features_batch.shape[1]] = features_batch
            features_batch = padded

        probas = qp.predict_batch(features_batch)
        assert len(probas) == 30
        assert all(0 <= p <= 1 for p in probas)


class TestABTestingPipelineIntegration:
    """Test A/B testing integration with signal detection pipeline"""

    def test_ab_test_pipeline_workflow(self):
        """Test complete A/B test workflow with signal detection"""
        # Create A/B testing wrapper
        wrapper = ABTestingWrapper(
            test_name="signal_vs_ml_pipeline",
            treatment_ratio=0.5
        )

        # Create metrics collector
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")  # Rule-based
        metrics.add_treatment("variant")  # ML-based

        # Create components
        detector = SignalDetector(threshold=70)
        fe = FeatureEngineering()
        qp = QualityPredictor(allow_mock_fallback=True)

        # Fit feature engineering
        train_records = [
            create_test_record(
                record_id=f"train{i}",
                data_preview=f"Tool help {i}",
                raw_data=f'{{"text": "Problem solution {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(train_records)
        qp._load_model()

        # Process test records through A/B test
        test_records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Looking for tool {i}" if i % 3 == 0 else "Regular content",
                raw_data=f'{{"text": "Need help {i}"}}',
            )
            for i in range(60)
        ]

        for idx, record in enumerate(test_records):
            # Get treatment assignment
            treatment = wrapper.controller.assign_treatment(record.record_id).treatment

            if treatment == "control":
                # Rule-based approach
                result = detector.detect_signals(record)
                prediction = int(result.should_analyze)
                score = result.signal_strength / 100
            else:
                # ML approach
                features = fe.extract_features(record)
                if len(features) < 111:
                    padded = np.zeros(111)
                    padded[:len(features)] = features
                    features = padded
                proba = qp.predict_proba(features)
                prediction = int(proba > 0.5)
                score = proba

            # Record metrics
            metrics.record_prediction(
                sample_id=record.record_id,
                treatment=treatment,
                prediction=bool(prediction),
                score=score,
                ground_truth=idx % 3 == 0  # Ground truth: every 3rd is high quality
            )

        # Verify metrics collected
        metrics_dict = metrics.get_all_metrics()
        assert "control" in metrics_dict
        assert "variant" in metrics_dict

        # Verify A/B test stats
        stats = wrapper.controller.get_stats()
        assert stats["total_samples"] == 60


class TestPipelinePerformance:
    """Test pipeline performance and optimization"""

    def test_regex_precompilation_performance(self):
        """Test that regex patterns are pre-compiled for performance"""
        detector = SignalDetector(threshold=70)

        # Verify patterns are pre-compiled
        assert detector.opportunity_patterns is not None
        for signal_type, patterns in detector.opportunity_patterns.items():
            for pattern in patterns:
                # Should be compiled Pattern objects, not strings
                assert hasattr(pattern, 'finditer'), f"Pattern for {signal_type} is not compiled"

        # Benchmark: Pre-compiled patterns should be fast
        record = create_test_record(
            record_id="perf_test",
            data_preview="Looking for a tool for automation and recommendations",
            raw_data='{"text": "Need help with solution"}',
        )

        start_time = time.time()
        for _ in range(100):
            detector.detect_signals(record)
        elapsed = time.time() - start_time

        # Should process 100 records in reasonable time (< 1 second)
        assert elapsed < 1.0, f"Performance issue: 100 detections took {elapsed:.3f}s"

    def test_feature_engineering_caching(self):
        """Test feature engineering handles repeated calls efficiently"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"cache{i}",
                data_preview=f"Tool help {i}",
                raw_data=f'{{"text": "Problem {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        # Same record should extract features consistently
        test_record = create_test_record(
            record_id="cache_test",
            data_preview="Looking for tool",
            raw_data=f'{{"text": "Need help"}}',
        )

        features1 = fe.extract_features(test_record)
        features2 = fe.extract_features(test_record)

        # Results should be identical
        np.testing.assert_array_equal(features1, features2)

    def test_model_loading_performance(self):
        """Test model loading is efficient (lazy loading)"""
        qp = QualityPredictor(allow_mock_fallback=True)

        # Model should not be loaded initially (lazy loading)
        assert qp.model is None
        assert qp.is_loaded is False

        # Load model
        qp._load_model()

        # Now it should be loaded
        assert qp.model is not None
        assert qp.is_loaded is True

        # Subsequent calls should not reload
        start_time = time.time()
        qp._load_model()
        elapsed = time.time() - start_time

        # Should be instant (already loaded)
        assert elapsed < 0.01, f"Model re-loading took {elapsed:.3f}s"


class TestPipelineEdgeCases:
    """Test pipeline handles edge cases correctly"""

    def test_pipeline_with_empty_text(self):
        """Test pipeline handles records with no text content"""
        record = create_test_record(
            record_id="empty_text",
            data_preview="",
            raw_data="",
            data_quality_score=0.9,
            access_count=100,
        )

        # Signal detector should handle empty text
        detector = SignalDetector(threshold=70)
        result = detector.detect_signals(record)

        assert result.signal_type == "NONE"
        assert result.signal_strength == 0
        assert result.should_analyze is False

        # Feature engineering should handle empty text
        fe = FeatureEngineering()
        fe.fit([record])
        features = fe.extract_features(record)

        # Should return features (all zeros for empty content)
        assert features is not None
        assert len(features) > 0

    def test_pipeline_with_special_characters(self):
        """Test pipeline handles special characters and unicode"""
        record = create_test_record(
            record_id="unicode_test",
            data_preview="Looking for tool with support for cafe, naive, and emoji",
            raw_data=f'{{"text": "Need help with cafe, naive, and special chars: @#$%^&*()"}}',
        )

        detector = SignalDetector(threshold=70)
        result = detector.detect_signals(record)

        # Should not crash on special characters
        assert result is not None
        assert isinstance(result.signal_strength, (int, float))

    def test_pipeline_with_very_long_content(self):
        """Test pipeline handles very long content"""
        long_text = "Looking for tool " * 1000

        record = create_test_record(
            record_id="long_content",
            data_preview=long_text[:200],  # Preview is truncated
            raw_data=f'{{"text": "{long_text}"}}',
        )

        detector = SignalDetector(threshold=70)
        result = detector.detect_signals(record)

        # Should handle long content without issues
        assert result is not None
        assert isinstance(result.signal_strength, (int, float))


class TestPipelineConsistency:
    """Test pipeline produces consistent results"""

    def test_signal_detector_consistency(self):
        """Test signal detector produces consistent results"""
        detector = SignalDetector(threshold=70)

        record = create_test_record(
            record_id="consistency_test",
            data_preview="Looking for tool recommendations",
            raw_data=f'{{"text": "Need help with automation"}}',
        )

        results = [detector.detect_signals(record) for _ in range(10)]

        # All results should be identical
        signal_types = [r.signal_type for r in results]
        strengths = [r.signal_strength for r in results]

        assert all(st == signal_types[0] for st in signal_types)
        assert all(s == strengths[0] for s in strengths)

    def test_feature_engineering_consistency(self):
        """Test feature engineering produces consistent results"""
        fe = FeatureEngineering()
        train_records = [
            create_test_record(
                record_id=f"train{i}",
                data_preview=f"Tool {i}",
                raw_data=f'{{"text": "Help {i}"}}',
            )
            for i in range(10)
        ]
        fe.fit(train_records)

        record = create_test_record(
            record_id="feat_consistency",
            data_preview="Test content",
            raw_data=f'{{"text": "Test text"}}',
        )

        features_list = [fe.extract_features(record) for _ in range(10)]

        # All features should be identical
        for features in features_list[1:]:
            np.testing.assert_array_equal(features_list[0], features)

    def test_ml_predictor_consistency(self):
        """Test ML predictor produces consistent results"""
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        features = np.ones(111)

        probas = [qp.predict_proba(features) for _ in range(10)]

        # All probabilities should be identical
        assert all(p == probas[0] for p in probas)


class TestPipelineIntegrationPoints:
    """Test integration points between pipeline components"""

    def test_feature_engineering_to_ml_predictor(self):
        """Test feature engineering output works with ML predictor"""
        fe = FeatureEngineering()
        train_records = [
            create_test_record(
                record_id=f"train{i}",
                data_preview=f"Tool {i}",
                raw_data=f'{{"text": "Help {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(train_records)

        record = create_test_record(
            record_id="integration_test",
            data_preview="Looking for tool",
            raw_data=f'{{"text": "Need help"}}',
        )

        features = fe.extract_features(record)

        # Pad if needed
        if len(features) < 111:
            padded = np.zeros(111)
            padded[:len(features)] = features
            features = padded

        # Should work with ML predictor
        qp = QualityPredictor(allow_mock_fallback=True)
        qp._load_model()

        proba = qp.predict_proba(features)
        assert 0 <= proba <= 1

    def test_signal_detector_to_ab_testing(self):
        """Test signal detector output integrates with A/B testing"""
        detector = SignalDetector(threshold=70)
        wrapper = ABTestingWrapper(test_name="signal_ab", treatment_ratio=0.5)
        metrics = BasicMetricsCollector()
        metrics.add_treatment("control")

        record = create_test_record(
            record_id="ab_integration",
            data_preview="Looking for tool",
            raw_data=f'{{"text": "Need help"}}',
        )

        # Get treatment and process
        treatment = wrapper.controller.assign_treatment(record.record_id).treatment
        signal_result = detector.detect_signals(record)

        # Should be able to record signal result as metric
        metrics.record_prediction(
            sample_id=record.record_id,
            treatment=treatment,
            prediction=signal_result.should_analyze,
            score=signal_result.signal_strength / 100,
            ground_truth=True,
        )

        # Verify metric was recorded
        metrics_dict = metrics.get_all_metrics()
        assert "control" in metrics_dict
