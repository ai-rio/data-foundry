"""
Worker Configuration

Configuration class for background job workers using pydantic-settings.

SOLID Principles:
- Single Responsibility: Only handles worker configuration
- Open/Closed: Easy to extend with new settings
"""

from uuid import uuid4
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerConfig(BaseSettings):
    """
    Configuration for JobWorker instances.

    Environment variables:
    - WORKER_POLL_INTERVAL: Seconds between polling for new jobs (default: 5.0)
    - WORKER_MAX_RETRIES: Maximum retry attempts for transient failures (default: 3)
    - WORKER_BACKOFF_BASE: Base for exponential backoff in seconds (default: 1.0)
    - WORKER_BATCH_SIZE: Number of jobs to poll at once (default: 1)
    - WORKER_ID: Unique identifier for this worker instance

    Exponential backoff formula: backoff_base * 4^attempt
    - Attempt 0: 1s
    - Attempt 1: 4s
    - Attempt 2: 16s

    Example:
        # From environment variables
        config = WorkerConfig()

        # With explicit values
        config = WorkerConfig(poll_interval=10.0, max_retries=5)

        # Create worker from config
        worker = JobWorker.from_config(job_repo, config)
    """

    model_config = SettingsConfigDict(
        env_prefix="WORKER_",
        case_sensitive=False,
    )

    poll_interval: float = 5.0
    max_retries: int = 3
    backoff_base: float = 1.0
    batch_size: int = 1
    worker_id: str = ""

    @model_validator(mode="after")
    def generate_worker_id(self) -> "WorkerConfig":
        """Generate worker_id if not provided."""
        if not self.worker_id:
            object.__setattr__(self, "worker_id", f"worker-{uuid4().hex[:8]}")
        return self
