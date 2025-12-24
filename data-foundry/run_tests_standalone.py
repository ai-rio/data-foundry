#!/usr/bin/env python3
"""
Standalone test runner for basic_metrics that imports tests directly
"""
import sys
sys.path.insert(0, '.')

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

# Import the test classes
from tests.unit.test_basic_metrics import (
    TestTreatmentMetrics,
    TestBasicMetricsCollectorInit,
    TestBasicMetricsCollectorRecording,
    TestBasicMetricsCollectorMetrics,
    TestBasicMetricsCollectorComparison,
    TestBasicMetricsCollectorExport,
    empty_collector,
    single_treatment_collector,
    sample_collector,
    confusion_matrix_data,
    temp_output_path
)

# Import the module under test
from src.core.basic_metrics import (
    BasicMetricsCollector,
    TreatmentMetrics
)

import pytest
import tempfile

def main():
    """Run all tests"""
    print("Running BasicMetricsCollector tests...")
    print("=" * 70)

    # Create a temporary directory for temp_output_path
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fixtures
        empty = BasicMetricsCollector()
        single = BasicMetricsCollector()
        single.add_treatment('treatment_a')

        sample = BasicMetricsCollector()
        sample.add_treatment('treatment_a')
        sample.add_treatment('treatment_b')

        # treatment_a predictions: 6 positive, 4 negative
        for i in range(10):
            sample_id = f'sample_a_{i}'
            prediction = i < 6  # First 6 are positive
            ground_truth = i < 5  # First 5 are actually positive
            score = 0.8 + (i * 0.01) if prediction else 0.3
            sample.record_prediction(
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
            sample.record_prediction(
                sample_id=sample_id,
                treatment='treatment_b',
                prediction=prediction,
                score=score,
                ground_truth=ground_truth
            )

        # Ground truth for confusion matrix tests
        gt = {
            'sample1': True,
            'sample2': True,
            'sample3': False,
            'sample4': False,
            'sample5': False
        }

        # Test 1: TestTreatmentMetrics
        print("\n[TestTreatmentMetrics]")
        test_metrics = TestTreatmentMetrics()

        test_metrics.test_precision_calculation_normal_case()
        print("  ✓ test_precision_calculation_normal_case")

        test_metrics.test_precision_calculation_zero_division()
        print("  ✓ test_precision_calculation_zero_division")

        test_metrics.test_recall_calculation_normal_case()
        print("  ✓ test_recall_calculation_normal_case")

        test_metrics.test_recall_calculation_zero_division()
        print("  ✓ test_recall_calculation_zero_division")

        test_metrics.test_f1_score_calculation_normal_case()
        print("  ✓ test_f1_score_calculation_normal_case")

        test_metrics.test_f1_score_calculation_zero_division()
        print("  ✓ test_f1_score_calculation_zero_division")

        test_metrics.test_accuracy_calculation_normal_case()
        print("  ✓ test_accuracy_calculation_normal_case")

        test_metrics.test_accuracy_calculation_zero_division()
        print("  ✓ test_accuracy_calculation_zero_division")

        test_metrics.test_positive_rate_calculation_normal_case()
        print("  ✓ test_positive_rate_calculation_normal_case")

        test_metrics.test_positive_rate_calculation_zero_division()
        print("  ✓ test_positive_rate_calculation_zero_division")

        test_metrics.test_to_dict_serialization_complete()
        print("  ✓ test_to_dict_serialization_complete")

        # Test 2: TestBasicMetricsCollectorInit
        print("\n[TestBasicMetricsCollectorInit]")
        test_init = TestBasicMetricsCollectorInit()

        test_init.test_collector_initialization_empty_state(empty)
        print("  ✓ test_collector_initialization_empty_state")

        test_init.test_add_treatment_single(empty)
        print("  ✓ test_add_treatment_single")

        empty2 = BasicMetricsCollector()
        test_init.test_add_treatment_multiple(empty2)
        print("  ✓ test_add_treatment_multiple")

        single2 = BasicMetricsCollector()
        single2.add_treatment('treatment_a')
        test_init.test_add_treatment_duplicate(single2)
        print("  ✓ test_add_treatment_duplicate")

        # Test 3: TestBasicMetricsCollectorRecording
        print("\n[TestBasicMetricsCollectorRecording]")
        test_rec = TestBasicMetricsCollectorRecording()

        test_rec.test_record_valid_prediction(single)
        print("  ✓ test_record_valid_prediction")

        empty3 = BasicMetricsCollector()
        test_rec.test_record_invalid_treatment_raises_error(empty3)
        print("  ✓ test_record_invalid_treatment_raises_error")

        single3 = BasicMetricsCollector()
        single3.add_treatment('treatment_a')
        test_rec.test_record_with_ground_truth(single3)
        print("  ✓ test_record_with_ground_truth")

        single4 = BasicMetricsCollector()
        single4.add_treatment('treatment_a')
        test_rec.test_record_with_score(single4)
        print("  ✓ test_record_with_score")

        single5 = BasicMetricsCollector()
        single5.add_treatment('treatment_a')
        test_rec.test_record_multiple_predictions(single5)
        print("  ✓ test_record_multiple_predictions")

        # Test 4: TestBasicMetricsCollectorMetrics
        print("\n[TestBasicMetricsCollectorMetrics]")
        test_metr = TestBasicMetricsCollectorMetrics()

        single6 = BasicMetricsCollector()
        single6.add_treatment('treatment_a')
        test_metr.test_empty_treatment_metrics(single6)
        print("  ✓ test_empty_treatment_metrics")

        single7 = BasicMetricsCollector()
        single7.add_treatment('treatment_a')
        test_metr.test_treatment_metrics_basic_counts(single7)
        print("  ✓ test_treatment_metrics_basic_counts")

        single8 = BasicMetricsCollector()
        single8.add_treatment('treatment_a')
        predictions = [
            ('sample1', True),
            ('sample2', False),
            ('sample3', True),
            ('sample4', False),
            ('sample5', False)
        ]
        for sample_id, prediction in predictions:
            single8.record_prediction(
                sample_id=sample_id,
                treatment='treatment_a',
                prediction=prediction,
                ground_truth=gt[sample_id]
            )
        test_metr.test_treatment_metrics_confusion_matrix(single8, (gt, predictions))
        print("  ✓ test_treatment_metrics_confusion_matrix")

        single9 = BasicMetricsCollector()
        single9.add_treatment('treatment_a')
        test_metr.test_treatment_metrics_partial_ground_truth(single9)
        print("  ✓ test_treatment_metrics_partial_ground_truth")

        # Test 5: TestBasicMetricsCollectorComparison
        print("\n[TestBasicMetricsCollectorComparison]")
        test_comp = TestBasicMetricsCollectorComparison()

        test_comp.test_get_all_metrics_structure(sample)
        print("  ✓ test_get_all_metrics_structure")

        test_comp.test_comparison_metrics(sample)
        print("  ✓ test_comparison_metrics")

        test_comp.test_get_distribution_stats(sample)
        print("  ✓ test_get_distribution_stats")

        empty4 = BasicMetricsCollector()
        test_comp.test_get_distribution_stats_empty(empty4)
        print("  ✓ test_get_distribution_stats_empty")

        # Test 6: TestBasicMetricsCollectorExport
        print("\n[TestBasicMetricsCollectorExport]")
        test_exp = TestBasicMetricsCollectorExport()

        sample2 = BasicMetricsCollector()
        sample2.add_treatment('treatment_a')
        sample2.add_treatment('treatment_b')

        # treatment_a predictions: 6 positive, 4 negative
        for i in range(10):
            sample_id = f'sample_a_{i}'
            prediction = i < 6
            ground_truth = i < 5
            score = 0.8 + (i * 0.01) if prediction else 0.3
            sample2.record_prediction(
                sample_id=sample_id,
                treatment='treatment_a',
                prediction=prediction,
                score=score,
                ground_truth=ground_truth
            )

        # treatment_b predictions: 4 positive, 6 negative
        for i in range(10):
            sample_id = f'sample_b_{i}'
            prediction = i < 4
            ground_truth = i < 5
            score = 0.7 + (i * 0.01) if prediction else 0.4
            sample2.record_prediction(
                sample_id=sample_id,
                treatment='treatment_b',
                prediction=prediction,
                score=score,
                ground_truth=ground_truth
            )

        import json
        temp_path = Path(tmpdir) / "metrics.json"
        test_exp.test_export_json_writes_file(sample2, temp_path)
        print("  ✓ test_export_json_writes_file")

        temp_path2 = Path(tmpdir) / "metrics2.json"
        test_exp.test_export_json_overwrites_existing(sample2, temp_path2)
        print("  ✓ test_export_json_overwrites_existing")

        # Thread safety tests
        print("\n  Thread Safety Tests:")

        sample3 = BasicMetricsCollector()
        sample3.add_treatment('treatment_a')
        test_exp.test_concurrent_prediction_recording(sample3)
        print("  ✓ test_concurrent_prediction_recording")

        empty5 = BasicMetricsCollector()
        test_exp.test_concurrent_multi_treatment_recording(empty5)
        print("  ✓ test_concurrent_multi_treatment_recording")

        empty6 = BasicMetricsCollector()
        test_exp.test_concurrent_add_treatment(empty6)
        print("  ✓ test_concurrent_add_treatment")

    print("\n" + "=" * 70)
    print("All tests passed! ✓")
    print("=" * 70)
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
