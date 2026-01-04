# Spend Intelligence Dashboard - Architecture

## Overview

The Spend Intelligence Dashboard is an analytics layer built on top of the existing Metering Service infrastructure, transforming meter event data into actionable insights on customer costs, margins, usage patterns, and peer benchmarks.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Data Sources (External)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Metering Service API              │  Stripe API                             │
│  - Meter events by customer        │  - Subscriptions                        │
│  - Usage metrics                   │  - Invoices                             │
└──────────────┬─────────────────────┴──────────────────┬─────────────────────┘
               │                                         │
               │ (Read-only access)                      │
               ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Analytics Services Layer                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐     │
│  │   Cost           │───▶│    Margin        │───▶│   Dashboard      │     │
│  │ Aggregation      │    │   Calculation    │    │      API         │     │
│  │   Service        │    │    Service       │    │                  │     │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘     │
│           │                      │                     ▲                    │
│           │                      │                     │                    │
│           ▼                      ▼                     │                    │
│  ┌──────────────────┐    ┌──────────────────┐         │                    │
│  │   Anomaly        │───▶│   Alerting       │─────────┘                    │
│  │  Detection       │    │   Service        │                              │
│  └──────────────────┘    └──────────────────┘                              │
│           │                                                                   │
│           ▼                                                                   │
│  ┌──────────────────┐                                                        │
│  │  Benchmarking    │                                                        │
│  │    Service       │                                                        │
│  └──────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Storage Layer                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL                                                                  │
│  - customer_costs                                                            │
│  - margin_reports                                                            │
│  - anomalies                                                                 │
│  - customer_baselines                                                        │
│  - benchmark_metrics                                                         │
│  - alert_history                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Notification Channels                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Slack Webhook                    Email (SMTP)                                │
│  - Margin compression alerts      - Weekly margin summaries                  │
│  - Anomaly notifications          - Benchmark reports                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Cost Aggregation Service

**Purpose:** Aggregate meter events by customer to calculate total infrastructure costs.

**Input:**
- Meter events from Metering Service API
  - Endpoint: `GET /api/v1/billing/usage/{tenant_id}?period_start={start}&period_end={end}`
  - Data: Event counts per model, endpoint, timestamp

**Processing:**
- Daily batch job (cron: 1 AM UTC)
- Group events by: tenant_id, model, endpoint, day
- Apply unit costs (from pricing configuration)
- Summarize by period (daily, weekly, monthly)

**Output:**
- `CustomerCostBreakdown` record
  - Total cost for period
  - Cost breakdown by model (JSONB)
  - Cost breakdown by endpoint (JSONB)
  - Event counts

**Storage:**
- Table: `customer_costs`
- Retention: 365 days
- Partitioning: By month

**Performance Target:**
- Process 1M events in <5 minutes

### 2. Margin Calculation Service

**Purpose:** Calculate customer profitability by comparing infrastructure costs against Stripe revenue.

**Input:**
- Pre-aggregated cost data from `customer_costs` table
- Revenue data from Stripe API
  - Subscriptions: Active recurring revenue
  - Invoices: One-time charges, prorations, discounts

**Processing:**
- On-demand (API request)
- Daily batch job (cron: 2 AM UTC)

**Calculation:**
```
Revenue = Active subscriptions + Invoices (paid)
Cost to Serve = Sum(customer_costs for period)
Margin Amount = Revenue - Cost to Serve
Margin % = (Margin Amount / Revenue) * 100
```

**Margin Status Logic:**
- `HEALTHY`: margin_percentage >= 40%
- `WARNING`: 20% <= margin_percentage < 40%
- `CRITICAL`: margin_percentage < 20%

**Output:**
- `CustomerMarginReport` record
  - tenant_id
  - period_start, period_end
  - revenue (decimal)
  - cost_to_serve (decimal)
  - margin_amount (decimal)
  - margin_percentage (decimal)
  - status (enum: HEALTHY/WARNING/CRITICAL)

**Storage:**
- Table: `margin_reports`
- Retention: 365 days

**Performance Target:**
- On-demand calculation: <2 seconds (using pre-aggregated costs)

### 3. Anomaly Detection Service

**Purpose:** Detect unusual usage patterns that may indicate margin compression, abuse, or technical issues.

**Input:**
- Historical meter events (last 30 days)
- Pre-calculated baselines from `customer_baselines` table

**Processing:**
- Hourly batch job (cron: every hour)
- For each customer:
  1. Fetch last 30 days of meter events
  2. Calculate baseline metrics (mean, std dev)
  3. Compare current day metrics to baseline
  4. Flag if deviation > 20%

**Anomaly Types:**
1. `USAGE_SPIKE`: Current usage > baseline * 1.2
   - Severity: HIGH
   - Potential causes: Abuse, unexpected workload, bug

2. `USAGE_DROP`: Current usage < baseline * 0.8
   - Severity: MEDIUM
   - Potential causes: Churn risk, integration issue

3. `COST_SPIKE`: Current cost > baseline * 1.2
   - Severity: HIGH
   - Potential causes: Price change, model shift, inefficiency

4. `MARGIN_COMPRESSION`: Margin % dropped > 10% vs baseline
   - Severity: CRITICAL
   - Action: Trigger immediate alert

**Output:**
- `AnomalyAlert` record
  - tenant_id
  - anomaly_type (enum)
  - severity (enum: LOW/MEDIUM/HIGH/CRITICAL)
  - description (text)
  - baseline_value (decimal)
  - current_value (decimal)
  - deviation_percent (decimal)
  - detected_at (timestamp)

**Storage:**
- Table: `anomalies` (individual alerts)
- Table: `customer_baselines` (rolling 30-day baselines)
- Retention:
  - Anomalies: 90 days
  - Baselines: Continuous (updated daily)

**Performance Target:**
- Hourly scan for all customers: <500ms

### 4. Benchmarking Service

**Purpose:** Provide peer comparison insights while preserving customer privacy.

**Input:**
- Aggregated, anonymized customer data
  - Costs per request
  - Usage patterns
  - Model preferences

**Privacy Safeguards:**
- Hash customer IDs (SHA-256)
- Minimum threshold: 10 customers per percentile calculation
- Opt-out: Customers can disable benchmarking via config flag
- GDPR/CCPA compliant: No PII, reversible anonymization

**Processing:**
- Daily batch job (cron: 3 AM UTC)
- Filter out opted-out customers
- For each metric, calculate percentiles:
  - 25th percentile (lower quartile)
  - 50th percentile (median)
  - 75th percentile (upper quartile)

**Benchmark Metrics:**
1. `COST_PER_1K_REQUESTS`: Total cost / (total requests / 1000)
2. `AVERAGE_MODEL_TIER`: Weighted average model tier (1=basic, 2=standard, 3=premium)
3. `DAILY_REQUEST_VOLUME`: Total requests / active days
4. `MARGIN_PERCENTAGE`: Revenue vs. cost ratio

**Output:**
- `BenchmarkReport` (per customer request)
  - Your current metrics
  - Peer percentiles (25th, 50th, 75th)
  - Your ranking (e.g., "You are in the 60th percentile")
  - Contextual recommendations

- `BenchmarkMetrics` (aggregated, stored)
  - metric_name
  - period_start, period_end
  - percentile_25, percentile_50, percentile_75
  - customer_count (sample size)

**Storage:**
- Table: `benchmark_metrics`
- Retention: 365 days

**Performance Target:**
- Daily aggregation: <10 minutes
- On-demand report: <1 second (from pre-calculated percentiles)

### 5. Alerting Service

**Purpose:** Deliver timely notifications for margin issues and anomalies.

**Input:**
- `AnomalyAlert` records from Anomaly Detection Service
- `MarginCompressionAlert` events (triggered when margin status → CRITICAL)
- Manual alerts (admin-initiated)

**Processing:**
- Real-time event handler (triggered by database inserts)
- For each alert:
  1. Format message (Slack markdown or HTML email)
  2. Send to configured channels
  3. Track delivery status
  4. Retry on failure (exponential backoff: 1s, 2s, 4s, 8s)

**Alert Channels:**

1. **Slack**
   - Method: Incoming webhook
   - Config: `SLACK_WEBHOOK_URL` env variable
   - Format: Block kit with severity color
   - Latency: <5s

2. **Email**
   - Method: SMTP (async)
   - Config: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `FROM_ADDRESS`
   - Format: HTML template with action buttons
   - Latency: <30s

**Alert Types:**
1. `MARGIN_COMPRESSION`: Margin status → CRITICAL
   - Channels: Slack + Email
   - Frequency: Immediate + daily summary if persistent

2. `USAGE_ANOMALY`: Usage spike/drop detected
   - Channels: Slack only
   - Frequency: Immediate (debounce: 1 alert per customer per hour)

3. `BENCHMARK_AVAILABLE`: New weekly benchmark report
   - Channels: Email only
   - Frequency: Weekly (Monday 9 AM customer timezone)

4. `WEEKLY_MARGIN_SUMMARY`: Rolled-up margin status
   - Channels: Email only
   - Frequency: Weekly (Friday 5 PM customer timezone)

**Output:**
- `AlertHistory` record
  - tenant_id
  - alert_type (enum)
  - channel (enum: slack/email)
  - status (enum: pending/sent/failed)
  - content (JSONB: formatted message)
  - sent_at (timestamp)
  - delivered_at (timestamp)
  - error_message (text, nullable)

**Storage:**
- Table: `alert_history`
- Retention: 90 days

**Performance Target:**
- Alert delivery: <5s (Slack), <30s (email)

## Data Flow

### Daily Aggregation Flow (Automated)

```
1:00 AM UTC ──────────────────────────────────────────────────────────────────▶
│
├─ Cost Aggregation Service runs
│  ├─ Fetch meter events from Metering Service (last 24 hours)
│  ├─ Group by tenant_id, model, endpoint
│  ├─ Apply unit costs
│  └─ Write to customer_costs table
│
2:00 AM UTC ──────────────────────────────────────────────────────────────────▶
│
├─ Margin Calculation Service runs
│  ├─ Read customer_costs (new records)
│  ├─ Fetch Stripe revenue data
│  ├─ Calculate margins
│  └─ Write to margin_reports table
│
3:00 AM UTC ──────────────────────────────────────────────────────────────────▶
│
├─ Benchmarking Service runs
│  ├─ Read customer_costs (all customers, opt-out filtered)
│  ├─ Calculate percentiles
│  └─ Write to benchmark_metrics table
│
Hourly (Every Hour) ──────────────────────────────────────────────────────────▶
│
└─ Anomaly Detection Service runs
   ├─ Read customer_baselines
   ├─ Fetch current meter events (last 24 hours)
   ├─ Compare to baseline
   ├─ Write anomalies (if deviation > 20%)
   └─ Trigger Alerting Service (if anomaly found)
      ├─ Format alert (Slack/email)
      ├─ Send notification
      └─ Write to alert_history
```

### On-Demand Flow (API Request)

```
CFO Dashboard ────────────────────────────────────────────────────────────────▶
│
├─ GET /api/v1/analytics/margins?tenant_id={id}&period=2024-01
│  │
│  ├─ MarginCalculationService.handle_request()
│  │  ├─ Read pre-aggregated customer_costs
│  │  ├─ Fetch Stripe revenue (cached if <1 hour old)
│  │  ├─ Calculate margin
│  │  └─ Return CustomerMarginReport (<2s)
│  │
└─ Response: JSON with margin breakdown
```

### Alert Flow (Real-Time)

```
Anomaly Detected ──────────────────────────────────────────────────────────────▶
│
├─ AnomalyDetectionService.detect_anomaly()
│  └─ Insert record into anomalies table
│     │
│     ├─ Database trigger: new_anomaly_trigger
│     │  │
│     │  └─ AlertingService.send_alert(anomaly)
│     │     ├─ Format message (Slack markdown)
│     │     ├─ POST to SLACK_WEBHOOK_URL
│     │     ├─ Format message (HTML email)
│     │     ├─ Send via SMTP
│     │     └─ Insert delivery confirmation to alert_history
│     │
│     └─ Alert delivered to customer
│        ├─ Slack: "⚠️ Usage Spike Detected: Your usage increased..."
│        └─ Email: "Your Data Foundry usage increased 45% this week..."
```

## Database Schema

### customer_costs

Stores aggregated infrastructure costs per customer per period.

**Columns:**
- `id` (UUID, PK)
- `tenant_id` (UUID, NOT NULL, FK: tenants.id)
- `period_start` (DATE, NOT NULL)
- `period_end` (DATE, NOT NULL)
- `total_cost` (DECIMAL(10,2), NOT NULL) - Total infrastructure cost for period
- `cost_breakdown` (JSONB, NOT NULL) - Detailed breakdown:
  ```json
  {
    "by_model": [
      {"model": "gpt-4", "cost": 1250.00, "requests": 50000},
      {"model": "gpt-3.5-turbo", "cost": 320.00, "requests": 250000}
    ],
    "by_endpoint": [
      {"endpoint": "/chat/completions", "cost": 1450.00, "requests": 280000},
      {"endpoint": "/embeddings", "cost": 120.00, "requests": 20000}
    ]
  }
  ```
- `created_at` (TIMESTAMP, DEFAULT NOW())
- `updated_at` (TIMESTAMP, DEFAULT NOW())

**Indexes:**
- `idx_customer_costs_tenant_period` ON (tenant_id, period_start, period_end)
- `idx_customer_costs_period` ON (period_start, period_end)

**Retention:** 365 days (partitioned by month)

**Constraints:**
- UNIQUE (tenant_id, period_start, period_end)
- CHECK (period_end >= period_start)

---

### margin_reports

Stores customer profitability metrics (revenue vs. cost).

**Columns:**
- `id` (UUID, PK)
- `tenant_id` (UUID, NOT NULL, FK: tenants.id)
- `period_start` (DATE, NOT NULL)
- `period_end` (DATE, NOT NULL)
- `revenue` (DECIMAL(10,2), NOT NULL) - From Stripe (subscriptions + invoices)
- `cost_to_serve` (DECIMAL(10,2), NOT NULL) - From customer_costs
- `margin_amount` (DECIMAL(10,2), NOT NULL) - revenue - cost_to_serve
- `margin_percentage` (DECIMAL(5,2), NOT NULL) - (margin_amount / revenue) * 100
- `status` (VARCHAR(20), NOT NULL) - HEALTHY / WARNING / CRITICAL
- `created_at` (TIMESTAMP, DEFAULT NOW())
- `updated_at` (TIMESTAMP, DEFAULT NOW())

**Indexes:**
- `idx_margin_reports_tenant_period` ON (tenant_id, period_start, period_end)
- `idx_margin_reports_status` ON (status)

**Retention:** 365 days (partitioned by month)

**Constraints:**
- UNIQUE (tenant_id, period_start, period_end)
- CHECK (revenue >= 0)
- CHECK (cost_to_serve >= 0)
- CHECK (status IN ('HEALTHY', 'WARNING', 'CRITICAL'))

---

### anomalies

Stores detected usage/cost anomalies.

**Columns:**
- `id` (UUID, PK)
- `tenant_id` (UUID, NOT NULL, FK: tenants.id)
- `anomaly_type` (VARCHAR(50), NOT NULL) - USAGE_SPIKE / USAGE_DROP / COST_SPIKE / MARGIN_COMPRESSION
- `severity` (VARCHAR(20), NOT NULL) - LOW / MEDIUM / HIGH / CRITICAL
- `description` (TEXT, NOT NULL) - Human-readable explanation
- `baseline_value` (DECIMAL(10,2), NOT NULL) - Expected value (30-day avg)
- `current_value` (DECIMAL(10,2), NOT NULL) - Actual value
- `deviation_percent` (DECIMAL(5,2), NOT NULL) - % difference from baseline
- `detected_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `acknowledged_at` (TIMESTAMP, NULLABLE) - When customer acknowledged
- `resolved_at` (TIMESTAMP, NULLABLE) - When issue was resolved

**Indexes:**
- `idx_anomalies_tenant_detected` ON (tenant_id, detected_at DESC)
- `idx_anomalies_severity` ON (severity)
- `idx_anomalies_unresolved` ON (tenant_id) WHERE resolved_at IS NULL

**Retention:** 90 days

**Constraints:**
- CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
- CHECK (deviation_percent > 20) - Only store significant anomalies
- CHECK (resolved_at IS NULL OR resolved_at >= detected_at)

---

### customer_baselines

Stores rolling 30-day baseline metrics for anomaly detection.

**Columns:**
- `id` (UUID, PK)
- `tenant_id` (UUID, NOT NULL, FK: tenants.id)
- `metric_name` (VARCHAR(100), NOT NULL) - daily_requests, daily_cost, avg_cost_per_request
- `baseline_value` (DECIMAL(10,2), NOT NULL) - 30-day average
- `baseline_std_dev` (DECIMAL(10,2), NOT NULL) - Standard deviation
- `baseline_period_start` (DATE, NOT NULL) - Start of 30-day window
- `baseline_period_end` (DATE, NOT NULL) - End of 30-day window
- `calculated_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())

**Indexes:**
- `idx_baselines_tenant_metric` ON (tenant_id, metric_name)
- `idx_baselines_calculated` ON (calculated_at DESC)

**Retention:** Continuous (updated daily, keep latest per metric)

**Constraints:**
- UNIQUE (tenant_id, metric_name)
- CHECK (baseline_std_dev >= 0)

---

### benchmark_metrics

Stores aggregated, anonymized peer metrics for benchmarking.

**Columns:**
- `id` (UUID, PK)
- `metric_name` (VARCHAR(100), NOT NULL) - COST_PER_1K_REQUESTS, MARGIN_PERCENTAGE, etc.
- `period_start` (DATE, NOT NULL)
- `period_end` (DATE, NOT NULL)
- `percentile_25` (DECIMAL(10,2), NOT NULL) - Lower quartile
- `percentile_50` (DECIMAL(10,2), NOT NULL) - Median
- `percentile_75` (DECIMAL(10,2), NOT NULL) - Upper quartile
- `customer_count` (INTEGER, NOT NULL) - Sample size (min 10)
- `created_at` (TIMESTAMP, DEFAULT NOW())

**Indexes:**
- `idx_benchmark_metric_period` ON (metric_name, period_start, period_end)

**Retention:** 365 days

**Constraints:**
- CHECK (customer_count >= 10) - Privacy threshold
- CHECK (percentile_25 <= percentile_50 AND percentile_50 <= percentile_75)
- UNIQUE (metric_name, period_start, period_end)

---

### alert_history

Stores delivery history for all alerts.

**Columns:**
- `id` (UUID, PK)
- `tenant_id` (UUID, NOT NULL, FK: tenants.id)
- `alert_type` (VARCHAR(50), NOT NULL) - MARGIN_COMPRESSION / USAGE_ANOMALY / BENCHMARK_AVAILABLE / WEEKLY_MARGIN_SUMMARY
- `channel` (VARCHAR(20), NOT NULL) - slack / email
- `status` (VARCHAR(20), NOT NULL) - pending / sent / failed
- `content` (JSONB, NOT NULL) - Formatted message:
  ```json
  {
    "slack": {"blocks": [...]},
    "email": {"subject": "...", "html_body": "..."}
  }
  ```
- `sent_at` (TIMESTAMP, NOT NULL, DEFAULT NOW())
- `delivered_at` (TIMESTAMP, NULLABLE)
- `error_message` (TEXT, NULLABLE)
- `retry_count` (INTEGER, DEFAULT 0)

**Indexes:**
- `idx_alert_history_tenant_sent` ON (tenant_id, sent_at DESC)
- `idx_alert_history_status` ON (status)

**Retention:** 90 days

**Constraints:**
- CHECK (channel IN ('slack', 'email'))
- CHECK (status IN ('pending', 'sent', 'failed'))
- CHECK (retry_count >= 0)

## Integration Points

### Data Sources (Read-Only Access)

#### Metering Service API

Fetches meter events for cost aggregation.

**Base URL:** `https://billing.data-foundry.com/api/v1`

**Authentication:** API Key (Bearer token)

**Endpoints:**

1. **Get Customer Usage**
   ```
   GET /billing/usage/{tenant_id}
   Query Params:
     - period_start (ISO date)
     - period_end (ISO date)
     - granularity (hour/day/week/month, default: day)
   Response:
   {
     "tenant_id": "uuid",
     "period_start": "2024-01-01",
     "period_end": "2024-01-31",
     "events": [
       {
         "timestamp": "2024-01-01T10:00:00Z",
         "model": "gpt-4",
         "endpoint": "/chat/completions",
         "event_count": 1250,
         "unit_cost": 0.03
       },
       ...
     ]
   }
   ```

2. **Get Usage Summary**
   ```
   GET /billing/usage/{tenant_id}/summary
   Query Params:
     - period_start (ISO date)
     - period_end (ISO date)
   Response:
   {
     "total_events": 500000,
     "total_cost": 1250.00,
     "by_model": {...},
     "by_endpoint": {...}
   }
   ```

**Frequency:**
- Daily batch: 1 AM UTC (full sync for last 24 hours)
- On-demand: When customer requests margin report (cached for 1 hour)

**Error Handling:**
- Retry on failure (exponential backoff: 1s, 2s, 4s, 8s)
- Timeout: 30 seconds
- Fallback: Use cached data if available

---

#### Stripe API

Fetches revenue data for margin calculation.

**Base URL:** `https://api.stripe.com/v1`

**Authentication:** Stripe secret key (sk_live_...)

**Endpoints:**

1. **Get Active Subscriptions**
   ```
   GET /subscriptions?status=active&customer={stripe_customer_id}
   Response:
   {
     "data": [
       {
         "id": "sub_...",
         "items": {
           "data": [
             {
               "price": {
                 "id": "price_...",
                 "unit_amount": 2900,
                 "recurring": {"interval": "month"}
               },
               "quantity": 1
             }
           ]
         }
       }
     ]
   }
   ```

2. **Get Paid Invoices**
   ```
   GET /invoices?customer={stripe_customer_id}&status=paid
   Response:
   {
     "data": [
       {
         "id": "in_...",
         "total": 5000,
         "currency": "usd",
         "status_transitions": {"paid_at": 1234567890}
       }
     ]
   }
   ```

**Frequency:**
- Daily batch: 2 AM UTC (fetch last 24 hours of paid invoices)
- On-demand: When customer requests margin report (cached for 1 hour)

**Error Handling:**
- Retry on network errors (max 3 retries)
- Log API errors to Sentry
- Use cached subscription data (refresh hourly)

---

### Notification Channels (Write Access)

#### Slack

Sends real-time alerts to customer Slack channels.

**Method:** Incoming webhook

**Configuration:**
- Environment variable: `SLACK_WEBHOOK_URL`
- Format: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX`

**Message Format:** Block kit
```json
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "⚠️ Margin Compression Alert"
      }
    },
    {
      "type": "section",
      "fields": [
        {"type": "mrkdwn", "text": "*Severity:*\nCritical"},
        {"type": "mrkdwn", "text": "*Margin:*\n15% (down from 42%)"}
      ]
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {"type": "plain_text", "text": "View Dashboard"},
          "url": "https://app.data-foundry.com/analytics/margins"
        }
      ]
    }
  ]
}
```

**Latency:** <5 seconds

**Error Handling:**
- Log failed deliveries to `alert_history`
- Retry on failure (max 3 retries, exponential backoff)
- Fallback to email if Slack unavailable

---

#### Email

Sends detailed alerts and weekly summaries.

**Method:** SMTP (async via Celery task)

**Configuration:**
- `SMTP_HOST`: smtp.resend.com (or AWS SES, SendGrid)
- `SMTP_PORT`: 587
- `SMTP_USER`: api_key
- `SMTP_PASS`: api_secret
- `FROM_ADDRESS`: alerts@data-foundry.com

**Message Format:** HTML (responsive template)
```html
<!DOCTYPE html>
<html>
<head>
  <style>
    .alert-critical { background-color: #fee2e2; }
    .metric { font-size: 24px; font-weight: bold; }
  </style>
</head>
<body>
  <div class="alert-critical">
    <h1>⚠️ Critical: Margin Compression Detected</h1>
    <p>Your margin dropped to 15% this week (down from 42%).</p>
    <div class="metric">-63% vs. last month</div>
    <a href="https://app.data-foundry.com/analytics/margins">View Details</a>
  </div>
</body>
</html>
```

**Latency:** <30 seconds

**Error Handling:**
- Log bounced emails to `alert_history`
- Retry soft bounces (max 3 retries)
- Disable recipients after 5 hard bounces

## Technology Stack

### Backend Framework

- **FastAPI** (Python 3.11+)
  - Async/await for high concurrency
  - Automatic OpenAPI docs
  - Pydantic for request/validation

### Database

- **PostgreSQL 14+**
  - JSONB for flexible cost breakdowns
  - Partitioning for time-series data
  - Row-level security (RLS) for multi-tenant isolation

### Analytics Libraries

- **pandas** - Data manipulation (cost aggregation)
- **numpy** - Numerical operations (percentile calculations)
- **scipy** - Statistical functions (baseline calculations)

### Caching

- **Redis** (optional, for performance)
  - Cache Stripe responses (TTL: 1 hour)
  - Cache benchmark metrics (TTL: 24 hours)
  - Session storage for dashboard

### Task Queue

- **Celery + Redis**
  - Daily batch jobs (cost aggregation, margin calculation)
  - Hourly anomaly scans
  - Async email delivery

### Notifications

- **slack-sdk** - Slack webhook client
- **aiosmtplib** - Async SMTP client

### Monitoring

- **Sentry** - Error tracking
- **Datadog** - Metrics and performance monitoring

## Performance Targets

| Component | Operation | Target | Notes |
|-----------|-----------|--------|-------|
| Cost Aggregation | Process 1M events | <5 min | Batch job, daily |
| Margin Calculation | On-demand report | <2s | Uses pre-aggregated costs |
| Anomaly Detection | Hourly scan (all customers) | <500ms | Baseline comparison |
| Benchmarking | Daily percentile calculation | <10 min | Aggregate all customers |
| Alert Delivery | Slack webhook | <5s | Real-time notifications |
| Alert Delivery | Email (SMTP) | <30s | Async via Celery |
| Dashboard API | Load margin report | <500ms | Cached response |
| Dashboard API | Load benchmark report | <300ms | Pre-calculated percentiles |

## Security & Privacy

### Multi-Tenant Isolation

- **Tenant Context:** All queries include `tenant_id` filter
- **Row-Level Security (RLS):** PostgreSQL policies enforce tenant isolation at DB level
- **API Authentication:** JWT tokens include `tenant_id` claim

### Data Access Controls

- **Role-Based Access Control (RBAC):**
  - `admin`: Full access to all tenants
  - `customer_full`: Full access to own tenant data
  - `customer_readonly`: Read-only access to own tenant data

### API Authentication

- **JWT Tokens:** Signed with HS256, TTL: 1 hour
- **API Keys:** Alternative for service-to-service communication
- **Rate Limiting:** 100 requests/minute per tenant

### Benchmarking Privacy

**Anonymization:**
- Hash customer IDs with SHA-256 (salt: per-deployment secret)
- Remove PII before aggregation
- No reverse lookup possible

**Minimum Threshold:**
- Only calculate percentiles if >= 10 customers in dataset
- If < 10, return "insufficient data" message

**Opt-Out:**
- Customer flag: `benchmarking_enabled` (default: true)
- Filtered out before aggregation
- Stored in `tenables` table

**GDPR/CCPA Compliance:**
- No PII stored in benchmark metrics
- Right to deletion: Customer data removed from all tables within 30 days
- Data export: Provide full analytics export on request

## Deployment

### Containerization

- **Docker** - Single container for all services
- **Base Image:** `python:3.11-slim`
- **Port:** 8000 (HTTP)

### Orchestration

- **Kubernetes** - For batch jobs (Cost Aggregation, Margin Calculation, etc.)
  - CronJob: `cost-aggregation` (schedule: "0 1 * * *")
  - CronJob: `margin-calculation` (schedule: "0 2 * * *")
  - CronJob: `benchmarking` (schedule: "0 3 * * *")
  - CronJob: `anomaly-detection` (schedule: "0 * * * *")

### Environment Variables

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `STRIPE_SECRET_KEY` - Stripe API key
- `JWT_SECRET` - JWT signing secret
- `SLACK_WEBHOOK_URL` - Slack webhook (optional, if alerts enabled)

**Optional:**
- `REDIS_URL` - Redis for caching (default: none)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` - Email config
- `SENTRY_DSN` - Error tracking
- `DATADOG_API_KEY` - Metrics monitoring

### Monitoring & Observability

- **Logging:** JSON logs to stdout (captured by Kubernetes)
  - Format: `{"level": "INFO", "tenant_id": "uuid", "message": "..."}`
- **Metrics:** Datadog agent integration
  - Track: job duration, API latency, error rates
- **Tracing:** OpenTelemetry (optional)
  - Distributed tracing for async workflows
- **Alerts:** PagerDuty integration for critical failures

## Next Steps

### Documentation

- **[API_SPECIFICATION.md](./API_SPECIFICATION.md)** - Complete API contracts for all analytics endpoints
- **[IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)** - Development phases, MVP scope, timeline

### Implementation

1. **Phase 1:** Cost Aggregation + Margin Calculation (MVP)
2. **Phase 2:** Anomaly Detection + Alerting
3. **Phase 3:** Benchmarking Service
4. **Phase 4:** Dashboard Frontend (React)

### Prerequisites

- Metering Service must be deployed and operational
- Stripe integration configured (products, prices, webhooks)
- PostgreSQL database provisioned (with partitioning enabled)
- Slack webhook configured (for alerts)
