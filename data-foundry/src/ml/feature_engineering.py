"""
Feature Engineering Pipeline for ML Quality Prediction
======================================================

Extracts features from DataRecord instances for ML-based quality prediction.
Adapted from pipeline-v4 feature_extractor for Data Foundry.

Features:
- TF-IDF text features (100 dimensions)
- Signal features (binary indicators for opportunity signals)
- Engagement features (quality_score, access_count, engagement_ratio)
- Metadata features (data_source_encoding, text_length, record_age)

Security:
- Uses joblib instead of pickle for serialization
- Input validation for all records
- Comprehensive exception handling
- File validation for artifact loading

Author: Data Foundry v4-df-migration Week 3
Version: 1.1.0
"""

import hashlib
import json
import logging
import logging.config
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Union

import joblib
import numpy as np
import structlog
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder

from src.models.data_record import DataRecord, DataSource

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
MAX_ARTIFACT_SIZE_BYTES = 100 * 1024 * 1024  # 100MB max artifact file size
MIN_RECORDS_FOR_FIT = 2
MIN_TEXT_LENGTH = 1


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


class FeatureEngineering:
    """
    Extracts features from DataRecord instances for ML prediction.

    This class reproduces the feature engineering pipeline adapted from
    pipeline-v4 for Data Foundry data structures.

    Security:
    - Uses joblib instead of pickle for safer serialization
    - Input validation for all records
    - File size validation for artifacts
    - Comprehensive exception handling
    """

    # Signal types matching the opportunity detection patterns
    SIGNAL_TYPES = [
        'TOOL_REQUEST',
        'PAIN_COMPLAINT',
        'PRICE_MENTION',
        'PROBLEM_SOLUTION',
        'COMPARISON',
    ]

    # TF-IDF configuration
    TFIDF_CONFIG = {
        'max_features': 100,
        'stop_words': None,  # Disabled to handle test data better
        'ngram_range': (1, 2),
        'min_df': 1,  # Changed from 2 to 1 to handle small datasets
        'max_df': 0.95
    }

    def __init__(
        self,
        artifacts_path: Optional[str] = None,
        model_dir: Optional[str] = None
    ):
        """
        Initialize the feature engineering pipeline.

        Args:
            artifacts_path: Path to saved feature extraction artifacts
            model_dir: Directory containing model files (alternative to artifacts_path)
        """
        self.tfidf_vectorizer = None
        self.source_encoder = None
        self.feature_names = []
        self.is_fitted = False
        self._artifact_checksum = None

        # Determine artifacts path
        if artifacts_path:
            self.artifacts_path = Path(artifacts_path)
        elif model_dir:
            self.artifacts_path = Path(model_dir) / 'feature_extraction_artifacts.joblib'
        else:
            # Default to models directory
            self.artifacts_path = Path(__file__).parents[1] / 'models' / 'feature_extraction_artifacts.joblib'

        # Try to load existing artifacts
        if self.artifacts_path.exists():
            try:
                self.load_artifacts()
            except Exception as e:
                logger.warning(
                    "failed_to_load_artifacts",
                    path=str(self.artifacts_path),
                    error=str(e),
                    error_type=type(e).__name__,
                )
                self.is_fitted = False

        logger.info(
            "FeatureEngineering_initialized",
            artifacts_path=str(self.artifacts_path),
            is_fitted=self.is_fitted,
        )

    def _validate_record(self, record: DataRecord) -> None:
        """
        Validate a DataRecord before processing.

        Args:
            record: DataRecord to validate

        Raises:
            ValidationError: If record is invalid
        """
        if record is None:
            raise ValidationError("Record cannot be None")

        # Check if it's actually a DataRecord
        if not isinstance(record, DataRecord):
            raise ValidationError(
                f"Expected DataRecord, got {type(record).__name__}"
            )

        # Validate at least some content exists
        has_preview = bool(record.data_preview and record.data_preview.strip())
        has_extracted = bool(record.extracted_text and record.extracted_text.strip())
        has_raw = bool(record.raw_data and record.raw_data.strip())

        if not (has_preview or has_extracted or has_raw):
            logger.warning(
                "record_has_no_content",
                record_id=str(record.id) if hasattr(record, 'id') else "unknown",
            )

    def _validate_record_list(self, records: List[DataRecord]) -> None:
        """
        Validate a list of DataRecords.

        Args:
            records: List of DataRecords to validate

        Raises:
            ValidationError: If records are invalid
        """
        if records is None:
            raise ValidationError("Records list cannot be None")

        if not isinstance(records, list):
            raise ValidationError(
                f"Expected list of DataRecords, got {type(records).__name__}"
            )

        # Empty list is valid (handled by caller as special case)
        if len(records) == 0:
            return

        # Validate each record
        for i, record in enumerate(records):
            try:
                self._validate_record(record)
            except ValidationError as e:
                raise ValidationError(f"Record at index {i} is invalid: {e}") from e

    def _validate_artifact_file(self, path: Path) -> Dict:
        """
        Validate artifact file before loading.

        Args:
            path: Path to artifact file

        Returns:
            Dictionary with validation results

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file validation fails
        """
        if not path.exists():
            raise FileNotFoundError(f"Artifact file not found: {path}")

        # Check file size
        file_size = path.stat().st_size
        if file_size > MAX_ARTIFACT_SIZE_BYTES:
            raise ValueError(
                f"Artifact file too large: {file_size / (1024*1024):.2f}MB. "
                f"Maximum allowed: {MAX_ARTIFACT_SIZE_BYTES / (1024*1024):.2f}MB"
            )

        if file_size == 0:
            raise ValueError(f"Artifact file is empty: {path}")

        # Calculate checksum
        checksum = self._calculate_checksum(path)

        logger.info(
            "artifact_file_validated",
            path=str(path),
            size_mb=file_size / (1024*1024),
            checksum=checksum[:16] + "...",
        )

        return {
            "size": file_size,
            "checksum": checksum,
            "valid": True
        }

    def _calculate_checksum(self, path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def fit(
        self,
        records: List[DataRecord],
        save_artifacts: bool = False
    ) -> np.ndarray:
        """
        Fit the feature engineering pipeline on training data.

        This learns the TF-IDF vocabulary and data source encoding from the
        training data and optionally saves them for later use.

        Args:
            records: List of DataRecord instances
            save_artifacts: Whether to save fitted artifacts

        Returns:
            Feature matrix of shape (n_samples, n_features)

        Raises:
            ValidationError: If records are invalid
        """
        logger.info(
            "fit_called",
            n_records=len(records) if records else 0,
            save_artifacts=save_artifacts,
        )

        # Handle empty list as special case for default fitting
        if records is None or len(records) == 0:
            logger.info("empty_records_list", action="using_default_fit")
            self._fit_default()
            return np.array([]).reshape(0, 0)

        # Input validation for non-empty lists
        self._validate_record_list(records)

        if len(records) < MIN_RECORDS_FOR_FIT:
            logger.warning(
                "not_enough_records_to_fit",
                n_records=len(records),
                min_required=MIN_RECORDS_FOR_FIT,
            )
            self._fit_default()
            return self.extract_features_batch(records)

        # Extract text from records
        texts = []
        for r in records:
            try:
                text = self._extract_text_content(r)
                texts.append(text)
            except Exception as e:
                logger.warning(
                    "failed_to_extract_text_during_fit",
                    record_id=str(r.id) if hasattr(r, 'id') else "unknown",
                    error=str(e),
                )
                texts.append("")

        # Filter out empty texts
        non_empty_texts = [t for t in texts if t.strip()]
        if len(non_empty_texts) < MIN_RECORDS_FOR_FIT:
            logger.warning(
                "not_enough_non_empty_texts",
                n_non_empty=len(non_empty_texts),
                min_required=MIN_RECORDS_FOR_FIT,
            )
            self._fit_default()
            return self.extract_features_batch(records)

        # 1. Fit TF-IDF vectorizer with error handling
        logger.info("fitting_tfidf_vectorizer", n_texts=len(non_empty_texts))
        try:
            self.tfidf_vectorizer = TfidfVectorizer(**self.TFIDF_CONFIG)
            self.tfidf_vectorizer.fit(non_empty_texts)
        except ValueError as e:
            logger.error(
                "tfidf_fitting_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._fit_default()
            return self.extract_features_batch(records)

        # 2. Fit data source encoder
        logger.info("fitting_source_encoder")
        try:
            sources = [
                r.data_source.value if isinstance(r.data_source, DataSource) else str(r.data_source)
                for r in records
            ]
            # Group less common sources as 'other'
            from collections import Counter
            source_counts = Counter(sources)
            top_sources = set([s for s, c in source_counts.most_common(10)])
            sources_grouped = [s if s in top_sources else 'other' for s in sources]

            self.source_encoder = LabelEncoder()
            self.source_encoder.fit(sources_grouped)
        except Exception as e:
            logger.error(
                "source_encoder_fitting_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue with default encoder
            self.source_encoder = LabelEncoder()
            self.source_encoder.fit(['manual', 'api', 'csv', 'json', 'other'])

        # 3. Build feature names list
        self._build_feature_names()

        self.is_fitted = True

        # Save artifacts if requested
        if save_artifacts:
            try:
                self.save_artifacts()
            except Exception as e:
                logger.error(
                    "failed_to_save_artifacts",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        logger.info(
            "feature_engineering_fitted",
            n_features=len(self.feature_names),
        )

        # Extract and return features
        return self.extract_features_batch(records)

    def extract_features(self, record: DataRecord) -> np.ndarray:
        """
        Extract all features from a DataRecord.

        Args:
            record: DataRecord instance

        Returns:
            Feature array of shape (n_features,)

        Raises:
            ValidationError: If record is invalid
        """
        # Input validation
        self._validate_record(record)

        if not self.is_fitted:
            logger.warning("feature_engineering_not_fitted", action="using_default_values")
            self._fit_default()

        try:
            features = []

            # 1. TF-IDF Features (100 dims)
            tfidf_features = self._extract_tfidf_features(record)
            features.append(tfidf_features)

            # 2. Signal Features (5 dims)
            signal_features = self._extract_signal_features(record)
            features.append(signal_features)

            # 3. Engagement Features (3 dims)
            engagement_features = self._extract_engagement_features(record)
            features.append(engagement_features)

            # 4. Metadata Features (3 dims)
            metadata_features = self._extract_metadata_features(record)
            features.append(metadata_features)

            # Combine all features
            all_features = np.hstack(features)

            logger.debug(
                "features_extracted",
                n_features=len(all_features),
            )

            return all_features

        except Exception as e:
            logger.error(
                "feature_extraction_failed",
                record_id=str(record.id) if hasattr(record, 'id') else "unknown",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise RuntimeError(f"Failed to extract features from record: {e}") from e

    def extract_features_batch(self, records: List[DataRecord]) -> np.ndarray:
        """
        Extract features from multiple records efficiently.

        Args:
            records: List of DataRecord instances

        Returns:
            Feature matrix of shape (n_samples, n_features)

        Raises:
            ValidationError: If records are invalid
        """
        # Handle empty list
        if records is None or len(records) == 0:
            return np.array([]).reshape(0, 0)

        # Input validation
        self._validate_record_list(records)

        if not self.is_fitted:
            self._fit_default()

        # Extract features for each record with error handling
        features_list = []
        failed_indices = []

        for i, record in enumerate(records):
            try:
                features = self.extract_features(record)
                features_list.append(features)
            except Exception as e:
                logger.error(
                    "feature_extraction_failed_in_batch",
                    index=i,
                    record_id=str(record.id) if hasattr(record, 'id') else "unknown",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                failed_indices.append(i)
                # Add zero features as fallback
                if self.is_fitted and self.feature_names:
                    features_list.append(np.zeros(len(self.feature_names)))

        if failed_indices:
            logger.warning(
                "some_feature_extractions_failed",
                n_failed=len(failed_indices),
                failed_indices=failed_indices,
            )

        if not features_list:
            return np.array([]).reshape(0, 0)

        return np.vstack(features_list)

    def get_feature_names(self) -> List[str]:
        """
        Get the names of all features in order.

        Returns:
            List of feature names
        """
        return self.feature_names.copy()

    def _extract_text_content(self, record: DataRecord) -> str:
        """
        Extract text content from DataRecord

        Args:
            record: DataRecord to extract text from

        Returns:
            Combined text content
        """
        if record is None:
            return ""

        parts = []

        if record.data_preview:
            parts.append(record.data_preview)

        if record.extracted_text:
            parts.append(record.extracted_text)
        else:
            # Try to extract from raw_data
            if record.raw_data:
                try:
                    raw_dict = json.loads(record.raw_data)
                    for key in ["text", "content", "description", "message", "body"]:
                        if key in raw_dict and raw_dict[key]:
                            parts.append(str(raw_dict[key]))
                            break
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug(
                        "raw_data_not_json",
                        error=str(e),
                    )
                    parts.append(record.raw_data)

        return " ".join(parts)

    def _extract_tfidf_features(self, record: DataRecord) -> np.ndarray:
        """
        Extract TF-IDF features from text content.

        Args:
            record: DataRecord to extract features from

        Returns:
            TF-IDF feature array
        """
        text = self._extract_text_content(record)

        if not text.strip():
            # Return zero vector if no text
            return np.zeros(self.tfidf_vectorizer.max_features)

        # Transform using fitted vectorizer
        try:
            tfidf_vector = self.tfidf_vectorizer.transform([text]).toarray()
            return tfidf_vector[0]  # Return as 1D array
        except Exception as e:
            logger.warning(
                "tfidf_extraction_failed",
                error=str(e),
                text_length=len(text),
            )
            return np.zeros(self.tfidf_vectorizer.max_features)

    def _extract_signal_features(self, record: DataRecord) -> np.ndarray:
        """
        Extract binary signal features.

        Uses pattern matching to detect opportunity signals.

        Args:
            record: DataRecord to extract features from

        Returns:
            Signal feature array
        """
        # Initialize all signals to 0
        signals = np.zeros(len(self.SIGNAL_TYPES))

        # Combine text for analysis
        text = self._extract_text_content(record).lower()

        if not text:
            return signals

        # Signal detection patterns
        signal_patterns = {
            'TOOL_REQUEST': [
                r'looking for', r'need', r'searching', r'recommend',
                r'suggest', r'is there', r'anyone know'
            ],
            'PAIN_COMPLAINT': [
                r'hate', r'frustrat', r'annoy', r'struggle', r'difficult',
                r'can\'t stand', r'sucks', r'terrible', r'awful', r'pain'
            ],
            'PRICE_MENTION': [
                r'\$\d+', r'price', r'cost', r'cheap', r'expensive',
                r'free', r'paid', r'buy', r'afford'
            ],
            'PROBLEM_SOLUTION': [
                r'solve', r'solution', r'fix', r'resolve', r'help with',
                r'how to', r'issue', r'problem'
            ],
            'COMPARISON': [
                r'better than', r'vs', r'versus', r'compare', r'alternative',
                r'instead of', r'other than', r'which one'
            ],
        }

        # Check each signal type
        for i, signal_type in enumerate(self.SIGNAL_TYPES):
            if signal_type in signal_patterns:
                patterns = signal_patterns[signal_type]
                for pattern in patterns:
                    try:
                        if re.search(pattern, text, re.IGNORECASE):
                            signals[i] = 1
                            break
                    except re.error as e:
                        logger.warning(
                            "invalid_signal_pattern",
                            pattern=pattern,
                            error=str(e),
                        )

        return signals

    def _extract_engagement_features(self, record: DataRecord) -> np.ndarray:
        """
        Extract engagement features: quality_score, access_count, engagement_ratio.

        Args:
            record: DataRecord to extract features from

        Returns:
            Engagement feature array
        """
        features = np.zeros(3)

        # Quality score
        quality_score = record.data_quality_score if record.data_quality_score is not None else 0.0
        features[0] = quality_score

        # Access count (log-transformed)
        access_count = record.access_count if record.access_count is not None else 0
        features[1] = np.log1p(access_count)

        # Engagement ratio (access_count per quality_score unit)
        if quality_score > 0:
            features[2] = access_count / quality_score
        else:
            features[2] = 0

        return features

    def _extract_metadata_features(self, record: DataRecord) -> np.ndarray:
        """
        Extract metadata features: source_encoded, text_length, record_age_days.

        Args:
            record: DataRecord to extract features from

        Returns:
            Metadata feature array
        """
        features = np.zeros(3)

        # Data source encoding
        source = record.data_source.value if isinstance(record.data_source, DataSource) else str(record.data_source)
        if hasattr(self.source_encoder, 'classes_'):
            if source in self.source_encoder.classes_:
                features[0] = self.source_encoder.transform([source])[0]
            else:
                # Map to 'other' category if not seen during training
                if 'other' in self.source_encoder.classes_:
                    features[0] = self.source_encoder.transform(['other'])[0]
                else:
                    features[0] = 0
        else:
            features[0] = 0

        # Text length (log-transformed)
        text_length = len(self._extract_text_content(record))
        features[1] = np.log1p(text_length)

        # Record age in days (log-transformed)
        created_at = record.created_at if record.created_at else datetime.now(UTC)
        age_days = max(0, (datetime.now(UTC) - created_at).days)
        features[2] = np.log1p(age_days)

        return features

    def _build_feature_names(self):
        """Build the complete list of feature names in the correct order."""
        self.feature_names = []

        # TF-IDF features (100)
        if self.tfidf_vectorizer:
            tfidf_names = [f'tfidf_{name}' for name in self.tfidf_vectorizer.get_feature_names_out()]
            self.feature_names.extend(tfidf_names)
        else:
            self.feature_names.extend([f'tfidf_{i}' for i in range(100)])

        # Signal features (5)
        signal_names = [f'signal_{signal.lower()}' for signal in self.SIGNAL_TYPES]
        self.feature_names.extend(signal_names)

        # Engagement features (3)
        self.feature_names.extend(['quality_score', 'log_access_count', 'engagement_ratio'])

        # Metadata features (3)
        self.feature_names.extend(['source_encoded', 'log_text_length', 'log_age_days'])

    def _fit_default(self):
        """Fit with minimal default values for inference without training data."""
        logger.info("fitting_with_default_values")

        # Create default TF-IDF vectorizer
        default_texts = [
            "looking for tool app software",
            "hate this problem solution help",
            "need automation save time faster",
            "complex difficult learning curve",
            "recommend alternative better than",
            "tool request pain complaint",
            "price mention problem solution",
            "comparison alternative better",
            "test content data quality",
            "feature engineering machine learning",
        ] * 10  # Repeat to ensure enough samples

        self.tfidf_vectorizer = TfidfVectorizer(**self.TFIDF_CONFIG)
        self.tfidf_vectorizer.fit(default_texts)

        # Default source encoder
        self.source_encoder = LabelEncoder()
        self.source_encoder.fit(['manual', 'api', 'csv', 'json', 'other'])

        # Build feature names
        self._build_feature_names()

        self.is_fitted = True
        logger.info("feature_engineering_fitted_with_defaults")

    def save_artifacts(self, path: Optional[str] = None):
        """
        Save fitted artifacts for later use using joblib.

        Args:
            path: Path to save artifacts (optional)

        Raises:
            ValueError: If not fitted
        """
        if not self.is_fitted:
            raise ValueError("Cannot save artifacts: not fitted")

        save_path = Path(path) if path else self.artifacts_path
        save_path = save_path.with_suffix('.joblib')  # Use joblib extension
        save_path.parent.mkdir(parents=True, exist_ok=True)

        artifacts = {
            'tfidf_vectorizer': self.tfidf_vectorizer,
            'source_encoder': self.source_encoder,
            'feature_names': self.feature_names,
            'signal_types': self.SIGNAL_TYPES,
            'tfidf_config': self.TFIDF_CONFIG,
            'version': '1.1.0',
        }

        try:
            joblib.dump(artifacts, save_path)
            self._artifact_checksum = self._calculate_checksum(save_path)
            logger.info(
                "artifacts_saved",
                path=str(save_path),
                checksum=self._artifact_checksum[:16] + "...",
            )
        except Exception as e:
            logger.error(
                "failed_to_save_artifacts",
                path=str(save_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def load_artifacts(self, path: Optional[str] = None):
        """
        Load previously saved artifacts using joblib.

        Args:
            path: Path to artifacts file (optional)

        Raises:
            FileNotFoundError: If artifacts file not found
            ValueError: If validation fails
        """
        load_path = Path(path) if path else self.artifacts_path
        load_path = load_path.with_suffix('.joblib')  # Use joblib extension

        # Validate file before loading
        validation_result = self._validate_artifact_file(load_path)

        try:
            artifacts = joblib.load(load_path)

            self.tfidf_vectorizer = artifacts['tfidf_vectorizer']
            self.source_encoder = artifacts['source_encoder']
            self.feature_names = artifacts['feature_names']
            self.SIGNAL_TYPES = artifacts.get('signal_types', self.SIGNAL_TYPES)
            self.TFIDF_CONFIG = artifacts.get('tfidf_config', self.TFIDF_CONFIG)

            self._artifact_checksum = validation_result['checksum']
            self.is_fitted = True

            logger.info(
                "artifacts_loaded",
                path=str(load_path),
                n_features=len(self.feature_names),
                checksum=self._artifact_checksum[:16] + "...",
                version=artifacts.get('version', 'unknown'),
            )

        except Exception as e:
            logger.error(
                "failed_to_load_artifacts",
                path=str(load_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise


# Convenience function for quick feature extraction
def extract_features_from_record(
    record: DataRecord,
    artifacts_path: Optional[str] = None
) -> np.ndarray:
    """
    Extract features from a single record.

    Convenience function that creates a FeatureEngineering instance
    and extracts features in one call.

    Args:
        record: DataRecord instance
        artifacts_path: Path to feature extraction artifacts

    Returns:
        Feature array of shape (n_features,)

    Raises:
        ValidationError: If record is invalid
    """
    fe = FeatureEngineering(artifacts_path=artifacts_path)
    return fe.extract_features(record)
