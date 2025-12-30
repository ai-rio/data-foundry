"""
Tests for /api/v1/jobs/ router endpoints.

P01-013: Schema fix - Add job_id to AML labels
Tests verify that download_results returns only job-specific labels, not all tenant labels.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.aml_transaction_label import AMLTransactionLabel
from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus
from src.infrastructure.repositories.job_repository import ProcessingJobDB
from src.domain.processing_job.aggregate import JobStatus


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_job_with_labels(
    db_session: AsyncSession,
    test_tenant
) -> tuple[str, str]:
    """
    Create a test job with AML labels.

    Returns:
        tuple: (job_id, tenant_id)
    """
    job_id = str(uuid4())
    tenant_id = test_tenant.tenant_id

    # Create processing job
    job = ProcessingJobDB(
        id=job_id,
        tenant_id=tenant_id,
        version=1,
        file_name="test.csv",
        file_size=1000,
        status=JobStatus.COMPLETE.value,
        result_records=3,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job)
    await db_session.commit()

    # Create AML labels for this job
    labels = [
        AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=f"txn_{i}",
            tenant_id=tenant_id,
            job_id=job_id,
            risk_level=AMLRiskLevel.HIGH if i == 0 else AMLRiskLevel.MEDIUM,
            typology="ML",
            confidence_score=Decimal("0.95"),
            ai_reasoning=f"Test reasoning {i}",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_audit_ready=False,
            is_deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        for i in range(3)
    ]

    for label in labels:
        db_session.add(label)
    await db_session.commit()

    return job_id, tenant_id


@pytest.fixture
async def multiple_jobs_with_labels(
    db_session: AsyncSession,
    test_tenant
) -> dict[str, dict[str, Any]]:
    """
    Create multiple jobs with labels for testing isolation.

    Returns:
        dict: {job_id: {"tenant_id": str, "label_count": int}}
    """
    job1_id = str(uuid4())
    job2_id = str(uuid4())
    tenant_id = test_tenant.tenant_id

    # Create job 1
    job1 = ProcessingJobDB(
        id=job1_id,
        tenant_id=tenant_id,
        version=1,
        file_name="job1.csv",
        file_size=1000,
        status=JobStatus.COMPLETE.value,
        result_records=2,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job1)

    # Create job 2
    job2 = ProcessingJobDB(
        id=job2_id,
        tenant_id=tenant_id,
        version=1,
        file_name="job2.csv",
        file_size=1000,
        status=JobStatus.COMPLETE.value,
        result_records=3,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job2)

    # Create labels for job 1
    for i in range(2):
        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=f"job1_txn_{i}",
            tenant_id=tenant_id,
            job_id=job1_id,
            risk_level=AMLRiskLevel.HIGH,
            typology="ML",
            confidence_score=Decimal("0.95"),
            ai_reasoning=f"Job1 reasoning {i}",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_audit_ready=False,
            is_deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(label)

    # Create labels for job 2
    for i in range(3):
        label = AMLTransactionLabel(
            id=str(uuid4()),
            transaction_id=f"job2_txn_{i}",
            tenant_id=tenant_id,
            job_id=job2_id,
            risk_level=AMLRiskLevel.MEDIUM,
            typology="TF",
            confidence_score=Decimal("0.85"),
            ai_reasoning=f"Job2 reasoning {i}",
            expert_review_status=AMLExpertReviewStatus.PENDING,
            is_audit_ready=False,
            is_deleted=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db_session.add(label)

    await db_session.commit()

    return {
        job1_id: {"tenant_id": tenant_id, "label_count": 2},
        job2_id: {"tenant_id": tenant_id, "label_count": 3}
    }


@pytest.fixture
def auth_headers(test_tenant) -> dict[str, str]:
    """Create authorization headers for test requests."""
    # In a real scenario, this would use actual JWT tokens
    # For testing, we'll use a mock that bypasses auth in conftest
    return {"X-Tenant-ID": test_tenant.tenant_id}


# =============================================================================
# Tests: download_results returns job-specific labels only (P01-013)
# =============================================================================

@pytest.mark.asyncio
async def test_download_results_returns_job_labels_only(
    async_test_client: AsyncClient,
    multiple_jobs_with_labels: dict[str, dict[str, Any]],
    auth_headers: dict[str, str]
):
    """
    P01-013: Verify download_results returns ONLY job-specific labels.

    CRITICAL: This test ensures the query filters by job_id and doesn't
    return all tenant labels (the original bug).

    Given:
    - Job 1 has 2 labels with risk_level HIGH
    - Job 2 has 3 labels with risk_level MEDIUM
    - Both jobs belong to the same tenant

    When:
    - Download results for Job 1

    Then:
    - Only 2 labels are returned (Job 1's labels)
    - Job 2's 3 labels are NOT included
    - All returned labels have job_id == job1_id
    """
    job1_id = list(multiple_jobs_with_labels.keys())[0]
    job1_info = multiple_jobs_with_labels[job1_id]

    response = await async_test_client.get(
        f"/api/v1/jobs/{job1_id}/download",
        headers=auth_headers
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Parse CSV content
    csv_content = response.text
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    # Verify: Only job1's labels are returned (2 labels)
    assert len(rows) == job1_info["label_count"], (
        f"Expected {job1_info['label_count']} labels for job {job1_id}, "
        f"got {len(rows)}. Bug: Query may be returning all tenant labels."
    )

    # Verify: All returned labels have correct job_id
    for row in rows:
        assert row["job_id"] == job1_id, (
            f"Label {row['id']} has job_id={row['job_id']}, "
            f"expected {job1_id}"
        )


@pytest.mark.asyncio
async def test_download_results_filters_by_tenant(
    async_test_client: AsyncClient,
    db_session: AsyncSession,
    test_tenant,
    auth_headers: dict[str, str]
):
    """
    P01-013: Verify download_results enforces tenant isolation.

    Given:
    - Job belongs to tenant_001
    - Another tenant (tenant_002) tries to download

    When:
    - tenant_002 attempts to download tenant_001's job results

    Then:
    - Request is denied with 403 Forbidden
    """
    from src.models.tenant import Tenant

    job_id = str(uuid4())
    tenant1_id = test_tenant.tenant_id

    # Create second tenant
    tenant2 = Tenant(
        tenant_id="tenant_002",
        name="Other Tenant",
        status="active",
        max_users=10,
        max_data_records=1000,
        storage_limit_gb=10.0
    )
    db_session.add(tenant2)

    # Create job for tenant 1
    job = ProcessingJobDB(
        id=job_id,
        tenant_id=tenant1_id,
        version=1,
        file_name="test.csv",
        file_size=1000,
        status=JobStatus.COMPLETE.value,
        result_records=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job)

    # Create label for tenant 1
    label = AMLTransactionLabel(
        id=str(uuid4()),
        transaction_id="txn_001",
        tenant_id=tenant1_id,
        job_id=job_id,
        risk_level=AMLRiskLevel.HIGH,
        typology="ML",
        confidence_score=Decimal("0.95"),
        ai_reasoning="Test",
        expert_review_status=AMLExpertReviewStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(label)
    await db_session.commit()

    # Attempt download with tenant 2's ID
    headers_tenant2 = {"X-Tenant-ID": "tenant_002"}
    response = await async_test_client.get(
        f"/api/v1/jobs/{job_id}/download",
        headers=headers_tenant2
    )

    assert response.status_code == 403, (
        f"Expected 403 Forbidden for cross-tenant access, got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_download_results_404_when_no_labels(
    async_test_client: AsyncClient,
    db_session: AsyncSession,
    test_tenant,
    auth_headers: dict[str, str]
):
    """
    P01-013: Verify download_results returns 404 when no labels for job.

    CRITICAL: This test ensures proper error handling instead of returning
    empty CSV (the "0 records downloaded" bug).

    Given:
    - Job exists with COMPLETE status
    - Job has result_records > 0
    - But NO AML labels exist for this job

    When:
    - Download results for this job

    Then:
    - Returns 404 Not Found
    - Error message indicates no labels found
    """
    job_id = str(uuid4())
    tenant_id = test_tenant.tenant_id

    # Create job with COMPLETE status but no labels
    job = ProcessingJobDB(
        id=job_id,
        tenant_id=tenant_id,
        version=1,
        file_name="empty.csv",
        file_size=1000,
        status=JobStatus.COMPLETE.value,
        result_records=100,  # Claims to have results
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job)
    await db_session.commit()

    response = await async_test_client.get(
        f"/api/v1/jobs/{job_id}/download",
        headers=auth_headers
    )

    assert response.status_code == 404, (
        f"Expected 404 when no labels for job, got {response.status_code}"
    )

    # Verify error message
    response_data = response.json()
    assert "detail" in response_data
    assert "No AML labels found" in response_data["detail"] or job_id in response_data["detail"]


@pytest.mark.asyncio
async def test_download_csv_format_correct(
    async_test_client: AsyncClient,
    test_job_with_labels: tuple[str, str],
    auth_headers: dict[str, str]
):
    """
    P01-013: Verify downloaded CSV has correct format and fields.

    Given:
    - Job has 3 AML labels with various fields populated

    When:
    - Download results

    Then:
    - CSV has correct headers (including job_id)
    - All expected fields are present
    - CSV can be parsed correctly
    """
    job_id, tenant_id = test_job_with_labels

    response = await async_test_client.get(
        f"/api/v1/jobs/{job_id}/download",
        headers=auth_headers
    )

    assert response.status_code == 200

    # Parse CSV
    csv_content = response.text
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    # Verify expected headers exist
    expected_fields = [
        "id", "transaction_id", "tenant_id", "job_id",
        "risk_level", "typology", "confidence_score", "ai_reasoning",
        "expert_review_status", "is_audit_ready", "is_deleted",
        "created_at", "updated_at"
    ]

    for field in expected_fields:
        assert field in reader.fieldnames, f"Missing expected field: {field}"

    # Verify data integrity
    assert len(rows) == 3

    # Verify job_id field is populated correctly
    for row in rows:
        assert row["job_id"] == job_id, f"job_id mismatch: {row['job_id']} != {job_id}"
        assert row["tenant_id"] == tenant_id
        assert row["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert row["typology"] == "ML"

    # Verify filename in Content-Disposition header
    content_disposition = response.headers.get("content-disposition", "")
    assert f"job_{job_id}_aml_results.csv" in content_disposition


@pytest.mark.asyncio
async def test_download_results_400_when_job_not_complete(
    async_test_client: AsyncClient,
    db_session: AsyncSession,
    test_tenant,
    auth_headers: dict[str, str]
):
    """
    Verify download_results returns 400 when job is not COMPLETE.

    Given:
    - Job exists with PROCESSING status

    When:
    - Download results attempted

    Then:
    - Returns 400 Bad Request
    - Error indicates job is not complete
    """
    job_id = str(uuid4())
    tenant_id = test_tenant.tenant_id

    # Create job with PROCESSING status
    job = ProcessingJobDB(
        id=job_id,
        tenant_id=tenant_id,
        version=1,
        file_name="processing.csv",
        file_size=1000,
        status=JobStatus.PROCESSING.value,
        result_records=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db_session.add(job)
    await db_session.commit()

    response = await async_test_client.get(
        f"/api/v1/jobs/{job_id}/download",
        headers=auth_headers
    )

    assert response.status_code == 400

    response_data = response.json()
    assert "detail" in response_data
    assert "not complete" in response_data["detail"].lower()


@pytest.mark.asyncio
async def test_download_results_404_when_job_not_found(
    async_test_client: AsyncClient,
    auth_headers: dict[str, str]
):
    """
    Verify download_results returns 404 when job doesn't exist.

    When:
    - Download results for non-existent job

    Then:
    - Returns 404 Not Found
    """
    fake_job_id = str(uuid4())

    response = await async_test_client.get(
        f"/api/v1/jobs/{fake_job_id}/download",
        headers=auth_headers
    )

    assert response.status_code == 404

    response_data = response.json()
    assert "detail" in response_data
    assert "not found" in response_data["detail"].lower() or fake_job_id in response_data["detail"]
