"""
Signal Detection API Package

Provides endpoints for detecting opportunity signals in data records.
Week 4 Phase 2.3 implementation following TDD principles.
"""

from src.api.v1.signals.router import router

__all__ = ["router"]
