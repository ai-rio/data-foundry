# Data Quality Service - End-to-End Flow

## Overview

This document maps complete user journeys through the Data Quality Service. Each flow shows what a user does, what the system processes, and what they receive.

---

## Primary Flow: Single Record Validation

### Scenario
A data engineer wants to validate a single customer record before processing.

### User Journey

```
┌─ START ──────────────────────────────────────────────────────┐
│                                                               │
│  Data Engineer                                                │
│    ↓                                                          │
│    "I have a customer record. Is it good quality?"           │
│    ↓                                                          │
│  Calls: POST /api/v1/quality/validate                        │
│  ├─ Header: Authorization: Bearer <jwt_token>               │
│  ├─ Body: {                                                  │
│  │   "record": {                                             │
│  │     "customer_id": "cust_123",                            │
│  │     "email": "john@example.com",                          │
│  │     "phone": "+1-555-0100",                               │
│  │     "country": "US",                                      │
│  │     "age": 35                                             │
│  │   }                                                       │
│  │ }                                                         │
│  └─ Query: user_id=user_123&tenant_id=tenant_456           │
│    ↓                                                          │
└─ SERVER PROCESSING ──────────────────────────────────────────┘

  Validation Engine
    ├─ [Auth Check]
    │  └─ Verify JWT signature
    │  └─ Extract: user_id, tenant_id from token
    │  └─ Check: token.user_id == query.user_id
    │  └─ Result: ✅ PASSED
    │
    ├─ [Quota Check]
    │  └─ Query DB: SELECT validations_used FROM user_quotas
    │             WHERE user_id = 'user_123' AND month = 2025-01
    │  └─ Result: validations_used = 450, limit = 500 (for Free tier)
    │  └─ Decision: ✅ ALLOWED (450 < 500)
    │
    ├─ [Rate Limit Check]
    │  └─ Check: In-memory token bucket (requests per minute)
    │  └─ Result: 3 requests this minute (limit: 10 for Free tier)
    │  └─ Decision: ✅ ALLOWED
    │
    ├─ [Field Extraction & Validation]
    │  └─ Required fields: customer_id ✅, email ✅
    │  └─ Optional fields: phone ✅, country ✅, age ✅
    │  └─ Format validation:
    │     ├─ email: john@example.com
    │        └─ Regex check: valid email format ✅
    │     ├─ phone: +1-555-0100
    │        └─ International format check ✅
    │     ├─ age: 35
    │        └─ Integer check ✅
    │        └─ Range check: 0-150 ✅
    │     └─ country: US
    │        └─ ISO-3166 code check ✅
    │
    ├─ [Scoring Calculation]
    │  ├─ Fields expected: 5 (customer_id, email, phone, country, age)
    │  ├─ Fields present: 5
    │  └─ Completeness score = 5/5 = 1.0 (100%)
    │
    │  ├─ Fields checked for validity: 5
    │  ├─ Fields valid: 5 (all formats passed)
    │  └─ Validity score = 5/5 = 1.0 (100%)
    │
    │  └─ Quality score = (0.6 × 1.0) + (0.4 × 1.0) = 1.0 (100%)
    │
    ├─ [Error Detection]
    │  └─ No required fields missing ✅
    │  └─ No format errors ✅
    │  └─ No warnings ✅
    │
    └─ [Quota Update]
       └─ UPDATE user_quotas SET validations_used = 451
                 WHERE user_id = 'user_123' AND month = 2025-01

┌─ RESPONSE ────────────────────────────────────────────────────┐
│                                                                │
│  HTTP 200 OK                                                   │
│  ├─ Headers:                                                   │
│  │  └─ X-RateLimit-Remaining: 7                               │
│  │  └─ X-RateLimit-Limit: 10                                  │
│  │  └─ X-RateLimit-Reset: 1704067860                          │
│  │                                                             │
│  └─ Body:                                                      │
│     {                                                          │
│       "validation_result": {                                  │
│         "is_valid": true,                                     │
│         "completeness_score": 1.0,                            │
│         "validity_score": 1.0,                                │
│         "quality_score": 1.0,                                 │
│         "errors": [],                                         │
│         "warnings": [],                                       │
│         "fields_checked": 5,                                  │
│         "fields_valid": 5                                     │
│       },                                                      │
│       "quota": {                                              │
│         "used": 451,                                          │
│         "limit": 500,                                         │
│         "remaining": 49,                                      │
│         "resets_at": "2025-02-01T00:00:00Z"                  │
│       },                                                      │
│       "metadata": {                                           │
│         "processing_time_ms": 23,                             │
│         "timestamp": "2025-01-31T15:30:45Z"                  │
│       }                                                       │
│     }                                                         │
│                                                               │
│  Data Engineer receives: "Record is 100% valid quality!"      │
│
└─ END ─────────────────────────────────────────────────────────┘
```

### Data Storage (Optional)
If analytics enabled, store result in DB:
```sql
INSERT INTO validations (
  user_id, tenant_id, input_data, completeness, validity, quality,
  errors, warnings, timestamp, expires_at
) VALUES (
  'user_123', 'tenant_456', {...}, 1.0, 1.0, 1.0, '[]', '[]',
  NOW(), NOW() + INTERVAL '90 days'
)
```

---

## Secondary Flow: Batch Validation (Large Dataset)

### Scenario
A data team wants to validate 50,000 customer records from a CSV export. They need async processing because it will take time.

### User Journey

```
┌─ START ──────────────────────────────────────────────────────┐
│                                                               │
│  Data Engineer                                                │
│    ↓                                                          │
│    "I have 50K records. Validate them asynchronously."       │
│    ↓                                                          │
│  Calls: POST /api/v1/quality/validate-batch                  │
│  ├─ Header: Authorization: Bearer <jwt_token>               │
│  ├─ Content-Type: application/json                          │
│  ├─ Body: {                                                  │
│  │   "records": [                                            │
│  │     {                                                     │
│  │       "customer_id": "cust_001",                          │
│  │       "email": "alice@example.com",                       │
│  │       "phone": "+1-555-0101",                             │
│  │       "country": "US",                                    │
│  │       "age": 28                                           │
│  │     },                                                    │
│  │     {                                                     │
│  │       "customer_id": "cust_002",                          │
│  │       "email": "bob@invalid",  ← Invalid email!          │
│  │       "phone": "555-0102",                                │
│  │       "country": "UK",                                    │
│  │       "age": "thirty-five"  ← Not a number!              │
│  │     },                                                    │
│  │     ... (50,000 records total)                            │
│  │   ]                                                       │
│  │ }                                                         │
│  └─ Query: user_id=user_123&tenant_id=tenant_456           │
│    ↓                                                          │
│  Webhook (optional): "Send results to https://..."          │
│    ↓                                                          │
└─ SERVER PROCESSING ──────────────────────────────────────────┘

  [Same Auth/Quota/RateLimit checks as single validation]

  Create Background Job
    ├─ Generate: job_id = uuid4() = "job_abc123def456"
    ├─ Store in DB:
    │  │  INSERT INTO batch_jobs (
    │  │    job_id, user_id, tenant_id, total_records, status
    │  │  ) VALUES (
    │  │    'job_abc123def456', 'user_123', 'tenant_456', 50000, 'queued'
    │  │  )
    │  └─ timestamp: 2025-01-31T15:30:45Z
    │
    ├─ Check Quota:
    │  └─ Pro tier allows 50K validations/month
    │  └─ Already used: 25,000
    │  └─ Remaining: 25,000
    │  └─ Request: 50,000 (MORE than remaining!)
    │  └─ Result: ❌ REJECT - quota exceeded
    │
    └─ Return to client: 402 Payment Required
       └─ Message: "Quota exceeded. Upgrade to Business tier."

┌─ RESPONSE (Quota Exceeded) ────────────────────────────────────┐
│                                                                │
│  HTTP 402 Payment Required                                    │
│  {                                                            │
│    "error": "quota_exceeded",                                │
│    "message": "Your tier allows 50K validations/month",      │
│    "quota": {                                                │
│      "used": 25000,                                          │
│      "limit": 50000,                                         │
│      "remaining": 25000,                                     │
│      "requested": 50000                                      │
│    },                                                        │
│    "recommendation": "Upgrade to Business tier (500K/month)" │
│  }                                                           │
│                                                               │
│  Data Engineer: "Hmm, I need to upgrade. Let me check..."    │
│
└─ END ────────────────────────────────────────────────────────┘

[Alternative scenario: Quota sufficient, continue...]

  Processing Background Job
    ├─ Update DB: UPDATE batch_jobs SET status = 'processing' WHERE job_id = ?
    │
    ├─ Stream processing (memory-efficient):
    │  ├─ Load records in batches of 1000
    │  ├─ For each record:
    │  │  ├─ Run validation (same as single record)
    │  │  ├─ Store result: INSERT INTO validations (...)
    │  │  ├─ Aggregate metrics
    │  │  └─ Update progress counter
    │  │
    │  └─ Process all 50,000 records
    │
    ├─ Calculate batch metrics:
    │  ├─ Total records: 50,000
    │  ├─ Valid records: 49,235 (98.47%)
    │  ├─ Invalid records: 765 (1.53%)
    │  ├─ Average quality score: 0.94
    │  ├─ Avg completeness: 0.98
    │  ├─ Avg validity: 0.91
    │  ├─ Top errors:
    │  │  ├─ Invalid email format: 312 occurrences
    │  │  ├─ Missing phone: 288 occurrences
    │  │  ├─ Invalid age (non-numeric): 165 occurrences
    │  │  └─ Invalid country code: 0 occurrences
    │  └─ Top issues by field:
    │     ├─ email: 312 errors (6.24% error rate)
    │     ├─ phone: 288 errors (5.76%)
    │     ├─ age: 165 errors (3.3%)
    │     └─ customer_id: 0 errors
    │
    ├─ Generate report:
    │  │  CREATE TABLE batch_report (
    │  │    job_id, total_records, valid_records, invalid_records,
    │  │    avg_quality_score, avg_completeness, avg_validity,
    │  │    error_distribution, field_issues, created_at
    │  │  )
    │  └─ INSERT batch metrics
    │
    ├─ Update DB:
    │  └─ UPDATE batch_jobs
    │        SET status = 'completed', processed_at = NOW()
    │        WHERE job_id = 'job_abc123def456'
    │
    └─ Webhook notification (if configured):
       └─ POST https://customer.com/webhooks/validation-complete
          {
            "event": "validation.completed",
            "job_id": "job_abc123def456",
            "status": "completed",
            "summary": {
              "total_records": 50000,
              "valid_records": 49235,
              "invalid_records": 765,
              "avg_quality_score": 0.94
            },
            "download_url": "https://data-quality.com/download/job_abc123def456",
            "expires_at": "2025-02-07T15:30:45Z"
          }

┌─ CLIENT POLLING ──────────────────────────────────────────────┐
│                                                                │
│  [Data Engineer polls for status]                             │
│  GET /api/v1/quality/batch/{job_id}/status                   │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  └─ Response (before completion):                             │
│     {                                                         │
│       "job_id": "job_abc123def456",                           │
│       "status": "processing",                                 │
│       "progress": {                                           │
│         "records_processed": 25000,                           │
│         "total_records": 50000,                               │
│         "percentage": 50                                      │
│       },                                                      │
│       "eta_seconds": 300,                                     │
│       "estimated_completion": "2025-01-31T15:35:00Z"         │
│     }                                                         │
│                                                               │
│  [Wait... polling every 30 seconds...]                        │
│                                                               │
│  [After ~600 seconds, status changes to 'completed']         │
│
│  GET /api/v1/quality/batch/{job_id}/status                   │
│  └─ Response (after completion):                              │
│     {                                                         │
│       "job_id": "job_abc123def456",                           │
│       "status": "completed",                                  │
│       "summary": {                                            │
│         "total_records": 50000,                               │
│         "valid_records": 49235,                               │
│         "invalid_records": 765,                               │
│         "avg_quality_score": 0.94,                            │
│         "processing_duration_seconds": 598                    │
│       },                                                      │
│       "download_url": "https://data-quality.com/download/...",│
│       "expires_at": "2025-02-07T15:30:45Z"                   │
│     }                                                         │
│                                                               │
│  Data Engineer: "Perfect! Let me download the results."       │
│
└─ END ────────────────────────────────────────────────────────┘

┌─ DOWNLOAD RESULTS ────────────────────────────────────────────┐
│                                                                │
│  POST /api/v1/quality/batch/{job_id}/export                  │
│  ├─ Query: format=csv (or json, parquet)                     │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  └─ Response:                                                │
│     HTTP 200 OK                                              │
│     Content-Type: text/csv                                   │
│     Content-Disposition: attachment; filename=results.csv    │
│                                                              │
│     customer_id,email,phone,country,age,is_valid,quality_...|
│     cust_001,alice@example.com,+1-555-0101,US,28,true,1.0,...|
│     cust_002,bob@invalid,555-0102,UK,thirty-five,false,0.4,...|
│     ...                                                      │
│                                                              │
│  Data Engineer downloads CSV with all validation results     │
│  ✅ Ready to import into data warehouse or ML pipeline       │
│
└─ END ────────────────────────────────────────────────────────┘
```

---

## Tertiary Flow: Analytics & Quality Trends

### Scenario
A data team wants to understand how their data quality changes over time. They check monthly quality metrics.

### User Journey

```
┌─ START ──────────────────────────────────────────────────────┐
│                                                               │
│  Data Manager                                                 │
│    ↓                                                          │
│    "How is our data quality trending?"                       │
│    ↓                                                          │
│  Calls: GET /api/v1/quality/scores                           │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  ├─ Query: period=2025-01&source=salesforce_export          │
│  └─ (or: period_start=2025-01-01&period_end=2025-01-31)     │
│    ↓                                                          │
└─ SERVER PROCESSING ──────────────────────────────────────────┘

  Authentication & Authorization
    ├─ Verify JWT token ✅
    ├─ Extract tenant_id from token
    └─ Check user has access to this data ✅

  Query Analytics Database
    ├─ SELECT * FROM quality_metrics_daily
    │  WHERE tenant_id = 'tenant_456'
    │    AND date BETWEEN '2025-01-01' AND '2025-01-31'
    │    AND source = 'salesforce_export'
    │
    └─ Result: 31 rows (one per day in January)

  Aggregate & Format Results
    ├─ Calculate:
    │  ├─ min_quality_score = 0.87 (worst day)
    │  ├─ max_quality_score = 0.96 (best day)
    │  ├─ avg_quality_score = 0.92 (overall average)
    │  ├─ trend: [0.90, 0.91, 0.92, 0.93, ..., 0.95, 0.96]
    │  │         (improving over month)
    │  ├─ completeness trend: [0.94, 0.94, 0.95, ...]
    │  ├─ validity trend: [0.88, 0.89, 0.90, ...]
    │  │
    │  └─ Top errors this period:
    │     ├─ Invalid email: 1,245 occurrences
    │     ├─ Missing phone: 892 occurrences
    │     ├─ Invalid age: 456 occurrences
    │     └─ Other: 203 occurrences
    │
    ├─ Error distribution by field:
    │  ├─ email: 42% of errors
    │  ├─ phone: 30% of errors
    │  ├─ age: 15% of errors
    │  └─ other: 13% of errors
    │
    └─ Correlation analysis:
       ├─ Phone errors tend to spike on weekends
       ├─ Email errors consistent throughout month
       └─ Age validation improved after system update (Jan 15)

┌─ RESPONSE ────────────────────────────────────────────────────┐
│                                                                │
│  HTTP 200 OK                                                  │
│  {                                                            │
│    "period": {                                                │
│      "start": "2025-01-01T00:00:00Z",                         │
│      "end": "2025-01-31T23:59:59Z",                           │
│      "days": 31                                               │
│    },                                                         │
│    "summary": {                                               │
│      "total_records_validated": 1500000,                      │
│      "avg_quality_score": 0.92,                               │
│      "min_quality_score": 0.87,                               │
│      "max_quality_score": 0.96,                               │
│      "avg_completeness": 0.94,                                │
│      "avg_validity": 0.91,                                    │
│      "trend": "improving"                                     │
│    },                                                         │
│    "daily_trends": [                                          │
│      {                                                        │
│        "date": "2025-01-01",                                  │
│        "quality_score": 0.90,                                 │
│        "records_validated": 50000,                            │
│        "completeness": 0.93,                                  │
│        "validity": 0.88                                       │
│      },                                                       │
│      {                                                        │
│        "date": "2025-01-02",                                  │
│        "quality_score": 0.91,                                 │
│        "records_validated": 48000,                            │
│        "completeness": 0.94,                                  │
│        "validity": 0.89                                       │
│      },                                                       │
│      ... (29 more days)                                       │
│    ],                                                         │
│    "top_errors": [                                            │
│      {                                                        │
│        "error_type": "INVALID_EMAIL_FORMAT",                  │
│        "count": 1245,                                         │
│        "percentage": 42,                                      │
│        "affected_records": 1245,                              │
│        "trend": "stable"                                      │
│      },                                                       │
│      {                                                        │
│        "error_type": "MISSING_PHONE",                         │
│        "count": 892,                                          │
│        "percentage": 30,                                      │
│        "affected_records": 892,                               │
│        "trend": "improving"                                   │
│      },                                                       │
│      ... (more errors)                                        │
│    ],                                                         │
│    "field_quality": {                                         │
│      "email": {                                               │
│        "completeness": 0.98,                                  │
│        "validity": 0.88,                                      │
│        "quality": 0.93,                                       │
│        "errors": 1245                                         │
│      },                                                       │
│      "phone": {                                               │
│        "completeness": 0.92,                                  │
│        "validity": 0.97,                                      │
│        "quality": 0.95,                                       │
│        "errors": 892                                          │
│      },                                                       │
│      ... (all fields)                                         │
│    },                                                         │
│    "recommendations": [                                       │
│      "Focus on email validation - 42% of errors",             │
│      "Phone field optional? Consider making required",        │
│      "Quality improved 8% over month - trending positive"     │
│    ]                                                          │
│  }                                                            │
│                                                               │
│  Data Manager: "Great! Email validation is our biggest issue. │
│                 Let's fix that and re-validate in a week."   │
│
└─ END ────────────────────────────────────────────────────────┘
```

---

## Error Scenarios

### Scenario: Invalid Record (Bad Data)

```
Input Record: {
  "customer_id": "cust_123",
  "email": "not_an_email",  ← Invalid format
  "age": "twenty-five"       ← Not a number
}

Validation Processing
  ├─ Field: email = "not_an_email"
  │  └─ Regex check: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/
  │  └─ Result: ❌ Does NOT match
  │  └─ Error: INVALID_EMAIL_FORMAT
  │
  ├─ Field: age = "twenty-five"
  │  └─ Type check: Is string convertible to integer?
  │  └─ Result: ❌ NO
  │  └─ Error: INVALID_INTEGER_TYPE
  │
  └─ Scoring:
     ├─ Required fields present: 1/1 ✅
     ├─ Optional fields present: 1/2 (missing phone)
     ├─ Completeness: (1+1) / (1+2) = 0.67
     ├─ Fields valid: 1/2 (email & age both invalid)
     ├─ Validity: 1/2 = 0.50
     └─ Quality: (0.6 × 0.67) + (0.4 × 0.50) = 0.60

Response:
{
  "is_valid": false,
  "quality_score": 0.60,
  "completeness_score": 0.67,
  "validity_score": 0.50,
  "errors": [
    { "field": "email", "error": "INVALID_EMAIL_FORMAT" },
    { "field": "age", "error": "INVALID_INTEGER_TYPE" }
  ],
  "warnings": [
    { "field": "phone", "warning": "OPTIONAL_FIELD_MISSING" }
  ]
}

HTTP 200 OK (validation succeeded, record is just bad quality)
```

### Scenario: Quota Exceeded

```
User Request: POST /api/v1/quality/validate-batch
  ├─ Tier: Free (500 validations/month)
  ├─ Used this month: 490
  ├─ Requesting: 20 more validations
  ├─ Check: 490 + 20 = 510 > 500 ❌
  └─ Decision: REJECT

Response:
{
  "error": "quota_exceeded",
  "message": "Your Free tier allows 500 validations per month",
  "quota": {
    "tier": "free",
    "used": 490,
    "limit": 500,
    "remaining": 10,
    "requested": 20,
    "resets_at": "2025-02-01T00:00:00Z"
  },
  "recommendation": "Upgrade to Pro tier (50,000/month) or wait for monthly reset"
}

HTTP 402 Payment Required
```

### Scenario: Rate Limited

```
User Request: POST /api/v1/quality/validate
  ├─ Tier: Free (10 requests/minute)
  ├─ Requests this minute: 11
  └─ Decision: REJECT (11 > 10)

Response:
{
  "error": "rate_limited",
  "message": "Too many requests. Rate limit: 10/minute for Free tier",
  "rate_limit": {
    "limit": 10,
    "remaining": 0,
    "reset_in_seconds": 35,
    "reset_at": "2025-01-31T15:31:35Z"
  }
}

HTTP 429 Too Many Requests
Headers:
  Retry-After: 35
  X-RateLimit-Limit: 10
  X-RateLimit-Remaining: 0
  X-RateLimit-Reset: 1704067895
```

### Scenario: Database Error

```
During validation processing, PostgreSQL connection fails
  ├─ Error: Connection timeout (database is down)
  ├─ Handling: FastAPI exception handler catches it
  ├─ Logging: Log error to Sentry + local logs
  └─ Response:

{
  "error": "service_unavailable",
  "message": "Data Quality Service is temporarily unavailable",
  "retry_after": 60,
  "status": "We're experiencing temporary issues. Please try again in 1 minute."
}

HTTP 503 Service Unavailable
Headers:
  Retry-After: 60
```

---

## Data Transformations Summary

### Validation Transformation
```
Raw Input
  └─ { customer_id: "123", email: "john@example.com", age: 35 }

After Field Extraction
  └─ { customer_id: "123", email: "john@example.com", age: 35 }
     (same as input, but parsed into typed fields)

After Validation Checks
  └─ [
       { field: "customer_id", valid: true, error: null },
       { field: "email", valid: true, error: null },
       { field: "age", valid: true, error: null }
     ]

After Scoring
  └─ {
       completeness: 1.0,
       validity: 1.0,
       quality: 1.0,
       errors: [],
       warnings: []
     }

Final Output
  └─ ValidationResult { is_valid: true, scores, errors, warnings }
```

### Batch Aggregation Transformation
```
50,000 Validation Results
  └─ [
       { record: {...}, is_valid: true, quality: 0.95 },
       { record: {...}, is_valid: false, quality: 0.60 },
       ... (49,998 more)
     ]

Aggregated Metrics
  └─ {
       total_records: 50000,
       valid_records: 49235,
       invalid_records: 765,
       avg_quality_score: 0.94,
       completeness_avg: 0.98,
       validity_avg: 0.91,
       error_distribution: { INVALID_EMAIL: 312, ... },
       field_quality: { email: 0.94, phone: 0.96, ... }
     }

Stored in Database
  └─ quality_metrics_daily table (1 row per day)
     + detailed validation results in validations table
```

---

## Storage & Retention Strategy

### What Gets Stored

**Detailed Records** (TTL: 90 days)
```sql
-- validations table
INSERT INTO validations (
  user_id, tenant_id, input_data, completeness, validity, quality,
  errors, warnings, timestamp, expires_at
) VALUES (
  'user_123', 'tenant_456', {...}, 0.95, 0.98, 0.97,
  '[]', '[]', NOW(), NOW() + INTERVAL '90 days'
)
```

**Aggregated Metrics** (Permanent)
```sql
-- quality_metrics_daily table (one row per day per user)
INSERT INTO quality_metrics_daily (
  user_id, tenant_id, date, total_validations, avg_quality,
  avg_completeness, avg_validity, error_count
) VALUES (
  'user_123', 'tenant_456', '2025-01-31',
  1500, 0.92, 0.94, 0.91, 2796
)

-- quality_metrics_monthly table (one row per month per user)
INSERT INTO quality_metrics_monthly (
  user_id, tenant_id, year_month, total_validations, avg_quality,
  ...
) VALUES (
  'user_123', 'tenant_456', '2025-01',
  42000, 0.92, ...
)
```

**Audit Logs** (Permanent)
```sql
-- audit_logs table
INSERT INTO audit_logs (
  user_id, tenant_id, action, resource, status, timestamp
) VALUES (
  'user_123', 'tenant_456', 'validate_batch',
  'job_abc123def456', 'completed', NOW()
)
```

### Why This Strategy
- **Detailed records (90 days):** Allow recent troubleshooting + GDPR compliance
- **Aggregated metrics (permanent):** Support long-term trend analysis
- **Audit logs (permanent):** Compliance + debugging
- **Auto-cleanup:** 90-day TTL prevents database bloat

---

## Summary: Key Data Transformations

| Stage | Input | Output | Storage |
|-------|-------|--------|---------|
| **Single Validation** | JSON record | ValidationResult | Optional (to DB) |
| **Batch Validation** | Array of records | Job ID | DB (batch_jobs) |
| **Batch Processing** | Job ID | BatchMetrics + Results | DB (validations + metrics_daily) |
| **Analytics Query** | Date range + filters | TrendData + Recommendations | DB (metrics_daily/monthly) |
| **Export** | Job ID + format | CSV/JSON/Parquet | Temporary file (S3 or local) |

---

## Next Steps

See: **API_SPECIFICATION.md** - Detailed API contracts for all endpoints
