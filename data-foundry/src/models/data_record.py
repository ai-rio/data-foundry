"""
Data record model for raw data ingestion
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON
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
    """Data record model for storing raw data."""

    __tablename__ = "data_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(index=True, unique=True, description="Unique record identifier")
    tenant_id: str = Field(index=True, description="Associated tenant ID")

    # Data metadata
    data_source: DataSource = Field(description="Source of the data")
    status: DataStatus = Field(default=DataStatus.RAW, description="Processing status")
    file_name: Optional[str] = Field(description="Original file name")
    file_size: Optional[int] = Field(description="File size in bytes")
    record_hash: Optional[str] = Field(description="Hash of the record for deduplication")

    # Processing info
    confidence_score: Optional[float] = Field(
        ge=0.0, le=1.0, description="AI confidence score"
    )
    ai_category: Optional[str] = Field(description="AI categorization")
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0, description="AI confidence level"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning")

    # PII information
    pii_detected: bool = Field(default=False, description="PII detected in record")
    pii_redacted: bool = Field(default=False, description="PII was redacted")
    pii_types: Optional[str] = Field(sa_type=JSON, description="Types of PII found (JSON)")

    # Data content
    raw_data: str = Field(description="Raw data as JSON string")
    processed_data: Optional[str] = Field(description="Processed data as JSON string")
    data_preview: Optional[str] = Field(description="Preview of data")

    # Error handling
    error_message: Optional[str] = Field(description="Error message if processing failed")
    retry_count: int = Field(default=0, description="Number of retry attempts")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    processed_at: Optional[datetime] = Field(description="Processing timestamp")

    # Metadata
    import_batch_id: Optional[str] = Field(description="Batch import ID")
    parent_record_id: Optional[str] = Field(description="Parent record ID (for relationships)")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    @property
    def is_ready_for_processing(self) -> bool:
        """Check if record is ready for processing."""
        return self.status == DataStatus.RAW

    @property
    def has_high_confidence(self) -> bool:
        """Check if record has high confidence score."""
        return self.ai_confidence and self.ai_confidence >= 0.85