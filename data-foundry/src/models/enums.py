"""
Shared enumerations for Data Foundry models.

This module contains common enums used across multiple models to avoid
circular imports and maintain consistency.
"""

from enum import Enum


class ConsentStatus(str, Enum):
    """Consent status enumeration for GDPR compliance"""
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"