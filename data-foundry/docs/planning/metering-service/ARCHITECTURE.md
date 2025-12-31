# Metering Service - Architecture

## High-Level Overview

The Metering Service is a production-grade usage tracking and billing backend for SaaS platforms. It integrates with Stripe for metered billing, tracks usage across multiple meter types, calculates costs, and ensures reliable synchronization between your system and Stripe.

```
┌──────────────────────────────────────────────────────────────────┐
│                    EXTERNAL CLIENTS                              │
│  (SaaS Platforms, AI API Builders, Indie Hackers)               │
└────────┬─────────────────────────────────┬──────────────────────┘
         │                                  │
         │ HTTP (REST API)                  │ Stripe Webhooks
         │                                  │ (subscription events)
┌────────▼──────────────────────────────────▼──────────────────────┐
│                  METERING SERVICE                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              FASTAPI APPLICATION                            ││
│  │  ┌────────────────────────────────────────────────────────┐││
│  │  │ Endpoints:                                             │││
│  │  │ • POST   /api/v1/billing/customers           (CRUD)    │││
│  │  │ • POST   /api/v1/billing/subscriptions       (CRUD)    │││
│  │  │ • GET    /api/v1/billing/usage/{tenant_id}   (stats)   │││
│  │  │ • POST   /api/v1/billing/webhook             (Stripe)  │││
│  │  │ • GET    /api/v1/billing/status              (health)  │││
│  │  └────────────────────────────────────────────────────────┘││
│  │                                                             ││
│  │  ┌────────────────────────────────────────────────────────┐││
│  │  │ Core Services:                                         │││
│  │  │ • StripeService: Customers, subscriptions, events     │││
│  │  │ • UsageCalculationService: Meter events, batching     │││
│  │  │ • CostCalculationService: AI pricing across providers │││
│  │  │ • MeterEventService: Report to Stripe (idempotent)   │││
│  │  │ • IdempotencyService: Prevent duplicate events        │││
│  │  │ • RetryService: Exponential backoff on failures      │││
│  │  │ • WebhookHandler: Process Stripe events              │││
│  │  └────────────────────────────────────────────────────────┘││
│  │                                                             ││
│  │  ┌────────────────────────────────────────────────────────┐││
│  │  │ Middleware:                                            │││
│  │  │ • Authentication (JWT tokens)                          │││
│  │  │ • Tenant Isolation (enforce per-tenant access)        │││
│  │  │ • Rate Limiting (per-tier request limits)             │││
│  │  │ • Request/Response Logging                             │││
│  │  │ • Error Handling                                       │││
│  │  └────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────┘│
└──────┬────────────────────┬───────────────┬────────────────┬────┘
       │                    │               │                │
       │ SQL                │ HTTP/REST     │ Async Queue    │ Event
       │ (Read/Write)       │ (Stripe API)  │ (Webhooks)     │ Publishing
       │                    │               │                │
┌──────▼─────────────┐ ┌───▼──────────┐ ┌──▼──────────┐ ┌──▼──────┐
│  POSTGRESQL        │ │  STRIPE API  │ │   REDIS    │ │ MESSAGE  │
│  ┌──────────────┐  │ │  (External)  │ │ (Optional) │ │ QUEUE    │
│  │ customers    │  │ │              │ │            │ │(Optional)│
│  │ subscriptions│  │ │ • Create     │ │ • Cache    │ │          │
│  │ meter_events │  │ │ • Update     │ │ • Queue    │ │ Webhook  │
│  │ usage_tokens │  │ │ • Report     │ │            │ │ events   │
│  │ billing_evts │  │ │   usage      │ │            │ │          │
│  │ audit_logs   │  │ │ • Webhooks   │ │            │ │ Retry    │
│  └──────────────┘  │ │              │ │            │ │ queue    │
└────────────────────┘ └───────────────┘ └────────────┘ └──────────┘
```

---

## Component Breakdown

### 1. API Gateway (FastAPI)
**Responsibility:** HTTP request handling, routing, authentication, response serialization

**Endpoints:**

**Customer Management:**
- `POST /api/v1/billing/customers` - Create Stripe customer (maps tenant → Stripe ID)
- `GET /api/v1/billing/customers/{tenant_id}` - Retrieve customer info
- `PUT /api/v1/billing/customers/{tenant_id}` - Update customer metadata
- `DELETE /api/v1/billing/customers/{tenant_id}` - Delete customer (archive in DB)

**Subscription Management:**
- `POST /api/v1/billing/subscriptions` - Create subscription (attach to customer + pricing)
- `GET /api/v1/billing/subscriptions/{tenant_id}` - Get current subscription status
- `PUT /api/v1/billing/subscriptions/{tenant_id}` - Update subscription (tier change, cancel at period end)
- `DELETE /api/v1/billing/subscriptions/{tenant_id}` - Cancel subscription (immediate or at period end)

**Usage & Billing:**
- `GET /api/v1/billing/usage/{tenant_id}` - Get usage summary (costs, meter events, sync status)
- `POST /api/v1/billing/usage/report` - Report meter events (internal, for AI pipeline)

**Webhooks:**
- `POST /api/v1/billing/webhook` - Receive Stripe webhook events

**Health:**
- `GET /api/v1/billing/health` - Service health check

**Characteristics:**
- Stateless (can scale horizontally)
- All customer/subscription state managed by Stripe (single source of truth)
- Your DB acts as audit log + cache
- Fast response times (mostly lookups)

---

### 2. Stripe Service (Facade)
**Responsibility:** Unified interface to Stripe API + local operations

**Primary Operations:**

**Customer Lifecycle:**
```
Create Customer
  ├─ Input: tenant_id, email, name, metadata
  ├─ Call Stripe API: Create customer (returns cus_XXXXX)
  ├─ Store in DB: StripeCustomer(tenant_id, stripe_customer_id, email, name)
  └─ Return: CustomerResponse

Get Customer
  ├─ Query DB: SELECT * FROM stripe_customers WHERE tenant_id = ?
  ├─ Verify customer exists in Stripe (optional sync check)
  └─ Return: CustomerResponse

Update Customer
  ├─ Update Stripe: PATCH /customers/{stripe_customer_id}
  ├─ Update DB: UPDATE stripe_customers
  └─ Return: CustomerResponse

Delete Customer
  ├─ Stripe doesn't support deletion (use deletion)
  ├─ Mark as inactive in DB: UPDATE stripe_customers SET deleted_at = NOW()
  └─ Return: Success response
```

**Subscription Lifecycle:**
```
Create Subscription
  ├─ Input: stripe_customer_id, tier, price_id
  ├─ Call Stripe API: Create subscription
  │  └─ POST /subscriptions { customer: cus_XXX, items: [ { price: price_XXX } ] }
  ├─ Store in DB: StripeSubscription(tenant_id, stripe_subscription_id, status, tier)
  └─ Return: SubscriptionResponse

Update Subscription
  ├─ Input: stripe_subscription_id, tier (for tier change)
  ├─ Calculate: price_id for new tier
  ├─ Call Stripe API: Update subscription items
  └─ Update DB & return

Cancel Subscription
  ├─ Input: stripe_subscription_id, immediate (boolean)
  ├─ If immediate: DELETE /subscriptions/{id}
  ├─ Else: PATCH /subscriptions/{id} { cancel_at_period_end: true }
  ├─ Update DB: mark as canceled
  └─ Return: SubscriptionResponse
```

**Cost Calculation Integration:**
```
Get Usage Summary
  ├─ Query: meter_events for tenant (this billing period)
  ├─ Aggregate: count by event type (ai_labels, human_audits, etc.)
  ├─ Calculate: cost using CostCalculationService
  │  └─ For each meter type: quantity × unit_price[tier]
  ├─ Get Stripe sync status: check if events synced
  └─ Return: UsageSummaryResponse with costs + metrics
```

---

### 3. Usage Calculation Service
**Responsibility:** Transform application events into billable meter events

**Input Source:** AI labeling pipeline (AML, data quality, etc.)

**Processing:**
```
AI Operation Completes
  ├─ Event: { tenant_id, operation: "aml_label", confidence: 0.92, cost: $0.001 }
  ├─ Classify: If confidence >= 0.85 → meter_type = "ai_labels"
  │           Else → meter_type = "human_audits"
  ├─ Aggregate: Batch events by tenant + meter type
  ├─ Create: StripeMeterEvent
  │  ├─ tenant_id
  │  ├─ event_name (ai_labels | human_audits)
  │  ├─ quantity (number of events in batch)
  │  ├─ batch_id (for idempotency)
  │  ├─ idempotency_key (unique, prevents Stripe duplicates)
  │  ├─ status (pending)
  │  └─ timestamp
  └─ Queue: Send to MeterEventService for Stripe reporting
```

**Key Features:**
- Confidence-based classification (high confidence = cheaper ai_labels, low = expensive human_audits)
- Batch processing (don't send 1 event at a time)
- Tenant isolation (each tenant's events tracked separately)
- Idempotency (same event never counted twice)

---

### 4. Cost Calculation Service
**Responsibility:** Calculate costs across multiple AI providers and models

**Input:** Model name, prompt tokens, completion tokens, tenant_id, tier

**Processing:**
```
Calculate Cost
  ├─ Input: model="gpt-4o", prompt_tokens=1000, completion_tokens=500, tier="growth"
  ├─ Lookup: Provider pricing
  │  ├─ OpenAI GPT-4o: $0.005/1K input, $0.015/1K output
  │  ├─ Anthropic Claude 3.5: $0.003/1K input, $0.015/1K output
  │  └─ [Multiple providers supported]
  ├─ Calculate:
  │  ├─ input_cost = (prompt_tokens / 1000) × input_price
  │  ├─ output_cost = (completion_tokens / 1000) × output_price
  │  ├─ subtotal = input_cost + output_cost
  │  └─ If tier=="growth" AND subtotal > threshold: Apply volume discount
  ├─ Store: TokenUsage record for audit
  └─ Return: Cost + detailed breakdown
```

**Tier-Based Pricing:**
```
Starter Tier:
  - ai_labels: $0.002/event
  - human_audits: $0.02/event

Growth Tier:
  - ai_labels: $0.001/event (50% discount)
  - human_audits: $0.01/event

Enterprise Tier:
  - Custom pricing per contract
```

**Integration with Metering:**
- CostCalculationService calculates → stored in TokenUsage
- UsageCalculationService transforms → sent to Stripe as meter events
- StripeService combines → returned as usage summary

---

### 5. Meter Event Service
**Responsibility:** Report usage events to Stripe (with idempotency and retry)

**Key Challenge:** Stripe API can be flaky; must guarantee "exactly once" delivery

**Solution: Idempotency**
```
First Attempt
  ├─ Generate: idempotency_key = sha256(tenant_id + event_name + batch_id + timestamp)
  ├─ Register: Store in idempotency registry (24-hour TTL)
  ├─ Call Stripe:
  │  POST /v1/billing/meter_events {
  │    event_name: "ai_labels",
  │    value: 150,
  │    timestamp: 1704067200,
  │    idempotency_key: "abc123def456"
  │  }
  ├─ Stripe: Checks if idempotency_key seen before
  │  ├─ If YES: Returns cached response (no duplicate charge)
  │  └─ If NO: Creates new meter event (first time seeing this key)
  └─ Store result in DB: StripeMeterEvent(status=succeeded)

Retry on Failure
  ├─ Same idempotency_key used
  ├─ Stripe: "I've seen this key before"
  ├─ Result: Same meter event, no duplicate
  └─ No overcharge due to retries
```

**Retry Logic:**
```
Attempt 1: Immediate
Attempt 2: Wait 1s + backoff
Attempt 3: Wait 2s + backoff
Attempt 4: Wait 4s + backoff
Attempt 5: Wait 8s + backoff
After 5 attempts: Mark as failed, alert ops
```

---

### 6. Idempotency Service
**Responsibility:** Manage idempotency keys, prevent duplicate Stripe charges

**Data Structure:**
```
idempotency_registry: {
  "key_abc123def456": {
    tenant_id: "tenant_123",
    event_name: "ai_labels",
    first_seen: 2025-01-01T12:00:00Z,
    expires_at: 2025-01-02T12:00:00Z,  # 24 hour TTL
    response: { event_id: "evt_..." }
  }
}
```

**Operations:**
- `register(key, value)` - Store idempotency key (24h TTL)
- `lookup(key)` - Check if key exists (returns cached response if so)
- `cleanup()` - Periodic job to remove expired keys

**Implementation:**
- Store in Redis (for speed) with TTL
- Fallback to PostgreSQL if Redis unavailable
- Automatic cleanup via cron job

---

### 7. Webhook Handler
**Responsibility:** Process Stripe webhook events, sync subscription state

**Stripe Events Handled:**
```
1. invoice.payment_succeeded
   ├─ Action: Mark invoice as paid
   ├─ Update DB: Update billing_event status
   └─ Trigger: Send customer receipt email

2. invoice.payment_failed
   ├─ Action: Retry payment (Stripe does this automatically)
   ├─ Alert: Notify customer to update payment method
   └─ Update DB: Mark as failed, retry count

3. customer.subscription.created
   ├─ Action: Sync subscription to local DB
   ├─ Store: StripeSubscription record
   └─ Status: Set to "active"

4. customer.subscription.updated
   ├─ Action: Sync status changes (tier change, cancel_at_period_end set)
   ├─ Update DB: Update subscription record
   └─ Notify: Customer if tier changed

5. customer.subscription.deleted
   ├─ Action: Mark as canceled
   ├─ Update DB: Set status = "canceled", set canceled_at
   └─ Stop: No more charges after this event
```

**Webhook Security:**
```
POST /api/v1/billing/webhook

Headers:
  - stripe-signature: t=1704067200,v1=abc123def456...

Processing:
  ├─ Extract timestamp from signature
  ├─ Calculate: HMAC-SHA256(timestamp + body, STRIPE_WEBHOOK_SECRET)
  ├─ Compare: Calculated signature vs. provided signature
  ├─ If mismatch: Return 401 Unauthorized
  ├─ If match: Process event
  └─ Return: 200 OK (even if processing fails internally)
```

**Retry Logic:**
- Stripe retries webhook delivery automatically (12 hours, exponential backoff)
- Your service should be idempotent (same webhook can be processed multiple times)
- Store webhook IDs in DB to detect duplicates

---

### 8. Database Layer (PostgreSQL)
**Responsibility:** Persistent storage of customers, subscriptions, usage, audit trails

**Core Tables:**

**stripe_customers**
```sql
id | tenant_id | stripe_customer_id | email | name | metadata |
created_at | updated_at | deleted_at
```
- Primary Key: id
- Unique Index: (tenant_id, stripe_customer_id)
- Use: Map local tenants to Stripe customers

**stripe_subscriptions**
```sql
id | tenant_id | stripe_subscription_id | stripe_customer_id | status |
tier | current_period_start | current_period_end | cancel_at_period_end |
created_at | updated_at | canceled_at
```
- Indexes: (tenant_id), (stripe_subscription_id)
- Status: active | canceled | past_due | trialing | incomplete
- Use: Track subscription lifecycle

**stripe_meter_events**
```sql
id | tenant_id | event_name | quantity | batch_id | idempotency_key |
stripe_response | status | error_message | retry_count | created_at |
updated_at | retried_at
```
- Indexes: (tenant_id), (idempotency_key), (status)
- Status: pending | succeeded | failed
- Use: Track all meter events (audit trail + retry state)

**token_usage** (from cost calculation)
```sql
id | tenant_id | user_id | request_id | model | provider |
prompt_tokens | completion_tokens | total_tokens | total_cost |
success | created_at
```
- Indexes: (tenant_id), (created_at)
- Use: Detailed cost breakdown per request

**tenant_usage** (aggregated for billing)
```sql
id | tenant_id | period_type | period_start | period_end |
total_requests | total_cost | cost_by_model | billing_status |
invoice_id | created_at
```
- Indexes: (tenant_id, period_start)
- billing_status: pending | processing | completed | failed | refunded
- Use: Monthly usage summaries for invoicing

**audit_logs**
```sql
id | tenant_id | user_id | action | resource | status | error |
timestamp
```
- Use: Compliance audit trail (customer-initiated operations)

---

### 9. Authentication & Authorization
**Method:** JWT Bearer Tokens + Tenant Isolation

**Token Claims:**
```json
{
  "user_id": "user_123",
  "tenant_id": "tenant_456",
  "tier": "growth",
  "exp": 1704067200,
  "iat": 1704066300
}
```

**Authorization Flow:**
```
Request
  ├─ Header: Authorization: Bearer <jwt_token>
  ├─ Extract tenant_id from token
  ├─ Extract tenant_id from request path (e.g., /api/v1/billing/customers/{tenant_id})
  ├─ Verify: token.tenant_id == request.tenant_id
  │  └─ If mismatch: Return 403 Forbidden (cross-tenant access attempt)
  ├─ Check tier for feature access
  │  └─ E.g., "human_audits" meter only available for growth+ tier
  └─ Process request scoped to tenant_id

Result: Complete tenant isolation
```

**Security:**
- Tokens signed with RS256 (asymmetric, more secure)
- Token expiration: 1 hour
- Refresh tokens: 7 days (rotated)
- No session state (stateless, can scale)

---

### 10. Rate Limiting
**Responsibility:** Prevent abuse, enforce fair usage per tier

**Rules:**
```
Starter Tier:
  - 10 requests/minute per API key
  - 100 requests/hour

Growth Tier:
  - 100 requests/minute per API key
  - 1000 requests/hour

Enterprise Tier:
  - Custom limits per contract
```

**Implementation:**
- Token bucket algorithm (allows burst traffic)
- In-memory counter (fast) or Redis (distributed)
- Return 429 (Too Many Requests) when exceeded
- Include rate limit headers in response

---

## External Dependencies

### Required (Essential)
- **Stripe Account** with metered billing enabled
- **Stripe API Keys:** Secret key (for API calls), Webhook secret (for signatures)
- **PostgreSQL 12+:** Persistent storage
- **Python 3.11+:** Runtime environment

### Stripe Configuration (Must Set Up)
```
1. Create Meters in Stripe:
   - Meter ID 1: "ai_labels" (for AI labeling events)
   - Meter ID 2: "human_audits" (for human review events)

2. Create Price IDs for each tier:
   - Starter:
     * price_ai_labels_starter
     * price_human_audits_starter
   - Growth:
     * price_ai_labels_growth
     * price_human_audits_growth
   - Enterprise: Custom

3. Create Products (if not auto-created):
   - Product: "AI Labeling"
   - Product: "Human Audits"
```

### Optional (Nice to Have)
- **Redis:** Cache + distributed rate limiting (default: in-memory)
- **Sentry:** Error tracking
- **Datadog/NewRelic:** Performance monitoring
- **Message Queue:** For async webhook retries (default: database queue)

### NOT Needed
- No additional AI services (cost calculation is algorithmic)
- No authentication provider (JWT is self-signed)

---

## Data Flow Diagram

### Complete Billing Workflow

```
SaaS Application
  ├─ AI Operation Completes (e.g., AML label)
  ├─ Event: { tenant_id, operation: "aml_label", confidence: 0.92 }
  │
  └─ UsageCalculationService
     ├─ Classify: confidence >= 0.85 → meter_type = "ai_labels"
     ├─ Aggregate: Batch events (e.g., 100 events together)
     ├─ Create: StripeMeterEvent(batch_id, idempotency_key, status=pending)
     └─ Queue: Send to MeterEventService
        │
        └─ MeterEventService
           ├─ Check idempotency key (not seen before?)
           ├─ Call Stripe: POST /v1/billing/meter_events
           │  └─ Stripe: Create meter event (charge customer)
           ├─ Store response: StripeMeterEvent(status=succeeded)
           ├─ On failure: Retry with exponential backoff (same idempotency key)
           └─ Log result: audit_logs
              │
              └─ Stripe (Meanwhile)
                 ├─ Aggregate meter events (daily)
                 ├─ Calculate: quantity × unit_price[tier]
                 ├─ Create invoice (at period end)
                 ├─ Send: Webhook to your service
                 │  └─ POST /api/v1/billing/webhook
                 │     ├─ Event: invoice.payment_succeeded
                 │     ├─ Your service: Verify signature
                 │     ├─ Update DB: Mark invoice as paid
                 │     └─ Send customer receipt
                 └─ Charge customer (automatic payment)

Customer Portal (via your API)
  ├─ GET /api/v1/billing/usage/{tenant_id}
  │  └─ Returns: Usage summary for current billing period
  │     ├─ Total meter events: 1,500 ai_labels, 50 human_audits
  │     ├─ Estimated cost: $2.50
  │     └─ Sync status: All events synced to Stripe
  │
  ├─ PUT /api/v1/billing/subscriptions/{tenant_id}
  │  └─ Action: Upgrade from Starter to Growth tier
  │     ├─ Call Stripe: Update subscription (new price)
  │     ├─ Update DB: tier = "growth"
  │     └─ New pricing: $0.001/ai_label (vs $0.002 before)
  │
  └─ DELETE /api/v1/billing/subscriptions/{tenant_id}
     └─ Action: Cancel subscription
        ├─ Stripe: Cancel at period end (finish current billing cycle)
        ├─ DB: Updated cancel_at_period_end = true
        └─ No more charges after period end
```

---

## Multi-Tenancy Model

**Isolation Level:** Complete isolation (no data cross-contamination)

**Implementation:**
```
Tenant Creation
  ├─ Input: tenant_id (unique identifier for customer)
  ├─ Create: Stripe customer (receives cus_XXXXX)
  ├─ Store: StripeCustomer(tenant_id, stripe_customer_id)
  └─ Result: Tenant now has a Stripe customer ID

API Request (with JWT token containing tenant_id)
  ├─ GET /api/v1/billing/usage/{tenant_id}
  ├─ Token verification: token.tenant_id == path.tenant_id
  ├─ Database query: SELECT * FROM stripe_meter_events WHERE tenant_id = ?
  └─ Result: Only this tenant's events returned

Stripe Webhook (includes customer ID)
  ├─ Stripe event: customer.subscription.updated
  ├─ Payload: { customer: "cus_XXXXX", subscription: "sub_XXXXX" }
  ├─ Lookup: SELECT tenant_id FROM stripe_customers WHERE stripe_customer_id = "cus_XXXXX"
  ├─ Update: UPDATE stripe_subscriptions WHERE tenant_id = ? AND stripe_subscription_id = ?
  └─ Result: Only correct tenant's subscription updated
```

**Multi-Tenant Scenarios:**
1. **Single developer** with one SaaS (tenant_id = app name)
2. **SaaS with multiple customers** (each customer = tenant_id)
3. **White-label platform** (reseller uses your metering, each end-customer = tenant_id)

---

## Deployment Topology

### Option 1: Single Container (MVP)
```
┌─────────────────────────────┐
│    Docker Container         │
│  ┌─────────────────────────┐│
│  │ FastAPI Service         ││
│  │ (All endpoints + logic) ││
│  └─────────────────────────┘│
└────────┬─────────┬──────────┘
         │         │
    PostgreSQL  Stripe API
```
**Best for:** Early stage, solo dev
**Scaling:** Run multiple containers behind load balancer

### Option 2: Microservices (Mature)
```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  API Server │     │ Meter Event  │     │ Webhook Handler│
│ (FastAPI)   │────▶│ Worker       │     │ (Async)        │
└─────────────┘     │ (Background) │     │                │
                    └──────────────┘     └────────────────┘
        │                    │                    │
        └────────┬───────────┴────────┬───────────┘
                 │                    │
            PostgreSQL            Redis (optional)
                 │                    │
                 └────┬───────────────┘
                      │
                  Stripe API
```
**Best for:** Scaling to high volume, multiple teams
**Scaling:** Each component scales independently

---

## Error Handling & Resilience

**Transient Errors** (Stripe API timeout, network issue)
```
MeterEventService.report_usage()
  ├─ Call Stripe: POST /v1/billing/meter_events
  ├─ Error: Connection timeout
  ├─ Action: Retry with exponential backoff
  │  ├─ Attempt 1: Immediate
  │  ├─ Attempt 2: Wait 1s
  │  ├─ Attempt 3: Wait 2s
  │  ├─ Attempt 4: Wait 4s
  │  ├─ Attempt 5: Wait 8s (final)
  └─ After max retries: Mark as failed, alert ops, do NOT lose event
```

**Permanent Errors** (Invalid API key, bad request)
```
MeterEventService.report_usage()
  ├─ Call Stripe: POST /v1/billing/meter_events
  ├─ Error: Invalid meter event name "ai_labels_typo"
  ├─ Stripe returns: 400 Bad Request
  ├─ Action: Do NOT retry (won't fix on second attempt)
  ├─ Log: Store error in StripeMeterEvent.error_message
  └─ Alert: Ops team needs to fix configuration
```

**Database Failures**
```
If PostgreSQL is down:
  ├─ Can't read customer info or subscription state
  ├─ Return: 503 Service Unavailable
  ├─ Include: Retry-After header
  ├─ Store events in memory queue (lose on restart)
  └─ Recommend: Use managed PostgreSQL (RDS, Cloud SQL) with HA
```

**Stripe Outage**
```
If Stripe API is down:
  ├─ Your service continues to work (reads from local DB)
  ├─ Meter events queue locally (in DB)
  ├─ Retry sending when Stripe recovers
  ├─ No double-charging (idempotency keys prevent it)
  └─ Customer sees: "Usage syncing..." status while Stripe is down
```

---

## Monitoring & Observability

**Critical Metrics:**
- Stripe API latency (p50, p95, p99)
- Meter event success rate (% events synced to Stripe)
- Idempotency key collision rate (should be near 0)
- Webhook processing latency
- Database query latency
- Error rates (by error type)

**Logging:**
- All API requests (method, path, status, latency, tenant_id)
- Meter event submissions (success/failure, retry count)
- Webhook receipts (event ID, signature verified, processing result)
- Database queries (slow queries > 100ms)
- Stripe API calls (latency, response code)

**Alerts:**
- Stripe API error rate > 1%
- Meter event failure rate > 0.1%
- Webhook processing failures
- Database connection errors
- API latency p95 > 1000ms

---

## Security Considerations

**Data at Rest:**
- PostgreSQL encryption (via cloud provider)
- Stripe API keys stored as environment variables (NOT in code)
- No credit card data stored (Stripe handles all payment info)

**Data in Transit:**
- HTTPS only (TLS 1.3+)
- JWT tokens signed (prevent tampering)
- Stripe webhook signatures verified (HMAC-SHA256)

**Authentication:**
- No passwords (JWT-based)
- API keys stored securely (environment variables)
- Token rotation: 1 hour (short-lived)
- Refresh tokens: 7 days (longer-lived, secure storage)

**Authorization:**
- Tenant isolation enforced at query level
- Cross-tenant access attempt returns 403 Forbidden
- Rate limiting prevents brute force
- No privilege escalation

**Audit Trail:**
- All API calls logged (user_id, tenant_id, action, timestamp)
- Stripe webhook events logged (event_id, timestamp, processing result)
- Meter event submissions logged (success/failure, retry count)
- 90-day retention (GDPR compliance)

---

## Summary

| Aspect | Details |
|--------|---------|
| **Architecture** | Stateless FastAPI service + PostgreSQL + Stripe API |
| **Scalability** | Horizontal (add more containers) |
| **Deployment** | Docker, Railway, or self-hosted |
| **Database** | PostgreSQL (single instance for MVP, HA for production) |
| **External API** | Stripe (metered billing) |
| **Authentication** | JWT Bearer tokens |
| **Multi-Tenancy** | Complete isolation per tenant_id |
| **Idempotency** | Key-based, 24-hour TTL, prevents Stripe duplicates |
| **Retry Logic** | Exponential backoff, max 5 attempts |
| **Webhooks** | Stripe → Your service, HMAC-SHA256 verification |
| **Error Handling** | Transient (retry), permanent (alert), network (queue) |
| **Monitoring** | Logs + metrics (Sentry, Datadog optional) |

---

## Next Steps

See: **E2E_FLOW.md** - Detailed user journeys and integration examples
