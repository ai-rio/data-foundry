"""
Processing Job Aggregate Root

The ProcessingJob is an Aggregate Root in DDD terms.
It encapsulates all state and behavior related to job processing.

Key Responsibilities:
1. State management with validated transitions
2. Cost tracking (estimated and actual)
3. Timing metrics
4. Error handling

SOLID Principles:
- Single Responsibility: Manages job lifecycle state
- Encapsulation: Internal state only modified through methods
- Information Hiding: State transition rules are internal
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any, Dict
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .exceptions import InvalidStateTransition
from .value_objects import JobCost


class JobStatus(str, Enum):
    """
    Job status states following a state machine pattern.

    Valid transitions:
    - PENDING -> PROCESSING, FAILED, CANCELLED
    - PROCESSING -> COMPLETE, FAILED, CANCELLED
    - COMPLETE -> (terminal)
    - FAILED -> PENDING (retry)
    - CANCELLED -> (terminal)
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in {JobStatus.COMPLETE, JobStatus.CANCELLED}

    @property
    def allowed_transitions(self) -> list["JobStatus"]:
        """Get list of states this status can transition to."""
        transitions = {
            JobStatus.PENDING: [JobStatus.PROCESSING, JobStatus.FAILED, JobStatus.CANCELLED],
            JobStatus.PROCESSING: [JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED],
            JobStatus.COMPLETE: [],  # Terminal
            JobStatus.FAILED: [JobStatus.PENDING],  # Can retry
            JobStatus.CANCELLED: [],  # Terminal
        }
        return transitions[self]


class ProcessingJob(BaseModel):
    """
    Aggregate Root: Processing Job

    Encapsulates all state and transitions for a file processing job.
    All modifications go through domain methods that enforce business rules.

    This is NOT a database model - it's a domain object. Persistence
    is handled by the repository, which maps to/from database models.
    """

    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    version: int = Field(default=1)  # Optimistic locking

    # File information
    file_name: str
    file_size: int = Field(ge=0)
    file_key: Optional[str] = None  # Storage key after upload
    complexity_tier: str = "simple"

    # Status and state
    status: JobStatus = JobStatus.PENDING
    error_message: Optional[str] = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Cost tracking
    estimated_cost: Decimal = Field(default=Decimal("0.00"))
    actual_cost: Optional[Decimal] = None

    # Results
    result_records: Optional[int] = None
    result_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Configuration for mutation
    model_config = {"validate_assignment": True}

    @field_validator("complexity_tier")
    @classmethod
    def validate_complexity_tier(cls, v: str) -> str:
        """Validate complexity tier is valid."""
        allowed = {"simple", "moderate", "complex"}
        if v.lower() not in allowed:
            raise ValueError(f"complexity_tier must be one of {allowed}")
        return v.lower()

    # -----------------------------------------------------------------
    # State Transition Methods (Encapsulate business rules)
    # -----------------------------------------------------------------

    def transition_to_processing(self) -> None:
        """
        Transition PENDING -> PROCESSING.

        Sets started_at timestamp and updates status.
        Raises InvalidStateTransition if current state doesn't allow this.
        """
        self._validate_transition(JobStatus.PROCESSING)
        self.status = JobStatus.PROCESSING
        self.started_at = datetime.utcnow()
        self._touch()

    def transition_to_complete(
        self,
        result_records: int,
        result_url: Optional[str] = None,
        actual_cost: Optional[Decimal] = None,
    ) -> None:
        """
        Transition PROCESSING -> COMPLETE.

        Records completion metrics and sets completed_at timestamp.
        """
        self._validate_transition(JobStatus.COMPLETE)
        self.status = JobStatus.COMPLETE
        self.completed_at = datetime.utcnow()
        self.result_records = result_records
        if result_url:
            self.result_url = result_url
        if actual_cost is not None:
            self.actual_cost = actual_cost
        self._touch()

    def transition_to_failed(
        self,
        error_message: str,
        increment_retry: bool = True,
    ) -> None:
        """
        Transition PENDING/PROCESSING -> FAILED.

        Records error information and optionally increments retry count.
        """
        self._validate_transition(JobStatus.FAILED)
        self.status = JobStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.utcnow()
        if increment_retry:
            self.retry_count += 1
        self._touch()

    def transition_to_cancelled(self, reason: Optional[str] = None) -> None:
        """
        Transition PENDING/PROCESSING -> CANCELLED.

        Records cancellation reason in metadata.
        """
        self._validate_transition(JobStatus.CANCELLED)
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()
        if reason:
            self.metadata["cancellation_reason"] = reason
        self._touch()

    def retry(self) -> None:
        """
        Transition FAILED -> PENDING for retry.

        Only allowed if retry_count < max_retries.
        """
        if self.retry_count >= self.max_retries:
            raise InvalidStateTransition(
                job_id=self.id,
                current_state=self.status.value,
                attempted_state=JobStatus.PENDING.value,
                allowed_transitions=["none - max retries exceeded"],
            )

        self._validate_transition(JobStatus.PENDING)
        self.status = JobStatus.PENDING
        self.error_message = None
        self.started_at = None
        self.completed_at = None
        self._touch()

    # -----------------------------------------------------------------
    # Query Methods (Read-only operations)
    # -----------------------------------------------------------------

    @property
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return (
            self.status == JobStatus.FAILED
            and self.retry_count < self.max_retries
        )

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status.is_terminal

    @property
    def is_processing(self) -> bool:
        """Check if job is currently processing."""
        return self.status == JobStatus.PROCESSING

    @property
    def processing_duration_seconds(self) -> Optional[float]:
        """Get processing duration in seconds."""
        if self.started_at is None:
            return None

        end_time = self.completed_at or datetime.utcnow()
        delta = end_time - self.started_at
        return delta.total_seconds()

    @property
    def queue_duration_seconds(self) -> Optional[float]:
        """Get time spent in queue (pending state)."""
        if self.started_at is None:
            return None

        delta = self.started_at - self.created_at
        return delta.total_seconds()

    @property
    def cost_estimate(self) -> JobCost:
        """Get cost information as value object."""
        return JobCost(
            estimated_total=self.estimated_cost,
            actual_total=self.actual_cost,
        )

    def get_allowed_transitions(self) -> list[str]:
        """Get list of allowed status transitions."""
        return [s.value for s in self.status.allowed_transitions]

    # -----------------------------------------------------------------
    # Internal Methods
    # -----------------------------------------------------------------

    def _validate_transition(self, target: JobStatus) -> None:
        """
        Validate state transition is allowed.

        Raises InvalidStateTransition if not allowed.
        """
        if target not in self.status.allowed_transitions:
            raise InvalidStateTransition(
                job_id=self.id,
                current_state=self.status.value,
                attempted_state=target.value,
                allowed_transitions=[s.value for s in self.status.allowed_transitions],
            )

    def _touch(self) -> None:
        """Update timestamp and increment version for optimistic locking."""
        self.updated_at = datetime.utcnow()
        self.version += 1

    # -----------------------------------------------------------------
    # Factory Methods
    # -----------------------------------------------------------------

    @classmethod
    def create(
        cls,
        tenant_id: str,
        file_name: str,
        file_size: int,
        complexity_tier: str = "simple",
        estimated_cost: Optional[Decimal] = None,
    ) -> "ProcessingJob":
        """
        Factory method to create a new job.

        Calculates estimated cost if not provided.
        """
        if estimated_cost is None:
            cost_obj = JobCost.estimate(complexity_tier, file_size)
            estimated_cost = cost_obj.estimated_total

        return cls(
            tenant_id=tenant_id,
            file_name=file_name,
            file_size=file_size,
            complexity_tier=complexity_tier,
            estimated_cost=estimated_cost,
        )
