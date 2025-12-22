"""
Consent API Module

REST API endpoints for GDPR-compliant consent management.

This module provides endpoints for:
- Granting and withdrawing consent
- Verifying consent status
- Objecting to processing (GDPR Art 21)
- Retrieving consent history and audit trails

All endpoints follow OpenAPI 3.0 specifications and include:
- Comprehensive request/response validation
- Rate limiting for protection
- Full audit trail integration
- GDPR compliance checks
"""

from .router import router as consent_router

__all__ = ["consent_router"]