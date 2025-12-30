"""
Worker Entry Point

Standalone entry point for running the background job worker.

Usage:
    # Run the worker
    python -m src.workers.main

    # Run with custom configuration via environment variables
    WORKER_POLL_INTERVAL=10 WORKER_MAX_RETRIES=5 python -m src.workers.main

Environment Variables:
    WORKER_POLL_INTERVAL: Seconds between polling for new jobs (default: 5.0)
    WORKER_MAX_RETRIES: Maximum retry attempts for transient failures (default: 3)
    WORKER_BACKOFF_BASE: Base for exponential backoff in seconds (default: 1.0)
    WORKER_BATCH_SIZE: Number of jobs to poll at once (default: 1)
    WORKER_ID: Unique identifier for this worker instance (auto-generated if not set)
    DATABASE_URL: PostgreSQL connection string (required)
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from src.workers.config import WorkerConfig
from src.workers.job_worker import JobWorker
from src.infrastructure.repositories.job_repository import JobRepository
from src.database.connection import db_connection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_job_repository() -> AsyncGenerator[JobRepository, None]:
    """
    Create a JobRepository with proper session management.

    Yields:
        Configured JobRepository instance
    """
    async with db_connection.get_session() as session:
        yield JobRepository(session)


async def run_worker() -> None:
    """
    Initialize and run the background job worker.

    This function:
    1. Initializes database connection
    2. Loads configuration from environment variables
    3. Creates database session and repository
    4. Creates and starts the JobWorker
    5. Handles graceful shutdown on SIGTERM/SIGINT
    """
    # Initialize database
    logger.info("Initializing database connection...")
    await db_connection.initialize()
    logger.info("Database connection initialized")

    # Load configuration
    config = WorkerConfig()
    logger.info(f"Starting worker {config.worker_id}")
    logger.info(
        f"Configuration: poll_interval={config.poll_interval}s, "
        f"max_retries={config.max_retries}, "
        f"backoff_base={config.backoff_base}s, "
        f"batch_size={config.batch_size}"
    )

    # Create repository and worker
    async with create_job_repository() as job_repo:
        worker = JobWorker.from_config(job_repo, config)

        # Run the worker (blocks until shutdown)
        await worker.run()

    logger.info(f"Worker {config.worker_id} stopped")


def main() -> None:
    """
    Main entry point for the worker process.

    Runs the async worker in the event loop.
    """
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
