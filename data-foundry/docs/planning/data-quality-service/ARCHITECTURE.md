# Data Quality Service - Architecture

## High-Level Overview

The Data Quality Service is a standalone, stateless validation engine that scores data quality in real-time. It's designed to integrate as an independent microservice or API within existing data pipelines.

```
┌─────────────────────────────────────────────────────────────────┐
│                      EXTERNAL CLIENTS                            │
│  (Data Engineering Teams, ETL Platforms, Webhook Subscribers)   │
└────────┬──────────────────────────────────────────────┬─────────┘
         │                                              │
         │ HTTP (REST API)                              │ Webhooks
         │                                              │
┌────────▼──────────────────────────────────────────────▼─────────┐
│                    DATA QUALITY SERVICE                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  FASTAPI APPLICATION                     │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │ Endpoints:                                          │ │  │
│  │  │ • POST   /api/v1/quality/validate          (single)│ │  │
│  │  │ • POST   /api/v1/quality/validate-batch    (batch) │ │  │
│  │  │ • GET    /api/v1/quality/scores             (hist) │ │  │
│  │  │ • POST   /api/v1/quality/export            (report)│ │  │
│  │  │ • POST   /webhooks/quality-events          (async) │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │ Core Services:                                      │ │  │
│  │  │ • ValidationEngine: Scores records, detects errors  │ │  │
│  │  │ • QuotaManager: Enforces tier limits              │ │  │
│  │  │ • AnalyticsService: Aggregates quality metrics    │ │  │
│  │  │ • WebhookDispatcher: Sends async notifications    │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  │                                                          │  │
│  │  ┌─────────────────────────────────────────────────────┐ │  │
│  │  │ Middleware:                                         │ │  │
│  │  │ • Authentication (JWT tokens)                       │ │  │
│  │  │ • Rate Limiting (per tier)                          │ │  │
│  │  │ • Request/Response Logging                          │ │  │
│  │  │ • Error Handling                                    │ │  │
│  │  └─────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────┬────────────────────────────────┬──────────────────┬──────┘
       │                                │                  │
       │ SQL (Read/Write)              │ SQL (Read)       │ Event
       │                                │                  │ Publishing
       │                                │                  │
┌──────▼─────────────┐  ┌──────────────▼──────┐  ┌────────▼─────┐
│  POSTGRESQL        │  │   CACHE (Redis)     │  │  MESSAGE     │
│  ┌──────────────┐  │  │  (Optional)         │  │  QUEUE       │
│  │ validations  │  │  │  ┌───────────────┐  │  │  (Optional)  │
│  │ quality_hist │  │  │  │ Score cache   │  │  │  ┌────────┐  │
│  │ audit_logs   │  │  │  │ Analytics     │  │  │  │ Events │  │
│  │ user_quotas  │  │  │  └───────────────┘  │  │  └────────┘  │
│  └──────────────┘  │  │                     │  │              │
└────────────────────┘  └─────────────────────┘  └──────────────┘
```

---

## Component Breakdown

### 1. API Gateway (FastAPI)
**Responsibility:** HTTP request handling, routing, response serialization

**Endpoints:**
- `POST /api/v1/quality/validate` - Single record validation
- `POST /api/v1/quality/validate-batch` - Batch record validation (streaming)
- `GET /api/v1/quality/scores` - Historical quality metrics
- `POST /api/v1/quality/export` - Generate validation reports
- `POST /webhooks/quality-events` - Receive webhooks (extensible)

**Characteristics:**
- Stateless (can scale horizontally)
- No session management
- All state in database
- Fast response times (validation is compute-light)

---

### 2. Validation Engine
**Responsibility:** Core validation logic, scoring algorithms, error detection

**Input:** Record (any JSON object)

**Processing:**
```
Record Input
    ↓
[1] Field Extraction
    ├─ Required fields present? (completeness)
    ├─ Field types correct? (validity)
    └─ Field formats valid? (format validation)
    ↓
[2] Scoring Calculation
    ├─ Completeness Score = fields_present / fields_expected
    ├─ Validity Score = fields_valid / fields_checked
    └─ Quality Score = (0.6 × completeness) + (0.4 × validity)
    ↓
[3] Error & Warning Detection
    ├─ Missing required fields → ERROR
    ├─ Invalid formats → ERROR
    ├─ Best-practice violations → WARNING
    └─ Suspicious patterns → WARNING
    ↓
ValidationResult Output
    ├─ is_valid: boolean
    ├─ completeness_score: float (0.0-1.0)
    ├─ validity_score: float (0.0-1.0)
    ├─ quality_score: float (0.0-1.0)
    ├─ errors: List[Error]
    └─ warnings: List[Warning]
```

**Key Features:**
- Regex with ReDoS protection (length checks before pattern matching)
- Comprehensive format validators (email, phone, timestamp, UUID, etc.)
- Thread-safe (can handle concurrent requests)
- No external API calls (all local computation)

---

### 3. Quota Manager
**Responsibility:** Enforce per-tier limits, prevent overage

**Quota Limits:**
```
Free Tier:
  - 500 validations/month
  - Reset: 1st of each month
  - No upload of files > 1MB

Pro Tier ($99/month):
  - 50,000 validations/month
  - Batch validation allowed (up to 10K records/batch)
  - No upload size limit

Business ($499/month):
  - 500,000 validations/month
  - Unlimited batch size
  - Priority queue

Enterprise (Custom):
  - Unlimited validations
  - SLA guarantees
  - Dedicated support
```

**Implementation:**
- Store quota usage in database (per user, per month)
- Check quota before processing (reject if exceeded)
- Return quota info in API response headers
- Monthly reset via cron job

---

### 4. Analytics Service
**Responsibility:** Track quality trends, generate insights

**What Gets Tracked:**
- Per-record: quality_score, completeness, validity, error count, timestamp
- Per-user: total validations, avg quality score, error patterns, top errors
- Per-month: quality trends, tier breakdown, top issues

**Storage:**
- `validation_results` table: Individual validation records (recent only, TTL 90 days)
- `quality_metrics_daily` table: Aggregated daily metrics
- `quality_metrics_monthly` table: Aggregated monthly metrics
- `user_quotas` table: Current month's usage

**Queries Supported:**
- "What's my average quality score this month?"
- "Which fields have the most errors?"
- "How does my data quality trend over time?"

---

### 5. Webhook Dispatcher
**Responsibility:** Async notifications for quality events

**Events Fired:**
- `validation.completed` - When a batch finishes
- `quality.alert` - When quality score drops below threshold
- `quota.warning` - When approaching monthly limit
- `report.ready` - When export completes

**Implementation:**
- Queue events in message broker (optional Redis)
- Retry with exponential backoff
- Store delivery logs (for debugging)
- Customer can configure webhook URL + events

---

### 6. Database Layer (PostgreSQL)
**Responsibility:** Persistent storage of validation results, metrics, audit trails

**Core Tables:**

**validations**
```sql
id | user_id | tenant_id | input_data | completeness | validity |
quality | errors | warnings | timestamp | expires_at
```
- Store last 90 days (TTL for compliance)
- Index on: user_id, tenant_id, timestamp

**quality_metrics_daily**
```sql
date | user_id | tenant_id | total_validations | avg_quality |
completeness_avg | validity_avg | error_count
```
- Pre-aggregated for fast queries

**user_quotas**
```sql
user_id | tenant_id | tier | month | validations_used |
validations_limit | reset_at
```
- Updated on each validation
- Checked before processing

**audit_logs**
```sql
id | user_id | action | resource | status | timestamp
```
- Track all API calls (for compliance)

---

### 7. Authentication & Authorization
**Method:** JWT Bearer Tokens

**Flow:**
```
Client
  ↓ (includes JWT token in Authorization header)
FastAPI Middleware
  ↓ (validates token signature)
Token Claims
  ├─ user_id
  ├─ tenant_id (for multi-tenant isolation)
  ├─ tier (free/pro/business/enterprise)
  └─ exp (expiration)
  ↓ (inject into request context)
Endpoint Handler
  ├─ Check user_id matches query param (prevent cross-tenant access)
  ├─ Check tier for feature access
  └─ Enforce quota limit
```

**Security:**
- No session state (stateless scaling)
- Tokens signed with RS256 (or HS256 + rotation)
- Token expiration: 1 hour (refresh token: 7 days)
- Tenant isolation at database query level

---

### 8. Rate Limiting
**Responsibility:** Prevent abuse, enforce fair usage

**Rules:**
```
Free Tier:
  - 10 requests/minute per API key
  - 100 requests/hour

Pro Tier:
  - 100 requests/minute per API key
  - 1000 requests/hour

Business Tier:
  - 1000 requests/minute per API key
  - Unlimited/hour
```

**Implementation:**
- In-memory counter (or Redis for distributed)
- Token bucket algorithm
- Return 429 (Too Many Requests) when exceeded
- Include retry-after header

---

## External Dependencies

### Required
- **PostgreSQL 12+**: Persistent storage
- **Python 3.11+**: Runtime
- **FastAPI**: Web framework
- **Pydantic**: Data validation/serialization
- **SQLAlchemy**: ORM

### Optional
- **Redis**: Caching + rate limiting distribution
- **Sentry**: Error tracking
- **Datadog/NewRelic**: Performance monitoring
- **Message Queue** (RabbitMQ/AWS SQS): For webhook dispatching

### NOT Needed
- External validation APIs (all validation is local)
- Machine learning models (deterministic scoring)
- Complex ETL pipelines (simple record-by-record validation)

---

## Data Flow Diagram

### Single Record Validation
```
POST /api/v1/quality/validate
│
├─ Auth Check (JWT valid + user matches)
├─ Quota Check (have validations left?)
├─ Rate Limit Check (not over request limit)
│
├─ Extract & Validate Record
│  ├─ Check required fields
│  ├─ Validate field formats
│  └─ Calculate scores
│
├─ Store Result (optional, to DB)
├─ Decrement Quota (if using)
│
└─ Return ValidationResult
   ├─ is_valid: boolean
   ├─ scores: { completeness, validity, quality }
   ├─ errors: [...]
   ├─ warnings: [...]
   └─ quota_remaining: { used, limit }
```

### Batch Validation
```
POST /api/v1/quality/validate-batch
│
├─ Auth + Quota + Rate Limit Checks
│
├─ Create Background Job (store in DB with job_id)
│  └─ job_status = "queued" → "processing" → "completed"
│
├─ Return Immediately (HTTP 202 Accepted)
│  └─ include job_id for polling
│
├─ Background Task
│  ├─ Process records in parallel (async)
│  ├─ Write results to temporary storage
│  ├─ Aggregate metrics (quality_score distribution, error patterns)
│  ├─ Generate report (optional)
│  └─ Update job_status = "completed"
│
└─ Webhook Notification (if configured)
   └─ POST to customer's webhook URL
      └─ payload: { job_id, status, summary, download_url }
```

### Analytics Query
```
GET /api/v1/quality/scores?period=2025-01&source=data_source_1
│
├─ Auth Check + Permission Check (user owns this data)
│
├─ Query Aggregated Metrics (from quality_metrics_daily)
│  ├─ avg_quality_score
│  ├─ trend (day-by-day scores)
│  ├─ error_distribution (top 5 error types)
│  └─ completeness_trend
│
└─ Return AnalyticsResponse
   ├─ period: date range
   ├─ avg_quality: float
   ├─ trend: [ { date, score }, ... ]
   ├─ top_errors: [ { error_type, count }, ... ]
   └─ fields_with_issues: [ { field, error_count }, ... ]
```

---

## Multi-Tenancy Model

**Isolation Level:** Complete tenant isolation (no data cross-contamination)

**Implementation:**
```
User Authentication
  ↓ (JWT includes tenant_id)
Request Context
  ├─ user_id: "user_123"
  ├─ tenant_id: "tenant_456"  ← Injected from token
  └─ tier: "pro"
  ↓
All Database Queries
  └─ WHERE tenant_id = "tenant_456"  ← Enforced at query level

Result: User can only see/modify their own tenant's data
```

**Multi-Tenant Scenarios:**
- Single user, single tenant (most common)
- Single organization (tenant) with multiple users (different API keys per user)
- White-label SaaS (different customers are different tenants)

---

## Deployment Topology

### Option 1: Single Container (Monolithic)
```
┌────────────────────────────┐
│   Docker Container         │
│  ┌──────────────────────┐  │
│  │ FastAPI + Workers    │  │
│  │ (all code in one)    │  │
│  └──────────────────────┘  │
└────────┬───────────────────┘
         │ SQL
         │ Redis (optional)
┌────────▼────────────┐
│   PostgreSQL        │
│   Redis (optional)  │
└─────────────────────┘
```
**Best for:** Solo dev, early stage
**Scaling:** Horizontal (run multiple containers, use load balancer)

### Option 2: Microservices (Advanced)
```
┌──────────────────┐
│  API Server      │
│  (FastAPI)       │
└────────┬─────────┘
         │
    ┌────┴──────┐
    │            │
┌───▼──────┐  ┌─▼──────────┐
│ Validator │  │ Analytics  │
│ Worker    │  │ Worker     │
└───┬──────┘  └─┬──────────┘
    │           │
    └─────┬─────┘
          │
    ┌─────▼──────────┐
    │  PostgreSQL    │
    │  Redis         │
    └────────────────┘
```
**Best for:** Scaling to multiple teams
**Scaling:** Each component scales independently

---

## Integration Points

### Inbound Integration
**Clients can integrate via:**
1. **Direct HTTP API** (recommended)
   - Language: Any (curl, Python, JS, Go, etc.)
   - Authentication: JWT token
   - Response: JSON

2. **SDK** (optional)
   - Provided: Python, JavaScript/TypeScript
   - Open source (community can add more)

3. **Webhooks** (for async pipelines)
   - Validation completes → POST to your webhook URL
   - Useful for ETL systems that want async processing

### Outbound Integration
**Service can notify via:**
1. **Webhooks** (quality events, quota warnings)
2. **Email** (monthly quality reports, alerts)
3. **Slack** (optional integration)
4. **Cloud Storage** (S3) for large exports

---

## Error Handling Strategy

**Validation Errors** (Record-Level)
```
Input Record: { email: "invalid_email", age: "not_a_number" }
        ↓
ValidationResult
  ├─ is_valid: false
  ├─ errors: [
  │   { field: "email", error: "INVALID_EMAIL_FORMAT" },
  │   { field: "age", error: "INVALID_INTEGER" }
  │ ]
  └─ quality_score: 0.3 (only 30% valid)

Return: HTTP 200 OK (validation succeeded, record is just bad)
```

**System Errors** (Service-Level)
```
Scenario: Database is down
        ↓
FastAPI Exception Handling
  ├─ Catch DatabaseError
  ├─ Log to Sentry
  └─ Return HTTP 503 Service Unavailable
     + Retry-After: 60 seconds
```

**Rate Limit Errors**
```
Scenario: User exceeded quota
        ↓
QuotaManager blocks validation
  └─ Return HTTP 429 Too Many Requests
     + headers: {
         X-RateLimit-Limit: 50000,
         X-RateLimit-Remaining: 0,
         X-RateLimit-Reset: 1704067200
       }
```

---

## Monitoring & Observability

**Metrics to Track:**
- Request latency (p50, p95, p99)
- Validation accuracy (how many records marked invalid)
- Error rates (by error type)
- Quota utilization (per tier)
- Webhook delivery success rate

**Logging:**
- All API requests (method, path, status, latency)
- Validation errors (field, error type, frequency)
- Database queries (slow queries > 100ms)
- Webhook failures (retry attempts, final status)

**Alerts:**
- Error rate > 1%
- Latency p95 > 500ms
- Database connection failures
- Webhook delivery failures > 10%

---

## Security Considerations

**Data at Rest:**
- PostgreSQL encryption (at filesystem level via cloud provider)
- PII data: Consider hashing/masking in audit logs

**Data in Transit:**
- HTTPS only (TLS 1.3+)
- JWT tokens signed (prevent tampering)

**Authentication:**
- No passwords stored (JWT-based)
- Token rotation every hour
- Revocation list for compromised tokens

**Authorization:**
- Tenant isolation enforced at query level
- Rate limiting prevents abuse
- No privilege escalation (users can't access other tenants)

**Audit Trail:**
- All API calls logged (user_id, endpoint, status, timestamp)
- 90-day retention (comply with GDPR)
- Read-only audit logs (immutable)

---

## Summary

| Aspect | Details |
|--------|---------|
| **Architecture** | Stateless FastAPI service + PostgreSQL |
| **Scalability** | Horizontal (add more containers) |
| **Deployment** | Docker, Railway, Vercel, or self-hosted |
| **Database** | PostgreSQL (single instance for MVP) |
| **External APIs** | None required (pure compute) |
| **Authentication** | JWT Bearer tokens |
| **Multi-Tenancy** | Complete isolation at query level |
| **Rate Limiting** | Per-tier request limits |
| **Quota Enforcement** | Monthly validations per tier |
| **Error Handling** | Record-level errors (HTTP 200), system errors (HTTP 5xx) |
| **Monitoring** | Logs + metrics (Sentry, Datadog optional) |

---

## Next Steps

See: **E2E_FLOW.md** - Detailed user journeys and data transformations
