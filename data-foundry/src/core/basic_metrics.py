"""
Basic Metrics Collector for A/B Testing
========================================

Simple metrics collection for comparing treatments in A/B testing scenarios.
Adapted from pipeline-v4 with generic treatment support and thread safety.

Features:
- Dynamic treatment registration (add_treatment method)
- Per-treatment precision/recall/F1/accuracy
- Confusion matrices
- Treatment distribution
- JSON export
- Thread-safe prediction recording

Author: Data Foundry (adapted from RedditHarbor ML Pipeline)
Version: 1.0.0
"""

import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

logger = logging.getLogger(__name__)


@dataclass
class TreatmentMetrics:
    """Metrics for a single treatment"""

    treatment: str
    total_samples: int
    predicted_positive: int
    predicted_negative: int
    true_positive: int = 0
    true_negative: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        """Calculate precision (TP / (TP + FP))"""
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator > 0 else 0.0

    @property
    def recall(self) -> float:
        """Calculate recall (TP / (TP + FN))"""
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator > 0 else 0.0

    @property
    def f1_score(self) -> float:
        """Calculate F1 score"""
        p = self.precision
        r = self.recall
        return 2 * (p * r) / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        """Calculate accuracy"""
        total = self.true_positive + self.true_negative + self.false_positive + self.false_negative
        return (self.true_positive + self.true_negative) / total if total > 0 else 0.0

    @property
    def positive_rate(self) -> float:
        """Percentage of samples predicted as positive"""
        return self.predicted_positive / self.total_samples if self.total_samples > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'treatment': self.treatment,
            'total_samples': self.total_samples,
            'predicted_positive': self.predicted_positive,
            'predicted_negative': self.predicted_negative,
            'positive_rate': self.positive_rate,
            'confusion_matrix': {
                'true_positive': self.true_positive,
                'true_negative': self.true_negative,
                'false_positive': self.false_positive,
                'false_negative': self.false_negative
            },
            'performance': {
                'precision': self.precision,
                'recall': self.recall,
                'f1_score': self.f1_score,
                'accuracy': self.accuracy
            }
        }


class BasicMetricsCollector:
    """
    Collect and compare metrics for A/B testing.

    Tracks predictions from multiple treatments and computes
    performance metrics when ground truth labels are available.
    Supports dynamic treatment registration and thread-safe operations.
    """

    def __init__(self):
        """Initialize metrics collector with empty state"""
        self.predictions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.ground_truth: Dict[str, bool] = {}
        self._treatments: Set[str] = set()
        self._lock = threading.RLock()  # RLock for re-entrant read-write consistency
        logger.info("BasicMetricsCollector initialized")

    def add_treatment(self, treatment: str) -> None:
        """
        Register a new treatment for tracking (thread-safe).

        Args:
            treatment: Treatment identifier (e.g., 'treatment_a', 'baseline')
        """
        with self._lock:
            if treatment in self.predictions:
                # Silently ignore duplicate treatments (idempotent operation)
                return
            self.predictions[treatment] = []
            self._treatments.add(treatment)

    def record_prediction(
        self,
        sample_id: str,
        treatment: str,
        prediction: bool,
        score: Optional[float] = None,
        ground_truth: Optional[bool] = None
    ) -> None:
        """
        Record a prediction from A/B test (thread-safe).

        Args:
            sample_id: Sample identifier (must be non-empty string)
            treatment: Treatment identifier (must be registered via add_treatment)
            prediction: Whether predicted as positive
            score: Prediction score/confidence (optional)
            ground_truth: True label if known (optional)

        Raises:
            ValueError: If treatment has not been registered or sample_id is invalid
        """
        # Validate sample_id
        if not sample_id or not isinstance(sample_id, str):
            raise ValueError(f"Invalid sample_id: {sample_id}. Must be a non-empty string.")

        if treatment not in self.predictions:
            raise ValueError(f"Invalid treatment: {treatment}. Must be registered via add_treatment() first.")

        with self._lock:
            self.predictions[treatment].append({
                'sample_id': sample_id,
                'prediction': prediction,
                'score': score
            })

            if ground_truth is not None:
                self.ground_truth[sample_id] = ground_truth

    def get_treatment_metrics(self, treatment: str) -> TreatmentMetrics:
        """
        Calculate metrics for a specific treatment (thread-safe).

        Args:
            treatment: Treatment identifier

        Returns:
            TreatmentMetrics object with calculated metrics
        """
        with self._lock:
            preds = self.predictions.get(treatment, [])

        if not preds:
            return TreatmentMetrics(
                treatment=treatment,
                total_samples=0,
                predicted_positive=0,
                predicted_negative=0
            )

        total = len(preds)
        predicted_positive = sum(1 for p in preds if p['prediction'])
        predicted_negative = total - predicted_positive

        metrics = TreatmentMetrics(
            treatment=treatment,
            total_samples=total,
            predicted_positive=predicted_positive,
            predicted_negative=predicted_negative
        )

        # Calculate confusion matrix if ground truth available
        if self.ground_truth:
            for pred in preds:
                sample_id = pred['sample_id']
                if sample_id not in self.ground_truth:
                    continue

                is_positive_pred = pred['prediction']
                is_positive_true = self.ground_truth[sample_id]

                if is_positive_pred and is_positive_true:
                    metrics.true_positive += 1
                elif is_positive_pred and not is_positive_true:
                    metrics.false_positive += 1
                elif not is_positive_pred and is_positive_true:
                    metrics.false_negative += 1
                else:
                    metrics.true_negative += 1

        return metrics

    def get_all_metrics(self) -> Dict:
        """
        Get metrics for all registered treatments (thread-safe).

        Returns:
            Dictionary with metrics for all treatments and comparison data
        """
        with self._lock:
            result = {}
            # Get snapshot of treatments to ensure consistency
            treatment_list = list(self.predictions.keys())

        # Get metrics for all treatments (each call is thread-safe)
        for treatment in treatment_list:
            result[treatment] = self.get_treatment_metrics(treatment).to_dict()

        # Add comparison if we have at least 2 treatments
        if len(treatment_list) >= 2:
            result['comparison'] = self._compare_treatments(treatment_list)

        return result

    def _compare_treatments(self, treatment_list: List[str]) -> Dict:
        """
        Compare metrics across multiple treatments.

        Args:
            treatment_list: List of treatment names

        Returns:
            Dictionary with comparison statistics
        """
        comparison = {}

        # Cache metrics for each treatment to avoid redundant calculations
        metrics_cache = {}
        for treatment in treatment_list:
            metrics_cache[treatment] = self.get_treatment_metrics(treatment)

        # Add sample counts for each treatment
        for treatment in treatment_list:
            metrics = metrics_cache[treatment]
            comparison[f'{treatment}_samples'] = metrics.total_samples
            comparison[f'{treatment}_positive_rate'] = metrics.positive_rate

        # Add positive rate differences (if we have 2+ treatments)
        if len(treatment_list) >= 2:
            t1_metrics = metrics_cache[treatment_list[0]]
            t2_metrics = metrics_cache[treatment_list[1]]
            comparison['positive_rate_diff'] = t1_metrics.positive_rate - t2_metrics.positive_rate

        # Performance comparison (if ground truth available)
        if self.ground_truth:
            for treatment in treatment_list:
                metrics = metrics_cache[treatment]
                comparison[f'{treatment}_precision'] = metrics.precision
                comparison[f'{treatment}_recall'] = metrics.recall
                comparison[f'{treatment}_f1'] = metrics.f1_score

            # Add differences if we have 2+ treatments
            if len(treatment_list) >= 2:
                t1_metrics = metrics_cache[treatment_list[0]]
                t2_metrics = metrics_cache[treatment_list[1]]
                comparison['precision_diff'] = t1_metrics.precision - t2_metrics.precision
                comparison['recall_diff'] = t1_metrics.recall - t2_metrics.recall
                comparison['f1_diff'] = t1_metrics.f1_score - t2_metrics.f1_score

        return comparison

    def get_distribution_stats(self) -> Dict:
        """
        Get treatment distribution statistics (thread-safe).

        Returns:
            Dictionary with distribution info including counts and ratios
        """
        with self._lock:
            treatment_counts = {t: len(preds) for t, preds in self.predictions.items()}
            total = sum(treatment_counts.values())

            result = {
                'total_samples': total
            }

            # Add counts and ratios for each treatment
            for treatment, count in treatment_counts.items():
                result[f'{treatment}_samples'] = count
                result[f'{treatment}_ratio'] = count / total if total > 0 else 0.0

        return result

    def export_json(self, output_path: Path) -> None:
        """
        Export all metrics to JSON file.

        Args:
            output_path: Path to save JSON file

        Raises:
            IOError: If file write operation fails
            OSError: If directory doesn't exist or path is invalid
        """
        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            metrics = {
                'distribution': self.get_distribution_stats(),
                'metrics': self.get_all_metrics(),
                'has_ground_truth': len(self.ground_truth) > 0,
                'total_ground_truth': len(self.ground_truth)
            }

            with open(output_path, 'w') as f:
                json.dump(metrics, f, indent=2)

            logger.info(f"Metrics exported to {output_path}")

        except (IOError, OSError) as e:
            logger.error(f"Failed to export metrics to {output_path}: {e}")
            raise
