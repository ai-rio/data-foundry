"""
AML Expert Review ORM Model

This module defines the SQLModel for expert human reviews of AI-generated
AML labels. Reviews are used for calculating inter-rater agreement
(Cohen's Kappa) for regulatory defensibility.

Features:
- Expert decision tracking (AGREE, DISAGREE, NEEDS_CLARIFICATION)
- Reasoning and confidence capture
- Review timestamp tracking
- Cohen's Kappa calculation support

Reference: P01-001 (Schema Design), P01-002 (Migrations)
Database table: aml_expert_reviews
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from .aml_enums import AMLExpertDecision


class AMLExpertReview(SQLModel, table=True):
    """
    AML Expert Review Model.

    Tracks expert human reviews of AI labels for inter-rater agreement
    calculation. Each review captures the expert's decision, reasoning,
    and confidence level.

    Relationships:
    - label: Many-to-one with AMLTransactionLabel
    - expert: Many-to-one with User
    - tenant: Many-to-one with Tenant

    Table: aml_expert_reviews
    """

    __tablename__ = "aml_expert_reviews"

    # Primary key - UUID
    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        description="Unique review identifier (UUID)"
    )

    # Foreign keys
    aml_transaction_label_id: str = Field(
        index=True,
        description="Transaction label being reviewed"
    )

    tenant_id: str = Field(
        index=True,
        description="Tenant identifier for multi-tenancy isolation"
    )

    expert_id: str = Field(
        index=True,
        description="User ID of the expert reviewer"
    )

    # Review decision
    expert_decision: AMLExpertDecision = Field(
        description="Expert decision: AGREE, DISAGREE, NEEDS_CLARIFICATION"
    )

    reasoning: str = Field(
        sa_column=Column(Text),
        description="Expert's reasoning for their decision"
    )

    # Confidence level
    confidence_level: Decimal = Field(
        description="Expert confidence in their decision (0.00 - 1.00)"
    )

    # Review timestamp
    reviewed_at: datetime = Field(
        description="Timestamp when review was completed"
    )

    # Soft delete
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

    # Created timestamp
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when record was created"
    )

    class Config:
        """SQLModel configuration."""
        use_enum_values = True

    # =========================================================================
    # Business Logic Methods
    # =========================================================================

    def is_agreement(self) -> bool:
        """
        Check if expert agrees with AI classification.

        Returns:
            bool: True if decision is AGREE, False otherwise
        """
        return self.expert_decision == AMLExpertDecision.AGREE

    def is_disagreement(self) -> bool:
        """
        Check if expert disagrees with AI classification.

        Returns:
            bool: True if decision is DISAGREE, False otherwise
        """
        return self.expert_decision == AMLExpertDecision.DISAGREE

    def needs_clarification(self) -> bool:
        """
        Check if expert needs clarification.

        Returns:
            bool: True if decision is NEEDS_CLARIFICATION, False otherwise
        """
        return self.expert_decision == AMLExpertDecision.NEEDS_CLARIFICATION

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert review to dictionary for serialization.

        Returns:
            dict: Serializable dictionary representation
        """
        return {
            "id": self.id,
            "aml_transaction_label_id": self.aml_transaction_label_id,
            "tenant_id": self.tenant_id,
            "expert_id": self.expert_id,
            "expert_decision": self.expert_decision.value if isinstance(self.expert_decision, AMLExpertDecision) else self.expert_decision,
            "reasoning": self.reasoning,
            "confidence_level": str(self.confidence_level) if self.confidence_level else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "is_deleted": self.is_deleted,
            "deleted_by": self.deleted_by,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
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

    def get_review_age_hours(self) -> Optional[float]:
        """
        Get age of review in hours since reviewed_at.

        Returns:
            float: Hours since review, or None if reviewed_at not set
        """
        if not self.reviewed_at:
            return None
        delta = datetime.utcnow() - self.reviewed_at
        return delta.total_seconds() / 3600
