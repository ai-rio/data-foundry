"""
Unit tests for BasicMetricsCollector

TDD RED Phase: Tests written before implementation
Expected: ImportError (module doesn't exist yet)

This test suite ensures comprehensive coverage of the BasicMetricsCollector
extraction from pipeline-v4 to Data Foundry with key adaptations:
- Generic treatments (dynamic registration via add_treatment())
- Thread safety with threading.Lock
- All original metrics preserved
"""

import pytest
import threading
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

# This import will fail in RED phase (module doesn't exist yet)
from src.core.basic_metrics import (
    TreatmentMetrics,
    BasicMetricsCollector
)


# ==================== FIXTURES ====================

@pytest.fixture
def empty_collector() -> BasicMetricsCollector:
    """Returns BasicMetricsCollector with no treatments registered"""
    return BasicMetricsCollector()


@pytest.fixture
def single_treatment_collector() -> BasicMetricsCollector:
    """Returns collector with one treatment registered"""
    collector = BasicMetricsCollector()
    collector.add_treatment('treatment_a')
    return collector


@pytest.fixture
def sample_collector() -> BasicMetricsCollector:
    """
    Returns collector with 2 treatments and comprehensive sample data.

    treatment_a: 10 predictions with ground truth
    treatment_b: 10 predictions with ground truth
    """
    collector = BasicMetricsCollector()
    collector.add_treatment('treatment_a')
    collector.add_treatment('treatment_b')

    # treatment_a predictions: 6 positive, 4 negative
    for i in range(10):
        sample_id = f'sample_a_{i}'
        prediction = i < 6  # First 6 are positive
        ground_truth = i < 5  # First 5 are actually positive
        score = 0.8 + (i * 0.01) if prediction else 0.3
        collector.record_prediction(
            sample_id=sample_id,
            treatment='treatment_a',
            prediction=prediction,
            score=score,
            ground_truth=ground_truth
        )

    # treatment_b predictions: 4 positive, 6 negative
    for i in range(10):
        sample_id = f'sample_b_{i}'
        prediction = i < 4  # First 4 are positive
        ground_truth = i < 5  # First 5 are actually positive
        score = 0.7 + (i * 0.01) if prediction else 0.4
        collector.record_prediction(
            sample_id=sample_id,
            treatment='treatment_b',
            prediction=prediction,
            score=score,
            ground_truth=ground_truth
        )

    return collector


@pytest.fixture
def confusion_matrix_data() -> tuple[Dict[str, bool], list]:
    """
    Ground truth and predictions for confusion matrix testing.

    Returns:
        (ground_truth, predictions) tuple

    Expected confusion matrix for treatment:
    - TP: 1 (sample1)
    - FN: 1 (sample2)
    - FP: 1 (sample3)
    - TN: 2 (sample4, sample5)
    """
    ground_truth = {
        'sample1': True,
        'sample2': True,
        'sample3': False,
        'sample4': False,
        'sample5': False
    }

    predictions = [
        ('sample1', True),   # TP
        ('sample2', False),  # FN
        ('sample3', True),   # FP
        ('sample4', False),  # TN
        ('sample5', False)   # TN
    ]

    return ground_truth, predictions


@pytest.fixture
def temp_output_path(tmp_path: Path) -> Path:
    """Temporary path for JSON export tests"""
    return tmp_path / "metrics.json"


# ==================== TreatmentMetrics TESTS ====================

class TestTreatmentMetrics:
    """Test TreatmentMetrics dataclass calculations and serialization"""

    def test_precision_calculation_normal_case(self):
        """Verify precision TP/(TP+FP) with normal values"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=5,
            predicted_negative=5,
            true_positive=5,
            false_positive=3
        )
        assert metrics.precision == pytest.approx(5.0 / (5 + 3))

    def test_precision_calculation_zero_division(self):
        """Verify precision returns 0.0 when TP + FP = 0"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=0,
            predicted_negative=10,
            true_positive=0,
            false_positive=0
        )
        assert metrics.precision == 0.0

    def test_recall_calculation_normal_case(self):
        """Verify recall TP/(TP+FN) with normal values"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=5,
            predicted_negative=5,
            true_positive=5,
            false_negative=2
        )
        assert metrics.recall == pytest.approx(5.0 / (5 + 2))

    def test_recall_calculation_zero_division(self):
        """Verify recall returns 0.0 when TP + FN = 0"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=0,
            predicted_negative=10,
            true_positive=0,
            false_negative=0
        )
        assert metrics.recall == 0.0

    def test_f1_score_calculation_normal_case(self):
        """Verify F1 score 2*(precision*recall)/(precision+recall)"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=5,
            predicted_negative=5,
            true_positive=4,
            false_positive=1,
            false_negative=1
        )
        expected_precision = 4.0 / (4 + 1)
        expected_recall = 4.0 / (4 + 1)
        expected_f1 = 2 * (expected_precision * expected_recall) / (expected_precision + expected_recall)
        assert metrics.f1_score == pytest.approx(expected_f1)

    def test_f1_score_calculation_zero_division(self):
        """Verify F1 score returns 0.0 when precision + recall = 0"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=0,
            predicted_negative=10,
            true_positive=0,
            false_positive=0,
            false_negative=0
        )
        assert metrics.f1_score == 0.0

    def test_accuracy_calculation_normal_case(self):
        """Verify accuracy (TP+TN)/total with normal values"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=5,
            predicted_negative=5,
            true_positive=4,
            true_negative=3,
            false_positive=2,
            false_negative=1
        )
        assert metrics.accuracy == pytest.approx((4 + 3) / 10.0)

    def test_accuracy_calculation_zero_division(self):
        """Verify accuracy returns 0.0 when no samples"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=0,
            predicted_positive=0,
            predicted_negative=0
        )
        assert metrics.accuracy == 0.0

    def test_positive_rate_calculation_normal_case(self):
        """Verify positive_rate = predicted_positive/total_samples"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=10,
            predicted_positive=3,
            predicted_negative=7
        )
        assert metrics.positive_rate == pytest.approx(3.0 / 10.0)

    def test_positive_rate_calculation_zero_division(self):
        """Verify positive_rate returns 0.0 when total_samples = 0"""
        metrics = TreatmentMetrics(
            treatment='test',
            total_samples=0,
            predicted_positive=0,
            predicted_negative=0
        )
        assert metrics.positive_rate == 0.0

    def test_to_dict_serialization_complete(self):
        """Verify to_dict returns complete structure with all fields"""
        metrics = TreatmentMetrics(
            treatment='test_treatment',
            total_samples=10,
            predicted_positive=5,
            predicted_negative=5,
            true_positive=4,
            true_negative=3,
            false_positive=1,
            false_negative=2
        )

        result = metrics.to_dict()

        # Verify top-level fields
        assert result['treatment'] == 'test_treatment'
        assert result['total_samples'] == 10
        assert result['predicted_positive'] == 5
        assert result['predicted_negative'] == 5
        assert result['positive_rate'] == pytest.approx(0.5)

        # Verify confusion_matrix nested dict
        assert result['confusion_matrix']['true_positive'] == 4
        assert result['confusion_matrix']['true_negative'] == 3
        assert result['confusion_matrix']['false_positive'] == 1
        assert result['confusion_matrix']['false_negative'] == 2

        # Verify performance nested dict
        assert 'performance' in result
        assert 'precision' in result['performance']
        assert 'recall' in result['performance']
        assert 'f1_score' in result['performance']
        assert 'accuracy' in result['performance']


# ==================== INITIALIZATION & REGISTRATION TESTS ====================

class TestBasicMetricsCollectorInit:
    """Test initialization and dynamic treatment registration"""

    def test_collector_initialization_empty_state(self, empty_collector: BasicMetricsCollector):
        """Verify empty collector has no treatments registered"""
        assert hasattr(empty_collector, 'predictions')
        assert hasattr(empty_collector, 'ground_truth')
        assert hasattr(empty_collector, 'treatments') or hasattr(empty_collector, '_treatments')
        assert len(empty_collector.predictions) == 0
        assert len(empty_collector.ground_truth) == 0

    def test_add_treatment_single(self, empty_collector: BasicMetricsCollector):
        """Verify adding a single treatment makes it available"""
        empty_collector.add_treatment('treatment_a')
        assert 'treatment_a' in empty_collector.predictions
        assert empty_collector.predictions['treatment_a'] == []

    def test_add_treatment_multiple(self, empty_collector: BasicMetricsCollector):
        """Verify adding multiple treatments dynamically"""
        empty_collector.add_treatment('treatment_a')
        empty_collector.add_treatment('treatment_b')
        empty_collector.add_treatment('treatment_c')

        assert 'treatment_a' in empty_collector.predictions
        assert 'treatment_b' in empty_collector.predictions
        assert 'treatment_c' in empty_collector.predictions

    def test_add_treatment_duplicate(self, single_treatment_collector: BasicMetricsCollector):
        """Verify adding duplicate treatment raises ValueError or is idempotent"""
        # Either behavior is acceptable: raise ValueError or silently ignore
        try:
            single_treatment_collector.add_treatment('treatment_a')
            # If no error, verify treatment still exists
            assert 'treatment_a' in single_treatment_collector.predictions
        except ValueError:
            # Also acceptable: explicitly prevent duplicates
            pass


# ==================== PREDICTION RECORDING TESTS ====================

class TestBasicMetricsCollectorRecording:
    """Test prediction recording functionality"""

    def test_record_valid_prediction(self, single_treatment_collector: BasicMetricsCollector):
        """Verify basic prediction recording for registered treatment"""
        single_treatment_collector.record_prediction(
            sample_id='sample_1',
            treatment='treatment_a',
            prediction=True
        )

        assert len(single_treatment_collector.predictions['treatment_a']) == 1
        recorded = single_treatment_collector.predictions['treatment_a'][0]
        assert recorded['sample_id'] == 'sample_1'
        assert recorded['prediction'] is True
        assert recorded['score'] is None

    def test_record_invalid_treatment_raises_error(self, empty_collector: BasicMetricsCollector):
        """Verify recording for unregistered treatment raises ValueError"""
        with pytest.raises(ValueError, match='Invalid treatment|treatment'):
            empty_collector.record_prediction(
                sample_id='sample_1',
                treatment='nonexistent_treatment',
                prediction=True
            )

    def test_record_with_ground_truth(self, single_treatment_collector: BasicMetricsCollector):
        """Verify ground truth is stored correctly"""
        single_treatment_collector.record_prediction(
            sample_id='sample_1',
            treatment='treatment_a',
            prediction=True,
            ground_truth=False
        )

        assert 'sample_1' in single_treatment_collector.ground_truth
        assert single_treatment_collector.ground_truth['sample_1'] is False

    def test_record_with_score(self, single_treatment_collector: BasicMetricsCollector):
        """Verify optional score parameter is stored"""
        single_treatment_collector.record_prediction(
            sample_id='sample_1',
            treatment='treatment_a',
            prediction=True,
            score=0.95
        )

        recorded = single_treatment_collector.predictions['treatment_a'][0]
        assert recorded['score'] == 0.95

    def test_record_multiple_predictions(self, single_treatment_collector: BasicMetricsCollector):
        """Verify multiple predictions are recorded in order"""
        for i in range(5):
            single_treatment_collector.record_prediction(
                sample_id=f'sample_{i}',
                treatment='treatment_a',
                prediction=i % 2 == 0
            )

        assert len(single_treatment_collector.predictions['treatment_a']) == 5


# ==================== METRICS CALCULATION TESTS ====================

class TestBasicMetricsCollectorMetrics:
    """Test metrics calculation functionality"""

    def test_empty_treatment_metrics(self, single_treatment_collector: BasicMetricsCollector):
        """Verify treatment with no predictions returns zeroed metrics"""
        metrics = single_treatment_collector.get_treatment_metrics('treatment_a')

        assert isinstance(metrics, TreatmentMetrics)
        assert metrics.treatment == 'treatment_a'
        assert metrics.total_samples == 0
        assert metrics.predicted_positive == 0
        assert metrics.predicted_negative == 0
        assert metrics.true_positive == 0
        assert metrics.true_negative == 0
        assert metrics.false_positive == 0
        assert metrics.false_negative == 0

    def test_treatment_metrics_basic_counts(self, single_treatment_collector: BasicMetricsCollector):
        """Verify correct total/predicted counts"""
        # Record 10 predictions: 6 positive, 4 negative
        for i in range(10):
            single_treatment_collector.record_prediction(
                sample_id=f'sample_{i}',
                treatment='treatment_a',
                prediction=i < 6
            )

        metrics = single_treatment_collector.get_treatment_metrics('treatment_a')

        assert metrics.total_samples == 10
        assert metrics.predicted_positive == 6
        assert metrics.predicted_negative == 4
        assert metrics.positive_rate == pytest.approx(0.6)

    def test_treatment_metrics_confusion_matrix(self, single_treatment_collector: BasicMetricsCollector,
                                                confusion_matrix_data: tuple):
        """Verify confusion matrix TP/TN/FP/FN correctness"""
        ground_truth, predictions = confusion_matrix_data

        # Record predictions with ground truth
        for sample_id, prediction in predictions:
            single_treatment_collector.record_prediction(
                sample_id=sample_id,
                treatment='treatment_a',
                prediction=prediction,
                ground_truth=ground_truth[sample_id]
            )

        metrics = single_treatment_collector.get_treatment_metrics('treatment_a')

        # Expected: TP=1, TN=2, FP=1, FN=1
        assert metrics.true_positive == 1
        assert metrics.true_negative == 2
        assert metrics.false_positive == 1
        assert metrics.false_negative == 1

        # Verify derived metrics
        assert metrics.precision == pytest.approx(1.0 / (1 + 1))
        assert metrics.recall == pytest.approx(1.0 / (1 + 1))
        assert metrics.accuracy == pytest.approx((1 + 2) / 5.0)

    def test_treatment_metrics_partial_ground_truth(self, single_treatment_collector: BasicMetricsCollector):
        """Verify metrics when some predictions have ground truth, some don't"""
        # Record 5 predictions with ground truth
        for i in range(5):
            single_treatment_collector.record_prediction(
                sample_id=f'sample_{i}',
                treatment='treatment_a',
                prediction=True,
                ground_truth=i < 3
            )

        # Record 5 predictions without ground truth
        for i in range(5, 10):
            single_treatment_collector.record_prediction(
                sample_id=f'sample_{i}',
                treatment='treatment_a',
                prediction=True
            )

        metrics = single_treatment_collector.get_treatment_metrics('treatment_a')

        # All 10 predictions counted
        assert metrics.total_samples == 10
        assert metrics.predicted_positive == 10

        # Only first 5 contribute to confusion matrix
        assert metrics.true_positive == 3
        assert metrics.false_positive == 2
        assert metrics.true_negative == 0
        assert metrics.false_negative == 0


# ==================== COMPARISON & DISTRIBUTION TESTS ====================

class TestBasicMetricsCollectorComparison:
    """Test treatment comparison and distribution statistics"""

    def test_get_all_metrics_structure(self, sample_collector: BasicMetricsCollector):
        """Verify get_all_metrics returns correct dict structure"""
        all_metrics = sample_collector.get_all_metrics()

        # Should have keys for both treatments
        assert 'treatment_a' in all_metrics
        assert 'treatment_b' in all_metrics

        # Should have comparison section
        assert 'comparison' in all_metrics

        # Each treatment should have complete structure
        for treatment in ['treatment_a', 'treatment_b']:
            assert 'total_samples' in all_metrics[treatment]
            assert 'positive_rate' in all_metrics[treatment]
            assert 'confusion_matrix' in all_metrics[treatment]
            assert 'performance' in all_metrics[treatment]

    def test_comparison_metrics(self, sample_collector: BasicMetricsCollector):
        """Verify treatment comparison logic and differences"""
        all_metrics = sample_collector.get_all_metrics()
        comparison = all_metrics['comparison']

        # Should have sample counts
        assert 'treatment_a_samples' in comparison or 'ml_samples' in comparison
        assert 'treatment_b_samples' in comparison or 'baseline_samples' in comparison

        # Should have positive rates
        assert 'positive_rate_diff' in comparison or 'treatment_a_positive_rate' in comparison

        # Should have performance differences (has ground truth)
        if sample_collector.ground_truth:
            assert 'precision_diff' in comparison or 'treatment_a_precision' in comparison
            assert 'recall_diff' in comparison or 'treatment_a_recall' in comparison
            assert 'f1_diff' in comparison or 'treatment_a_f1' in comparison

    def test_get_distribution_stats(self, sample_collector: BasicMetricsCollector):
        """Verify distribution statistics with correct ratios and counts"""
        dist = sample_collector.get_distribution_stats()

        # Should have total and individual counts
        assert 'total_samples' in dist
        assert dist['total_samples'] == 20  # 10 + 10

        # Should have ratios
        # Adapt for generic treatment names
        if 'treatment_a_samples' in dist:
            assert dist['treatment_a_samples'] == 10
            assert dist['treatment_b_samples'] == 10
            assert dist['treatment_a_ratio'] == pytest.approx(0.5)
            assert dist['treatment_b_ratio'] == pytest.approx(0.5)
        elif 'ml_samples' in dist:
            # Backward compatibility check
            assert 'ml_ratio' in dist
            assert 'baseline_ratio' in dist

    def test_get_distribution_stats_empty(self, empty_collector: BasicMetricsCollector):
        """Verify distribution with no samples returns zeroed values"""
        dist = empty_collector.get_distribution_stats()

        assert dist['total_samples'] == 0
        # Ratios should be 0.0 when no samples
        for key, value in dist.items():
            if 'ratio' in key:
                assert value == 0.0


# ==================== EXPORT & THREAD SAFETY TESTS ====================

class TestBasicMetricsCollectorExport:
    """Test JSON export and thread safety"""

    def test_export_json_writes_file(self, sample_collector: BasicMetricsCollector,
                                     temp_output_path: Path):
        """Verify export_json creates file with correct structure"""
        sample_collector.export_json(temp_output_path)

        # Verify file exists
        assert temp_output_path.exists()

        # Verify JSON structure
        with open(temp_output_path, 'r') as f:
            data = json.load(f)

        # Should have top-level sections
        assert 'distribution' in data
        assert 'metrics' in data
        assert 'has_ground_truth' in data
        assert 'total_ground_truth' in data

        # Verify distribution section
        assert data['distribution']['total_samples'] == 20

        # Verify metrics section has both treatments
        assert 'metrics' in data
        metrics = data['metrics']

    def test_export_json_overwrites_existing(self, sample_collector: BasicMetricsCollector,
                                             temp_output_path: Path):
        """Verify export overwrites existing file"""
        # Create initial file
        temp_output_path.write_text('{"old": "data"}')

        # Export should overwrite
        sample_collector.export_json(temp_output_path)

        with open(temp_output_path, 'r') as f:
            data = json.load(f)

        assert 'old' not in data
        assert 'distribution' in data

    def test_concurrent_prediction_recording(self, single_treatment_collector: BasicMetricsCollector):
        """
        Verify thread safety with concurrent predictions.

        Uses 10 threads recording 100 predictions each = 1000 total.
        """
        num_threads = 10
        predictions_per_thread = 100
        total_predictions = num_threads * predictions_per_thread

        def record_predictions(thread_id: int):
            for i in range(predictions_per_thread):
                sample_id = f'sample_thread_{thread_id}_iter_{i}'
                single_treatment_collector.record_prediction(
                    sample_id=sample_id,
                    treatment='treatment_a',
                    prediction=i % 2 == 0,
                    score=0.5
                )

        # Use ThreadPoolExecutor for concurrent execution
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(record_predictions, thread_id)
                for thread_id in range(num_threads)
            ]

            # Wait for all to complete
            for future in futures:
                future.result()

        # Verify all predictions recorded
        final_count = len(single_treatment_collector.predictions['treatment_a'])
        assert final_count == total_predictions, \
            f"Expected {total_predictions} predictions, got {final_count}"

    def test_concurrent_multi_treatment_recording(self, empty_collector: BasicMetricsCollector):
        """
        Verify thread safety with multiple treatments recorded concurrently.
        """
        empty_collector.add_treatment('treatment_a')
        empty_collector.add_treatment('treatment_b')

        def record_for_treatment(treatment: str, count: int):
            for i in range(count):
                empty_collector.record_prediction(
                    sample_id=f'{treatment}_sample_{i}',
                    treatment=treatment,
                    prediction=True
                )

        # Record concurrently for both treatments
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(record_for_treatment, 'treatment_a', 100)
            future_b = executor.submit(record_for_treatment, 'treatment_b', 150)

            future_a.result()
            future_b.result()

        # Verify counts
        assert len(empty_collector.predictions['treatment_a']) == 100
        assert len(empty_collector.predictions['treatment_b']) == 150

    def test_concurrent_add_treatment(self, empty_collector: BasicMetricsCollector):
        """
        Verify thread safety of concurrent add_treatment() calls.

        Tests that multiple threads can safely add treatments concurrently
        without race conditions. Verifies idempotent behavior (duplicate
        additions don't cause errors).
        """
        num_treatments = 50
        treatment_names = [f'treatment_{i}' for i in range(num_treatments)]

        def add_duplicate_treatments(treatment_subset: list):
            """Each thread adds a subset of treatments, with duplicates"""
            for treatment in treatment_subset:
                # Add each treatment twice to test idempotent behavior
                empty_collector.add_treatment(treatment)
                empty_collector.add_treatment(treatment)

        # Split treatments across 10 threads
        num_threads = 10
        treatments_per_thread = num_treatments // num_threads

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for i in range(num_threads):
                start_idx = i * treatments_per_thread
                end_idx = start_idx + treatments_per_thread if i < num_threads - 1 else num_treatments
                subset = treatment_names[start_idx:end_idx]
                futures.append(executor.submit(add_duplicate_treatments, subset))

            # Wait for all threads to complete
            for future in futures:
                future.result()

        # Verify all treatments were added exactly once
        assert len(empty_collector.predictions) == num_treatments
        assert len(empty_collector._treatments) == num_treatments

        # Verify all expected treatments exist
        for treatment in treatment_names:
            assert treatment in empty_collector.predictions
            assert treatment in empty_collector._treatments
            assert empty_collector.predictions[treatment] == []  # Empty predictions list
