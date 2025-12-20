"""
Human review queue model for low-confidence data
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import JSON
from sqlmodel import Field, SQLModel


class ReviewPriority(str, Enum):
    """Review priority enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ReviewStatus(str, Enum):
    """Review status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class HumanReviewQueue(SQLModel, table=True):
    """Human review queue model for storing data requiring human review."""

    __tablename__ = "human_review_queue"

    id: Optional[int] = Field(default=None, primary_key=True)
    review_id: str = Field(index=True, unique=True, description="Unique review identifier")
    record_id: str = Field(index=True, description="Original record ID")
    tenant_id: str = Field(index=True, description="Associated tenant ID")

    # Review info
    status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Review status")
    priority: ReviewPriority = Field(default=ReviewPriority.MEDIUM, description="Review priority")
    assigned_to: Optional[str] = Field(description="Assigned reviewer user ID")
    assigned_at: Optional[datetime] = Field(description="Assignment timestamp")

    # AI information
    ai_category: Optional[str] = Field(description="AI categorization")
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0, description="AI confidence level"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning")
    ai_suggestions: Optional[str] = Field(description="AI suggestions")

    # Review data
    original_data: str = Field(description="Original data as JSON string")
    ai_processed_data: Optional[str] = Field(description="AI processed data as JSON string")
    review_data: Optional[str] = Field(description="Review data as JSON string")

    # Review results
    reviewer_category: Optional[str] = Field(description="Reviewer category")
    reviewer_confidence: Optional[float] = Field(
        ge=0.0, le=1.0, description="Reviewer confidence"
    )
    reviewer_notes: Optional[str] = Field(description="Reviewer notes")
    reviewer_action: Optional[str] = Field(description="Action taken by reviewer")

    # Labels and tags
    final_labels: Optional[str] = Field(sa_type=JSON, description="Final labels (JSON)")
    final_tags: Optional[str] = Field(sa_type=JSON, description="Final tags (JSON)")
    final_categories: Optional[str] = Field(sa_type=JSON, description="Final categories (JSON)")

    # Time tracking
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    submitted_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    started_at: Optional[datetime] = Field(description="Review start timestamp")
    completed_at: Optional[datetime] = Field(description="Review completion timestamp")

    # Time metrics
    queue_time_minutes: Optional[int] = Field(description="Time in queue (minutes)")
    review_time_minutes: Optional[int] = Field(description="Time spent reviewing (minutes)")

    # Integration with external systems
    label_studio_task_id: Optional[int] = Field(description="Label Studio task ID")
    label_studio_url: Optional[str] = Field(description="Label Studio task URL")

    # Quality metrics
    reviewer_experience: Optional[int] = Field(
        ge=1, le=5, description="Reviewer experience rating"
    )
    data_quality_rating: Optional[int] = Field(
        ge=1, le=5, description="Data quality rating"
    )
    review_difficulty: Optional[int] = Field(
        ge=1, le=5, description="Review difficulty rating"
    )

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    @property
    def is_active(self) -> bool:
        """Check if review is active (not completed)."""
        return self.status in [ReviewStatus.PENDING, ReviewStatus.IN_PROGRESS]

    @property
    def is_completed(self) -> bool:
        """Check if review is completed."""
        return self.status in [ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.SKIPPED]

    @property
    def pending_time_minutes(self) -> Optional[int]:
        """Calculate pending time in minutes."""
        if self.started_at:
            return int((self.started_at - self.created_at).total_seconds() / 60)
        return None