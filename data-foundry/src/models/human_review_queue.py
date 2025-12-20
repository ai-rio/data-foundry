"""
Human review queue model for low-confidence data

This module defines the HumanReviewQueue model which manages records that
require human review due to low AI confidence, ambiguity, or policy
requirements. It tracks the entire review workflow and integrates with
external annotation tools.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class ReviewPriority(str, Enum):
    """Review priority enumeration.

    LOW: Non-urgent review, can be handled when convenient
    MEDIUM: Standard priority review queue
    HIGH: Urgent review, should be handled promptly
    URGENT: Critical review, requires immediate attention
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ReviewStatus(str, Enum):
    """Review status enumeration.

    PENDING: Awaiting assignment to reviewer
    IN_PROGRESS: Currently being reviewed
    REVIEWED: Review completed, awaiting final decision
    APPROVED: Data approved and finalized
    REJECTED: Data rejected or requires rework
    SKIPPED: Review skipped (e.g., due to policy)
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ReviewType(str, Enum):
    """Review type enumeration."""

    CATEGORY_REVIEW = "category_review"
    QUALITY_CHECK = "quality_check"
    PII_VERIFICATION = "pii_verification"
    COMPLIANCE_CHECK = "compliance_check"
    CONTENT_MODERATION = "content_moderation"
    DISPUTE_RESOLUTION = "dispute_resolution"


class HumanReviewQueue(SQLModel, table=True):
    """Human review queue model for storing data requiring human review.

    This model manages the workflow for records that cannot be automatically
    processed due to low confidence, ambiguity, or requiring domain expertise.
    It supports assignment, escalation, and integration with external tools.
    """

    __tablename__ = "human_review_queue"

    # Primary identification
    id: Optional[int] = Field(default=None, primary_key=True)
    review_id: str = Field(
        index=True,
        unique=True,
        description="Unique review identifier (UUID)"
    )
    record_id: str = Field(
        index=True,
        description="Original record ID from data_records"
    )
    tenant_id: str = Field(
        index=True,
        description="Associated tenant ID for data isolation"
    )

    # Review metadata
    review_type: ReviewType = Field(
        index=True,
        description="Type of review required"
    )
    status: ReviewStatus = Field(
        index=True,
        default=ReviewStatus.PENDING,
        description="Review status"
    )
    priority: ReviewPriority = Field(
        index=True,
        default=ReviewPriority.MEDIUM,
        description="Review priority"
    )
    batch_id: Optional[str] = Field(
        index=True,
        description="Batch ID for group reviews"
    )

    # Assignment information
    assigned_to: Optional[str] = Field(index=True, description="Assigned reviewer user ID")
    assigned_by: Optional[str] = Field(description="Who assigned the review")
    assigned_at: Optional[datetime] = Field(description="Assignment timestamp")
    due_date: Optional[datetime] = Field(index=True, description="Review due date")
    escalation_level: int = Field(default=0, description="Escalation level")
    escalated_to: Optional[str] = Field(description="Escalated to reviewer ID")

    # AI processing information
    ai_category: Optional[str] = Field(description="AI categorization")
    ai_confidence: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="AI confidence level"
    )
    ai_reasoning: Optional[str] = Field(description="AI reasoning for decisions")
    ai_suggestions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="AI suggestions and alternatives"
    )
    conflicting_suggestions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Conflicting AI suggestions"
    )

    # Review data
    original_data: str = Field(description="Original data as JSON string")
    ai_processed_data: Optional[str] = Field(description="AI processed data as JSON string")
    review_data: Optional[str] = Field(description="Review data as JSON string")
    reference_materials: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Reference materials for review"
    )
    review_instructions: Optional[str] = Field(description="Specific review instructions")

    # Review results
    reviewer_category: Optional[str] = Field(
        index=True,
        description="Final category from reviewer"
    )
    reviewer_confidence: Optional[float] = Field(
        ge=0.0, le=1.0,
        description="Reviewer confidence in decision"
    )
    reviewer_notes: Optional[str] = Field(description="Detailed reviewer notes")
    reviewer_action: Optional[str] = Field(description="Action taken by reviewer")
    rejection_reason: Optional[str] = Field(description="Reason for rejection")

    # Labels and classifications
    final_labels: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Final approved labels"
    )
    final_tags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Final approved tags"
    )
    final_categories: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Final approved categories"
    )
    corrected_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Corrections made during review"
    )

    # Quality and difficulty assessments
    data_complexity: Optional[int] = Field(
        ge=1, le=5,
        description="Data complexity rating (1=simple, 5=complex)"
    )
    ambiguity_level: Optional[int] = Field(
        ge=1, le=5,
        description="Ambiguity level in data"
    )
    domain_expertise_required: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Required domain expertise areas"
    )

    # Time tracking
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        index=True
    )
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    submitted_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        description="When submitted to queue"
    )
    started_at: Optional[datetime] = Field(description="Review start timestamp")
    paused_at: Optional[datetime] = Field(description="When review was paused")
    resumed_at: Optional[datetime] = Field(description="When review was resumed")
    completed_at: Optional[datetime] = Field(index=True, description="Review completion timestamp")

    # Time metrics
    queue_time_minutes: Optional[int] = Field(description="Time in queue before assignment")
    review_time_minutes: Optional[int] = Field(description="Total time spent reviewing")
    active_review_time_minutes: Optional[int] = Field(description="Active review time (excluding pauses)")
    first_response_time_minutes: Optional[int] = Field(description="Time to first response")
    resolution_time_hours: Optional[float] = Field(description="Total resolution time in hours")

    # Integration with external systems
    label_studio_task_id: Optional[int] = Field(description="Label Studio task ID")
    label_studio_url: Optional[str] = Field(description="Label Studio task URL")
    external_review_ids: Optional[Dict[str, str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="IDs from external review systems"
    )
    webhook_url: Optional[str] = Field(description="Webhook URL for notifications")

    # Reviewer metrics
    reviewer_experience: Optional[int] = Field(
        ge=1, le=5,
        description="Self-assessed reviewer experience"
    )
    data_quality_rating: Optional[int] = Field(
        ge=1, le=5,
        description="Data quality rating by reviewer"
    )
    review_difficulty: Optional[int] = Field(
        ge=1, le=5,
        description="Perceived difficulty of review"
    )
    satisfaction_score: Optional[int] = Field(
        ge=1, le=5,
        description="Reviewer satisfaction with tools/process"
    )

    # Review verification
    verified_by: Optional[str] = Field(description="Secondary reviewer for verification")
    verified_at: Optional[datetime] = Field(description="Verification timestamp")
    verification_notes: Optional[str] = Field(description="Verification notes")
    disagreements: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Points of disagreement with AI"
    )

    # Feedback loop for AI improvement
    ai_feedback_provided: bool = Field(default=False, description="Feedback provided for AI training")
    feedback_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Structured feedback for AI improvement"
    )
    model_correction_applied: bool = Field(default=False, description="Used for model correction")

    # Compliance and legal
    legal_review_required: bool = Field(default=False, description="Legal review required")
    compliance_flags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Compliance concerns raised"
    )
    gdpr_impact: Optional[str] = Field(description="GDPR impact assessment")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    # Table indexes for optimal performance
    __table_args__ = (
        Index('idx_human_review_tenant_status', 'tenant_id', 'status'),
        Index('idx_human_review_priority_status', 'priority', 'status'),
        Index('idx_human_review_assigned', 'assigned_to', 'status'),
        Index('idx_human_review_created', 'created_at'),
        Index('idx_human_review_due', 'due_date', 'status'),
        Index('idx_human_review_type', 'review_type'),
        Index('idx_human_review_batch', 'batch_id'),
        Index('idx_human_review_escalation', 'escalation_level'),
        Index('idx_human_review_completed', 'completed_at'),
    )

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