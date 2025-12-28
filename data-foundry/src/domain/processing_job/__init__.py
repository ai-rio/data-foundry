"""
Processing Job Domain Module

Contains the ProcessingJob aggregate root, state machine,
repository interface, and related value objects.

Domain-Driven Design:
- ProcessingJob is an Aggregate Root
- State transitions are encapsulated in the aggregate
- Repository pattern for persistence abstraction
"""

from .aggregate import ProcessingJob, JobStatus
from .repository import IJobRepository
from .exceptions import (
    JobError,
    InvalidStateTransition,
    JobNotFoundError,
    JobConcurrencyError,
)
from .value_objects import JobCost, JobMetrics

__all__ = [
    "ProcessingJob",
    "JobStatus",
    "IJobRepository",
    "JobError",
    "InvalidStateTransition",
    "JobNotFoundError",
    "JobConcurrencyError",
    "JobCost",
    "JobMetrics",
]
