"""
Regulatory API Contracts Module

Defines Pydantic models for request/response validation in regulatory endpoints.
Following API contract first approach for type safety and documentation.

This module provides contracts for:
- Regulatory framework information
- Risk level definitions
- Typology classifications
- Standard error responses

All contracts use Pydantic v2 for automatic validation and serialization.

Implementation: P01-016
"""

from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class RiskLevel(str, Enum):
    """
    AML risk level enumeration.

    Standard risk classifications used across regulatory frameworks
    (FATF, FinCEN, 6AMLD, COAF).
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TypologyCategory(str, Enum):
    """
    AML typology category enumeration.

    Classifies money laundering and terrorist financing typologies
    based on FATF, FinCEN, and COAF frameworks.
    """

    ML = "ML"  # Money Laundering
    TF = "TF"  # Terrorist Financing
    PEP = "PEP"  # Politically Exposed Persons
    FRAUD = "FRAUD"  # Fraud-related activity
    SANCTIONS = "SANCTIONS"  # Sanctions violations/evasion


# =============================================================================
# Response Models - Regulatory Framework
# =============================================================================

class RegulatoryFramework(BaseModel):
    """
    Regulatory framework information.

    Represents a regulatory body or framework (e.g., FATF, FinCEN).

    Attributes:
        name: Framework name (e.g., "FATF", "FinCEN")
        description: Brief description of the regulatory body
        recommendations: List of key recommendations or advisories
        url: Official website URL
    """

    name: str = Field(
        ...,
        description="Regulatory framework name",
        example="FATF"
    )

    description: str = Field(
        ...,
        description="Brief description of the regulatory body",
        example="Financial Action Task Force"
    )

    recommendations: List[str] = Field(
        default_factory=list,
        description="Key recommendations or advisories",
        example=["Rec 10", "Rec 15", "Rec 20"]
    )

    url: str = Field(
        ...,
        description="Official website URL",
        example="https://www.fatf-gafi.org"
    )


# =============================================================================
# Response Models - Regulatory Context
# =============================================================================

class RegulatoryContextResponse(BaseModel):
    """
    Complete regulatory context for AML service.

    Returns comprehensive regulatory framework information including
    FATF, FinCEN, EU 6AMLD/AMLA, and BCB/COAF references used in
    AML labeling methodology.

    Attributes:
        service: Service name
        version: Service version
        regulatory_frameworks: List of regulatory frameworks referenced
        risk_levels: Available risk level classifications
        typologies: AML typology categories
        last_updated: Last update timestamp
    """

    service: str = Field(
        default="AML Service",
        description="Service name"
    )

    version: str = Field(
        default="1.0",
        description="Service version",
        pattern=r"^\d+\.\d+(\.\d+)?$"
    )

    regulatory_frameworks: List[RegulatoryFramework] = Field(
        ...,
        description="List of regulatory frameworks referenced"
    )

    risk_levels: List[str] = Field(
        ...,
        description="Available risk level classifications",
        example=["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    )

    typologies: List[str] = Field(
        ...,
        description="AML typology categories",
        example=["ML", "TF", "PEP", "FRAUD", "SANCTIONS"]
    )

    last_updated: str = Field(
        ...,
        description="Last update timestamp (ISO 8601)",
        example="2025-12-30"
    )

    @field_validator('risk_levels')
    @classmethod
    def validate_risk_levels(cls, v: List[str]) -> List[str]:
        """Validate risk levels match expected values."""
        expected = [level.value for level in RiskLevel]
        if set(v) != set(expected):
            raise ValueError(f'risk_levels must be {expected}')
        return v

    @field_validator('typologies')
    @classmethod
    def validate_typologies(cls, v: List[str]) -> List[str]:
        """Validate typologies match expected values."""
        expected = [typ.value for typ in TypologyCategory]
        if set(v) != set(expected):
            raise ValueError(f'typologies must be {expected}')
        return v


# =============================================================================
# Response Models - Standard Responses
# =============================================================================

class HealthCheckResponse(BaseModel):
    """
    Health check response for regulatory endpoints.

    Attributes:
        status: Service health status
        timestamp: Current timestamp
        cached: Whether response is from cache
    """

    status: str = Field(
        default="healthy",
        description="Service health status",
        example="healthy"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Current timestamp"
    )

    cached: bool = Field(
        default=False,
        description="Whether response is from cache"
    )


class ErrorResponse(BaseModel):
    """
    Standard error response for regulatory endpoints.

    Attributes:
        error: Error message
        detail: Detailed error description (optional)
        status: HTTP status code
    """

    error: str = Field(
        ...,
        description="Error type or category",
        example="Validation error"
    )

    detail: Optional[str] = Field(
        None,
        description="Detailed error description"
    )

    status: int = Field(
        ...,
        description="HTTP status code",
        example=400,
        ge=400,
        le=599
    )


# =============================================================================
# Documentation
# =============================================================================

REGULATORY_API_TAGS = [
    {
        "name": "regulatory",
        "description": "Regulatory reference and compliance information"
    }
]

REGULATORY_ENDPOINT_DESCRIPTIONS = {
    "aml_context": (
        "Get regulatory context for AML service. "
        "Returns FATF, FinCEN, 6AMLD/AMLA, and BCB/COAF regulatory references "
        "used in AML labeling methodology. Includes risk levels, typologies, "
        "and framework information."
    ),
    "health": (
        "Health check endpoint for regulatory API. "
        "Returns service status and cache information."
    ),
}


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    # Enums
    'RiskLevel',
    'TypologyCategory',
    # Response models
    'RegulatoryFramework',
    'RegulatoryContextResponse',
    'HealthCheckResponse',
    'ErrorResponse',
    # Documentation
    'REGULATORY_API_TAGS',
    'REGULATORY_ENDPOINT_DESCRIPTIONS',
]
