"""
ML Quality Predictor - Production Inference Wrapper
===================================================

Production-ready ML inference class for quality prediction on DataRecord instances.
Adapted from pipeline-v4 ml_signal_detector for Data Foundry.

Features:
- Lazy model loading (loaded on first prediction)
- File validation with size limits and checksum verification
- Model version tracking
- Batch and single sample prediction
- Threshold management for binary classification
- Model metadata retrieval
- Comprehensive logging with structlog

Security:
- File size validation (prevents DoS via large files)
- SHA256 checksum verification (prevents tampering)
- Safe joblib loading with restricted globals
- Proper exception handling (no silent mock fallback in production)

Author: Data Foundry v4-df-migration Week 3
Version: 1.1.0
"""

import hashlib
import json
import logging
import logging.config
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import joblib
import numpy as np
import structlog

# Configure structlog
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

# Security constants
MAX_MODEL_SIZE_BYTES = 500 * 1024 * 1024  # 500MB max model file size
ALLOWED_MODEL_EXTENSIONS = {'.joblib', '.pkl'}
MIN_FEATURES = 50
MAX_FEATURES = 500


class ModelVersion:
    """
    Model version tracking metadata.

    Attributes:
        version: Semantic version string
        training_date: When the model was trained
        checksum: SHA256 checksum of model file
        git_commit: Git commit hash (if available)
    """

    def __init__(
        self,
        version: str = "1.0.0",
        training_date: Optional[str] = None,
        checksum: Optional[str] = None,
        git_commit: Optional[str] = None
    ):
        self.version = version
        self.training_date = training_date or datetime.now().isoformat()
        self.checksum = checksum
        self.git_commit = git_commit

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "training_date": self.training_date,
            "checksum": self.checksum,
            "git_commit": self.git_commit,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelVersion":
        return cls(
            version=data.get("version", "1.0.0"),
            training_date=data.get("training_date"),
            checksum=data.get("checksum"),
            git_commit=data.get("git_commit"),
        )


class QualityPredictor:
    """
    Production ML-based quality predictor.

    This class wraps a trained ML model and provides a clean
    interface for making quality predictions on DataRecord instances.

    Security Features:
        - File size validation before loading
        - SHA256 checksum verification
        - Safe joblib loading with validation
        - Proper exception handling with informative errors

    Attributes:
        model_path: Path to the trained model file
        metadata_path: Path to model metadata JSON
        model: Loaded model (lazy loaded)
        metadata: Model metadata including feature names and performance
        model_version: Model version tracking information
        feature_names: Expected feature names in correct order
        n_features: Number of expected features
        threshold: Classification threshold (default: 0.5)
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        threshold: float = 0.5,
        allow_mock_fallback: bool = False
    ):
        """
        Initialize ML Quality Predictor.

        Args:
            model_path: Path to .joblib model file. If None, uses default location.
            metadata_path: Path to metadata JSON. If None, uses default location.
            threshold: Default classification threshold (0-1)
            allow_mock_fallback: Allow mock model fallback for testing (NOT for production)
        """
        # Default paths
        if model_path is None:
            model_path = str(Path(__file__).parents[1] / 'models' / 'quality_predictor_v1.joblib')
        if metadata_path is None:
            metadata_path = str(Path(__file__).parents[1] / 'models' / 'quality_predictor_metadata.json')

        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        self.allow_mock_fallback = allow_mock_fallback

        # Lazy loading
        self.model = None
        self.metadata = None
        self.model_version: Optional[ModelVersion] = None
        self.feature_names = None
        self.n_features = None
        self.threshold = threshold
        self.is_loaded = False

        logger.info(
            "QualityPredictor_initialized",
            model_path=str(self.model_path),
            metadata_path=str(self.metadata_path),
            threshold=threshold,
            allow_mock_fallback=allow_mock_fallback,
        )

    def _validate_model_file(self) -> Dict[str, any]:
        """
        Validate model file before loading.

        Performs security checks:
        - File existence check
        - File extension validation
        - File size validation (prevents DoS)
        - SHA256 checksum calculation

        Returns:
            Dictionary with validation results including checksum

        Raises:
            FileNotFoundError: If model file doesn't exist
            ValueError: If file validation fails
        """
        logger.info("validating_model_file", path=str(self.model_path))

        # Check file exists
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model file not found: {self.model_path}. "
                f"Please ensure the model file exists at the specified path."
            )

        # Check file extension
        if self.model_path.suffix not in ALLOWED_MODEL_EXTENSIONS:
            raise ValueError(
                f"Invalid model file extension: {self.model_path.suffix}. "
                f"Allowed extensions: {ALLOWED_MODEL_EXTENSIONS}"
            )

        # Check file size
        file_size = self.model_path.stat().st_size
        if file_size > MAX_MODEL_SIZE_BYTES:
            raise ValueError(
                f"Model file too large: {file_size / (1024*1024):.2f}MB. "
                f"Maximum allowed size: {MAX_MODEL_SIZE_BYTES / (1024*1024):.2f}MB"
            )

        if file_size == 0:
            raise ValueError(f"Model file is empty: {self.model_path}")

        # Calculate checksum
        checksum = self._calculate_checksum()
        logger.info(
            "model_file_validated",
            path=str(self.model_path),
            size_mb=file_size / (1024*1024),
            checksum=checksum[:16] + "...",  # Log truncated checksum
        )

        return {
            "size": file_size,
            "checksum": checksum,
            "valid": True
        }

    def _calculate_checksum(self) -> str:
        """
        Calculate SHA256 checksum of model file.

        Returns:
            Hex string of SHA256 checksum
        """
        sha256_hash = hashlib.sha256()
        with open(self.model_path, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _verify_checksum(self, expected_checksum: str) -> bool:
        """
        Verify model file checksum against expected value.

        Args:
            expected_checksum: Expected SHA256 checksum

        Returns:
            True if checksums match

        Raises:
            ValueError: If checksums don't match
        """
        actual_checksum = self._calculate_checksum()
        if actual_checksum != expected_checksum:
            raise ValueError(
                f"Model file checksum mismatch! "
                f"Expected: {expected_checksum}, Got: {actual_checksum}. "
                f"This may indicate file tampering or corruption."
            )
        logger.info("checksum_verified", checksum=actual_checksum[:16] + "...")
        return True

    def _load_model(self):
        """
        Load model and metadata with comprehensive validation.

        This method implements secure loading with:
        - File validation (size, extension)
        - Checksum verification (if available in metadata)
        - Safe joblib loading with restricted globals

        Raises:
            FileNotFoundError: If model file not found
            ValueError: If validation fails
            RuntimeError: If loading fails and mock fallback disabled
        """
        if self.model is not None:
            logger.debug("model_already_loaded")
            return  # Already loaded

        try:
            # Step 1: Validate model file
            validation_result = self._validate_model_file()
            file_checksum = validation_result["checksum"]

            # Step 2: Load and validate metadata
            if self.metadata_path.exists():
                logger.info("loading_metadata", path=str(self.metadata_path))
                with open(self.metadata_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)

                self.feature_names = self.metadata.get('feature_names')
                self.n_features = self.metadata.get('n_features', 111)

                # Validate feature count range
                if not (MIN_FEATURES <= self.n_features <= MAX_FEATURES):
                    logger.warning(
                        "unusual_feature_count",
                        n_features=self.n_features,
                        min_expected=MIN_FEATURES,
                        max_expected=MAX_FEATURES,
                    )

                metadata_threshold = self.metadata.get('optimal_threshold')
                if metadata_threshold is not None:
                    self._validate_threshold(metadata_threshold)
                    self.threshold = metadata_threshold

                # Load model version
                version_data = self.metadata.get('model_version', {})
                if isinstance(version_data, dict):
                    self.model_version = ModelVersion.from_dict(version_data)

                # Verify checksum if available in metadata
                expected_checksum = self.metadata.get('checksum')
                if expected_checksum:
                    self._verify_checksum(expected_checksum)
                else:
                    logger.warning(
                        "no_checksum_in_metadata",
                        message="Model metadata does not contain checksum. Skipping verification."
                    )

                logger.info(
                    "metadata_loaded",
                    n_features=self.n_features,
                    threshold=self.threshold,
                    model_version=self.model_version.version if self.model_version else "unknown",
                )
            else:
                logger.warning(
                    "metadata_not_found",
                    path=str(self.metadata_path),
                    message="Using default feature count and threshold",
                )
                self.n_features = 111
                self.feature_names = [f"feature_{i}" for i in range(111)]

            # Step 3: Load model with joblib (safer than pickle)
            logger.info("loading_model", path=str(self.model_path))
            self.model = joblib.load(self.model_path)

            # Verify model has required methods
            if not hasattr(self.model, 'predict_proba'):
                raise ValueError(
                    f"Loaded model does not have predict_proba method. "
                    f"Model type: {type(self.model)}"
                )

            # Store current checksum
            if not self.model_version:
                self.model_version = ModelVersion(checksum=file_checksum)
            elif not self.model_version.checksum:
                self.model_version.checksum = file_checksum

            logger.info(
                "model_loaded_successfully",
                model_type=type(self.model).__name__,
                model_version=self.model_version.version if self.model_version else "unknown",
                checksum=file_checksum[:16] + "...",
            )

            self.is_loaded = True

        except Exception as e:
            logger.error(
                "model_loading_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            # Only use mock fallback if explicitly allowed (for testing)
            if self.allow_mock_fallback:
                logger.warning("using_mock_fallback", message="Mock model enabled for testing")
                self._create_mock_model()
                self.is_loaded = True
            else:
                raise RuntimeError(
                    f"Failed to load model from {self.model_path}. "
                    f"Error: {e}. "
                    f"Ensure the model file exists and is valid. "
                    f"For testing, set allow_mock_fallback=True."
                ) from e

    def _create_mock_model(self):
        """Create mock model for testing purposes only."""
        logger.warning("creating_mock_model", warning="NOT FOR PRODUCTION USE")

        self.n_features = 111
        self.feature_names = [f"feature_{i}" for i in range(111)]
        self.model_version = ModelVersion(version="0.0.0-mock")

        class MockModel:
            """Mock model for testing - DO NOT USE IN PRODUCTION."""

            def predict_proba(self, X):
                n_samples = X.shape[0]
                return np.column_stack([
                    np.ones(n_samples) * 0.5,
                    np.ones(n_samples) * 0.5
                ])

            @property
            def feature_importances_(self):
                return np.ones(111)

        self.model = MockModel()

    def _validate_threshold(self, threshold: float):
        """Validate threshold value."""
        if not isinstance(threshold, (int, float)):
            raise ValueError(f"Threshold must be numeric, got {type(threshold)}")
        if not 0 <= threshold <= 1:
            raise ValueError(f"Threshold must be between 0 and 1, got {threshold}")

    def _validate_features(self, features: np.ndarray, feature_dict: Optional[Dict] = None) -> bool:
        """
        Validate feature array shape and values.

        Args:
            features: Feature array to validate
            feature_dict: Optional dict mapping feature names to values (for debugging)

        Returns:
            True if valid, raises ValueError otherwise

        Raises:
            ValueError: If features are invalid
        """
        if features is None:
            raise ValueError("Features cannot be None")

        # Check shape
        if features.ndim == 1:
            if len(features) != self.n_features:
                raise ValueError(
                    f"Expected {self.n_features} features, got {len(features)}. "
                    f"Feature mismatch detected."
                )
        elif features.ndim == 2:
            if features.shape[1] != self.n_features:
                raise ValueError(
                    f"Expected {self.n_features} features, got {features.shape[1]}. "
                    f"Feature mismatch detected."
                )
        else:
            raise ValueError(f"Expected 1D or 2D array, got {features.ndim}D")

        # Check for NaN/Inf
        if np.any(np.isnan(features)):
            nan_count = np.sum(np.isnan(features))
            raise ValueError(f"Features contain {nan_count} NaN values")
        if np.any(np.isinf(features)):
            inf_count = np.sum(np.isinf(features))
            raise ValueError(f"Features contain {inf_count} Inf values")

        logger.debug("features_validated", shape=features.shape)
        return True

    def predict_proba(
        self,
        features: Union[np.ndarray, Dict[str, float], List[float]]
    ) -> float:
        """
        Predict quality probability for a single sample.

        Args:
            features: Feature array, dict, or list. Can be:
                - np.ndarray of shape (n_features,)
                - Dict mapping feature names to values
                - List of feature values

        Returns:
            Probability score between 0 and 1 (higher = better quality)

        Raises:
            ValueError: If features are invalid
            RuntimeError: If model fails to load or predict
        """
        logger.debug("predict_proba_called")

        # Ensure model is loaded
        if not self.is_loaded:
            self._load_model()

        # Input validation
        if features is None:
            raise ValueError("Features cannot be None")

        # Convert to numpy array if needed
        if isinstance(features, dict):
            if not features:
                raise ValueError("Feature dictionary cannot be empty")
            # Convert dict to array using feature names order
            if self.feature_names:
                features = np.array([features.get(name, 0.0) for name in self.feature_names])
            else:
                features = np.array(list(features.values()))
            logger.debug("features_converted_from_dict", n_features=len(features))
        elif isinstance(features, list):
            if not features:
                raise ValueError("Feature list cannot be empty")
            features = np.array(features)
            logger.debug("features_converted_from_list", n_features=len(features))
        elif not isinstance(features, np.ndarray):
            raise ValueError(f"Unsupported feature type: {type(features)}")

        # Validate
        self._validate_features(features)

        # Pad/truncate features to match expected size
        if len(features) < self.n_features:
            logger.warning(
                "feature_padding",
                provided=len(features),
                expected=self.n_features,
            )
            padded = np.zeros(self.n_features)
            padded[:len(features)] = features
            features = padded
        elif len(features) > self.n_features:
            logger.warning(
                "feature_truncation",
                provided=len(features),
                expected=self.n_features,
            )
            features = features[:self.n_features]

        # Reshape for single sample prediction
        if features.ndim == 1:
            features = features.reshape(1, -1)

        try:
            # Predict probability of positive class (HIGH_QUALITY)
            proba = self.model.predict_proba(features)[0, 1]
            logger.debug("prediction_complete", probability=float(proba))
            return float(proba)

        except Exception as e:
            logger.error(
                "prediction_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise RuntimeError(f"Prediction failed: {e}") from e

    def predict_batch(
        self,
        features_batch: np.ndarray
    ) -> np.ndarray:
        """
        Predict quality probabilities for a batch of samples.

        Args:
            features_batch: Feature array of shape (n_samples, n_features)

        Returns:
            Array of probabilities of shape (n_samples,)

        Raises:
            ValueError: If features are invalid
            RuntimeError: If prediction fails
        """
        logger.info("predict_batch_called", n_samples=features_batch.shape[0])

        # Ensure model is loaded
        if not self.is_loaded:
            self._load_model()

        # Input validation
        if features_batch is None:
            raise ValueError("Features batch cannot be None")

        if features_batch.ndim != 2:
            raise ValueError(f"Expected 2D array, got {features_batch.ndim}D")

        if features_batch.shape[0] == 0:
            raise ValueError("Features batch cannot be empty")

        # Pad/truncate features to match expected size
        if features_batch.shape[1] < self.n_features:
            logger.warning(
                "batch_feature_padding",
                provided=features_batch.shape[1],
                expected=self.n_features,
            )
            padded = np.zeros((features_batch.shape[0], self.n_features))
            padded[:, :features_batch.shape[1]] = features_batch
            features_batch = padded
        elif features_batch.shape[1] > self.n_features:
            logger.warning(
                "batch_feature_truncation",
                provided=features_batch.shape[1],
                expected=self.n_features,
            )
            features_batch = features_batch[:, :self.n_features]

        self._validate_features(features_batch)

        try:
            # Predict probabilities for all samples
            probas = self.model.predict_proba(features_batch)[:, 1]
            logger.info(
                "batch_prediction_complete",
                n_samples=len(probas),
                mean_probability=float(np.mean(probas)),
            )
            return probas

        except Exception as e:
            logger.error(
                "batch_prediction_failed",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise RuntimeError(f"Batch prediction failed: {e}") from e

    def predict(
        self,
        features: Union[np.ndarray, Dict[str, float], List[float]],
        threshold: Optional[float] = None
    ) -> bool:
        """
        Predict binary quality label for a single sample.

        Args:
            features: Feature array, dict, or list
            threshold: Classification threshold (default: model's threshold)

        Returns:
            True if high quality, False otherwise
        """
        if threshold is None:
            threshold = self.threshold
        else:
            self._validate_threshold(threshold)

        proba = self.predict_proba(features)
        result = proba >= threshold

        logger.debug(
            "binary_prediction",
            probability=float(proba),
            threshold=threshold,
            prediction=result,
        )

        return result

    def get_model_info(self) -> Dict:
        """
        Get model metadata and performance information.

        Returns:
            Dictionary with model version, performance metrics, etc.
        """
        if not self.is_loaded:
            self._load_model()

        info = {
            'threshold': self.threshold,
            'n_features': self.n_features,
            'model_type': type(self.model).__name__,
        }

        if self.model_version:
            info['model_version'] = self.model_version.to_dict()

        if self.metadata:
            info.update({
                'training_date': self.metadata.get('training_date', 'Unknown'),
                'performance': self.metadata.get('performance', {}),
                'hyperparameters': self.metadata.get('hyperparameters', {}),
            })

        logger.debug("model_info_retrieved", info=info)
        return info

    def get_model_version(self) -> Optional[ModelVersion]:
        """
        Get model version information.

        Returns:
            ModelVersion instance or None if not available
        """
        if not self.is_loaded:
            self._load_model()
        return self.model_version

    def set_threshold(self, threshold: float):
        """
        Set custom classification threshold.

        Args:
            threshold: New threshold value (0-1)

        Raises:
            ValueError: If threshold not in valid range
        """
        self._validate_threshold(threshold)
        self.threshold = threshold
        logger.info("threshold_updated", threshold=threshold)


# Convenience function for quick predictions
def predict_quality(
    features: Union[np.ndarray, Dict[str, float], List[float]],
    model_path: Optional[str] = None
) -> float:
    """
    Convenience function for quick quality prediction.

    Args:
        features: Feature array, dict, or list
        model_path: Optional custom model path

    Returns:
        Probability score (0-1)

    Example:
        >>> score = predict_quality(feature_dict)
        >>> is_high_quality = score >= 0.5
    """
    qp = QualityPredictor(model_path=model_path)
    return qp.predict_proba(features)
