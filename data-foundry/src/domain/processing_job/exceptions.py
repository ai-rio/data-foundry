"""
Processing Job Domain Exceptions

Custom exceptions for job-related operations.
Each exception has a single, clear purpose (Single Responsibility).
"""

from typing import Optional


class JobError(Exception):
    """
    Base exception for job-related errors.
    """

    def __init__(
        self,
        message: str,
        job_id: Optional[str] = None,
        code: str = "JOB_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.job_id = job_id
        self.code = code

    def to_dict(self) -> dict:
        """Convert exception to API-friendly dictionary."""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.job_id:
            result["job_id"] = self.job_id
        return result


class InvalidStateTransition(JobError):
    """
    Raised when an invalid state transition is attempted.

    The state machine enforces valid transitions. This exception
    is raised when trying to transition to an invalid state.
    """

    def __init__(
        self,
        job_id: str,
        current_state: str,
        attempted_state: str,
        allowed_transitions: list[str],
    ):
        self.current_state = current_state
        self.attempted_state = attempted_state
        self.allowed_transitions = allowed_transitions

        message = (
            f"Invalid state transition for job {job_id}: "
            f"cannot transition from {current_state} to {attempted_state}. "
            f"Allowed transitions: {', '.join(allowed_transitions) or 'none'}"
        )
        super().__init__(
            message=message,
            job_id=job_id,
            code="INVALID_STATE_TRANSITION",
        )

    def to_dict(self) -> dict:
        result = super().to_dict()
        result["current_state"] = self.current_state
        result["attempted_state"] = self.attempted_state
        result["allowed_transitions"] = self.allowed_transitions
        return result


class JobNotFoundError(JobError):
    """
    Raised when a job is not found.
    """

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job not found: {job_id}",
            job_id=job_id,
            code="JOB_NOT_FOUND",
        )


class JobConcurrencyError(JobError):
    """
    Raised when a concurrent modification conflict is detected.

    This happens when two processes try to update the same job
    simultaneously and the optimistic locking check fails.
    """

    def __init__(
        self,
        job_id: str,
        expected_version: int,
        actual_version: int,
    ):
        self.expected_version = expected_version
        self.actual_version = actual_version

        message = (
            f"Concurrent modification detected for job {job_id}. "
            f"Expected version {expected_version}, found {actual_version}. "
            "Please retry the operation."
        )
        super().__init__(
            message=message,
            job_id=job_id,
            code="JOB_CONCURRENCY_ERROR",
        )


class JobTimeoutError(JobError):
    """
    Raised when a job times out during processing.
    """

    def __init__(
        self,
        job_id: str,
        timeout_seconds: int,
    ):
        self.timeout_seconds = timeout_seconds
        super().__init__(
            message=f"Job {job_id} timed out after {timeout_seconds} seconds",
            job_id=job_id,
            code="JOB_TIMEOUT",
        )


class JobAlreadyExistsError(JobError):
    """
    Raised when trying to create a job that already exists.
    """

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job already exists: {job_id}",
            job_id=job_id,
            code="JOB_ALREADY_EXISTS",
        )
