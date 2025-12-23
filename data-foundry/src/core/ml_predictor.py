"""
MLPredictor class for predicting data quality scores and extracting features

This module provides machine learning prediction capabilities for data records,
including quality scoring, feature extraction, and model management.

Features:
- Model loading and reloading capabilities
- Feature extraction from data records
- Quality score prediction
- Thread-safe model management
- Comprehensive logging with structlog

Pattern reference: src/core/signal_detector.py
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import structlog
from pydantic import BaseModel, Field

# Configure structlog (same as signal_detector)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# RESULT MODELS
# ============================================================================

class PredictionResult(BaseModel):
    """Result of ML prediction analysis."""

    quality_score: float = Field(description="Predicted quality score (0.0-1.0)")
    confidence: float = Field(description="Prediction confidence (0.0-1.0)")
    feature_importance: Dict[str, float] = Field(
        default_factory=dict,
        description="Feature importance scores"
    )
    prediction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional prediction metadata"
    )


class FeatureExtractionResult(BaseModel):
    """Result of feature extraction from a data record."""

    features: Dict[str, Any] = Field(description="Extracted feature values")
    feature_count: int = Field(description="Number of features extracted")
    extraction_time_ms: float = Field(description="Time taken for extraction in milliseconds")


class ModelMetadata(BaseModel):
    """Metadata about the current ML model."""

    model_version: str = Field(description="Model version identifier")
    model_type: str = Field(description="Model type/algorithm")
    last_trained: Optional[datetime] = Field(description="Last training date")
    feature_count: int = Field(description="Number of features used by model")
    performance_metrics: Dict[str, float] = Field(
        default_factory=dict,
        description="Model performance metrics"
    )
    is_loaded: bool = Field(description="Whether model is currently loaded")


# ============================================================================
# FEATURE EXTRACTOR
# ============================================================================

class FeatureExtractor:
    """
    Extracts features from data records for ML prediction.

    Pattern reference: Similar to SignalDetector's text extraction methods
    """

    def __init__(self):
        """Initialize feature extractor."""
        logger.info("FeatureExtractor_initialized")

    def extract_features(self, record: Any) -> FeatureExtractionResult:
        """
        Extract features from a data record.

        Args:
            record: Data record (dict or DataRecord-like object)

        Returns:
            FeatureExtractionResult with extracted features
        """
        import time
        start_time = time.time()

        # Handle different record types
        if isinstance(record, dict):
            record_dict = record
        elif hasattr(record, '__dict__'):
            record_dict = {
                'id': getattr(record, 'id', None),
                'data_preview': getattr(record, 'data_preview', None),
                'raw_data': getattr(record, 'raw_data', None),
                'extracted_text': getattr(record, 'extracted_text', None),
                'data_quality_score': getattr(record, 'data_quality_score', None),
                'access_count': getattr(record, 'access_count', None),
                'tenant_id': getattr(record, 'tenant_id', None),
                'data_source': getattr(record, 'data_source', None),
            }
        else:
            record_dict = {}

        # Extract text content
        text_content = self._extract_text_content(record_dict)

        # Calculate features
        features = {
            # Text-based features
            'text_length': len(text_content),
            'word_count': len(text_content.split()) if text_content else 0,
            'has_preview': 1 if record_dict.get('data_preview') else 0,
            'has_raw_data': 1 if record_dict.get('raw_data') else 0,
            'has_extracted_text': 1 if record_dict.get('extracted_text') else 0,

            # Quality-based features
            'quality_score': float(record_dict.get('data_quality_score', 0.0) or 0.0),
            'access_count': int(record_dict.get('access_count', 0) or 0),

            # Source-based features
            'source_type': hash(str(record_dict.get('data_source', 'unknown'))) % 1000,

            # Text complexity features
            'avg_word_length': self._calculate_avg_word_length(text_content),
            'unique_word_ratio': self._calculate_unique_word_ratio(text_content),
            'has_number': 1 if any(c.isdigit() for c in text_content) else 0,
        }

        extraction_time = (time.time() - start_time) * 1000  # Convert to ms

        logger.debug(
            "features_extracted",
            feature_count=len(features),
            extraction_time_ms=extraction_time,
        )

        return FeatureExtractionResult(
            features=features,
            feature_count=len(features),
            extraction_time_ms=extraction_time
        )

    def _extract_text_content(self, record_dict: Dict[str, Any]) -> str:
        """Extract text content from record dictionary."""
        parts = []

        if record_dict.get('data_preview'):
            parts.append(str(record_dict['data_preview']))

        if record_dict.get('extracted_text'):
            parts.append(str(record_dict['extracted_text']))
        elif record_dict.get('raw_data'):
            # Try to parse raw_data as JSON
            try:
                raw_dict = json.loads(record_dict['raw_data'])
                for key in ['text', 'content', 'description', 'message', 'body']:
                    if key in raw_dict and raw_dict[key]:
                        parts.append(str(raw_dict[key]))
                        break
            except (json.JSONDecodeError, TypeError):
                parts.append(str(record_dict['raw_data']))

        return ' '.join(parts)

    def _calculate_avg_word_length(self, text: str) -> float:
        """Calculate average word length."""
        words = text.split()
        if not words:
            return 0.0
        return sum(len(word) for word in words) / len(words)

    def _calculate_unique_word_ratio(self, text: str) -> float:
        """Calculate ratio of unique words to total words."""
        words = text.lower().split()
        if not words:
            return 0.0
        unique_words = set(words)
        return len(unique_words) / len(words)


# ============================================================================
# ML PREDICTOR
# ============================================================================

class MLPredictor:
    """
    ML-based predictor for data quality scoring.

    Provides prediction capabilities with model loading/reloading,
    feature extraction, and quality scoring.

    Pattern reference: src/core/signal_detector.py
    """

    # Default model path
    DEFAULT_MODEL_PATH = "models/quality_predictor.pkl"
    DEFAULT_MODEL_VERSION = "1.0.0"
    DEFAULT_MODEL_TYPE = "RandomForestClassifier"

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_version: Optional[str] = None,
    ):
        """
        Initialize ML predictor.

        Args:
            model_path: Path to model file (optional, uses default if not provided)
            model_version: Model version string (optional, uses default if not provided)
        """
        self.model_path = model_path or self.DEFAULT_MODEL_PATH
        self.model_version = model_version or self.DEFAULT_MODEL_VERSION
        self.model_type = self.DEFAULT_MODEL_TYPE
        self.feature_extractor = FeatureExtractor()

        # Model loading state (thread-safe)
        # Use RLock (reentrant) to allow reload_model() to call _load_model() while holding the lock
        self._model_lock = threading.RLock()
        self._model = None
        self._is_loaded = False

        # Try to load model
        self._load_model()

        logger.info(
            "MLPredictor_initialized",
            model_path=self.model_path,
            model_version=self.model_version,
            model_loaded=self._is_loaded,
        )

    def _load_model(self) -> None:
        """
        Load ML model from disk.

        Thread-safe model loading with state management.
        """
        with self._model_lock:
            try:
                model_file = Path(self.model_path)
                if model_file.exists():
                    # In production, this would load the actual model
                    # For now, we simulate a loaded model
                    self._model = {"loaded": True, "path": str(model_file)}
                    self._is_loaded = True
                    logger.info(
                        "model_loaded_successfully",
                        path=self.model_path,
                    )
                else:
                    # Use a simple heuristic-based model
                    self._model = {"loaded": True, "heuristic": True}
                    self._is_loaded = True
                    logger.info(
                        "model_file_not_found_using_heuristic",
                        path=self.model_path,
                    )
            except Exception as e:
                logger.error(
                    "model_loading_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self._model = None
                self._is_loaded = False

    def reload_model(self) -> ModelMetadata:
        """
        Reload the ML model from disk.

        Thread-safe model reloading.

        Returns:
            ModelMetadata with updated model information

        Raises:
            RuntimeError: If model reload fails
        """
        with self._model_lock:
            logger.info("model_reload_started")

            try:
                # Unload current model
                self._model = None
                self._is_loaded = False

                # Reload model
                self._load_model()

                if not self._is_loaded:
                    raise RuntimeError("Failed to reload model")

                logger.info("model_reload_completed")

                return self.get_model_metadata()
            except Exception as e:
                logger.error(
                    "model_reload_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise RuntimeError(f"Model reload failed: {str(e)}")

    def get_model_metadata(self) -> ModelMetadata:
        """
        Get metadata about the current model.

        Returns:
            ModelMetadata with model information
        """
        with self._model_lock:
            # In production, this would extract actual metadata from the model
            return ModelMetadata(
                model_version=self.model_version,
                model_type=self.model_type,
                last_trained=datetime.now(),  # Placeholder
                feature_count=11,  # Based on FeatureExtractor output
                performance_metrics={
                    "accuracy": 0.85,  # Placeholder
                    "precision": 0.82,  # Placeholder
                    "recall": 0.88,  # Placeholder
                },
                is_loaded=self._is_loaded
            )

    def predict(self, record: Any) -> PredictionResult:
        """
        Predict quality score for a data record.

        Args:
            record: Data record (dict or DataRecord-like object)

        Returns:
            PredictionResult with quality score and metadata

        Raises:
            ValueError: If record is invalid
        """
        if record is None:
            raise ValueError("Record cannot be None")

        logger.debug(
            "predict_called",
            record_id=str(getattr(record, 'id', 'unknown')) if hasattr(record, 'id') else 'unknown',
        )

        # Extract features
        feature_result = self.feature_extractor.extract_features(record)
        features = feature_result.features

        # Make prediction
        # In production, this would use the actual loaded model
        # For now, use a heuristic approach
        quality_score = self._heuristic_prediction(features)

        # Calculate confidence based on feature completeness
        confidence = self._calculate_confidence(features)

        # Feature importance (placeholder)
        feature_importance = {
            'quality_score': 0.4,
            'access_count': 0.2,
            'text_length': 0.15,
            'word_count': 0.1,
            'source_type': 0.05,
            'other': 0.1,
        }

        logger.info(
            "prediction_completed",
            quality_score=quality_score,
            confidence=confidence,
        )

        return PredictionResult(
            quality_score=quality_score,
            confidence=confidence,
            feature_importance=feature_importance,
            prediction_metadata={
                'model_version': self.model_version,
                'feature_count': feature_result.feature_count,
            }
        )

    def predict_batch(self, records: List[Any]) -> List[PredictionResult]:
        """
        Predict quality scores for multiple records.

        Args:
            records: List of data records

        Returns:
            List of PredictionResult objects

        Raises:
            ValueError: If records list is empty or contains invalid records
        """
        if not records:
            raise ValueError("Records list cannot be empty")

        logger.info(
            "predict_batch_called",
            record_count=len(records),
        )

        results = []
        for record in records:
            result = self.predict(record)
            results.append(result)

        logger.info(
            "predict_batch_completed",
            total_predictions=len(results),
        )

        return results

    def _heuristic_prediction(self, features: Dict[str, Any]) -> float:
        """
        Generate a heuristic-based prediction.

        This is a placeholder for actual ML prediction.
        In production, this would use the loaded model.

        Args:
            features: Extracted feature dictionary

        Returns:
            Quality score (0.0-1.0)
        """
        # Start with base quality score
        score = features.get('quality_score', 0.5)

        # Boost for high access count
        access_count = features.get('access_count', 0)
        if access_count > 100:
            score = min(1.0, score + 0.1)
        elif access_count > 50:
            score = min(1.0, score + 0.05)

        # Boost for text content
        text_length = features.get('text_length', 0)
        if text_length > 100:
            score = min(1.0, score + 0.05)

        # Boost for complete records
        completeness = (
            features.get('has_preview', 0) +
            features.get('has_raw_data', 0) +
            features.get('has_extracted_text', 0)
        ) / 3.0
        score = min(1.0, score + completeness * 0.1)

        # Ensure score is in valid range
        return max(0.0, min(1.0, score))

    def _calculate_confidence(self, features: Dict[str, Any]) -> float:
        """
        Calculate prediction confidence based on feature completeness.

        Args:
            features: Extracted feature dictionary

        Returns:
            Confidence score (0.0-1.0)
        """
        # Base confidence
        confidence = 0.5

        # Boost for quality score presence
        if features.get('quality_score', 0) > 0:
            confidence += 0.2

        # Boost for text content
        if features.get('text_length', 0) > 0:
            confidence += 0.1

        # Boost for complete records
        if features.get('has_preview', 0) and features.get('has_raw_data', 0):
            confidence += 0.2

        return min(1.0, confidence)
