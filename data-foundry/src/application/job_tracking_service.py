"""
Job Tracking Application Service

Manages the lifecycle of processing jobs through the state machine.
Coordinates between domain aggregate and repository.

SOLID Principles:
- Single Responsibility: Only manages job state transitions
- Dependency Inversion: Depends on IJobRepository interface
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Protocol, runtime_checkable

from src.domain.processing_job.aggregate import ProcessingJob, JobStatus
from src.domain.processing_job.repository import IJobRepository
from src.domain.processing_job.exceptions import (
    JobNotFoundError,
    InvalidStateTransition,
)
from src.models.aml_enums import AMLExpertReviewStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class AMLLabelProtocol(Protocol):
    """
    Protocol for AML transaction labels to ensure type safety.

    This protocol defines the expected interface for AML label objects,
    allowing for duck typing while maintaining type checking.
    """
    risk_level: str
    typology: str
    confidence_score: Optional[float]

    def __init__(self, **kwargs): ...  # type: ignore

    # Optional expert review status
    expert_review_status: Optional[AMLExpertReviewStatus] = None


class JobTrackingService:
    """
    Application Service: Job Tracking

    Provides the application-level interface for managing processing jobs.
    All job state transitions go through this service, which coordinates
    with the repository for persistence.

    This service:
    - Creates new jobs
    - Transitions job states
    - Queries job status
    - Handles job timeouts and retries

    Dependency Inversion: Accepts IJobRepository, not concrete implementation.
    """

    def __init__(self, repo: IJobRepository):
        """
        Initialize with job repository.

        Args:
            repo: IJobRepository implementation for persistence
        """
        self._repo = repo
        logger.info("JobTrackingService initialized")

    # -----------------------------------------------------------------
    # Job Creation
    # -----------------------------------------------------------------

    async def create_job(
        self,
        tenant_id: str,
        file_name: str,
        file_size: int,
        complexity_tier: str = "simple",
        estimated_cost: Optional[Decimal] = None,
        metadata: Optional[dict] = None,
    ) -> ProcessingJob:
        """
        Create a new processing job.

        Args:
            tenant_id: Tenant identifier
            file_name: Name of the file being processed
            file_size: Size of the file in bytes
            complexity_tier: Processing complexity tier
            estimated_cost: Optional pre-calculated cost estimate
            metadata: Optional job metadata

        Returns:
            Created ProcessingJob in PENDING state
        """
        job = ProcessingJob.create(
            tenant_id=tenant_id,
            file_name=file_name,
            file_size=file_size,
            complexity_tier=complexity_tier,
            estimated_cost=estimated_cost,
        )

        if metadata:
            job.metadata.update(metadata)

        saved_job = await self._repo.save(job)

        logger.info(
            f"Created job {saved_job.id} for tenant {tenant_id}: "
            f"{file_name} ({file_size} bytes, tier={complexity_tier})"
        )

        return saved_job

    # -----------------------------------------------------------------
    # State Transitions
    # -----------------------------------------------------------------

    async def start_processing(self, job_id: str) -> ProcessingJob:
        """
        Transition a job from PENDING to PROCESSING.

        Args:
            job_id: Job identifier

        Returns:
            Updated ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If transition not allowed
        """
        job = await self._repo.get_by_id(job_id)

        job.transition_to_processing()
        saved_job = await self._repo.save(job)

        logger.info(f"Job {job_id} started processing")
        return saved_job

    async def mark_complete(
        self,
        job_id: str,
        result_records: int,
        result_url: Optional[str] = None,
        actual_cost: Optional[Decimal] = None,
        aml_risk_level_counts: Optional[Dict[str, int]] = None,
        aml_inter_rater_agreement: Optional[float] = None,
        aml_expert_review_count: Optional[int] = None,
        aml_audit_report_url: Optional[str] = None,
    ) -> ProcessingJob:
        """
        Transition a job from PROCESSING to COMPLETE.

        Args:
            job_id: Job identifier
            result_records: Number of records processed
            result_url: Optional URL to results
            actual_cost: Optional actual processing cost
            aml_risk_level_counts: Optional dict of AML risk level distributions
            aml_inter_rater_agreement: Optional Cohen's Kappa score
            aml_expert_review_count: Optional number routed to expert review
            aml_audit_report_url: Optional path to generated audit report

        Returns:
            Updated ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If transition not allowed
        """
        job = await self._repo.get_by_id(job_id)

        job.transition_to_complete(
            result_records=result_records,
            result_url=result_url,
            actual_cost=actual_cost,
        )

        # Store AML-specific results in metadata
        # Build aml_results dict only with non-None/empty values to avoid
        # storing zeros or False values incorrectly
        aml_results = {}
        if aml_risk_level_counts:
            aml_results["risk_level_counts"] = aml_risk_level_counts
        if aml_inter_rater_agreement is not None:
            aml_results["inter_rater_agreement"] = aml_inter_rater_agreement
        if aml_expert_review_count is not None:
            aml_results["expert_review_count"] = aml_expert_review_count
        if aml_audit_report_url:
            aml_results["audit_report_url"] = aml_audit_report_url

        if aml_results:
            job.metadata["aml_results"] = aml_results

        saved_job = await self._repo.save(job)

        logger.info(
            f"Job {job_id} completed: {result_records} records processed"
        )
        return saved_job

    async def mark_failed(
        self,
        job_id: str,
        error_message: str,
    ) -> ProcessingJob:
        """
        Transition a job to FAILED state.

        Args:
            job_id: Job identifier
            error_message: Description of the failure

        Returns:
            Updated ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If transition not allowed
        """
        job = await self._repo.get_by_id(job_id)

        job.transition_to_failed(error_message=error_message)
        saved_job = await self._repo.save(job)

        logger.warning(f"Job {job_id} failed: {error_message}")
        return saved_job

    async def cancel_job(
        self,
        job_id: str,
        reason: Optional[str] = None,
    ) -> ProcessingJob:
        """
        Cancel a job.

        Args:
            job_id: Job identifier
            reason: Optional cancellation reason

        Returns:
            Updated ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If job cannot be cancelled
        """
        job = await self._repo.get_by_id(job_id)

        job.transition_to_cancelled(reason=reason)
        saved_job = await self._repo.save(job)

        logger.info(f"Job {job_id} cancelled: {reason or 'No reason provided'}")
        return saved_job

    async def retry_job(self, job_id: str) -> ProcessingJob:
        """
        Retry a failed job.

        Args:
            job_id: Job identifier

        Returns:
            Updated ProcessingJob in PENDING state

        Raises:
            JobNotFoundError: If job doesn't exist
            InvalidStateTransition: If job cannot be retried
        """
        job = await self._repo.get_by_id(job_id)

        if not job.can_retry:
            raise InvalidStateTransition(
                job_id=job_id,
                current_state=job.status.value,
                attempted_state=JobStatus.PENDING.value,
                allowed_transitions=["none - max retries exceeded or not in FAILED state"],
            )

        job.retry()
        saved_job = await self._repo.save(job)

        logger.info(
            f"Job {job_id} queued for retry (attempt {job.retry_count + 1})"
        )
        return saved_job

    # -----------------------------------------------------------------
    # Query Operations
    # -----------------------------------------------------------------

    async def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """
        Get a job by ID.

        Args:
            job_id: Job identifier

        Returns:
            ProcessingJob if found, None otherwise
        """
        return await self._repo.get(job_id)

    async def get_job_or_fail(self, job_id: str) -> ProcessingJob:
        """
        Get a job by ID, raising if not found.

        Args:
            job_id: Job identifier

        Returns:
            ProcessingJob

        Raises:
            JobNotFoundError: If job doesn't exist
        """
        return await self._repo.get_by_id(job_id)

    async def list_tenant_jobs(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ProcessingJob]:
        """
        List jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of ProcessingJob
        """
        return await self._repo.list_by_tenant(
            tenant_id=tenant_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def count_tenant_jobs(
        self,
        tenant_id: str,
        status: Optional[JobStatus] = None,
    ) -> int:
        """
        Count jobs for a tenant.

        Args:
            tenant_id: Tenant identifier
            status: Optional status filter

        Returns:
            Count of matching jobs
        """
        return await self._repo.count_by_tenant(
            tenant_id=tenant_id,
            status=status,
        )

    # -----------------------------------------------------------------
    # Background Operations
    # -----------------------------------------------------------------

    async def handle_stale_jobs(
        self,
        timeout_minutes: int = 60,
        limit: int = 100,
    ) -> List[ProcessingJob]:
        """
        Find and fail jobs that have been processing too long.

        This should be called periodically by a background worker.

        Args:
            timeout_minutes: Minutes after which a job is considered stale
            limit: Maximum jobs to process

        Returns:
            List of jobs that were marked as failed
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        stale_jobs = await self._repo.get_stale_processing_jobs(
            older_than=cutoff,
            limit=limit,
        )

        failed_jobs = []
        for job in stale_jobs:
            try:
                job.transition_to_failed(
                    error_message=f"Job timed out after {timeout_minutes} minutes"
                )
                saved_job = await self._repo.save(job)
                failed_jobs.append(saved_job)
                logger.warning(f"Job {job.id} marked as failed due to timeout")
            except InvalidStateTransition:
                # Job state changed since we queried - skip
                logger.debug(f"Job {job.id} state changed, skipping timeout")

        return failed_jobs

    async def get_pending_jobs(
        self,
        limit: int = 100,
    ) -> List[ProcessingJob]:
        """
        Get jobs ready for processing.

        Args:
            limit: Maximum jobs to return

        Returns:
            List of PENDING jobs
        """
        return await self._repo.list_by_status(
            status=JobStatus.PENDING,
            limit=limit,
        )

    # -----------------------------------------------------------------
    # AML-specific Operations
    # -----------------------------------------------------------------

    async def get_aml_job_metrics(
        self,
        job_id: str,
        aml_labels: Optional[List[AMLLabelProtocol]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve AML-specific metrics for a completed job.

        This method calculates comprehensive AML metrics including:
        - Total transactions processed
        - Risk level distribution
        - Typology distribution
        - Average confidence score
        - Expert review count
        - Inter-rater agreement (if expert reviews exist)

        Args:
            job_id: Job identifier
            aml_labels: Optional list of AMLTransactionLabel objects for calculation.
                       If None, retrieves aml_results from job metadata.

        Returns:
            Dictionary with:
                - total_transactions: int
                - risk_distribution: dict[str, int]
                - typology_distribution: dict[str, int]
                - average_confidence: float
                - expert_review_count: int
                - inter_rater_agreement: float | None

        Raises:
            JobNotFoundError: If job doesn't exist
        """
        job = await self._repo.get_by_id(job_id)

        # Check if job has AML results stored in metadata
        aml_results = job.metadata.get("aml_results", {})

        # If AML labels provided, calculate metrics directly
        if aml_labels:
            total_transactions = len(aml_labels)

            # Calculate risk distribution
            risk_distribution: Dict[str, int] = {}
            for label in aml_labels:
                risk_level = label.risk_level if hasattr(label.risk_level, 'value') else label.risk_level
                risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1

            # Calculate typology distribution
            typology_distribution: Dict[str, int] = {}
            for label in aml_labels:
                typology = label.typology
                typology_distribution[typology] = typology_distribution.get(typology, 0) + 1

            # Calculate average confidence
            confidences = [
                float(label.confidence_score)
                for label in aml_labels
                if label.confidence_score is not None
            ]
            average_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            # Count expert reviews (labels with PENDING status or with reviews)
            expert_review_count = sum(
                1 for label in aml_labels
                if hasattr(label, 'expert_review_status') and
                label.expert_review_status == AMLExpertReviewStatus.PENDING
            )

            # Calculate inter-rater agreement if expert reviews exist
            inter_rater_agreement = aml_results.get("inter_rater_agreement")

        else:
            # Use stored metrics from metadata
            total_transactions = job.result_records or 0
            risk_distribution = aml_results.get("risk_level_counts", {})
            typology_distribution = aml_results.get("typology_counts", {})
            average_confidence = aml_results.get("average_confidence", 0.0)
            expert_review_count = aml_results.get("expert_review_count") or 0
            inter_rater_agreement = aml_results.get("inter_rater_agreement")

        return {
            "total_transactions": total_transactions,
            "risk_distribution": risk_distribution,
            "typology_distribution": typology_distribution,
            "average_confidence": average_confidence,
            "expert_review_count": expert_review_count,
            "inter_rater_agreement": inter_rater_agreement,
        }
