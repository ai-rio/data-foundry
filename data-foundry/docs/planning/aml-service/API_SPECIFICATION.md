# AML Service - API Specification

## 1. Overview

The Data Foundry platform provides Anti-Money Laundering (AML) transaction labeling through a **generic job-based processing architecture**. Unlike the fictional `/api/v1/aml/` endpoints described in earlier drafts, the actual implementation uses:

- **Generic upload endpoints** that accept CSV/JSON files containing AML transaction data
- **Job-based processing** where AML labeling happens asynchronously
- **AML-specific metadata** embedded in job status responses
- **Results download** via job completion endpoints

**IMPORTANT:** There are no dedicated `/api/v1/aml/*` endpoints. AML functionality is accessed through the generic Data Foundry API with AML transaction data and AML-specific result fields.

### Base URL

```
Production:  https://api.datafoundry.com
Staging:     https://staging-api.datafoundry.com
Development: http://localhost:8000
```

### API Version

Current version: `v1`

All endpoints are prefixed with `/api/v1/`

### Response Format

All responses are JSON-formatted. AML-specific information is embedded in job metadata:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "complete",
  "aml_risk_level_counts": {
    "LOW": 8500,
    "MEDIUM": 1200,
    "HIGH": 250,
    "CRITICAL": 50
  },
  "aml_inter_rater_agreement": 0.72,
  "aml_expert_review_count": 300,
  "aml_audit_report_url": "https://storage.example.com/audit/reports/job-123.pdf"
}
```

### Common Headers

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <jwt_token>
X-Tenant-ID: <tenant-identifier>  (for multi-tenancy in development)
```

**Response Headers:**
```
Content-Type: application/json
```

---

## 2. Authentication & Authorization

### JWT Bearer Token Authentication

All API requests require a valid JWT token in the `Authorization` header:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Test Token Generation (Development Only)

In development mode, you can generate test tokens:

```bash
curl -X GET http://localhost:8000/test-token
```

Response:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "test_user": {
    "user_id": "load-test-user",
    "tenant_id": "test-tenant-1",
    "email": "load-test@datafoundry.com",
    "role": "user"
  }
}
```

**WARNING:** This endpoint is only available in DEBUG mode and should be disabled in production.

### Required Token Claims

The JWT token must include:

```json
{
  "sub": "user_123",
  "exp": 1735689425,
  "iat": 1735685825
}
```

| Claim | Type | Description |
|-------|------|-------------|
| `sub` | string | Subject/user identifier |
| `exp` | int | Token expiration (Unix timestamp) |
| `iat` | int | Token issued at (Unix timestamp) |

### Tenant Isolation

All API operations are scoped to a tenant. In development, the `X-Tenant-ID` header is used:

```http
X-Tenant-ID: test-tenant-001
```

If not provided, defaults to `test-tenant-001`.

In production, tenant ID would be extracted from JWT token claims.

---

## 3. AML Processing Architecture

### How AML Works in the Generic System

1. **Upload AML Transaction Data**
   - Upload a CSV file containing transactions to `/api/v1/upload`
   - Specify `vertical=aml` in form data
   - File is stored and a job is created

2. **Job Processing**
   - Job status available at `/api/v1/jobs/{job_id}`
   - AML metadata embedded in job status when complete:
     - `aml_risk_level_counts`: Distribution of risk levels
     - `aml_inter_rater_agreement`: Cohen's Kappa for AI-expert agreement
     - `aml_expert_review_count`: Labels reviewed by experts
     - `aml_audit_report_url`: Link to compliance audit report

3. **Download Results**
   - GET `/api/v1/jobs/{job_id}/results` returns CSV with AML labels
   - Each transaction includes: risk_level, typology, confidence_score, reasoning

### Job Status Flow

| Status | Description |
|--------|-------------|
| `pending` | Job created, waiting to start |
| `processing` | AML labeling in progress |
| `complete` | All transactions labeled successfully |
| `failed` | Job failed (check error_message) |
| `cancelled` | Job was cancelled by user |

---

## 4. Endpoints (Detailed)

### 4.1 POST /api/v1/upload

Upload a file containing AML transaction data for processing.

**Request:**

```http
POST /api/v1/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>
X-Tenant-ID: tenant-001

file: <CSV file with transactions>
vertical: aml
auto_start: true
```

**Request Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | file | Yes | CSV file with AML transaction data |
| `vertical` | string | No | Industry vertical (use `aml` for AML processing) |
| `auto_start` | boolean | No | Automatically start processing (default: true) |

**CSV Format for AML Transactions:**

The uploaded CSV should contain transaction data:

```csv
transaction_id,sender_id,recipient_id,recipient_country,amount,currency,timestamp,payment_method,sender_country,reference
txn_001,cust_001,merchant_001,BR,8500.00,USD,2025-12-30T14:00:00Z,wire_transfer,US,Payment
txn_002,cust_002,merchant_002,MX,25000.00,USD,2025-12-30T15:30:00Z,wire_transfer,US,Invoice
```

**Response (201 Created):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "transactions.csv",
  "size_bytes": 1048576,
  "complexity_tier": "moderate",
  "estimated_cost": "0.024",
  "status": "pending",
  "storage_key": "tenant-001/job_550e8400...csv",
  "created_at": "2025-12-31T15:30:45Z"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 201 | File uploaded successfully |
| 400 | Bad Request (invalid file, validation error) |
| 401 | Unauthorized (missing or invalid JWT token) |
| 413 | File too large |
| 500 | Storage error |

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001" \
  -F "file=@transactions.csv" \
  -F "vertical=aml" \
  -F "auto_start=true"
```

---

### 4.2 GET /api/v1/jobs/{job_id}

Get the status of a processing job, including AML-specific metrics.

**Request:**

```http
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer <token>
X-Tenant-ID: tenant-001
```

**Response (Processing - 200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "tenant-001",
  "status": "processing",
  "file_name": "transactions.csv",
  "file_size": 1048576,
  "complexity_tier": "moderate",
  "estimated_cost": "0.024",
  "created_at": "2025-12-31T15:30:45Z",
  "started_at": "2025-12-31T15:30:50Z",
  "result_records": null,
  "result_url": null,
  "error_message": null,
  "retry_count": 0,
  "can_retry": false,
  "aml_risk_level_counts": null,
  "aml_inter_rater_agreement": null,
  "aml_expert_review_count": null,
  "aml_audit_report_url": null
}
```

**Response (Complete - 200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "tenant-001",
  "status": "complete",
  "file_name": "transactions.csv",
  "file_size": 1048576,
  "complexity_tier": "moderate",
  "estimated_cost": "0.024",
  "actual_cost": "0.021",
  "created_at": "2025-12-31T15:30:45Z",
  "started_at": "2025-12-31T15:30:50Z",
  "completed_at": "2025-12-31T15:35:32Z",
  "result_records": 500,
  "result_url": "https://storage.example.com/results/job_550e8400...csv",
  "error_message": null,
  "retry_count": 0,
  "can_retry": false,
  "aml_risk_level_counts": {
    "LOW": 385,
    "MEDIUM": 85,
    "HIGH": 25,
    "CRITICAL": 5
  },
  "aml_inter_rater_agreement": 0.76,
  "aml_expert_review_count": 30,
  "aml_audit_report_url": "https://storage.example.com/audit/reports/job-123.pdf"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Job status retrieved successfully |
| 404 | Job ID not found |
| 403 | Forbidden (tenant_id mismatch) |

**cURL Example:**

```bash
curl -X GET http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001"
```

---

### 4.3 GET /api/v1/jobs

List all jobs with filtering and pagination.

**Request:**

```http
GET /api/v1/jobs?status=complete&limit=20&offset=0
Authorization: Bearer <token>
X-Tenant-ID: tenant-001
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by status: pending, processing, complete, failed, cancelled |
| `limit` | int | No | Number of results per page (1-100, default: 20) |
| `offset` | int | No | Pagination offset (default: 0) |

**Response (200 OK):**

```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "tenant_id": "tenant-001",
      "status": "complete",
      "file_name": "transactions.csv",
      "file_size": 1048576,
      "complexity_tier": "moderate",
      "estimated_cost": "0.024",
      "actual_cost": "0.021",
      "created_at": "2025-12-31T15:30:45Z",
      "started_at": "2025-12-31T15:30:50Z",
      "completed_at": "2025-12-31T15:35:32Z",
      "result_records": 500,
      "result_url": "https://storage.example.com/results/...",
      "error_message": null,
      "retry_count": 0,
      "can_retry": false,
      "aml_risk_level_counts": {
        "LOW": 385,
        "MEDIUM": 85,
        "HIGH": 25,
        "CRITICAL": 5
      },
      "aml_inter_rater_agreement": 0.76,
      "aml_expert_review_count": 30,
      "aml_audit_report_url": "https://storage.example.com/audit/reports/job-123.pdf"
    }
  ],
  "total": 45,
  "limit": 20,
  "offset": 0,
  "has_more": true
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Jobs list retrieved successfully |
| 400 | Bad Request (invalid query parameters) |
| 401 | Unauthorized |

**cURL Example:**

```bash
curl -X GET "http://localhost:8000/api/v1/jobs?status=complete&limit=20" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001"
```

---

### 4.4 GET /api/v1/jobs/{job_id}/results

Download AML labeling results as CSV.

**Request:**

```http
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/results
Authorization: Bearer <token>
X-Tenant-ID: tenant-001
```

**Response (200 OK - CSV):**

```http
Content-Type: text/csv
Content-Disposition: attachment; filename="job_550e8400..._aml_results.csv"

job_id,transaction_id,sender_id,recipient_id,risk_level,typology,confidence_score,ai_reasoning,regulatory_flags,expert_review_status,is_audit_ready,created_at,updated_at
550e8400...,txn_001,cust_001,merchant_001,HIGH,STRUCTURING,0.87,"Transaction exhibits structuring behavior...", "{\"fincen_sar\": true}",PENDING,true,2025-12-31T15:30:50Z,2025-12-31T15:30:50Z
550e8400...,txn_002,cust_002,merchant_002,MEDIUM,LAYERING,0.72,"Cross-border transfer to Mexico...", "{\"fatf_r10\": true}",PENDING,true,2025-12-31T15:30:51Z,2025-12-31T15:30:51Z
...
```

**CSV Fields:**

| Field | Description |
|-------|-------------|
| `job_id` | Job identifier |
| `transaction_id` | Transaction identifier |
| `sender_id` | Sender/customer ID |
| `recipient_id` | Recipient/merchant ID |
| `risk_level` | AML risk level (LOW, MEDIUM, HIGH, CRITICAL) |
| `typology` | FATF typology code |
| `confidence_score` | AI model confidence (0.0 - 1.0) |
| `ai_reasoning` | AI model explanation |
| `regulatory_flags` | JSON of regulatory compliance flags |
| `expert_review_status` | Expert review status (PENDING, AGREED, DISPUTED) |
| `is_audit_ready` | Whether label is audit-ready |
| `created_at` | Label creation timestamp |
| `updated_at` | Label last update timestamp |

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Results ready for download |
| 404 | Job ID not found, job not complete, or no labels found |
| 403 | Forbidden (tenant_id mismatch) |

**cURL Example:**

```bash
curl -X GET http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/results \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001" \
  --output aml_results.csv
```

---

### 4.5 GET /api/v1/jobs/{job_id}/download

Get download URL for job results.

**Request:**

```http
GET /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/download
Authorization: Bearer <token>
X-Tenant-ID: tenant-001
```

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "download_url": "https://storage.example.com/results/job_550e8400...csv",
  "expires_in_seconds": 3600
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Download URL retrieved successfully |
| 400 | Job is not complete |
| 404 | Job ID not found or no results available |
| 403 | Forbidden (tenant_id mismatch) |

**cURL Example:**

```bash
curl -X GET http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/download \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001"
```

---

### 4.6 POST /api/v1/jobs/{job_id}/retry

Retry a failed job.

**Request:**

```http
POST /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/retry
Authorization: Bearer <token>
X-Tenant-ID: tenant-001
```

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "retry_count": 1,
  "message": "Job queued for retry (attempt 1)"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Job queued for retry |
| 400 | Job cannot be retried (not in FAILED status) |
| 404 | Job ID not found |
| 403 | Forbidden (tenant_id mismatch) |

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/retry \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001"
```

---

### 4.7 POST /api/v1/jobs/{job_id}/cancel

Cancel a pending or processing job.

**Request:**

```http
POST /api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/cancel
Authorization: Bearer <token>
X-Tenant-ID: tenant-001

{
  "reason": "No longer needed"
}
```

**Request Body:**

```json
{
  "reason": "Reason for cancellation (optional)"
}
```

**Response (200 OK):**

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "tenant-001",
  "status": "cancelled",
  "file_name": "transactions.csv",
  "file_size": 1048576,
  "complexity_tier": "moderate",
  "estimated_cost": "0.024",
  "created_at": "2025-12-31T15:30:45Z",
  "started_at": "2025-12-31T15:30:50Z",
  "completed_at": null,
  "result_records": null,
  "result_url": null,
  "error_message": "Cancelled by user: No longer needed",
  "retry_count": 0,
  "can_retry": false,
  "aml_risk_level_counts": null,
  "aml_inter_rater_agreement": null,
  "aml_expert_review_count": null,
  "aml_audit_report_url": null
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Job cancelled successfully |
| 400 | Job cannot be cancelled (already complete) |
| 404 | Job ID not found |
| 403 | Forbidden (tenant_id mismatch) |

**cURL Example:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000/cancel \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Tenant-ID: tenant-001" \
  -H "Content-Type: application/json" \
  -d '{"reason": "No longer needed"}'
```

---

### 4.8 GET /api/v1/upload/supported-types

Get supported file types and size limits.

**Request:**

```http
GET /api/v1/upload/supported-types
```

**Response (200 OK):**

```json
{
  "supported_types": ["csv", "json", "xlsx", "pdf", "parquet"],
  "max_size_bytes": 104857600,
  "max_size_mb": 100.0
}
```

**cURL Example:**

```bash
curl -X GET http://localhost:8000/api/v1/upload/supported-types
```

---

## 5. Data Models (Pydantic Schemas)

### JobStatusContract

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

class JobStatusContract(BaseModel):
    """Job status details with AML-specific metrics."""

    job_id: str
    tenant_id: str
    status: str

    # File info
    file_name: str
    file_size: int
    complexity_tier: str

    # Cost
    estimated_cost: str
    actual_cost: Optional[str] = None

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    result_records: Optional[int] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None

    # Retry info
    retry_count: int = 0
    can_retry: bool = False

    # AML-specific fields
    aml_risk_level_counts: Optional[Dict[str, int]] = Field(
        None,
        description="Distribution of AML risk levels (LOW, MEDIUM, HIGH, CRITICAL)"
    )
    aml_inter_rater_agreement: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Cohen's Kappa coefficient measuring AI-expert agreement"
    )
    aml_expert_review_count: Optional[int] = Field(
        None,
        ge=0,
        description="Number of AML labels reviewed by human experts"
    )
    aml_audit_report_url: Optional[str] = Field(
        None,
        description="URL to generated AML compliance audit report"
    )
```

### AMLMetricsContract

```python
class AMLMetricsContract(BaseModel):
    """AML processing metrics and statistics."""

    total_transactions: int
    risk_distribution: Dict[str, int]
    typology_distribution: Dict[str, int]
    average_confidence: float
    expert_review_count: int
    inter_rater_agreement: Optional[float] = None
```

### AMLTransactionLabelContract

```python
class AMLTransactionLabelContract(BaseModel):
    """Individual AML transaction label details."""

    transaction_id: str
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    typologies: List[str]
    confidence_score: float
    reasoning: str
    regulatory_flags: List[str] = []
    expert_review_status: str = "PENDING"
```

---

## 6. Error Codes & Responses

### 400 Bad Request

```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid file type",
    "errors": ["Supported types: csv, json, xlsx, pdf, parquet"]
  }
}
```

### 401 Unauthorized

```json
{
  "detail": "Could not validate credentials"
}
```

### 403 Forbidden

```json
{
  "detail": "Access denied to this job"
}
```

### 404 Not Found

```json
{
  "detail": "Job not found: 550e8400-e29b-41d4-a716-446655440000"
}
```

### 413 Payload Too Large

```json
{
  "detail": {
    "code": "FILE_TOO_LARGE",
    "message": "File size exceeds maximum allowed size"
  }
}
```

### 500 Internal Server Error

```json
{
  "error": {
    "type": "internal_server_error",
    "detail": "An internal error occurred"
  }
}
```

---

## 7. Example Client Implementation

### Python Client

```python
import requests
import time
import pandas as pd
from typing import Optional

class AMLServiceClient:
    """
    Data Foundry AML Service Client

    Provides methods for AML transaction labeling through the generic
    job-based processing architecture.
    """

    def __init__(
        self,
        api_token: str,
        base_url: str = "http://localhost:8000",
        tenant_id: Optional[str] = None
    ):
        self.api_token = api_token
        self.base_url = base_url.rstrip('/')
        self.tenant_id = tenant_id or "test-tenant-001"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "X-Tenant-ID": self.tenant_id
        })

    def upload_transactions(
        self,
        file_path: str,
        auto_start: bool = True
    ) -> dict:
        """
        Upload a CSV file containing AML transaction data.

        Args:
            file_path: Path to CSV file with transaction data
            auto_start: Whether to automatically start processing

        Returns:
            Job information with job_id for tracking
        """
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {
                'vertical': 'aml',
                'auto_start': str(auto_start).lower()
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/upload",
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    def get_job_status(self, job_id: str) -> dict:
        """Get the status of a processing job."""
        response = self.session.get(
            f"{self.base_url}/api/v1/jobs/{job_id}"
        )
        response.raise_for_status()
        return response.json()

    def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int = 10,
        timeout: int = 600
    ) -> dict:
        """
        Wait for job completion by polling status.

        Args:
            job_id: Job identifier to poll
            poll_interval: Seconds between polls (default: 10)
            timeout: Maximum seconds to wait (default: 600)

        Returns:
            Completed job data with AML metrics

        Raises:
            TimeoutError: If job doesn't complete within timeout
        """
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Job {job_id} did not complete within {timeout} seconds"
                )

            job = self.get_job_status(job_id)
            status = job["status"]

            if status == "complete":
                return job
            elif status == "failed":
                raise Exception(
                    f"Job {job_id} failed: {job.get('error_message', 'Unknown error')}"
                )
            elif status in ["pending", "processing"]:
                print(f"Status: {status}")
                time.sleep(poll_interval)

    def download_results(
        self,
        job_id: str,
        output_path: str
    ) -> None:
        """
        Download AML labeling results to a CSV file.

        Args:
            job_id: Job identifier
            output_path: Path to save the CSV file
        """
        response = self.session.get(
            f"{self.base_url}/api/v1/jobs/{job_id}/results"
        )
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

    def download_results_as_dataframe(
        self,
        job_id: str
    ) -> pd.DataFrame:
        """
        Download AML labeling results as a pandas DataFrame.

        Args:
            job_id: Job identifier

        Returns:
            DataFrame with AML labeling results
        """
        response = self.session.get(
            f"{self.base_url}/api/v1/jobs/{job_id}/results"
        )
        response.raise_for_status()

        from io import StringIO
        return pd.read_csv(StringIO(response.text))

    def list_jobs(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """List jobs with filtering."""
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = self.session.get(
            f"{self.base_url}/api/v1/jobs",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def cancel_job(
        self,
        job_id: str,
        reason: Optional[str] = None
    ) -> dict:
        """Cancel a pending or processing job."""
        data = {"reason": reason} if reason else {}
        response = self.session.post(
            f"{self.base_url}/api/v1/jobs/{job_id}/cancel",
            json=data
        )
        response.raise_for_status()
        return response.json()

    def retry_job(self, job_id: str) -> dict:
        """Retry a failed job."""
        response = self.session.post(
            f"{self.base_url}/api/v1/jobs/{job_id}/retry"
        )
        response.raise_for_status()
        return response.json()


# Usage example
if __name__ == "__main__":
    # Initialize client
    client = AMLServiceClient(
        api_token="your_jwt_token_here",
        base_url="http://localhost:8000",
        tenant_id="tenant-001"
    )

    # Step 1: Upload transaction data
    print("Uploading transactions...")
    job = client.upload_transactions(
        file_path="transactions.csv",
        auto_start=True
    )
    job_id = job["job_id"]
    print(f"Job created: {job_id}")

    # Step 2: Wait for completion
    print("Waiting for processing...")
    completed_job = client.wait_for_completion(job_id)
    print(f"Job completed!")

    # Step 3: Display AML metrics
    aml_metrics = {
        "risk_distribution": completed_job.get("aml_risk_level_counts"),
        "inter_rater_agreement": completed_job.get("aml_inter_rater_agreement"),
        "expert_review_count": completed_job.get("aml_expert_review_count"),
        "audit_report_url": completed_job.get("aml_audit_report_url")
    }
    print(f"AML Metrics: {aml_metrics}")

    # Step 4: Download results as DataFrame
    df = client.download_results_as_dataframe(job_id)
    print(f"\nResults: {len(df)} transactions labeled")
    print(df.head())

    # Analyze high-risk transactions
    high_risk = df[df['risk_level'] == 'HIGH']
    print(f"\nHigh-risk transactions: {len(high_risk)}")
    print(high_risk[['transaction_id', 'typology', 'confidence_score', 'ai_reasoning']])
```

---

## 8. Common Patterns

### Pattern 1: Upload, Process, and Download

```python
# Upload and process
job = client.upload_transactions("transactions.csv")
job_id = job["job_id"]

# Wait for completion
completed_job = client.wait_for_completion(job_id)

# Download results
df = client.download_results_as_dataframe(job_id)

# Filter high-risk transactions
high_risk = df[df['risk_level'].isin(['HIGH', 'CRITICAL'])]
print(f"Found {len(high_risk)} high-risk transactions")
```

### Pattern 2: Error Handling

```python
try:
    job = client.upload_transactions("transactions.csv")
    job_id = job["job_id"]

    completed_job = client.wait_for_completion(job_id, timeout=300)

except requests.exceptions.HTTPError as e:
    print(f"HTTP Error: {e.response.status_code}")
    print(f"Detail: {e.response.json()}")
except TimeoutError as e:
    print(f"Timeout: {e}")
    print("Consider increasing timeout or checking job status later")
except Exception as e:
    print(f"Error: {e}")
```

### Pattern 3: Batch Processing

```python
import os

# Process multiple files
for csv_file in os.listdir("data/"):
    if csv_file.endswith(".csv"):
        print(f"Processing {csv_file}...")
        job = client.upload_transactions(f"data/{csv_file}")
        job_id = job["job_id"]

        # Don't wait - just track the job
        print(f"  Job ID: {job_id}")

# Later, check status of all jobs
jobs = client.list_jobs(status="processing")
for job in jobs["jobs"]:
    print(f"Job {job['job_id']}: {job['status']}")
```

---

## 9. Testing

### Generate Test Token (Development Only)

```bash
# Get a test token for development
curl http://localhost:8000/test-token

# Use the returned access_token in subsequent requests
export JWT_TOKEN="<access_token_from_response>"
```

### Example Test Data

**CSV File (transactions.csv):**

```csv
transaction_id,sender_id,recipient_id,recipient_country,amount,currency,timestamp,payment_method,sender_country,reference
txn_001,cust_001,merchant_001,BR,8500.00,USD,2025-12-30T14:00:00Z,wire_transfer,US,Payment for services
txn_002,cust_002,merchant_002,MX,25000.00,USD,2025-12-30T15:30:00Z,wire_transfer,US,Invoice #12345
txn_003,cust_003,merchant_003,US,150.00,USD,2025-12-30T16:00:00Z,card,US,Retail purchase
```

### Complete Test Flow

```bash
# 1. Get test token
TOKEN=$(curl -s http://localhost:8000/test-token | jq -r '.access_token')

# 2. Upload transactions
JOB_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: test-tenant-001" \
  -F "file=@transactions.csv" \
  -F "vertical=aml" \
  -F "auto_start=true")

JOB_ID=$(echo $JOB_RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# 3. Check status
curl -X GET "http://localhost:8000/api/v1/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: test-tenant-001" | jq '.'

# 4. Wait for complete (polling)
while true; do
  STATUS=$(curl -s "http://localhost:8000/api/v1/jobs/$JOB_ID" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-Tenant-ID: test-tenant-001" | jq -r '.status')

  echo "Status: $STATUS"

  if [ "$STATUS" = "complete" ]; then
    break
  fi

  sleep 5
done

# 5. Download results
curl -X GET "http://localhost:8000/api/v1/jobs/$JOB_ID/results" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Tenant-ID: test-tenant-001" \
  --output aml_results.csv

echo "Results saved to aml_results.csv"
cat aml_results.csv
```

---

## 10. Summary

This API specification provides:

1. **Generic job-based processing** - AML labeling through upload/jobs architecture
2. **JWT authentication** - Bearer token-based authentication
3. **Tenant isolation** - Multi-tenancy via X-Tenant-ID header (development) or JWT claims (production)
4. **AML-embedded metadata** - AML metrics in job status responses
5. **CSV results download** - AML labels via job results endpoint
6. **Error handling** - Standard HTTP status codes with JSON error responses
7. **Python client example** - Ready-to-use client implementation

### Key Differences from Fictional Spec

| Fictional | Actual |
|-----------|--------|
| `/api/v1/aml/transactions/submit` | `/api/v1/upload` with AML CSV data |
| `/api/v1/aml/transactions/batch` | Same as above (process entire file) |
| `/api/v1/aml/jobs/{id}` | `/api/v1/jobs/{id}` (generic job endpoint) |
| `/api/v1/aml/jobs/{id}/download` | `/api/v1/jobs/{id}/results` (CSV download) |
| `/api/v1/aml/transactions/{id}` | Not available (query results CSV instead) |
| `/api/v1/aml/regulatory-context` | Not available (see Regulatory Reference docs) |
| Dedicated quota endpoints | Not implemented |

### AML-Specific Fields

AML functionality is accessed through these fields in job responses:

- `aml_risk_level_counts`: Risk distribution
- `aml_inter_rater_agreement`: Quality metric
- `aml_expert_review_count`: Human review count
- `aml_audit_report_url`: Compliance report link

### Related Documentation

- **IMPLEMENTATION_PLAN.md**: Development roadmap
- **REGULATORY_REFERENCE.md**: Complete regulatory framework
- **INDEX.md**: Documentation overview

---

**Document Version:** 2.0 (Aligned with actual codebase)
**Last Updated:** December 31, 2025
**API Version:** v1
**Base URL:** http://localhost:8000 (development)
