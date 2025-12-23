"""
ML Components for Data Foundry

This module contains machine learning infrastructure for:
- Feature engineering and extraction
- Quality prediction models
- Signal detection with ML

Components:
- FeatureEngineering: Extract features from data records for ML prediction
- QualityPredictor: ML-based quality prediction using trained models
"""

from src.ml.feature_engineering import FeatureEngineering
from src.ml.quality_predictor import QualityPredictor

__all__ = [
    "FeatureEngineering",
    "QualityPredictor",
]
