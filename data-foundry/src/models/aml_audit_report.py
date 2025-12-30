"""
AML Audit Report ORM Model

This module defines the SQLModel for AML audit reports, storing
generated compliance reports with inter-rater agreement metrics.

Features:
- Transaction and labeling statistics
- Cohen's Kappa coefficient tracking
- Agreement level classification
- Report URL for generated PDF/document
- Regulatory defensibility support

Reference: P01-001 (Schema Design), P01-002 (Migrations)
Database table: aml_audit_reports
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlmodel import Field, SQLModel

from .aml_enums import AMLAgreementLevel


class AMLAuditReport(SQLModel, table=True):
    """
    AML Audit Report Model.

    Stores generated audit reports for regulatory defensibility and compliance.
    Each report captures labeling statistics and inter-rater agreement metrics.

    Relationships:
    - tenant: Many-to-one with Tenant
    - job: Many-to-one with ProcessingJob

    Table: aml_audit_reports
    """

    __tablename__ = "aml_audit_reports"

    # Primary key - UUID
    id: Optional[str] = Field(
        default=None,
        primary_key=True,
        description="Unique report identifier (UUID)"
    )

    # Foreign keys
    tenant_id: str = Field(
        index=True,
        description="Tenant identifier for multi-tenancy isolation"
    )

    job_id: str = Field(
        index=True,
        description="Processing job ID that generated this report"
    )

    # Transaction statistics
    transaction_count: int = Field(
        ge=0,
        description="Total number of transactions in the audit scope"
    )

    labeled_count: int = Field(
        ge=0,
        description="Number of transactions that were labeled"
    )

    expert_reviewed_count: int = Field(
        ge=0,
        description="Number of labels reviewed by experts"
    )

    # Inter-rater agreement metrics
    kappa_coefficient: Decimal = Field(
        description="Cohen's Kappa coefficient (-1.00 to 1.00)"
    )

    agreement_level: AMLAgreementLevel = Field(
        description="Qualitative agreement level from kappa interpretation"
    )

    # Report metadata
    generated_at: datetime = Field(
        description="Timestamp when report was generated"
    )

    report_url: str = Field(
        description="URL/path to generated report file (S3, storage, etc.)"
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

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary metrics for the audit report.

        Returns:
            dict: Summary metrics including counts, rates, and agreement level
        """
        # Calculate labeling rate
        labeling_rate = 0.0
        if self.transaction_count > 0:
            labeling_rate = self.labeled_count / self.transaction_count

        # Calculate review rate
        review_rate = 0.0
        if self.labeled_count > 0:
            review_rate = self.expert_reviewed_count / self.labeled_count

        return {
            "transaction_count": self.transaction_count,
            "labeled_count": self.labeled_count,
            "expert_reviewed_count": self.expert_reviewed_count,
            "kappa_coefficient": self.kappa_coefficient,
            "agreement_level": self.agreement_level.value if isinstance(self.agreement_level, AMLAgreementLevel) else self.agreement_level,
            "labeling_rate": round(labeling_rate, 2),
            "review_rate": round(review_rate, 2),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "report_url": self.report_url
        }

    def is_substantial_agreement(self) -> bool:
        """
        Check if report has substantial inter-rater agreement.

        Substantial agreement is defined as kappa >= 0.6, which is
        typically required for regulatory defensibility.

        Returns:
            bool: True if kappa >= 0.6, False otherwise
        """
        return self.kappa_coefficient >= Decimal("0.6")

    def is_perfect_agreement(self) -> bool:
        """
        Check if report has perfect agreement level.

        Returns:
            bool: True if agreement_level is PERFECT
        """
        return self.agreement_level == AMLAgreementLevel.PERFECT

    def get_labeling_coverage(self) -> float:
        """
        Calculate labeling coverage percentage.

        Returns:
            float: Percentage of transactions that were labeled (0-100)
        """
        if self.transaction_count == 0:
            return 0.0
        return (self.labeled_count / self.transaction_count) * 100

    def get_review_coverage(self) -> float:
        """
        Calculate expert review coverage percentage.

        Returns:
            float: Percentage of labels that were reviewed (0-100)
        """
        if self.labeled_count == 0:
            return 0.0
        return (self.expert_reviewed_count / self.labeled_count) * 100

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert report to dictionary for serialization.

        Returns:
            dict: Serializable dictionary representation
        """
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "job_id": self.job_id,
            "transaction_count": self.transaction_count,
            "labeled_count": self.labeled_count,
            "expert_reviewed_count": self.expert_reviewed_count,
            "kappa_coefficient": str(self.kappa_coefficient) if self.kappa_coefficient else None,
            "agreement_level": self.agreement_level.value if isinstance(self.agreement_level, AMLAgreementLevel) else self.agreement_level,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "report_url": self.report_url,
            "is_deleted": self.is_deleted,
            "deleted_by": self.deleted_by,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "labeling_coverage_pct": self.get_labeling_coverage(),
            "review_coverage_pct": self.get_review_coverage(),
            "is_substantial_agreement": self.is_substantial_agreement()
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

    @staticmethod
    def interpret_kappa(kappa: Decimal) -> AMLAgreementLevel:
        """
        Interpret kappa coefficient to agreement level.

        Based on Landis & Koch (1977) interpretation scale.

        Args:
            kappa: Cohen's Kappa coefficient (-1 to 1)

        Returns:
            AMLAgreementLevel: Qualitative interpretation
        """
        if kappa < Decimal("0.0"):
            return AMLAgreementLevel.POOR
        elif kappa < Decimal("0.21"):
            return AMLAgreementLevel.FAIR
        elif kappa < Decimal("0.41"):
            return AMLAgreementLevel.MODERATE
        elif kappa < Decimal("0.61"):
            return AMLAgreementLevel.SUBSTANTIAL
        else:
            return AMLAgreementLevel.PERFECT
