"""
Jobs API Contracts

Pydantic models for job-related API operations, including AML-specific contracts
for Anti-Money Laundering transaction labeling and metrics.

Contracts:
- JobStatusContract: Enhanced with AML-specific fields for risk metrics
- AMLMetricsContract: AML processing metrics and statistics
- AMLTransactionLabelContract: Individual AML transaction label details
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.models.aml_enums import (
    AMLExpertReviewStatus,
    AMLRiskLevel,
)


class JobStatusContract(BaseModel):
    """
    API Response: Job status details with AML-specific metrics.

    Extends the base job status contract to include AML processing metrics
    such as risk level distributions, inter-rater agreement, and audit report
    URLs for regulatory compliance.

    Attributes:
        job_id: Unique job identifier (UUID)
        tenant_id: Tenant identifier for multi-tenancy
        status: Current job status (pending, processing, complete, failed, cancelled)
        file_name: Original filename
        file_size: File size in bytes
        complexity_tier: Processing complexity tier (simple, moderate, complex)
        estimated_cost: Estimated cost in USD
        actual_cost: Actual cost in USD (if completed)
        created_at: Job creation timestamp
        started_at: Job start timestamp (if started)
        completed_at: Job completion timestamp (if completed)
        result_records: Number of records processed
        result_url: Download URL for results
        error_message: Error message if job failed
        retry_count: Number of retry attempts
        can_retry: Whether job can be retried
        aml_risk_level_counts: Count of transactions by risk level (LOW, MEDIUM, HIGH, CRITICAL)
        aml_inter_rater_agreement: Cohen's Kappa coefficient for AI-expert agreement
        aml_expert_review_count: Number of labels reviewed by experts
        aml_audit_report_url: URL to generated AML audit report (if available)
    """

    job_id: str = Field(..., description="Job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    status: str = Field(..., description="Current status")

    # File info
    file_name: str = Field(..., description="Original filename")
    file_size: int = Field(..., description="File size in bytes")
    complexity_tier: str = Field(..., description="Processing complexity")

    # Cost
    estimated_cost: str = Field(..., description="Estimated cost (USD)")
    actual_cost: Optional[str] = Field(None, description="Actual cost (USD)")

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    result_records: Optional[int] = Field(None, description="Records processed")
    result_url: Optional[str] = Field(None, description="Results download URL")
    error_message: Optional[str] = Field(None, description="Error if failed")

    # Retry info
    retry_count: int = Field(default=0, description="Number of retries")
    can_retry: bool = Field(default=False, description="Can be retried")

    # AML-specific fields
    aml_risk_level_counts: Optional[Dict[str, int]] = Field(
        None,
        description="Distribution of AML risk levels (LOW, MEDIUM, HIGH, CRITICAL)"
    )

    aml_inter_rater_agreement: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Cohen's Kappa coefficient measuring AI-expert agreement (-1.0 to 1.0)"
    )

    aml_expert_review_count: Optional[int] = Field(
        None,
        ge=0,
        description="Number of AML labels reviewed by human experts"
    )

    aml_audit_report_url: Optional[str] = Field(
        None,
        description="URL to generated AML compliance audit report"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "tenant_id": "tenant-123",
                "status": "complete",
                "file_name": "customer_data.csv",
                "file_size": 1048576,
                "complexity_tier": "simple",
                "estimated_cost": "0.006089",
                "actual_cost": "0.005500",
                "created_at": "2025-01-15T10:30:00Z",
                "started_at": "2025-01-15T10:30:05Z",
                "completed_at": "2025-01-15T10:31:30Z",
                "result_records": 10000,
                "result_url": "https://storage.example.com/results/...",
                "error_message": None,
                "retry_count": 0,
                "can_retry": False,
                "aml_risk_level_counts": {
                    "LOW": 8500,
                    "MEDIUM": 1200,
                    "HIGH": 250,
                    "CRITICAL": 50
                },
                "aml_inter_rater_agreement": 0.72,
                "aml_expert_review_count": 300,
                "aml_audit_report_url": "https://storage.example.com/audit/reports/job-123.pdf"
            }
        }
    }

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert contract to dictionary for serialization.

        Returns:
            Dictionary representation of the job status with all fields
        """
        return {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "status": self.status,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "complexity_tier": self.complexity_tier,
            "estimated_cost": self.estimated_cost,
            "actual_cost": self.actual_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result_records": self.result_records,
            "result_url": self.result_url,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "can_retry": self.can_retry,
            "aml_risk_level_counts": self.aml_risk_level_counts,
            "aml_inter_rater_agreement": self.aml_inter_rater_agreement,
            "aml_expert_review_count": self.aml_expert_review_count,
            "aml_audit_report_url": self.aml_audit_report_url,
        }


class JobListContract(BaseModel):
    """
    API Response: List of jobs with pagination.
    """
    jobs: List[JobStatusContract] = Field(..., description="List of jobs")
    total: int = Field(..., description="Total matching jobs")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="More results available")


class JobRetryContract(BaseModel):
    """
    API Response: Job retry result.
    """
    job_id: str
    status: str
    retry_count: int
    message: str


class JobCancelContract(BaseModel):
    """
    API Request: Job cancellation.
    """
    reason: Optional[str] = Field(
        default=None,
        description="Reason for cancellation"
    )


class JobStatsContract(BaseModel):
    """
    API Response: Job statistics for a tenant.
    """
    tenant_id: str
    total_jobs: int
    pending: int
    processing: int
    complete: int
    failed: int
    cancelled: int
    total_estimated_cost: str
    total_actual_cost: str


class AMLMetricsContract(BaseModel):
    """
    API Response: AML processing metrics and statistics.

    Provides comprehensive AML labeling metrics including risk distribution,
    typology breakdown, confidence scores, and expert review statistics.

    Attributes:
        total_transactions: Total number of transactions processed
        risk_distribution: Count of transactions by risk level (LOW, MEDIUM, HIGH, CRITICAL)
        typology_distribution: Count of transactions by FATF typology (ML, TF, PEP, etc.)
        average_confidence: Average AI model confidence score across all labels
        expert_review_count: Number of labels reviewed by human experts
        inter_rater_agreement: Cohen's Kappa coefficient (optional, None if insufficient reviews)
    """

    total_transactions: int = Field(
        ...,
        ge=0,
        description="Total number of transactions processed"
    )

    risk_distribution: Dict[str, int] = Field(
        ...,
        description="Distribution of transactions by risk level (LOW, MEDIUM, HIGH, CRITICAL)"
    )

    typology_distribution: Dict[str, int] = Field(
        ...,
        description="Distribution of transactions by FATF typology (ML, TF, PEP, etc.)"
    )

    average_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Average AI model confidence score (0.0 - 1.0)"
    )

    expert_review_count: int = Field(
        ...,
        ge=0,
        description="Number of labels reviewed by human experts"
    )

    inter_rater_agreement: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Cohen's Kappa coefficient for AI-expert agreement (None if < 2 reviews)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_transactions": 10000,
                "risk_distribution": {
                    "LOW": 8500,
                    "MEDIUM": 1200,
                    "HIGH": 250,
                    "CRITICAL": 50
                },
                "typology_distribution": {
                    "ML": 4500,
                    "TF": 1200,
                    "PEP": 800,
                    "FRAUD": 650,
                    "SANCTIONS": 350,
                    "OTHER": 2500
                },
                "average_confidence": 0.73,
                "expert_review_count": 300,
                "inter_rater_agreement": 0.72
            }
        }
    }

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert contract to dictionary for serialization.

        Returns:
            Dictionary representation of AML metrics
        """
        return {
            "total_transactions": self.total_transactions,
            "risk_distribution": self.risk_distribution,
            "typology_distribution": self.typology_distribution,
            "average_confidence": self.average_confidence,
            "expert_review_count": self.expert_review_count,
            "inter_rater_agreement": self.inter_rater_agreement,
        }

    @classmethod
    def from_orm(cls, obj: Any) -> "AMLMetricsContract":
        """
        Create contract from ORM object or dictionary.

        Args:
            obj: ORM object or dictionary containing AML metrics

        Returns:
            AMLMetricsContract instance
        """
        if isinstance(obj, dict):
            return cls(**obj)

        # Handle ORM object attributes
        return cls(
            total_transactions=getattr(obj, "total_transactions", 0),
            risk_distribution=getattr(obj, "risk_distribution", {}),
            typology_distribution=getattr(obj, "typology_distribution", {}),
            average_confidence=getattr(obj, "average_confidence", 0.0),
            expert_review_count=getattr(obj, "expert_review_count", 0),
            inter_rater_agreement=getattr(obj, "inter_rater_agreement", None),
        )


class AMLTransactionLabelContract(BaseModel):
    """
    API Response: Individual AML transaction label details.

    Represents a single AML transaction label with all relevant information
    including risk classification, typologies, confidence scores, and expert
    review status.

    Attributes:
        transaction_id: Unique transaction identifier
        risk_level: AML risk level (LOW, MEDIUM, HIGH, CRITICAL)
        typologies: List of FATF typologies assigned to this transaction
        confidence_score: AI model confidence score (0.0 - 1.0)
        reasoning: AI model reasoning/explanation for the classification
        regulatory_flags: List of regulatory compliance flags
        expert_review_status: Expert review workflow status
    """

    transaction_id: str = Field(
        ...,
        description="Unique transaction identifier"
    )

    risk_level: str = Field(
        ...,
        description="AML risk level (LOW, MEDIUM, HIGH, CRITICAL)"
    )

    typologies: List[str] = Field(
        ...,
        description="List of FATF typologies assigned to this transaction"
    )

    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI model confidence score (0.0 - 1.0)"
    )

    reasoning: str = Field(
        ...,
        description="AI model reasoning/explanation for the classification"
    )

    regulatory_flags: List[str] = Field(
        default_factory=list,
        description="List of regulatory compliance flags"
    )

    expert_review_status: str = Field(
        default=AMLExpertReviewStatus.PENDING.value,
        description="Expert review workflow status"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "txn_abc123xyz",
                "risk_level": "HIGH",
                "typologies": ["ML", "LAYERING"],
                "confidence_score": 0.78,
                "reasoning": "Transaction exhibits layering behavior with multiple rapid transfers between accounts in high-risk jurisdictions.",
                "regulatory_flags": ["HIGH_RISK_JURISDICTION", "LAYERING", "RAPID_MOVEMENT"],
                "expert_review_status": "PENDING"
            }
        }
    }

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert contract to dictionary for serialization.

        Returns:
            Dictionary representation of the AML transaction label
        """
        return {
            "transaction_id": self.transaction_id,
            "risk_level": self.risk_level,
            "typologies": self.typologies,
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "regulatory_flags": self.regulatory_flags,
            "expert_review_status": self.expert_review_status,
        }

    @classmethod
    def from_orm(cls, obj: Any) -> "AMLTransactionLabelContract":
        """
        Create contract from ORM object or dictionary.

        Handles conversion from AMLTransactionLabel ORM model to API contract.

        Args:
            obj: AMLTransactionLabel ORM model or dictionary

        Returns:
            AMLTransactionLabelContract instance
        """
        if isinstance(obj, dict):
            return cls(**obj)

        # Handle AMLTransactionLabel ORM model
        # Extract typologies from single typology field or convert if needed
        typologies = [obj.typology] if hasattr(obj, "typology") and obj.typology else []

        # Handle regulatory_flags if it's a dict
        regulatory_flags = []
        if hasattr(obj, "regulatory_flags"):
            if isinstance(obj.regulatory_flags, dict):
                regulatory_flags = list(obj.regulatory_flags.keys())
            elif isinstance(obj.regulatory_flags, list):
                regulatory_flags = obj.regulatory_flags

        # Extract risk level value if it's an enum
        risk_level = obj.risk_level.value if isinstance(obj.risk_level, AMLRiskLevel) else str(obj.risk_level)

        # Extract expert review status value if it's an enum
        expert_status = obj.expert_review_status.value if isinstance(obj.expert_review_status, AMLExpertReviewStatus) else str(obj.expert_review_status)

        return cls(
            transaction_id=obj.transaction_id,
            risk_level=risk_level,
            typologies=typologies,
            confidence_score=float(obj.confidence_score) if hasattr(obj, "confidence_score") else 0.0,
            reasoning=obj.ai_reasoning if hasattr(obj, "ai_reasoning") else "",
            regulatory_flags=regulatory_flags,
            expert_review_status=expert_status,
        )
