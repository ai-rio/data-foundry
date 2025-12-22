"""
Consent API Contracts - OpenAPI 3.0 Specification

Defines the contract for consent management endpoints following OpenAPI standards.
This implements a contract-first approach for API design and documentation.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class ConsentType(str, Enum):
    """Standard consent types for GDPR compliance."""
    DATA_PROCESSING = "data_processing"
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    THIRD_PARTY_SHARING = "third_party_sharing"
    COOKIES = "cookies"
    EMAIL_COMMUNICATION = "email_communication"
    RESEARCH = "research"


class ConsentStatus(str, Enum):
    """Consent status enumeration."""
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ObjectionCategory(str, Enum):
    """Categories for GDPR Article 21 objections."""
    DIRECT_MARKETING = "direct_marketing"
    PROFILING = "profiling"
    ANALYTICS = "analytics"
    RESEARCH = "research"
    THIRD_PARTY = "third_party"
    GENERAL = "general"


class MetadataModel(BaseModel):
    """Standard metadata model for consent requests."""
    ip: str = Field(..., description="IP address of the user (required for audit)")
    user_agent: str = Field(..., description="Browser/client identifier")
    purpose: Optional[str] = Field(None, description="Specific purpose of consent")
    retention_period: Optional[str] = Field(None, description="Data retention period")
    source: Optional[str] = Field(None, description="Source of consent (webform, mobile, etc.)")
    version: Optional[str] = Field(None, description="Consent form version")
    locale: Optional[str] = Field(None, description="Language/locale of consent")
    custom_fields: Optional[Dict[str, Any]] = Field(None, description="Additional custom metadata")


# Request Models
class GrantConsentRequest(BaseModel):
    """Request model for granting consent."""
    user_id: str = Field(..., min_length=1, max_length=255, description="User identifier")
    consent_type: ConsentType = Field(..., description="Type of consent being granted")
    consent_text: str = Field(
        ...,
        min_length=50,
        max_length=10000,
        description="Full consent text shown to user (minimum 50 characters for GDPR compliance)"
    )
    metadata: MetadataModel = Field(..., description="Request metadata for audit trail")

    @validator('consent_text')
    def validate_consent_text(cls, v):
        """Ensure consent text is specific and not generic."""
        v_lower = v.lower()
        vague_patterns = ["i agree", "i accept", "terms", "privacy policy", "yes", "ok", "i consent"]

        if any(pattern in v_lower for pattern in vague_patterns) and len(v) < 100:
            raise ValueError(
                "Consent text must be specific - avoid generic 'I agree' statements. "
                "Include details about what data is processed and why."
            )

        # Check for required elements
        required_elements = {
            "data_purpose": ["purpose", "why", "reason", "objective"],
            "data_type": ["data", "information", "personal data", "details"],
            "processing": ["processing", "use", "analyze", "store", "collect"],
            "retention": ["retain", "keep", "store", "period", "duration", "delete"]
        }

        missing_elements = []
        for element, keywords in required_elements.items():
            if not any(keyword in v_lower for keyword in keywords):
                missing_elements.append(element)

        if missing_elements:
            raise ValueError(
                f"Consent text must explain: {', '.join(missing_elements)}. "
                "Include details about what data is processed, why, how long it's kept, and the purpose."
            )

        return v


class WithdrawConsentRequest(BaseModel):
    """Request model for withdrawing consent."""
    user_id: str = Field(..., min_length=1, max_length=255, description="User identifier")
    consent_type: ConsentType = Field(..., description="Type of consent to withdraw")
    reason: Optional[str] = Field(None, max_length=1000, description="Optional reason for withdrawal")
    metadata: MetadataModel = Field(..., description="Request metadata for audit trail")


class ObjectToProcessingRequest(BaseModel):
    """Request model for GDPR Article 21 objection to processing."""
    user_id: str = Field(..., min_length=1, max_length=255, description="User identifier")
    consent_type: ConsentType = Field(..., description="Type of processing being objected to")
    reason: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Reason for objection (minimum 10 characters)"
    )
    category: ObjectionCategory = Field(
        ObjectionCategory.GENERAL,
        description="Category of objection"
    )
    metadata: MetadataModel = Field(..., description="Request metadata for audit trail")


class VerifyConsentRequest(BaseModel):
    """Request model for verifying consent status."""
    user_id: str = Field(..., min_length=1, max_length=255, description="User identifier")
    consent_type: ConsentType = Field(..., description="Type of consent to verify")
    check_time: Optional[datetime] = Field(
        None,
        description="Optional timestamp to check consent at specific time"
    )


# Response Models
class ConsentRecordResponse(BaseModel):
    """Response model for consent records."""
    id: int = Field(..., description="Consent record ID")
    user_id: str = Field(..., description="User identifier")
    consent_type: str = Field(..., description="Type of consent")
    consent_text: str = Field(..., description="Full consent text")
    granted_at: datetime = Field(..., description="When consent was granted")
    status: ConsentStatus = Field(..., description="Current consent status")
    withdrawn_at: Optional[datetime] = Field(None, description="When consent was withdrawn")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Consent metadata")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ConsentHistoryResponse(BaseModel):
    """Response model for consent history."""
    user_id: str = Field(..., description="User identifier")
    consent_type: Optional[str] = Field(None, description="Filter by consent type")
    records: List[ConsentRecordResponse] = Field(..., description="Historical consent records")
    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Records per page")
    has_more: bool = Field(..., description="Whether more records are available")


class ConsentVerificationResponse(BaseModel):
    """Response model for consent verification."""
    user_id: str = Field(..., description="User identifier")
    consent_type: str = Field(..., description="Type of consent checked")
    has_consent: bool = Field(..., description="Whether user has active consent")
    granted_at: Optional[datetime] = Field(None, description="When consent was granted")
    status: Optional[ConsentStatus] = Field(None, description="Current consent status")
    last_updated: Optional[datetime] = Field(None, description="When consent was last updated")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ObjectionResponse(BaseModel):
    """Response model for processing objections."""
    user_id: str = Field(..., description="User identifier")
    consent_type: str = Field(..., description="Type of processing objected to")
    objection_id: int = Field(..., description="Objection record ID")
    category: str = Field(..., description="Objection category")
    created_at: datetime = Field(..., description="When objection was recorded")
    status: str = Field(default="active", description="Objection status")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SuccessResponse(BaseModel):
    """Standard success response model."""
    success: bool = Field(default=True, description="Operation success status")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# Query Parameters
class ConsentQueryParams(BaseModel):
    """Common query parameters for consent endpoints."""
    page: int = Field(1, ge=1, description="Page number for pagination")
    per_page: int = Field(20, ge=1, le=100, description="Records per page (max 100)")
    status: Optional[ConsentStatus] = Field(None, description="Filter by consent status")
    consent_type: Optional[ConsentType] = Field(None, description="Filter by consent type")
    from_date: Optional[datetime] = Field(None, description="Filter from date")
    to_date: Optional[datetime] = Field(None, description="Filter to date")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# OpenAPI Documentation
CONSENT_API_TAGS = [
    {
        "name": "consent",
        "description": "Consent management endpoints for GDPR compliance",
        "externalDocs": {
            "description": "GDPR Reference",
            "url": "https://gdpr.eu/article-7-conditions-for-consent/"
        }
    }
]

CONSENT_ENDPOINT_DESCRIPTIONS = {
    "grant": """
    Grant new consent for data processing.

    This endpoint records a new consent according to GDPR Article 7 requirements:
    - Consent must be freely given, specific, informed, and unambiguous
    - Consent text must be detailed (minimum 50 characters)
    - IP address and user agent are recorded for audit purposes
    - All consents are logged to the audit trail

    **GDPR Compliance Notes:**
    - Article 7(1): Conditions for consent
    - Article 7(3): Right to withdraw consent
    - Record-keeping requirement for demonstrable consent
    """,

    "withdraw": """
    Withdraw previously granted consent.

    This endpoint implements the right to withdraw consent under GDPR Article 7(3):
    - Withdrawal is as easy as giving consent
    - Previous processing remains lawful
    - Withdrawal takes effect immediately
    - All withdrawals are logged to the audit trail

    **GDPR Compliance Notes:**
    - Article 7(3): Right to withdraw consent at any time
    - Withdrawal must be as easy as giving consent
    - Processing before withdrawal remains lawful
    """,

    "verify": """
    Verify if a user has active consent for a specific type of processing.

    This endpoint checks the current status of user consent:
    - Returns only active consents
    - Includes consent grant timestamp
    - Useful for pre-processing checks
    - All verifications are logged to the audit trail

    **Use Cases:**
    - Before data processing operations
    - For consent-gated features
    - To validate user permissions
    """,

    "object": """
    Object to processing of personal data (GDPR Article 21).

    This endpoint implements the right to object to processing:
    - Users can object even without prior consent
    - Creates a legally binding objection record
    - Processing must stop upon objection
    - All objections are logged to the audit trail

    **GDPR Compliance Notes:**
    - Article 21: Right to object to processing
    - Applies to profiling, direct marketing, and other processing
    - Objection must be respected unless compelling legitimate grounds exist
    """,

    "history": """
    Retrieve the complete consent history for a user.

    This endpoint provides an audit trail of all consent activities:
    - Includes both granted and withdrawn consents
    - Sorted by timestamp (newest first)
    - Paginated for efficient retrieval
    - Includes all metadata and audit information

    **Use Cases:**
    - GDPR data subject access requests
    - Internal audits and compliance checks
    - Consent management and reporting
    """,

    "user_consents": """
    Get all current consents for a user.

    This endpoint returns a user's current consent status:
    - Only active consents are included
    - Organized by consent type
    - Includes consent details and metadata
    - Useful for consent management interfaces

    **Use Cases:**
    - User preference centers
    - Consent management dashboards
    - Compliance reporting
    """
}