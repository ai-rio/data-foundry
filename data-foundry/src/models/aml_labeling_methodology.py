"""
AML Labeling Methodology ORM Model

This module defines the SQLModel for AML labeling methodology versioning,
enabling audit trail and regulatory defensibility for AML classification rules.

The methodology tracks:
- Versioned labeling rules and thresholds
- FATF typologies used for classification
- Regulatory references for compliance
- Lifecycle status (DRAFT, ACTIVE, ARCHIVED)

Reference: P01-001 (Schema Design), P01-002 (Migrations)
Database table: aml_labeling_methodology
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

from .aml_enums import AMLMethodologyStatus


class AMLLabelingMethodology(SQLModel, table=True):
    """
    AML Labeling Methodology Model.

    Tracks versioned AML labeling rules and methodologies for audit trail.
    Each version captures the complete set of rules used for labeling
    transactions at a specific point in time.

    Relationships:
    - tenant: Many-to-one with Tenant
    - created_by_user: Many-to-one with User
    - labels: One-to-many with AMLTransactionLabel

    Table: aml_labeling_methodology
    """

    __tablename__ = "aml_labeling_methodology"

    # Primary key - UUID
    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        description="Unique methodology identifier (UUID)"
    )

    # Foreign keys
    tenant_id: str = Field(
        index=True,
        description="Tenant identifier for multi-tenancy isolation"
    )

    created_by: Optional[str] = Field(
        default=None,
        description="User ID who created this methodology version"
    )

    # Methodology versioning
    version: str = Field(
        description="Methodology version string (e.g., '1.0', '1.1', '2.0')"
    )

    description: str = Field(
        sa_column=Column(Text),
        description="Human-readable description of this methodology version"
    )

    # JSONB configuration fields
    risk_thresholds: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Confidence thresholds for each risk level (LOW, MEDIUM, HIGH, CRITICAL)"
    )

    typologies: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of valid FATF AML typologies for this methodology"
    )

    regulatory_references: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Links to regulatory frameworks (FATF, FinCEN, etc.)"
    )

    # Status and soft delete
    status: AMLMethodologyStatus = Field(
        index=True,
        description="Methodology lifecycle status (DRAFT, ACTIVE, ARCHIVED)"
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

    # Timestamp
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when methodology was created"
    )

    class Config:
        """SQLModel configuration."""
        use_enum_values = True

    # =========================================================================
    # Business Logic Methods
    # =========================================================================

    def is_active(self) -> bool:
        """
        Check if methodology is currently active.

        Returns:
            bool: True if status is ACTIVE, False otherwise
        """
        return self.status == AMLMethodologyStatus.ACTIVE

    def get_thresholds(self) -> Dict[str, Any]:
        """
        Get risk thresholds configuration.

        Returns:
            dict: Risk thresholds for each level
            Example: {
                "LOW": {"min": 0.0, "max": 0.25},
                "MEDIUM": {"min": 0.25, "max": 0.5},
                ...
            }
        """
        return self.risk_thresholds or {}

    def get_typologies(self) -> List[str]:
        """
        Get list of valid FATF typologies for this methodology.

        Returns:
            list: List of typology codes (e.g., ["ML", "TF", "PEP"])
        """
        return self.typologies or []

    def get_regulatory_references(self) -> Dict[str, Any]:
        """
        Get regulatory framework references.

        Returns:
            dict: Regulatory references with URLs
            Example: {
                "FATF": "https://www.fatf-gafi.org/",
                "FinCEN": "https://www.fincen.gov/"
            }
        """
        return self.regulatory_references or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert methodology to dictionary for serialization.

        Returns:
            dict: Serializable dictionary representation
        """
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "version": self.version,
            "description": self.description,
            "risk_thresholds": self.risk_thresholds,
            "typologies": self.typologies,
            "regulatory_references": self.regulatory_references,
            "created_by": self.created_by,
            "status": self.status.value if isinstance(self.status, AMLMethodologyStatus) else self.status,
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
