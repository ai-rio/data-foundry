"""
API v1 Module

Version 1 of the Data Foundry REST API.

This module organizes all v1 API endpoints by functional area:
- consent: GDPR-compliant consent management
- billing: Stripe billing and webhook handling
- (Future modules can be added here)
"""

from .consent import consent_router
from .billing import billing_router

__all__ = ["consent_router", "billing_router"]