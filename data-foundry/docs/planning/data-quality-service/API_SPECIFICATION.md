# Data Quality Service - API Specification

## 1. Overview

The Data Quality Service API provides real-time data validation and quality scoring for any JSON record. This RESTful API enables data engineering teams to validate records before processing, track quality trends over time, and export validation reports.

### Base URL

```
Production:  https://api.datafoundry.com
Staging:     https://staging-api.datafoundry.com
Development: http://localhost:8000
```

### API Version

Current version: `v1`

All endpoints are prefixed with `/api/v1/quality`

### Response Format

All responses are JSON-formatted with standard structure:

```json
{
  "data": { ... },
  "metadata": {
    "timestamp": "2025-01-31T15:30:45Z",
    "processing_time_ms": 23
  }
}
```

### Common Headers

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <jwt_token>
X-Request-ID: <unique-request-id>  (optional, for tracking)
```

**Response Headers:**
```
Content-Type: application/json
X-Request-ID: <request-id>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: <remaining>
X-RateLimit-Reset: <unix-timestamp>
```

---

## 2. Authentication & Authorization

### JWT Bearer Token Authentication

All API requests require a valid JWT token in the `Authorization` header:

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### How to Obtain a Token

**Option 1: Via Authentication Endpoint** (if using Data Foundry Auth)
```bash
curl -X POST https://api.datafoundry.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Option 2: Via API Key** (for server-to-server integration)
```bash
curl -X POST https://api.datafoundry.com/api/v1/auth/token \
  -H "X-API-Key: df_live_abc123def456"
```

### Required Token Claims

The JWT token must include:

```json
{
  "user_id": "user_123",
  "tenant_id": "tenant_456",
  "tier": "pro",
  "exp": 1704070845,
  "iat": 1704067245
}
```

| Claim | Type | Description |
|-------|------|-------------|
| `user_id` | string | Unique user identifier |
| `tenant_id` | string | Tenant/organization identifier |
| `tier` | string | Subscription tier: free, pro, business, enterprise |
| `exp` | int | Token expiration (Unix timestamp) |
| `iat` | int | Token issued at (Unix timestamp) |

### Tenant Isolation

All API operations are scoped to the `tenant_id` in the JWT token. Cross-tenant access is prevented:

```
Token tenant_id: "tenant_456"
Request path: /api/v1/quality/scores?tenant_id=tenant_789

Result: 403 Forbidden (tenant_id mismatch)
```

**How It Works:**
1. JWT token is validated and decoded
2. `tenant_id` is extracted from token claims
3. All database queries are filtered by `WHERE tenant_id = ?`
4. Users can only access their own tenant's data

### Example Token

```json
{
  "user_id": "user_abc123",
  "tenant_id": "tenant_xyz789",
  "tier": "pro",
  "email": "engineer@company.com",
  "exp": 1704070845,
  "iat": 1704067245,
  "jti": "token_unique_id_123"
}
```

---

## 3. Rate Limiting & Quotas

### Per-Tier Monthly Quotas

| Tier | Validations/Month | Batch Size Limit | Monthly Cost |
|------|-------------------|------------------|--------------|
| Free | 500 | 100 records | $0 |
| Pro | 50,000 | 10,000 records | $99/month |
| Business | 500,000 | Unlimited | $499/month |
| Enterprise | Unlimited | Unlimited | Custom |

### Per-Minute Request Limits

| Tier | Requests/Minute | Requests/Hour |
|------|----------------|---------------|
| Free | 10 | 100 |
| Pro | 100 | 1,000 |
| Business | 1,000 | Unlimited |
| Enterprise | Custom | Custom |

### Rate Limit Response Headers

Every API response includes rate limit information:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1704067860
```

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed in current window |
| `X-RateLimit-Remaining` | Requests remaining in current window |
| `X-RateLimit-Reset` | Unix timestamp when limit resets |

### Quota Checking

Check your current quota usage:

```bash
GET /api/v1/quality/quota
Authorization: Bearer <token>
```

Response:
```json
{
  "quota": {
    "tier": "pro",
    "period": "2025-01",
    "used": 12450,
    "limit": 50000,
    "remaining": 37550,
    "percentage_used": 24.9,
    "resets_at": "2025-02-01T00:00:00Z"
  }
}
```

### Quota Exceeded Response

When quota is exceeded, API returns `402 Payment Required`:

```json
{
  "error": "quota_exceeded",
  "message": "Your Pro tier allows 50,000 validations per month",
  "quota": {
    "used": 50000,
    "limit": 50000,
    "remaining": 0,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "recommendation": "Upgrade to Business tier (500,000/month) or wait for monthly reset",
  "upgrade_url": "https://datafoundry.com/billing/upgrade"
}
```

---

## 4. Endpoints (Detailed)

### 4.1 POST /api/v1/quality/validate

Validate a single data record and receive quality scores immediately.

**Request:**

```http
POST /api/v1/quality/validate
Content-Type: application/json
Authorization: Bearer <token>

{
  "record": {
    "customer_id": "cust_123",
    "email": "john@example.com",
    "phone": "+1-555-0100",
    "country": "US",
    "age": 35,
    "created_at": "2025-01-31T10:00:00Z"
  }
}
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `record` | object | Yes | Any JSON object (max 1MB) |

**Response (Success - 200 OK):**

```json
{
  "validation_result": {
    "is_valid": true,
    "completeness_score": 1.0,
    "validity_score": 1.0,
    "quality_score": 1.0,
    "errors": [],
    "warnings": [],
    "fields_checked": 6,
    "fields_valid": 6,
    "field_details": {
      "customer_id": { "present": true, "valid": true },
      "email": { "present": true, "valid": true, "format": "email" },
      "phone": { "present": true, "valid": true, "format": "e164" },
      "country": { "present": true, "valid": true, "format": "iso3166" },
      "age": { "present": true, "valid": true, "type": "integer", "range": "0-150" },
      "created_at": { "present": true, "valid": true, "format": "iso8601" }
    }
  },
  "quota": {
    "used": 451,
    "limit": 500,
    "remaining": 49,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "metadata": {
    "processing_time_ms": 23,
    "timestamp": "2025-01-31T15:30:45Z"
  }
}
```

**Response (Invalid Record - 200 OK):**

Note: Status is still 200 because validation *succeeded* (the record is just invalid):

```json
{
  "validation_result": {
    "is_valid": false,
    "completeness_score": 0.67,
    "validity_score": 0.50,
    "quality_score": 0.60,
    "errors": [
      {
        "field": "email",
        "error_code": "INVALID_EMAIL_FORMAT",
        "message": "Email format is invalid",
        "value": "not_an_email"
      },
      {
        "field": "age",
        "error_code": "INVALID_INTEGER_TYPE",
        "message": "Expected integer, got string",
        "value": "twenty-five"
      }
    ],
    "warnings": [
      {
        "field": "phone",
        "warning_code": "OPTIONAL_FIELD_MISSING",
        "message": "Recommended field is missing"
      }
    ],
    "fields_checked": 3,
    "fields_valid": 1
  },
  "quota": {
    "used": 451,
    "limit": 500,
    "remaining": 49,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "metadata": {
    "processing_time_ms": 18,
    "timestamp": "2025-01-31T15:30:45Z"
  }
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Validation completed successfully (record may be valid or invalid) |
| 400 | Bad Request (malformed JSON, record > 1MB) |
| 401 | Unauthorized (missing or invalid JWT token) |
| 403 | Forbidden (tenant_id mismatch) |
| 429 | Too Many Requests (rate limit exceeded) |

**cURL Example:**

```bash
curl -X POST https://api.datafoundry.com/api/v1/quality/validate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "record": {
      "customer_id": "cust_123",
      "email": "john@example.com",
      "phone": "+1-555-0100",
      "country": "US",
      "age": 35
    }
  }'
```

---

### 4.2 POST /api/v1/quality/validate-batch

Submit a batch of records for asynchronous validation. Returns immediately with a job ID.

**Request:**

```http
POST /api/v1/quality/validate-batch
Content-Type: application/json
Authorization: Bearer <token>

{
  "records": [
    {
      "customer_id": "cust_001",
      "email": "alice@example.com",
      "phone": "+1-555-0101",
      "country": "US",
      "age": 28
    },
    {
      "customer_id": "cust_002",
      "email": "bob@invalid",
      "phone": "555-0102",
      "country": "UK",
      "age": "thirty-five"
    }
  ],
  "webhook_url": "https://yourapp.com/webhooks/validation-complete",
  "metadata": {
    "batch_name": "January Customer Import",
    "source": "salesforce_export"
  }
}
```

**Request Schema:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `records` | array | Yes | Array of records to validate (1-10,000) |
| `webhook_url` | string | No | URL to receive completion notification |
| `metadata` | object | No | Custom metadata for tracking |

**Response (202 Accepted):**

```json
{
  "job_id": "job_abc123def456",
  "status": "queued",
  "total_records": 2,
  "estimated_completion_seconds": 120,
  "created_at": "2025-01-31T15:30:45Z",
  "status_url": "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/status",
  "download_url": "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export"
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 202 | Accepted - Job queued for processing |
| 400 | Bad Request (invalid records, batch too large) |
| 401 | Unauthorized (missing or invalid JWT token) |
| 402 | Payment Required (quota exceeded) |
| 429 | Too Many Requests (rate limit exceeded) |

**Quota Check:**

If batch size exceeds remaining quota:

```json
{
  "error": "quota_exceeded",
  "message": "Batch size (10,000 records) exceeds remaining quota (5,000 records)",
  "quota": {
    "used": 45000,
    "limit": 50000,
    "remaining": 5000,
    "requested": 10000,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "recommendation": "Reduce batch size to 5,000 records or upgrade to Business tier"
}
```

**cURL Example:**

```bash
curl -X POST https://api.datafoundry.com/api/v1/quality/validate-batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "records": [
      {
        "customer_id": "cust_001",
        "email": "alice@example.com",
        "phone": "+1-555-0101",
        "age": 28
      },
      {
        "customer_id": "cust_002",
        "email": "bob@example.com",
        "phone": "+1-555-0102",
        "age": 35
      }
    ],
    "webhook_url": "https://yourapp.com/webhooks/validation-complete"
  }'
```

---

### 4.3 GET /api/v1/quality/batch/{job_id}/status

Check the status of a batch validation job.

**Request:**

```http
GET /api/v1/quality/batch/job_abc123def456/status
Authorization: Bearer <token>
```

**Response (Processing - 200 OK):**

```json
{
  "job_id": "job_abc123def456",
  "status": "processing",
  "progress": {
    "records_processed": 2500,
    "total_records": 5000,
    "percentage": 50.0
  },
  "eta_seconds": 150,
  "estimated_completion": "2025-01-31T15:35:00Z",
  "started_at": "2025-01-31T15:30:45Z"
}
```

**Response (Completed - 200 OK):**

```json
{
  "job_id": "job_abc123def456",
  "status": "completed",
  "summary": {
    "total_records": 5000,
    "valid_records": 4823,
    "invalid_records": 177,
    "avg_quality_score": 0.94,
    "avg_completeness": 0.98,
    "avg_validity": 0.91,
    "processing_duration_seconds": 287
  },
  "top_errors": [
    {
      "error_code": "INVALID_EMAIL_FORMAT",
      "count": 89,
      "percentage": 50.3,
      "example": "user@invalid"
    },
    {
      "error_code": "MISSING_REQUIRED_FIELD",
      "field": "phone",
      "count": 63,
      "percentage": 35.6
    }
  ],
  "download_url": "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export",
  "expires_at": "2025-02-07T15:30:45Z",
  "started_at": "2025-01-31T15:30:45Z",
  "completed_at": "2025-01-31T15:35:32Z"
}
```

**Job Status Values:**

| Status | Description |
|--------|-------------|
| `queued` | Job is waiting to start |
| `processing` | Validation is in progress |
| `completed` | All records validated successfully |
| `failed` | Job failed (system error) |
| `expired` | Results expired (7 days after completion) |

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Status retrieved successfully |
| 404 | Job ID not found |

**cURL Example:**

```bash
curl -X GET https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/status \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### 4.4 POST /api/v1/quality/batch/{job_id}/export

Download batch validation results in CSV, JSON, or Parquet format.

**Request:**

```http
POST /api/v1/quality/batch/job_abc123def456/export?format=csv
Authorization: Bearer <token>
```

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `format` | string | No | `json` | Export format: `csv`, `json`, `parquet` |

**Response (200 OK - CSV):**

```http
Content-Type: text/csv
Content-Disposition: attachment; filename="validation_results_job_abc123def456.csv"

customer_id,email,phone,country,age,is_valid,quality_score,completeness_score,validity_score,errors,warnings
cust_001,alice@example.com,+1-555-0101,US,28,true,1.0,1.0,1.0,"",""
cust_002,bob@invalid,555-0102,UK,thirty-five,false,0.60,0.67,0.50,"INVALID_EMAIL_FORMAT|INVALID_INTEGER_TYPE","OPTIONAL_FIELD_MISSING:phone"
...
```

**Response (200 OK - JSON):**

```json
{
  "job_id": "job_abc123def456",
  "total_records": 5000,
  "results": [
    {
      "record": {
        "customer_id": "cust_001",
        "email": "alice@example.com",
        "phone": "+1-555-0101",
        "country": "US",
        "age": 28
      },
      "validation": {
        "is_valid": true,
        "quality_score": 1.0,
        "completeness_score": 1.0,
        "validity_score": 1.0,
        "errors": [],
        "warnings": []
      }
    },
    {
      "record": {
        "customer_id": "cust_002",
        "email": "bob@invalid",
        "phone": "555-0102",
        "country": "UK",
        "age": "thirty-five"
      },
      "validation": {
        "is_valid": false,
        "quality_score": 0.60,
        "completeness_score": 0.67,
        "validity_score": 0.50,
        "errors": [
          {
            "field": "email",
            "error_code": "INVALID_EMAIL_FORMAT",
            "message": "Email format is invalid"
          }
        ],
        "warnings": []
      }
    }
  ]
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Export file ready for download |
| 404 | Job ID not found or job not completed |
| 410 | Gone - Results expired (7 days after completion) |

**cURL Example:**

```bash
# Download as CSV
curl -X POST "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export?format=csv" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  --output validation_results.csv

# Download as JSON
curl -X POST "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export?format=json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  --output validation_results.json

# Download as Parquet
curl -X POST "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export?format=parquet" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  --output validation_results.parquet
```

---

### 4.5 GET /api/v1/quality/scores

Retrieve historical quality metrics and trends.

**Request:**

```http
GET /api/v1/quality/scores?period=2025-01&source=salesforce_export
Authorization: Bearer <token>
```

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `period` | string | No | YYYY-MM format (e.g., "2025-01") |
| `period_start` | string | No | ISO 8601 date (e.g., "2025-01-01") |
| `period_end` | string | No | ISO 8601 date (e.g., "2025-01-31") |
| `source` | string | No | Filter by data source (custom metadata) |

**Response (200 OK):**

```json
{
  "period": {
    "start": "2025-01-01T00:00:00Z",
    "end": "2025-01-31T23:59:59Z",
    "days": 31
  },
  "summary": {
    "total_records_validated": 150000,
    "avg_quality_score": 0.92,
    "min_quality_score": 0.87,
    "max_quality_score": 0.96,
    "avg_completeness": 0.94,
    "avg_validity": 0.91,
    "trend": "improving"
  },
  "daily_trends": [
    {
      "date": "2025-01-01",
      "quality_score": 0.90,
      "records_validated": 5000,
      "completeness": 0.93,
      "validity": 0.88
    },
    {
      "date": "2025-01-02",
      "quality_score": 0.91,
      "records_validated": 4800,
      "completeness": 0.94,
      "validity": 0.89
    }
  ],
  "top_errors": [
    {
      "error_type": "INVALID_EMAIL_FORMAT",
      "count": 1245,
      "percentage": 42,
      "affected_records": 1245,
      "trend": "stable"
    },
    {
      "error_type": "MISSING_PHONE",
      "count": 892,
      "percentage": 30,
      "affected_records": 892,
      "trend": "improving"
    }
  ],
  "field_quality": {
    "email": {
      "completeness": 0.98,
      "validity": 0.88,
      "quality": 0.93,
      "errors": 1245
    },
    "phone": {
      "completeness": 0.92,
      "validity": 0.97,
      "quality": 0.95,
      "errors": 892
    }
  },
  "recommendations": [
    "Focus on email validation - 42% of errors",
    "Phone field has low completeness (92%) - consider making required",
    "Quality improved 8% over month - trending positive"
  ]
}
```

**Status Codes:**

| Code | Description |
|------|-------------|
| 200 | Metrics retrieved successfully |
| 400 | Bad Request (invalid date range) |
| 401 | Unauthorized (missing or invalid JWT token) |

**cURL Example:**

```bash
curl -X GET "https://api.datafoundry.com/api/v1/quality/scores?period=2025-01&source=salesforce_export" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 5. Data Models (Pydantic Schemas)

### ValidationResult

```python
class ValidationResult(BaseModel):
    is_valid: bool
    completeness_score: float  # 0.0 - 1.0
    validity_score: float      # 0.0 - 1.0
    quality_score: float        # 0.0 - 1.0
    errors: List[Error]
    warnings: List[Warning]
    fields_checked: int
    fields_valid: int
```

### Error

```python
class Error(BaseModel):
    field: str
    error_code: str
    message: str
    value: Optional[Any] = None
```

**Common Error Codes:**

| Code | Description |
|------|-------------|
| `INVALID_EMAIL_FORMAT` | Email format doesn't match RFC 5322 |
| `INVALID_PHONE_FORMAT` | Phone not in E.164 format |
| `INVALID_INTEGER_TYPE` | Expected integer, got different type |
| `INVALID_DATE_FORMAT` | Date not in ISO 8601 format |
| `MISSING_REQUIRED_FIELD` | Required field is null or missing |
| `INVALID_COUNTRY_CODE` | Country code not ISO 3166-1 alpha-2 |
| `VALUE_OUT_OF_RANGE` | Numeric value outside expected range |

### Warning

```python
class Warning(BaseModel):
    field: str
    warning_code: str
    message: str
```

**Common Warning Codes:**

| Code | Description |
|------|-------------|
| `OPTIONAL_FIELD_MISSING` | Recommended field is missing |
| `SUSPICIOUS_PATTERN` | Field value matches suspicious pattern |
| `LOW_CONFIDENCE_FORMAT` | Format validation has low confidence |

### ValidationRequest

```python
class ValidationRequest(BaseModel):
    record: Dict[str, Any]  # Max 1MB
```

### BatchValidationRequest

```python
class BatchValidationRequest(BaseModel):
    records: List[Dict[str, Any]]  # 1-10,000 records, max 10MB total
    webhook_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

### BatchJobStatus

```python
class BatchJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed", "expired"]
    progress: Optional[ProgressInfo] = None
    eta_seconds: Optional[int] = None
    summary: Optional[BatchSummary] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
```

### BatchSummary

```python
class BatchSummary(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    avg_quality_score: float
    avg_completeness: float
    avg_validity: float
    processing_duration_seconds: int
```

### QualityMetrics

```python
class QualityMetrics(BaseModel):
    period: PeriodInfo
    summary: SummaryStats
    daily_trends: List[DailyTrend]
    top_errors: List[ErrorDistribution]
    field_quality: Dict[str, FieldQuality]
    recommendations: List[str]
```

### QuotaInfo

```python
class QuotaInfo(BaseModel):
    tier: str
    period: str  # YYYY-MM
    used: int
    limit: int
    remaining: int
    percentage_used: float
    resets_at: datetime
```

---

## 6. Error Codes & Responses

### 400 Bad Request

**Invalid Record Size:**
```json
{
  "error": "invalid_request",
  "message": "Record size exceeds maximum allowed size of 1MB",
  "details": {
    "record_size_bytes": 1572864,
    "max_size_bytes": 1048576
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

**Missing Required Field:**
```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "details": {
    "field": "record",
    "error": "Field required"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 401 Unauthorized

**Missing Token:**
```json
{
  "error": "unauthorized",
  "message": "Missing or invalid authorization token",
  "timestamp": "2025-01-31T15:30:45Z"
}
```

**Expired Token:**
```json
{
  "error": "token_expired",
  "message": "JWT token has expired",
  "details": {
    "expired_at": "2025-01-31T14:30:45Z"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 402 Payment Required

**Quota Exceeded:**
```json
{
  "error": "quota_exceeded",
  "message": "Your Pro tier allows 50,000 validations per month",
  "quota": {
    "used": 50000,
    "limit": 50000,
    "remaining": 0,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "recommendation": "Upgrade to Business tier (500,000/month)",
  "upgrade_url": "https://datafoundry.com/billing/upgrade",
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 403 Forbidden

**Cross-Tenant Access:**
```json
{
  "error": "forbidden",
  "message": "Access denied: tenant_id mismatch",
  "details": {
    "token_tenant_id": "tenant_456",
    "requested_tenant_id": "tenant_789"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 404 Not Found

**Batch Job Not Found:**
```json
{
  "error": "not_found",
  "message": "Batch job not found",
  "details": {
    "job_id": "job_invalid_123"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 410 Gone

**Results Expired:**
```json
{
  "error": "resource_expired",
  "message": "Batch results expired after 7 days",
  "details": {
    "job_id": "job_abc123def456",
    "completed_at": "2025-01-24T15:30:45Z",
    "expired_at": "2025-01-31T15:30:45Z"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

### 429 Too Many Requests

**Rate Limited:**
```json
{
  "error": "rate_limited",
  "message": "Too many requests. Rate limit: 10/minute for Free tier",
  "rate_limit": {
    "limit": 10,
    "remaining": 0,
    "reset_in_seconds": 35,
    "reset_at": "2025-01-31T15:31:35Z"
  },
  "timestamp": "2025-01-31T15:30:45Z"
}
```

**Response Headers:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 35
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704067895
```

### 503 Service Unavailable

**Database Error:**
```json
{
  "error": "service_unavailable",
  "message": "Data Quality Service is temporarily unavailable",
  "retry_after": 60,
  "status": "We're experiencing temporary issues. Please try again in 1 minute.",
  "timestamp": "2025-01-31T15:30:45Z"
}
```

**Response Headers:**
```http
HTTP/1.1 503 Service Unavailable
Retry-After: 60
```

---

## 7. Example Client Implementations

### cURL

**Single Record Validation:**
```bash
curl -X POST https://api.datafoundry.com/api/v1/quality/validate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -d '{
    "record": {
      "customer_id": "cust_123",
      "email": "john@example.com",
      "phone": "+1-555-0100",
      "country": "US",
      "age": 35
    }
  }'
```

**Batch Validation:**
```bash
curl -X POST https://api.datafoundry.com/api/v1/quality/validate-batch \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -d @batch_records.json
```

**Check Job Status:**
```bash
JOB_ID="job_abc123def456"
curl -X GET "https://api.datafoundry.com/api/v1/quality/batch/${JOB_ID}/status" \
  -H "Authorization: Bearer ${JWT_TOKEN}"
```

### Python SDK

```python
import requests
from typing import Dict, Any, List

class DataQualityClient:
    def __init__(self, api_key: str, base_url: str = "https://api.datafoundry.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def validate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single record."""
        response = self.session.post(
            f"{self.base_url}/api/v1/quality/validate",
            json={"record": record}
        )
        response.raise_for_status()
        return response.json()

    def validate_batch(
        self,
        records: List[Dict[str, Any]],
        webhook_url: str = None
    ) -> Dict[str, Any]:
        """Submit batch validation job."""
        payload = {"records": records}
        if webhook_url:
            payload["webhook_url"] = webhook_url

        response = self.session.post(
            f"{self.base_url}/api/v1/quality/validate-batch",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def get_batch_status(self, job_id: str) -> Dict[str, Any]:
        """Get batch job status."""
        response = self.session.get(
            f"{self.base_url}/api/v1/quality/batch/{job_id}/status"
        )
        response.raise_for_status()
        return response.json()

    def export_batch_results(
        self,
        job_id: str,
        format: str = "json"
    ) -> bytes:
        """Download batch results."""
        response = self.session.post(
            f"{self.base_url}/api/v1/quality/batch/{job_id}/export",
            params={"format": format}
        )
        response.raise_for_status()
        return response.content

    def get_quality_scores(
        self,
        period: str = None,
        period_start: str = None,
        period_end: str = None
    ) -> Dict[str, Any]:
        """Get historical quality metrics."""
        params = {}
        if period:
            params["period"] = period
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end

        response = self.session.get(
            f"{self.base_url}/api/v1/quality/scores",
            params=params
        )
        response.raise_for_status()
        return response.json()

    def check_quota(self) -> Dict[str, Any]:
        """Check current quota usage."""
        response = self.session.get(
            f"{self.base_url}/api/v1/quality/quota"
        )
        response.raise_for_status()
        return response.json()

# Usage example
client = DataQualityClient(api_key="your_jwt_token_here")

# Validate single record
result = client.validate_record({
    "customer_id": "cust_123",
    "email": "john@example.com",
    "phone": "+1-555-0100",
    "age": 35
})
print(f"Quality Score: {result['validation_result']['quality_score']}")

# Check quota
quota = client.check_quota()
print(f"Quota: {quota['quota']['used']}/{quota['quota']['limit']}")
```

### JavaScript/TypeScript

```typescript
interface ValidationResult {
  is_valid: boolean;
  completeness_score: number;
  validity_score: number;
  quality_score: number;
  errors: Error[];
  warnings: Warning[];
}

interface BatchJobResponse {
  job_id: string;
  status: string;
  total_records: number;
  estimated_completion_seconds: number;
}

class DataQualityClient {
  private apiKey: string;
  private baseUrl: string;

  constructor(apiKey: string, baseUrl: string = 'https://api.datafoundry.com') {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl;
  }

  private async request(endpoint: string, options: RequestInit = {}): Promise<any> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async validateRecord(record: Record<string, any>): Promise<ValidationResult> {
    const data = await this.request('/api/v1/quality/validate', {
      method: 'POST',
      body: JSON.stringify({ record }),
    });
    return data.validation_result;
  }

  async validateBatch(
    records: Record<string, any>[],
    webhookUrl?: string
  ): Promise<BatchJobResponse> {
    const payload: any = { records };
    if (webhookUrl) {
      payload.webhook_url = webhookUrl;
    }

    return this.request('/api/v1/quality/validate-batch', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getBatchStatus(jobId: string): Promise<any> {
    return this.request(`/api/v1/quality/batch/${jobId}/status`);
  }

  async exportBatchResults(
    jobId: string,
    format: 'json' | 'csv' | 'parquet' = 'json'
  ): Promise<Blob> {
    const response = await fetch(
      `${this.baseUrl}/api/v1/quality/batch/${jobId}/export?format=${format}`,
      {
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
        },
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return response.blob();
  }

  async getQualityScores(params: {
    period?: string;
    period_start?: string;
    period_end?: string;
  } = {}): Promise<any> {
    const queryString = new URLSearchParams(params).toString();
    return this.request(`/api/v1/quality/scores?${queryString}`);
  }

  async checkQuota(): Promise<any> {
    return this.request('/api/v1/quality/quota');
  }
}

// Usage example
const client = new DataQualityClient('your_jwt_token_here');

// Validate single record
const result = await client.validateRecord({
  customer_id: 'cust_123',
  email: 'john@example.com',
  phone: '+1-555-0100',
  age: 35,
});
console.log(`Quality Score: ${result.quality_score}`);

// Handle quota in headers
const quota = await client.checkQuota();
console.log(`Quota: ${quota.quota.used}/${quota.quota.limit}`);
```

### Handling Quota and Rate Limit Headers

**Python Example:**
```python
def validate_with_quota_check(client, record):
    """Validate and check remaining quota."""
    try:
        response = client.session.post(
            f"{client.base_url}/api/v1/quality/validate",
            json={"record": record}
        )

        # Check rate limit headers
        remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
        limit = int(response.headers.get('X-RateLimit-Limit', 0))
        reset = int(response.headers.get('X-RateLimit-Reset', 0))

        print(f"Rate Limit: {remaining}/{limit} remaining")

        if remaining < 10:
            print(f"Warning: Only {remaining} requests remaining")
            print(f"Limit resets at: {datetime.fromtimestamp(reset)}")

        result = response.json()
        quota = result.get('quota', {})

        if quota.get('remaining', 0) < 100:
            print(f"Warning: Only {quota['remaining']} validations remaining in quota")

        return result

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            retry_after = int(e.response.headers.get('Retry-After', 60))
            print(f"Rate limited. Retry after {retry_after} seconds")
            time.sleep(retry_after)
            return validate_with_quota_check(client, record)
        raise
```

**JavaScript Example:**
```javascript
async function validateWithQuotaCheck(client, record) {
  try {
    const response = await fetch(`${client.baseUrl}/api/v1/quality/validate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${client.apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ record }),
    });

    // Check rate limit headers
    const remaining = parseInt(response.headers.get('X-RateLimit-Remaining') || '0');
    const limit = parseInt(response.headers.get('X-RateLimit-Limit') || '0');
    const reset = parseInt(response.headers.get('X-RateLimit-Reset') || '0');

    console.log(`Rate Limit: ${remaining}/${limit} remaining`);

    if (remaining < 10) {
      console.warn(`Warning: Only ${remaining} requests remaining`);
      console.warn(`Limit resets at: ${new Date(reset * 1000)}`);
    }

    const data = await response.json();
    const quota = data.quota || {};

    if (quota.remaining < 100) {
      console.warn(`Warning: Only ${quota.remaining} validations remaining in quota`);
    }

    return data;

  } catch (error) {
    if (error.response?.status === 429) {
      const retryAfter = parseInt(error.response.headers.get('Retry-After') || '60');
      console.log(`Rate limited. Retrying after ${retryAfter} seconds`);
      await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
      return validateWithQuotaCheck(client, record);
    }
    throw error;
  }
}
```

---

## 8. Webhook Events

When you provide a `webhook_url` in batch validation requests, the service will send HTTP POST requests to that URL when processing completes.

### Event: validation.completed

Sent when batch validation finishes successfully.

**Webhook Request:**

```http
POST https://yourapp.com/webhooks/validation-complete
Content-Type: application/json
X-Webhook-Signature: sha256=abc123def456...
X-Webhook-ID: evt_abc123def456
X-Webhook-Timestamp: 1704067845

{
  "event": "validation.completed",
  "job_id": "job_abc123def456",
  "status": "completed",
  "summary": {
    "total_records": 5000,
    "valid_records": 4823,
    "invalid_records": 177,
    "avg_quality_score": 0.94,
    "processing_duration_seconds": 287
  },
  "download_url": "https://api.datafoundry.com/api/v1/quality/batch/job_abc123def456/export",
  "expires_at": "2025-02-07T15:30:45Z",
  "timestamp": "2025-01-31T15:35:32Z"
}
```

### Webhook Signature Verification

Verify webhook authenticity using HMAC-SHA256:

**Python Example:**
```python
import hmac
import hashlib

def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str
) -> bool:
    """Verify webhook signature."""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(
        f"sha256={expected_signature}",
        signature
    )

# In your webhook handler
@app.post("/webhooks/validation-complete")
async def handle_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get('X-Webhook-Signature')

    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    data = await request.json()

    # Process webhook event
    job_id = data['job_id']
    print(f"Batch {job_id} completed: {data['summary']}")

    return {"status": "received"}
```

### Retry Logic

The webhook service uses **Stripe-like exponential backoff**:

1. **Initial Attempt:** Immediate
2. **Retry 1:** After 5 seconds
3. **Retry 2:** After 15 seconds
4. **Retry 3:** After 45 seconds
5. **Retry 4:** After 2 minutes
6. **Retry 5:** After 5 minutes
7. **Final Retry:** After 15 minutes

**Total retry window:** ~23 minutes

**Success Criteria:**
- HTTP status codes: 200-299
- Response received within 10 seconds

**Failure Handling:**
- After final retry, webhook is marked as failed
- Event is stored for manual inspection
- You can re-trigger via support

**Idempotency:**
- Same `X-Webhook-ID` for all retry attempts
- Your service should handle duplicate deliveries

---

## 9. Common Patterns

### Pattern 1: Checking Quota Remaining

**Before submitting batch:**
```python
# Check quota before batch submission
quota = client.check_quota()

if quota['quota']['remaining'] < len(records):
    print(f"Insufficient quota: {quota['quota']['remaining']} remaining, need {len(records)}")
    print(f"Upgrade at: {quota.get('upgrade_url')}")
    return

# Submit batch
job = client.validate_batch(records)
```

**From response headers:**
```python
response = client.validate_record(record)

# Extract quota from response body
quota_info = response.get('quota', {})
remaining = quota_info.get('remaining', 0)

if remaining < 100:
    print(f"Warning: Only {remaining} validations left this month")
```

### Pattern 2: Async Batch Jobs (Polling)

**Polling approach:**
```python
import time

def wait_for_batch_completion(client, job_id, poll_interval=30):
    """Poll batch job until completion."""
    while True:
        status = client.get_batch_status(job_id)

        if status['status'] == 'completed':
            print(f"Batch completed: {status['summary']}")
            return status

        elif status['status'] == 'failed':
            raise Exception(f"Batch failed: {status.get('error')}")

        elif status['status'] == 'processing':
            progress = status.get('progress', {})
            pct = progress.get('percentage', 0)
            eta = status.get('eta_seconds', 0)
            print(f"Progress: {pct}% complete, ETA: {eta}s")

        time.sleep(poll_interval)

# Usage
job = client.validate_batch(records)
result = wait_for_batch_completion(client, job['job_id'])

# Download results
csv_data = client.export_batch_results(job['job_id'], format='csv')
with open('results.csv', 'wb') as f:
    f.write(csv_data)
```

### Pattern 3: Async Batch Jobs (Webhook)

**Webhook approach:**
```python
# Submit batch with webhook
job = client.validate_batch(
    records=records,
    webhook_url="https://yourapp.com/webhooks/validation-complete"
)

print(f"Job submitted: {job['job_id']}")
print("Webhook will be called when complete")

# In your webhook handler (Flask example)
@app.post("/webhooks/validation-complete")
def handle_validation_complete():
    data = request.json
    job_id = data['job_id']

    # Download results
    client = DataQualityClient(api_key=API_KEY)
    results = client.export_batch_results(job_id, format='json')

    # Process results
    process_validation_results(results)

    return {"status": "received"}, 200
```

### Pattern 4: Export in Different Formats

**CSV for Excel/BI tools:**
```python
csv_data = client.export_batch_results(job_id, format='csv')
with open('validation_results.csv', 'wb') as f:
    f.write(csv_data)
```

**JSON for programmatic processing:**
```python
json_data = client.export_batch_results(job_id, format='json')
results = json.loads(json_data)

for item in results['results']:
    if not item['validation']['is_valid']:
        print(f"Invalid record: {item['record']}")
        print(f"Errors: {item['validation']['errors']}")
```

**Parquet for data science/ML:**
```python
parquet_data = client.export_batch_results(job_id, format='parquet')
with open('validation_results.parquet', 'wb') as f:
    f.write(parquet_data)

# Read with pandas
import pandas as pd
df = pd.read_parquet('validation_results.parquet')
print(df['quality_score'].describe())
```

### Pattern 5: Query Trends Over Time

**Monthly trends:**
```python
# Get January 2025 metrics
metrics = client.get_quality_scores(period='2025-01')

print(f"Average quality: {metrics['summary']['avg_quality_score']}")
print(f"Trend: {metrics['summary']['trend']}")

# Plot daily trends
import matplotlib.pyplot as plt

dates = [d['date'] for d in metrics['daily_trends']]
scores = [d['quality_score'] for d in metrics['daily_trends']]

plt.plot(dates, scores)
plt.xlabel('Date')
plt.ylabel('Quality Score')
plt.title('Data Quality Trend - January 2025')
plt.show()
```

**Custom date range:**
```python
metrics = client.get_quality_scores(
    period_start='2025-01-15',
    period_end='2025-01-31'
)

# Analyze top errors
for error in metrics['top_errors']:
    print(f"{error['error_type']}: {error['count']} occurrences ({error['percentage']}%)")
```

---

## 10. Testing & Sandbox

### Sandbox Environment

Use the sandbox environment for testing without consuming production quota:

```
Sandbox URL: https://sandbox-api.datafoundry.com
```

**Key Differences:**
- Separate quota (unlimited for testing)
- No charges
- Data not persisted long-term (7 days retention)
- Same API contract as production

**Getting Sandbox Access:**
```bash
curl -X POST https://sandbox-api.datafoundry.com/api/v1/auth/sandbox \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com"
  }'
```

Response includes sandbox JWT token.

### Test Mode

Production API supports test mode via header:

```http
X-Test-Mode: true
```

**Test Mode Behavior:**
- Validations don't count against quota
- Results not stored in analytics
- Webhook events marked as test events
- Rate limits still apply (prevent abuse)

**Example:**
```bash
curl -X POST https://api.datafoundry.com/api/v1/quality/validate \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -H "X-Test-Mode: true" \
  -d '{"record": {"email": "test@example.com"}}'
```

### Example Test Data

**Valid Record:**
```json
{
  "customer_id": "cust_test_001",
  "email": "john.doe@example.com",
  "phone": "+1-555-0100",
  "country": "US",
  "age": 35,
  "created_at": "2025-01-31T10:00:00Z"
}
```

**Invalid Record (Multiple Errors):**
```json
{
  "customer_id": "cust_test_002",
  "email": "not_an_email",
  "phone": "555-0102",
  "country": "INVALID",
  "age": "twenty-five",
  "created_at": "invalid-date"
}
```

**Partially Valid Record (Warnings):**
```json
{
  "customer_id": "cust_test_003",
  "email": "jane@example.com",
  "country": "CA",
  "age": 28
}
```
(Missing `phone` field - triggers warning)

---

## Summary

This API specification provides:

1. **Authentication** via JWT Bearer tokens with tenant isolation
2. **Rate limiting** and quota enforcement per subscription tier
3. **Single validation** for real-time quality checks
4. **Batch validation** with async processing and webhooks
5. **Quality analytics** for trend analysis and insights
6. **Multiple export formats** (CSV, JSON, Parquet)
7. **Comprehensive error handling** with clear status codes
8. **Client SDK examples** in Python, JavaScript/TypeScript
9. **Webhook integration** for async batch completion
10. **Testing support** via sandbox and test mode

For implementation details, see:
- **ARCHITECTURE.md** - System design and components
- **E2E_FLOW.md** - Complete user journeys
- **INDEX.md** - Documentation overview
