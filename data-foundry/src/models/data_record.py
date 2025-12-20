"""
Data record model for raw data ingestion

This module defines the DataRecord model which is the core entity for storing
raw data ingested into the platform. It supports multiple data sources,
AI processing metadata, PII detection, and comprehensive audit trails.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class DataSource(str, Enum):
    """Data source enumeration."""
    CSV = "csv"
    JSON = "json"
    EXCEL = "excel"
    PARQUET = "parquet"
    API = "api"
    MANUAL = "manual"


class DataStatus(str, Enum):
    """Data status enumeration."""
    RAW = "raw"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    ARCHIVED = "archived"


class DataRecord(SQLModel, table=True):
    """Data record model for storing raw data with AI processing metadata.

    This is the core entity for storing ingested data. It tracks the entire
    lifecycle from raw ingestion through AI processing, PII detection,
    and human review. All data is isolated by tenant_id.
    """

    __tablename__ = "data_records"

    # Primary identification
    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(
        index=True,
        unique=True,
        description="Unique record identifier (UUID)"
    )
    tenant_id: str = Field(
        index=True,
        description="Associated tenant ID for data isolation"
    )

    # Data metadata
    data_source: DataSource = Field(
        index=True,
        description="Source of the data (csv, json, api, etc.)"
    )
    status: DataStatus = Field(
        index=True,
        default=DataStatus.RAW,
        description="Processing status of the record"
    )
    file_name: Optional[str] = Field(description="Original file name")
    file_size: Optional[int] = Field(description="File size in bytes")
    record_hash: Optional[str] = Field(
        index=True,
        description="Hash of the record for deduplication"
    )
    mime_type: Optional[str] = Field(description="MIME type of the data")

    # Processing info and AI results
    confidence_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="AI confidence score for categorization"
    )
    ai_category: Optional[str] = Field(
        index=True,
        description="AI-generated category"
    )
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="AI confidence level for processing"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning for decisions")
    ai_tags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="AI-generated tags"
    )

    # PII information and privacy
    pii_detected: bool = Field(
        default=False,
        index=True,
        description="PII detected in record"
    )
    pii_redacted: bool = Field(default=False, description="PII was redacted")
    pii_types: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Types of PII found"
    )
    pii_confidence: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Confidence score for PII detection"
    )
    data_sensitivity: Optional[str] = Field(
        index=True,
        description="Data sensitivity level"
    )

    # Data content
    raw_data: str = Field(description="Raw data as JSON string")
    processed_data: Optional[str] = Field(description="Processed data as JSON string")
    data_preview: Optional[str] = Field(description="Preview of data")
    extracted_text: Optional[str] = Field(description="Extracted text content")

    # Quality metrics
    data_quality_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Overall data quality score"
    )
    completeness_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Data completeness score"
    )
    validity_score: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Data validity score"
    )

    # Error handling and retries
    error_message: Optional[str] = Field(description="Error message if processing failed")
    error_code: Optional[str] = Field(description="Error code for classification")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    last_error_at: Optional[datetime] = Field(description="Timestamp of last error")

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        index=True
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False
    )
    processed_at: Optional[datetime] = Field(index=True, description="Processing timestamp")
    expires_at: Optional[datetime] = Field(index=True, description="Data expiration timestamp")

    # Metadata and relationships
    import_batch_id: Optional[str] = Field(
        index=True,
        description="Batch import ID for grouping"
    )
    parent_record_id: Optional[str] = Field(
        index=True,
        description="Parent record ID (for relationships)"
    )
    child_record_ids: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="IDs of child records"
    )
    source_system: Optional[str] = Field(description="Originating system")
    external_id: Optional[str] = Field(description="ID in external system")

    # AI Processing Metadata (enhanced)
    ai_model: Optional[str] = Field(
        index=True,
        description="AI model used for processing"
    )
    ai_request_id: Optional[str] = Field(
        index=True,
        description="AI request identifier"
    )
    ai_tokens_used: Optional[int] = Field(description="Total AI tokens used")
    ai_cost: Optional[str] = Field(description="AI processing cost as string")
    ai_processing_time_ms: Optional[float] = Field(description="AI processing time in milliseconds")
    ai_model_version: Optional[str] = Field(description="Version of AI model used")

    # Provenance and audit trail
    provenance_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Provenance metadata including source chain"
    )
    processing_history: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Processing history with timestamps"
    )
    accessed_by: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="List of users who accessed this record"
    )
    access_count: int = Field(default=0, description="Number of times accessed")

    # Review and approval
    requires_review: bool = Field(default=False, index=True, description="Requires human review")
    reviewed_by: Optional[str] = Field(description="User who reviewed the record")
    reviewed_at: Optional[datetime] = Field(description="Review timestamp")
    review_status: Optional[str] = Field(description="Review status")
    review_notes: Optional[str] = Field(description="Review notes")

    # Classification and taxonomy
    taxonomy_path: Optional[str] = Field(description="Taxonomy classification path")
    domain: Optional[str] = Field(index=True, description="Domain classification")
    subdomain: Optional[str] = Field(description="Subdomain classification")
    industry: Optional[str] = Field(index=True, description="Industry classification")

    # Compliance and legal
    gdpr_relevant: bool = Field(default=False, description="Subject to GDPR")
    retention_period_days: Optional[int] = Field(description="Retention period in days")
    legal_hold: bool = Field(default=False, description="Legal hold status")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    # Table indexes for optimal performance
    __table_args__ = (
        Index('idx_data_records_tenant_status', 'tenant_id', 'status'),
        Index('idx_data_records_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_data_records_tenant_source', 'tenant_id', 'data_source'),
        Index('idx_data_records_status_created', 'status', 'created_at'),
        Index('idx_data_records_ai_category', 'ai_category'),
        Index('idx_data_records_pii_detected', 'pii_detected'),
        Index('idx_data_records_requires_review', 'requires_review'),
        Index('idx_data_records_batch_id', 'import_batch_id'),
        Index('idx_data_records_parent_record', 'parent_record_id'),
        Index('idx_data_records_ai_model', 'ai_model'),
        Index('idx_data_records_ai_request', 'ai_request_id'),
        Index('idx_data_records_hash', 'record_hash'),
        Index('idx_data_records_expires', 'expires_at'),
    )

    @property
    def is_ready_for_processing(self) -> bool:
        """Check if record is ready for processing."""
        return self.status == DataStatus.RAW

    @property
    def has_high_confidence(self) -> bool:
        """Check if record has high confidence score."""
        return self.ai_confidence and self.ai_confidence >= 0.85