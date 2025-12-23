"""
Data Quality API Router Package

This package contains the data quality validation API router.

Components:
- contracts.py: Pydantic models for request/response validation
- router.py: FastAPI router with quality endpoints
"""

from src.api.v1.quality.router import router

__all__ = ["router"]
