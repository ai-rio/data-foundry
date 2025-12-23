"""
ML Predictor API Router Package

This package provides ML prediction endpoints for data quality scoring,
feature extraction, and model management.

Components:
- contracts.py: Pydantic request/response models
- router.py: FastAPI router with endpoints
- __init__.py: Package initialization

Pattern reference: src/api/v1/signals/__init__.py
"""

from src.api.v1.ml.router import router

__all__ = ["router"]
