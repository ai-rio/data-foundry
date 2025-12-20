"""
Processed data model for auto-approved data
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class ProcessedData(SQLModel, table=True):
    """Processed data model for storing auto-approved data."""

    __tablename__ = "processed_data"

    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(index=True, description="Original record ID")
    tenant_id: str = Field(index=True, description="Associated tenant ID")

    # Processing info
    confidence_score: float = Field(ge=0.0, le=1.0, description="Final confidence score")
    auto_approved: bool = Field(description="Whether data was auto-approved")
    review_required: bool = Field(default=False, description="Whether human review is required")

    # AI labeling
    ai_category: Optional[str] = Field(description="AI categorization")
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0, description="AI confidence level"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning")
    ai_model: Optional[str] = Field(description="AI model used")

    # Data quality
    data_quality_score: Optional[float] = Field(
        ge=0.0, le=1.0, description="Data quality score"
    )
    completeness_score: Optional[float] = Field(
        ge=0.0, le=1.0, description="Data completeness score"
    )
    accuracy_score: Optional[float] = Field(
        ge=0.0, le=1.0, description="Data accuracy score"
    )

    # Processed content
    cleaned_data: str = Field(description="Cleaned and enriched data as JSON string")
    normalized_data: Optional[str] = Field(description="Normalized data as JSON string")
    enriched_data: Optional[str] = Field(description="Enriched data as JSON string")

    # Tags and metadata
    tags: Optional[str] = Field(sa_type=JSON, default="[]", description="Data tags (JSON)")
    categories: Optional[str] = Field(sa_type=JSON, default="[]", description="Categories (JSON)")
    keywords: Optional[str] = Field(sa_type=JSON, default="[]", description="Keywords (JSON)")

    # Processing pipeline info
    pipeline_version: Optional[str] = Field(description="Pipeline version")
    processing_time_ms: Optional[int] = Field(description="Processing time in milliseconds")
    processing_steps: Optional[str] = Field(sa_type=JSON, default="[]", description="Processing steps completed (JSON)")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    processed_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # Audit trail
    processed_by: Optional[str] = Field(description="Processed by (system/user)")
    review_by: Optional[str] = Field(description="Reviewed by (if applicable)")
    review_at: Optional[datetime] = Field(description="Review timestamp")
    review_notes: Optional[str] = Field(description="Review notes")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True