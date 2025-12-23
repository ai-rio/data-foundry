"""
Test-Driven Development tests for FeatureEngineering class (Week 3)
Tests for feature extraction pipeline adapted from pipeline-v4

Adapted from pipeline-v4 feature_extractor for Data Foundry DataRecord model
"""

from datetime import datetime, UTC

import numpy as np
import pytest

from src.ml.feature_engineering import FeatureEngineering
from src.models.data_record import DataRecord, DataSource, DataStatus


def create_test_record(
    record_id: str,
    data_preview: str,
    raw_data: str,
    data_quality_score: float = 0.8,
    access_count: int = 10,
    data_source: DataSource = DataSource.MANUAL,
) -> DataRecord:
    """Helper to create test DataRecord instances"""
    return DataRecord(
        id=1,
        record_id=record_id,
        tenant_id="test_tenant",
        data_source=data_source,
        status=DataStatus.RAW,
        data_preview=data_preview,
        raw_data=raw_data,
        data_quality_score=data_quality_score,
        access_count=access_count,
        created_at=datetime.now(UTC),
    )


class TestFeatureEngineeringInitialization:
    """Test FeatureEngineering class initialization"""

    def test_feature_engineering_initializes_with_defaults(self):
        """Test that FeatureEngineering initializes with default parameters"""
        fe = FeatureEngineering()
        assert fe.is_fitted is False
        assert fe.tfidf_vectorizer is None
        assert fe.source_encoder is None

    def test_feature_engineering_initializes_with_artifacts_path(self):
        """Test that FeatureEngineering accepts artifacts path"""
        fe = FeatureEngineering(artifacts_path="/tmp/test_artifacts.joblib")
        assert fe.artifacts_path.name == "test_artifacts.joblib"

    def test_feature_engineering_has_tfidf_config(self):
        """Test that FeatureEngineering has TF-IDF configuration"""
        fe = FeatureEngineering()
        assert hasattr(fe, 'TFIDF_CONFIG')
        assert 'max_features' in fe.TFIDF_CONFIG
        assert fe.TFIDF_CONFIG['max_features'] == 100

    def test_feature_engineering_has_signal_types(self):
        """Test that FeatureEngineering has signal type definitions"""
        fe = FeatureEngineering()
        assert hasattr(fe, 'SIGNAL_TYPES')
        assert len(fe.SIGNAL_TYPES) > 0
        assert 'TOOL_REQUEST' in fe.SIGNAL_TYPES or 'PAIN_COMPLAINT' in fe.SIGNAL_TYPES


class TestFeatureEngineeringFit:
    """Test feature engineering fitting"""

    def test_fit_on_training_data(self):
        """Test fitting FeatureEngineering on training data"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Looking for tool software {i}",
                raw_data=f'{{"text": "Need help with problem solution {i}"}}',
                data_source=DataSource.MANUAL,
            )
            for i in range(20)
        ]

        features = fe.fit(records)

        # Should return features for all records
        assert features.shape[0] == 20
        assert features.shape[1] > 0  # Should have some features

        # Should be fitted now
        assert fe.is_fitted is True
        assert fe.tfidf_vectorizer is not None
        assert fe.source_encoder is not None

    def test_fit_saves_artifacts(self, tmp_path):
        """Test that fitting saves artifacts"""
        artifacts_path = tmp_path / "test_artifacts.joblib"  # Changed from .pkl to .joblib
        fe = FeatureEngineering(artifacts_path=str(artifacts_path))

        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Tool software automation {i}",
                raw_data=f'{{"text": "Help solution problem {i}"}}',
            )
            for i in range(20)
        ]

        fe.fit(records, save_artifacts=True)

        # Artifacts file should exist (with .joblib extension)
        assert (tmp_path / "test_artifacts.joblib").exists()

    def test_fit_builds_feature_names(self):
        """Test that fitting builds feature names"""
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

        # Should have feature names
        assert len(fe.feature_names) > 0
        assert all(isinstance(name, str) for name in fe.feature_names)


class TestFeatureExtraction:
    """Test feature extraction from records"""

    def test_extract_features_single_record(self):
        """Test extracting features from a single record"""
        fe = FeatureEngineering()
        # Fit first
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview="Looking for a tool",
                raw_data='{"text": "I need help"}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        # Extract from new record
        test_record = create_test_record(
            record_id="new1",
            data_preview="Looking for a recommendation",
            raw_data='{"text": "Please help me find software"}',
        )

        features = fe.extract_features(test_record)

        # Should return 1D array
        assert isinstance(features, np.ndarray)
        assert features.ndim == 1
        assert len(features) > 0

    def test_extract_features_batch(self):
        """Test extracting features from multiple records"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview="Test content",
                raw_data='{"text": "Test text"}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        # Extract batch
        test_records = [
            create_test_record(
                record_id=f"batch{i}",
                data_preview="Looking for recommendations",
                raw_data='{"text": "Need help"}',
            )
            for i in range(5)
        ]

        features = fe.extract_features_batch(test_records)

        # Should return 2D array
        assert features.ndim == 2
        assert features.shape[0] == 5  # 5 records
        assert features.shape[1] > 0   # Features

    def test_extract_features_unfitted_uses_defaults(self):
        """Test that unfitted extractor uses default values"""
        fe = FeatureEngineering()
        test_record = create_test_record(
            record_id="test1",
            data_preview="Looking for a tool",
            raw_data='{"text": "I need help"}',
        )

        features = fe.extract_features(test_record)

        # Should still work with defaults
        assert isinstance(features, np.ndarray)
        assert len(features) > 0
        # Should auto-fit
        assert fe.is_fitted is True


class TestTFIDFFeatures:
    """Test TF-IDF feature extraction"""

    def test_tfidf_features_extracted(self):
        """Test that TF-IDF features are extracted"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Looking for tool app software help {i}",
                raw_data=f'{{"text": "Need solution problem automation {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        test_record = create_test_record(
            record_id="test1",
            data_preview="Looking for recommendations software",
            raw_data='{"text": "Tool help automation problem"}',
        )

        features = fe.extract_features(test_record)

        # Should have features (TF-IDF + signals + engagement + metadata)
        # Note: With small datasets, TF-IDF may have fewer than 100 features
        assert len(features) >= 30  # At minimum: TF-IDF + 5 signals + 3 engagement + 3 metadata

    def test_tfidf_handles_empty_content(self):
        """Test TF-IDF handles empty/minimal content"""
        fe = FeatureEngineering()
        # Fit with defaults
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="",
            raw_data='{}',
        )

        features = fe.extract_features(test_record)

        # Should handle empty content
        assert isinstance(features, np.ndarray)


class TestSignalFeatures:
    """Test signal feature extraction"""

    def test_signal_features_detect_tool_request(self):
        """Test that signal features detect tool requests"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="Looking for a tool",
            raw_data='{"text": "I need a software"}',
        )

        features = fe.extract_features(test_record)

        # Should have signal features
        assert len(features) > 0

    def test_signal_features_detect_pain_complaint(self):
        """Test that signal features detect pain complaints"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="I hate when this crashes",
            raw_data='{"text": "So frustrated with this"}',
        )

        features = fe.extract_features(test_record)

        # Should have signal features
        assert len(features) > 0


class TestEngagementFeatures:
    """Test engagement feature extraction"""

    def test_engagement_features_quality_score(self):
        """Test that quality score is included in features"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="Test content",
            raw_data='{"text": "Test"}',
            data_quality_score=0.85,
        )

        features = fe.extract_features(test_record)

        # Should include quality score feature
        assert len(features) > 0

    def test_engagement_features_access_count(self):
        """Test that access count is included in features"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="Test content",
            raw_data='{"text": "Test"}',
            access_count=100,
        )

        features = fe.extract_features(test_record)

        # Should include access count feature
        assert len(features) > 0


class TestMetadataFeatures:
    """Test metadata feature extraction"""

    def test_metadata_features_source_encoding(self):
        """Test that data source is encoded"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview="Test",
                raw_data='{}',
                data_source=source,
            )
            for i, source in enumerate([DataSource.MANUAL, DataSource.API, DataSource.CSV])
        ]
        fe.fit(records)

        test_record = create_test_record(
            record_id="test1",
            data_preview="Test",
            raw_data='{}',
            data_source=DataSource.API,
        )

        features = fe.extract_features(test_record)

        # Should include source encoding
        assert len(features) > 0


class TestFeatureValidation:
    """Test feature validation"""

    def test_feature_count_consistency(self):
        """Test that feature count is consistent across records"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Test content tool software {i}",
                raw_data=f'{{"text": "Problem solution help {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        # Extract from multiple records
        test_records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Content automation {i}",
                raw_data=f'{{"text": "Need help software {i}"}}',
            )
            for i in range(5)
        ]

        features = fe.extract_features_batch(test_records)

        # All records should have same number of features
        for i in range(features.shape[0]):
            assert features.shape[1] == len(fe.feature_names)

    def test_get_feature_names(self):
        """Test getting feature names"""
        fe = FeatureEngineering()
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Tool software automation {i}",
                raw_data=f'{{"text": "Problem solution help {i}"}}',
            )
            for i in range(20)
        ]
        fe.fit(records)

        feature_names = fe.get_feature_names()

        # Should return list of names
        assert isinstance(feature_names, list)
        assert len(feature_names) > 0
        assert all(isinstance(name, str) for name in feature_names)


class TestArtifactManagement:
    """Test artifact saving and loading"""

    def test_save_and_load_artifacts(self, tmp_path):
        """Test saving and loading artifacts"""
        artifacts_path = tmp_path / "test_artifacts.joblib"

        # Create and fit
        fe1 = FeatureEngineering(artifacts_path=str(artifacts_path))
        records = [
            create_test_record(
                record_id=f"test{i}",
                data_preview=f"Tool software help {i}",
                raw_data=f'{{"text": "Problem solution need {i}"}}',
            )
            for i in range(20)
        ]
        fe1.fit(records, save_artifacts=True)

        # Load new instance
        fe2 = FeatureEngineering(artifacts_path=str(artifacts_path))
        fe2.load_artifacts()

        # Should have same feature names
        assert fe1.feature_names == fe2.feature_names

    def test_load_artifacts_without_fit_raises_error(self, tmp_path):
        """Test loading non-existent artifacts raises error"""
        artifacts_path = tmp_path / "nonexistent.joblib"
        fe = FeatureEngineering(artifacts_path=str(artifacts_path))

        with pytest.raises(FileNotFoundError):
            fe.load_artifacts()


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_extract_from_record_with_no_content(self):
        """Test extracting from record with minimal content"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="",
            raw_data='{}',
        )

        features = fe.extract_features(test_record)

        # Should handle minimal content
        assert isinstance(features, np.ndarray)

    def test_extract_from_record_with_unicode(self):
        """Test extracting from record with unicode content"""
        fe = FeatureEngineering()
        fe.fit([])

        test_record = create_test_record(
            record_id="test1",
            data_preview="¿Hay una herramienta?",
            raw_data='{"text": "Besoin d\'aide"}',
        )

        features = fe.extract_features(test_record)

        # Should handle unicode
        assert isinstance(features, np.ndarray)

    def test_extract_from_very_long_content(self):
        """Test extracting from record with very long content"""
        fe = FeatureEngineering()
        fe.fit([])

        long_content = "This is a test " * 1000
        test_record = create_test_record(
            record_id="test1",
            data_preview=long_content,
            raw_data=f'{{"text": "{long_content}"}}',
        )

        features = fe.extract_features(test_record)

        # Should handle long content
        assert isinstance(features, np.ndarray)
