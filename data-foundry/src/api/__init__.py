"""
API Module

REST API endpoints for Data Foundry.

This module provides versioned API endpoints following REST principles.
"""

from .v1 import consent_router, billing_router, regulatory_router

__all__ = ["consent_router", "billing_router", "regulatory_router"]