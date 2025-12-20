"""
Processed data model for auto-approved data

This module defines the ProcessedData model which stores data that has been
automatically processed and approved by the AI system without requiring
human review. This represents the final, production-ready data.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class ProcessedData(SQLModel, table=True):
    """Processed data model for storing auto-approved data.

    This model stores the final output of the data processing pipeline for
    records that meet the confidence threshold for automatic approval.
    It includes enriched data, quality metrics, and full audit trails.
    """

    __tablename__ = "processed_data"

    # Primary identification
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(
        index=True,
        unique=True,
        description="Original record ID from data_records"
    )
    tenant_id: str = Field(
        index=True,
        description="Associated tenant ID for data isolation"
    )

    # Processing decision
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        index=True,
        description="Final confidence score for auto-approval"
    )
    auto_approved: bool = Field(
        index=True,
        description="Whether data was auto-approved"
    )
    approval_threshold: float = Field(
        ge=0.0, le=1.0,
        description="Threshold used for approval"
    )

    # AI processing results
    ai_category: Optional[str] = Field(
        index=True,
        description="Final AI categorization"
    )
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="AI confidence level for categorization"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning for decisions")
    ai_model: Optional[str] = Field(index=True, description="AI model used")
    ai_model_version: Optional[str] = Field(description="Version of AI model")
    processing_pipeline: Optional[str] = Field(description="Processing pipeline used")

    # Data quality metrics
    data_quality_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        index=True,
        description="Overall data quality score"
    )
    completeness_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Data completeness score"
    )
    accuracy_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Data accuracy score"
    )
    consistency_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Data consistency score"
    )

    # Processed content
    cleaned_data: str = Field(description="Cleaned and normalized data as JSON string")
    normalized_data: Optional[str] = Field(description="Normalized data as JSON string")
    enriched_data: Optional[str] = Field(description="Enriched data with additional context")
    extracted_entities: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Extracted entities and their metadata"
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Structured representation of the data"
    )

    # Classification and taxonomy
    tags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Auto-generated tags"
    )
    categories: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Assigned categories"
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Extracted keywords"
    )
    taxonomy_classification: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Full taxonomy classification"
    )

    # Processing metadata
    pipeline_version: Optional[str] = Field(index=True, description="Pipeline version")
    processing_time_ms: Optional[int] = Field(description="Processing time in milliseconds")
    processing_steps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Processing steps completed with metrics"
    )
    transformation_rules: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Transformation rules applied"
    )
    validation_results: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Validation results and checks"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        index=True
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    processed_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        index=True
    )
    last_validated: Optional[datetime] = Field(description="Last validation timestamp")

    # Audit trail
    processed_by: Optional[str] = Field(description="Processed by (system/user)")
    processing_job_id: Optional[str] = Field(description="Batch processing job ID")
    review_by: Optional[str] = Field(description="Reviewed by (if applicable)")
    review_at: Optional[datetime] = Field(description="Review timestamp")
    review_notes: Optional[str] = Field(description="Review notes")
    quality_flags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Quality flags raised during processing"
    )

    # Usage and access tracking
    access_count: int = Field(default=0, description="Number of times accessed")
    last_accessed: Optional[datetime] = Field(description="Last access timestamp")
    export_count: int = Field(default=0, description="Number of times exported")
    integration_used: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Integrations that have used this data"
    )

    # Retention and lifecycle
    expires_at: Optional[datetime] = Field(index=True, description="Data expiration timestamp")
    archive_after: Optional[datetime] = Field(description="When to archive this record")
    deletion_scheduled: Optional[datetime] = Field(description="Scheduled deletion timestamp")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    # Table indexes for optimal performance
    __table_args__ = (
        Index('idx_processed_data_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_processed_data_tenant_processed', 'tenant_id', 'processed_at'),
        Index('idx_processed_data_confidence', 'confidence_score'),
        Index('idx_processed_data_quality', 'data_quality_score'),
        Index('idx_processed_data_category', 'ai_category'),
        Index('idx_processed_data_pipeline', 'pipeline_version'),
        Index('idx_processed_data_auto_approved', 'auto_approved'),
        Index('idx_processed_data_expires', 'expires_at'),
    )

    @property
    def is_high_quality(self) -> bool:
        """Check if data meets high quality standards."""
        return (
            self.data_quality_score is not None and
            self.data_quality_score >= 0.85 and
            self.completeness_score is not None and
            self.completeness_score >= 0.90
        )

    @property
    def processing_duration(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if self.processing_time_ms:
            return self.processing_time_ms / 1000.0
        return None

    @property
    def days_since_processed(self) -> int:
        """Calculate days since processing."""
        return (datetime.utcnow() - self.processed_at).days

    @property
    def is_expired(self) -> bool:
        """Check if data has expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False