"""
Worker Metrics

Observability metrics for background job workers.

SOLID Principles:
- Single Responsibility: Only handles metrics collection
- Interface Segregation: Simple interface for recording events
"""

import time
from datetime import datetime
from typing import Dict, Any


class WorkerMetrics:
    """
    Metrics collector for JobWorker.

    Tracks:
    - jobs_processed: Total number of jobs attempted
    - jobs_completed: Jobs that completed successfully
    - jobs_failed: Jobs that failed
    - total_processing_time: Cumulative processing time in seconds
    - last_job_at: Timestamp of last processed job
    """

    def __init__(self):
        """Initialize metrics with zero values."""
        self.jobs_processed: int = 0
        self.jobs_completed: int = 0
        self.jobs_failed: int = 0
        self.total_processing_time: float = 0.0
        self.last_job_at: datetime | None = None
        self._current_job_start: float | None = None

    def start_job(self) -> None:
        """Mark the start of job processing."""
        self._current_job_start = time.time()

    def record_job_completed(self) -> None:
        """Record a successfully completed job."""
        self._finish_job()
        self.jobs_completed += 1

    def record_job_failed(self) -> None:
        """Record a failed job."""
        self._finish_job()
        self.jobs_failed += 1

    def _finish_job(self) -> None:
        """Common finish logic for job processing."""
        self.jobs_processed += 1
        self.last_job_at = datetime.utcnow()

        if self._current_job_start is not None:
            duration = time.time() - self._current_job_start
            self.total_processing_time += duration
            self._current_job_start = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for export."""
        return {
            "jobs_processed": self.jobs_processed,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "total_processing_time": self.total_processing_time,
            "average_processing_time": (
                self.total_processing_time / self.jobs_processed
                if self.jobs_processed > 0
                else 0.0
            ),
            "last_job_at": (
                self.last_job_at.isoformat()
                if self.last_job_at
                else None
            ),
        }

    def reset(self) -> None:
        """Reset all metrics to zero."""
        self.jobs_processed = 0
        self.jobs_completed = 0
        self.jobs_failed = 0
        self.total_processing_time = 0.0
        self.last_job_at = None
        self._current_job_start = None
