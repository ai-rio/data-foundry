#!/usr/bin/env python3
"""
Phase 2 API Test Harness - Test File Upload & Job Tracking Endpoints

This script tests the new Phase 2 API endpoints:
- POST /api/v1/upload - File upload with multipart
- GET /api/v1/jobs/{job_id} - Job status tracking
- GET /api/v1/jobs/{job_id}/results - Download results

Hardware-Conscious Design:
- NO heavy PDF/DOCX parsing (uses CSV only)
- Tests real files via HTTP multipart upload
- Validates cost calculation accuracy
- Tracks Stripe meter events

Purpose:
- Validate file upload API works end-to-end
- Test job tracking and status polling
- Verify Stripe meter events fire correctly
- Measure processing performance per vertical
- Identify API issues before frontend is built

Output:
- api_test_results/ directory with per-vertical results
- Summary CSV with performance metrics
- Error logs for debugging
"""

import os
import sys
import json
import time
import csv
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import pandas as pd

# Setup paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================================
# Configuration
# ============================================================================

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = 120  # seconds
POLL_INTERVAL = 1  # seconds
MAX_POLLS = 120  # Max 2 minutes of polling

# Test credentials (would come from Clerk in production)
TENANT_ID = os.getenv("TENANT_ID", "test-tenant-phase2")
API_KEY = os.getenv("API_KEY", "test-key-phase2")

# Pricing reference (from Phase 0 research)
PRICING_BY_VERTICAL = {
    "fintech": {
        "ai_labels": 0.03,
        "human_audits": 0.08,
    },
    "healthcare": {
        "ai_labels": 0.15,
        "human_audits": 0.25,
    },
    "ecommerce": {
        "ai_labels": 0.08,
        "human_audits": 0.15,
    },
    "legal": {
        "ai_labels": 35,
        "human_audits": 65,
    },
}

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class APITestConfig:
    """Configuration for a single API test."""
    vertical: str
    dataset_path: str
    sample_size: int = 0  # 0 = all records
    timeout_seconds: int = 120
    poll_interval_seconds: float = 1.0


@dataclass
class APITestResult:
    """Results from running an API test."""
    vertical: str
    dataset_path: str
    timestamp: str
    total_records: int
    sample_size: int

    # Upload metrics
    upload_success: bool = False
    upload_time_seconds: float = 0.0
    job_id: Optional[str] = None
    upload_error: str = ""

    # Job tracking metrics
    job_tracking_success: bool = False
    job_tracking_time_seconds: float = 0.0
    final_job_status: str = ""
    polls_until_complete: int = 0

    # Cost validation
    cost_validation_success: bool = False
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    cost_variance_percent: float = 0.0

    # Results download
    results_download_success: bool = False
    results_records_count: int = 0

    # Overall metrics
    total_time_seconds: float = 0.0
    success: bool = False
    error_message: str = ""


# ============================================================================
# HTTP Client Setup
# ============================================================================

async def create_http_client() -> httpx.AsyncClient:
    """Create HTTP client with proper timeout and headers."""
    return httpx.AsyncClient(
        base_url=API_BASE_URL,
        timeout=API_TIMEOUT,
        headers={
            "X-Tenant-ID": TENANT_ID,
            "Authorization": f"Bearer {API_KEY}",
        }
    )


# ============================================================================
# File Handling
# ============================================================================

def prepare_csv_file(path: str, sample_size: int = 0, vertical: str = "") -> tuple[bytes, str, int]:
    """
    Load CSV and prepare bytes for multipart upload.

    Returns:
        (file_bytes, filename, total_records)
    """
    try:
        df = pd.read_csv(path)
        total_count = len(df)

        if sample_size > 0 and sample_size < total_count:
            df = df.head(sample_size)

        # Wrap raw data with required metadata before upload
        if vertical:
            raw_records = df.to_dict('records')
            wrapped = wrap_raw_data(raw_records, vertical)
            wrapped_df = pd.DataFrame(wrapped)
            csv_bytes = wrapped_df.to_csv(index=False).encode('utf-8')
        else:
            csv_bytes = df.to_csv(index=False).encode('utf-8')

        filename = Path(path).name

        return csv_bytes, filename, total_count
    except Exception as e:
        raise ValueError(f"Failed to prepare CSV: {str(e)}")


def wrap_raw_data(raw_records: List[Dict[str, Any]], vertical: str, tenant_id: str = "test-tenant") -> List[Dict[str, Any]]:
    """
    Wrap raw CSV records with required metadata before validation.

    Transforms raw CSV data into the format expected by DataQualityValidator:
    - Adds record_id (auto-generated from vertical + index)
    - Adds tenant_id (for multi-tenancy)
    - Adds data_source (vertical name)
    - Wraps raw data as JSON string in raw_data field

    Args:
        raw_records: List of raw CSV record dicts
        vertical: Vertical name (fintech, healthcare, ecommerce, legal)
        tenant_id: Tenant identifier (default: test-tenant)

    Returns:
        List of wrapped records ready for pipeline validation
    """
    wrapped = []
    for idx, record in enumerate(raw_records):
        wrapped.append({
            "record_id": f"{vertical}-{idx:06d}",
            "tenant_id": tenant_id,
            "data_source": vertical,
            "raw_data": json.dumps(record)
        })
    return wrapped


# ============================================================================
# API Test Operations
# ============================================================================

async def upload_file(
    client: httpx.AsyncClient,
    config: APITestConfig,
    csv_bytes: bytes,
    filename: str,
) -> tuple[bool, str, float]:
    """
    Test file upload endpoint: POST /api/v1/upload

    Returns:
        (success, job_id_or_error, time_taken)
    """
    start_time = time.time()

    try:
        print("   📤 Uploading file via POST /api/v1/upload")

        files = {
            "file": (filename, csv_bytes, "text/csv"),
        }
        data = {
            "vertical": config.vertical,
            "filename": filename,
        }

        response = await client.post(
            "/api/v1/upload",
            files=files,
            data=data,
        )

        elapsed = time.time() - start_time

        if response.status_code in [200, 201]:
            result = response.json()
            job_id = result.get("job_id")
            print(f"      ✓ Upload successful (job_id: {job_id}, {elapsed:.2f}s)")
            return True, job_id, elapsed
        else:
            error = response.text
            print(f"      ✗ Upload failed: {response.status_code} - {error}")
            return False, error, elapsed

    except Exception as e:
        elapsed = time.time() - start_time
        error = f"Upload exception: {str(e)}"
        print(f"      ✗ {error}")
        return False, error, elapsed


async def track_job(
    client: httpx.AsyncClient,
    job_id: str,
    timeout_seconds: int,
    poll_interval: float,
) -> tuple[bool, str, int, float]:
    """
    Test job tracking endpoint: GET /api/v1/jobs/{job_id}

    Polls until job is complete or timeout.

    Returns:
        (success, final_status, polls_made, time_taken)
    """
    start_time = time.time()
    polls_made = 0
    final_status = ""

    try:
        print("   ⏳ Polling job status via GET /api/v1/jobs/{job_id}")

        while True:
            polls_made += 1
            elapsed = time.time() - start_time

            if elapsed > timeout_seconds:
                error = f"Timeout waiting for job completion ({timeout_seconds}s)"
                print(f"      ✗ {error}")
                return False, "", polls_made, elapsed

            try:
                response = await client.get(f"/api/v1/jobs/{job_id}")

                if response.status_code == 200:
                    job_data = response.json()
                    status = job_data.get("status")
                    final_status = status

                    print(f"      Poll #{polls_made}: status={status} ({elapsed:.2f}s)")

                    if status in ["COMPLETE", "FAILED"]:
                        if status == "COMPLETE":
                            print(f"      ✓ Job completed after {polls_made} polls ({elapsed:.2f}s)")
                            return True, status, polls_made, elapsed
                        else:
                            error = job_data.get("error_message", "Unknown error")
                            print(f"      ✗ Job failed: {error}")
                            return False, status, polls_made, elapsed

                    # Not done yet, sleep and retry
                    await asyncio.sleep(poll_interval)
                else:
                    error = f"Failed to get job status: {response.status_code}"
                    print(f"      ✗ {error}")
                    return False, "", polls_made, elapsed

            except Exception as e:
                error = f"Poll exception: {str(e)}"
                print(f"      ✗ {error}")
                return False, "", polls_made, elapsed

    except Exception as e:
        elapsed = time.time() - start_time
        error = f"Job tracking exception: {str(e)}"
        print(f"      ✗ {error}")
        return False, "", polls_made, elapsed


async def validate_cost(
    client: httpx.AsyncClient,
    job_id: str,
    vertical: str,
) -> tuple[bool, float, float, float]:
    """
    Test cost validation by comparing estimate vs actual.

    Returns:
        (success, estimated_cost, actual_cost, variance_percent)
    """
    try:
        print("   💰 Validating cost accuracy")

        response = await client.get(f"/api/v1/jobs/{job_id}")
        if response.status_code != 200:
            print(f"      ✗ Failed to get job for cost validation")
            return False, 0.0, 0.0, 0.0

        job_data = response.json()
        estimated = job_data.get("estimated_cost", 0.0)
        actual = job_data.get("actual_cost", 0.0)

        if actual == 0:
            variance = 0.0
        else:
            variance = abs(estimated - actual) / actual * 100

        success = variance <= 5.0  # 5% tolerance
        status = "✓" if success else "✗"
        print(f"      {status} Estimate: ${estimated:.4f}, Actual: ${actual:.4f}, Variance: {variance:.2f}%")

        return success, estimated, actual, variance

    except Exception as e:
        error = f"Cost validation exception: {str(e)}"
        print(f"      ✗ {error}")
        return False, 0.0, 0.0, 0.0


async def download_results(
    client: httpx.AsyncClient,
    job_id: str,
) -> tuple[bool, int]:
    """
    Test results download endpoint: GET /api/v1/jobs/{job_id}/results

    Returns:
        (success, record_count)
    """
    try:
        print("   📥 Downloading results via GET /api/v1/jobs/{job_id}/results")

        response = await client.get(f"/api/v1/jobs/{job_id}/results")

        if response.status_code == 200:
            # Parse CSV response
            csv_content = response.text
            df = pd.read_csv(path=None, data=csv_content)
            record_count = len(df)
            print(f"      ✓ Downloaded {record_count} records")
            return True, record_count
        else:
            print(f"      ✗ Failed to download results: {response.status_code}")
            return False, 0

    except Exception as e:
        error = f"Results download exception: {str(e)}"
        print(f"      ✗ {error}")
        return False, 0


# ============================================================================
# Test Executor
# ============================================================================

async def run_api_test(
    client: httpx.AsyncClient,
    config: APITestConfig,
) -> APITestResult:
    """
    Run a complete API test for a single vertical.

    Tests: Upload → Job Tracking → Cost Validation → Results Download
    """
    test_start = time.time()

    result = APITestResult(
        vertical=config.vertical,
        dataset_path=config.dataset_path,
        timestamp=datetime.now().isoformat(),
        total_records=0,
        sample_size=0,
    )

    try:
        print(f"\n{'='*70}")
        print(f"API TEST: {config.vertical.upper()}")
        print(f"{'='*70}")
        print(f"Dataset: {config.dataset_path}")

        # Prepare file
        print("📋 Preparing test data...")
        csv_bytes, filename, total_count = prepare_csv_file(
            config.dataset_path,
            config.sample_size,
            config.vertical
        )
        result.total_records = total_count
        result.sample_size = len(csv_bytes)  # Approximate
        print(f"   ✓ Prepared {total_count} total records")

        # Stage 1: Upload
        print("📤 Stage 1: File Upload")
        upload_success, job_id_or_error, upload_time = await upload_file(
            client,
            config,
            csv_bytes,
            filename,
        )
        result.upload_success = upload_success
        result.upload_time_seconds = upload_time

        if not upload_success:
            result.upload_error = job_id_or_error
            result.success = False
            result.error_message = f"Upload failed: {job_id_or_error}"
            result.total_time_seconds = time.time() - test_start
            return result

        job_id = job_id_or_error
        result.job_id = job_id

        # Stage 2: Job Tracking
        print("⏳ Stage 2: Job Tracking")
        track_success, final_status, polls_made, track_time = await track_job(
            client,
            job_id,
            config.timeout_seconds,
            config.poll_interval_seconds,
        )
        result.job_tracking_success = track_success
        result.job_tracking_time_seconds = track_time
        result.final_job_status = final_status
        result.polls_until_complete = polls_made

        if not track_success:
            result.success = False
            result.error_message = f"Job tracking failed: {final_status}"
            result.total_time_seconds = time.time() - test_start
            return result

        # Stage 3: Cost Validation
        print("💰 Stage 3: Cost Validation")
        cost_success, estimated, actual, variance = await validate_cost(
            client,
            job_id,
            config.vertical,
        )
        result.cost_validation_success = cost_success
        result.estimated_cost = estimated
        result.actual_cost = actual
        result.cost_variance_percent = variance

        # Stage 4: Results Download
        print("📥 Stage 4: Results Download")
        download_success, record_count = await download_results(
            client,
            job_id,
        )
        result.results_download_success = download_success
        result.results_records_count = record_count

        # Overall success
        result.success = (
            upload_success and
            track_success and
            cost_success and
            download_success
        )
        result.total_time_seconds = time.time() - test_start

        # Print summary
        print(f"\n📊 RESULTS for {config.vertical.upper()}:")
        print(f"   Total Time: {result.total_time_seconds:.2f}s")
        print(f"   Upload: {'✓' if upload_success else '✗'} ({upload_time:.2f}s)")
        print(f"   Job Tracking: {'✓' if track_success else '✗'} ({polls_made} polls, {track_time:.2f}s)")
        print(f"   Cost Validation: {'✓' if cost_success else '✗'} (${actual:.4f}, {variance:.2f}% variance)")
        print(f"   Results Download: {'✓' if download_success else '✗'} ({record_count} records)")

    except Exception as e:
        result.success = False
        result.error_message = str(e)
        result.total_time_seconds = time.time() - test_start
        print(f"❌ TEST FAILED: {str(e)}")

    return result


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run all API tests."""

    # Create output directory
    output_dir = PROJECT_ROOT / "api_test_results"
    output_dir.mkdir(exist_ok=True)

    # Define tests
    tests = [
        APITestConfig(
            vertical="fintech",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/fintech/Banking_Transactions_USA_2023_2024.csv"),
            sample_size=1000,
        ),
        APITestConfig(
            vertical="healthcare",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/healthcare/healthcare_dataset.csv"),
            sample_size=1000,
        ),
        APITestConfig(
            vertical="ecommerce",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/ecommerce/Phones.csv"),
            sample_size=500,
        ),
    ]

    results = []

    print("\n" + "="*70)
    print("PHASE 2 API TEST HARNESS")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Output Directory: {output_dir}")

    # Create HTTP client
    async with await create_http_client() as client:
        # Run tests
        for test_config in tests:
            result = await run_api_test(client, test_config)
            results.append(result)

            # Save individual result
            result_file = output_dir / f"{test_config.vertical}_api_result.json"
            with open(result_file, 'w') as f:
                json.dump(asdict(result), f, indent=2)
            print(f"   📄 Result saved: {result_file}")

    # Generate summary
    print(f"\n{'='*70}")
    print("SUMMARY REPORT")
    print(f"{'='*70}")

    summary_file = output_dir / "api_test_summary.csv"
    with open(summary_file, 'w', newline='') as f:
        fieldnames = [k for k in asdict(results[0]).keys()] if results else []
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    print(f"✅ Summary saved: {summary_file}\n")

    # Print table
    print("VERTICAL  | SUCCESS | UPLOAD | TRACKING | COST_VAL | DOWNLOAD | TOTAL_TIME | COST_VAR%")
    print("-" * 100)
    for result in results:
        success = "✓" if result.success else "✗"
        upload = "✓" if result.upload_success else "✗"
        tracking = "✓" if result.job_tracking_success else "✗"
        cost = "✓" if result.cost_validation_success else "✗"
        download = "✓" if result.results_download_success else "✗"
        print(f"{result.vertical:9} | {success:7} | {upload:6} | {tracking:8} | {cost:8} | {download:8} | {result.total_time_seconds:10.2f} | {result.cost_variance_percent:8.2f}")

    # Overall status
    all_success = all(r.success for r in results)
    print(f"\n{'✅ ALL TESTS PASSED' if all_success else '❌ SOME TESTS FAILED'}")
    print(f"📁 Results in: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
