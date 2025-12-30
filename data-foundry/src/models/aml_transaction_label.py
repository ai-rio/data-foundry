"""
AML Transaction Label ORM Model

This module defines the SQLModel for AI-generated AML transaction labels,
the core model for the AML service MLP. Labels include risk levels,
FATF typologies, confidence scores, and expert review tracking.

Features:
- AI-generated risk classification
- FATF typology assignment
- Confidence scoring with explainability
- Expert review workflow integration
- Audit readiness tracking
- CSV export support

Reference: P01-001 (Schema Design), P01-002 (Migrations)
Database table: aml_transaction_labels
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

from .aml_enums import AMLRiskLevel, AMLExpertReviewStatus


class AMLTransactionLabel(SQLModel, table=True):
    """
    AML Transaction Label Model.

    Stores AI-generated AML labels for transactions with risk levels,
    typologies, and expert review tracking. This is the core model
    for the AML service.

    Relationships:
    - tenant: Many-to-one with Tenant
    - methodology: Many-to-one with AMLLabelingMethodology
    - expert_reviews: One-to-many with AMLExpertReview

    Table: aml_transaction_labels
    """

    __tablename__ = "aml_transaction_labels"

    # Primary key - UUID
    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        description="Unique label identifier (UUID)"
    )

    # Foreign keys
    transaction_id: str = Field(
        index=True,
        description="Transaction identifier being labeled"
    )

    tenant_id: str = Field(
        index=True,
        description="Tenant identifier for multi-tenancy isolation"
    )

    version_id: Optional[str] = Field(
        default=None,
        description="Methodology version ID used for this label"
    )

    # Risk classification
    risk_level: AMLRiskLevel = Field(
        index=True,
        description="Risk classification: LOW, MEDIUM, HIGH, CRITICAL"
    )

    typology: str = Field(
        description="FATF typology code (e.g., ML, TF, PEP)"
    )

    # Confidence and reasoning
    confidence_score: Decimal = Field(
        description="AI model confidence score (0.00 - 1.00)"
    )

    ai_reasoning: str = Field(
        sa_column=Column(Text),
        description="AI model reasoning for explainability"
    )

    # Expert review workflow
    expert_review_status: AMLExpertReviewStatus = Field(
        index=True,
        default=AMLExpertReviewStatus.PENDING,
        description="Expert review workflow status"
    )

    # Regulatory flags (JSONB for flexibility)
    regulatory_flags: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Dynamic regulatory flags (FATF, FinCEN, etc.)"
    )

    # Audit tracking
    is_audit_ready: bool = Field(
        default=False,
        description="Indicates label is reviewed and ready for compliance audit"
    )

    is_deleted: bool = Field(
        default=False,
        description="Soft delete flag for data retention"
    )

    # Audit trail fields for soft delete tracking
    deleted_by: Optional[str] = Field(
        default=None,
        description="User ID who soft-deleted this record"
    )

    deleted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of soft deletion"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when label was created"
    )

    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when label was last updated"
    )

    # Audit trail for mutable record tracking
    updated_by: Optional[str] = Field(
        default=None,
        description="User ID who last updated this record"
    )

    class Config:
        """SQLModel configuration."""
        use_enum_values = True

    # =========================================================================
    # Business Logic Methods
    # =========================================================================

    def is_audit_ready_check(self) -> bool:
        """
        Check if label is ready for audit.

        A label is audit-ready when:
        1. is_audit_ready flag is True, AND
        2. Expert review status is AGREED

        Returns:
            bool: True if ready for audit, False otherwise
        """
        return self.is_audit_ready and self.expert_review_status == AMLExpertReviewStatus.AGREED

    def to_csv_row(self) -> Dict[str, Any]:
        """
        Convert label to CSV export format.

        Returns:
            dict: Dictionary suitable for CSV export with string values
        """
        return {
            "id": str(self.id) if self.id else "",
            "transaction_id": str(self.transaction_id) if self.transaction_id else "",
            "tenant_id": str(self.tenant_id) if self.tenant_id else "",
            "risk_level": self.risk_level.value if isinstance(self.risk_level, AMLRiskLevel) else str(self.risk_level),
            "typology": str(self.typology) if self.typology else "",
            "confidence_score": str(self.confidence_score) if self.confidence_score else "",
            "ai_reasoning": str(self.ai_reasoning) if self.ai_reasoning else "",
            "expert_review_status": self.expert_review_status.value if isinstance(self.expert_review_status, AMLExpertReviewStatus) else str(self.expert_review_status),
            "is_audit_ready": self.is_audit_ready,
            "is_deleted": self.is_deleted,
            "deleted_by": str(self.deleted_by) if self.deleted_by else "",
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else "",
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
            "updated_by": str(self.updated_by) if self.updated_by else "",
            "version_id": str(self.version_id) if self.version_id else ""
        }

    def get_risk_color(self) -> str:
        """
        Get color code for risk level (for UI display).

        Returns:
            str: Color name for the risk level
                - LOW: green
                - MEDIUM: yellow
                - HIGH: orange
                - CRITICAL: red
        """
        color_map = {
            AMLRiskLevel.LOW: "green",
            AMLRiskLevel.MEDIUM: "yellow",
            AMLRiskLevel.HIGH: "orange",
            AMLRiskLevel.CRITICAL: "red",
            # Handle string values as well
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "orange",
            "CRITICAL": "red"
        }
        return color_map.get(self.risk_level, "gray")

    def mark_for_review(self, updated_by: Optional[str] = None) -> None:
        """
        Mark label for expert review.

        Sets expert_review_status to PENDING and clears audit_ready flag.

        Args:
            updated_by: Optional user ID who is marking for review
        """
        self.expert_review_status = AMLExpertReviewStatus.PENDING
        self.is_audit_ready = False
        self.updated_at = datetime.utcnow()
        if updated_by:
            self.updated_by = updated_by

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert label to dictionary for serialization.

        Returns:
            dict: Serializable dictionary representation
        """
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "tenant_id": self.tenant_id,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, AMLRiskLevel) else self.risk_level,
            "typology": self.typology,
            "confidence_score": str(self.confidence_score) if self.confidence_score else None,
            "ai_reasoning": self.ai_reasoning,
            "expert_review_status": self.expert_review_status.value if isinstance(self.expert_review_status, AMLExpertReviewStatus) else self.expert_review_status,
            "regulatory_flags": self.regulatory_flags,
            "is_audit_ready": self.is_audit_ready,
            "is_deleted": self.is_deleted,
            "deleted_by": self.deleted_by,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "version_id": self.version_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by
        }

    def mark_as_deleted_by(self, user_id: str) -> None:
        """
        Mark record as soft-deleted by a specific user.

        Sets is_deleted flag to True and records who deleted it and when.

        Args:
            user_id: The ID of the user performing the soft delete
        """
        self.is_deleted = True
        self.deleted_by = user_id
        self.deleted_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.updated_by = user_id
