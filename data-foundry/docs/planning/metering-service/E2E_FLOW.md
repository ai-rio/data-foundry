# Metering Service - End-to-End Flow

## Overview

This document maps complete user journeys through the Metering Service. Each flow shows what a SaaS customer does, what the system processes, and how Stripe gets integrated.

---

## Primary Flow: Complete Billing Lifecycle

### Scenario
A SaaS founder (Alice) builds an AI-powered data validation tool. She wants to meter usage and charge customers based on how many records they validate.

### Part 1: Initial Setup (One-Time)

```
┌─ ALICE'S SETUP ───────────────────────────────────────────────┐
│                                                               │
│  Alice (SaaS Founder)                                         │
│    "I need usage metering for my SaaS"                       │
│    ↓                                                          │
│  1. Signs up for Metering Service                            │
│  2. Gets API key: mk_live_abc123def456xyz789                 │
│  3. Sets up Stripe account with meters:                      │
│     ├─ Meter 1: "validations" (name: validations)            │
│     ├─ Meter 2: "exports" (name: batch_exports)              │
│     └─ Price IDs for tiers: growth_validations, etc.         │
│  4. Stores config in .env:                                   │
│     ├─ METERING_API_KEY=mk_live_abc123def456xyz789           │
│     ├─ STRIPE_SECRET_KEY=sk_live_...                         │
│     ├─ STRIPE_WEBHOOK_SECRET=whsec_...                       │
│     ├─ METER_VALIDATIONS_ID=mtr_123                          │
│     └─ METER_EXPORTS_ID=mtr_456                              │
│                                                               │
└─ END SETUP ───────────────────────────────────────────────────┘
```

### Part 2: Customer Onboarding (Per Customer)

```
┌─ ALICE ONBOARDS CUSTOMER (Bob) ────────────────────────────────┐
│                                                               │
│  Step 1: Create Customer in Stripe                           │
│  ────────────────────────────────────────────────────────    │
│  POST /api/v1/billing/customers                              │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│ ├─ Body: {                                                   │
│  │   "email": "bob@bobscorp.com",                            │
│  │   "name": "Bob's Corp",                                   │
│  │   "metadata": { "company_id": "comp_bob_123" }            │
│  │ }                                                         │
│  └─ Query: user_id=alice_123&tenant_id=alice_saas_app       │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth check: ✅ Valid JWT                              │
│    ├─ Stripe API call:                                       │
│    │  POST https://api.stripe.com/v1/customers              │
│    │  {                                                      │
│    │    email: "bob@bobscorp.com",                           │
│    │    name: "Bob's Corp",                                  │
│    │    metadata: { company_id: "comp_bob_123" }             │
│    │  }                                                      │
│    │  ↓ Response:                                            │
│    │  {                                                      │
│    │    id: "cus_BOB123XYZ",                                 │
│    │    email: "bob@bobscorp.com",                           │
│    │    ...                                                  │
│    │  }                                                      │
│    │                                                         │
│    └─ Store in DB:                                           │
│       INSERT INTO stripe_customers (                         │
│         tenant_id, stripe_customer_id, email, name           │
│       ) VALUES (                                             │
│         'alice_saas_app', 'cus_BOB123XYZ',                   │
│         'bob@bobscorp.com', 'Bobs Corp'                      │
│       )                                                      │
│                                                               │
│  Response: HTTP 201 Created                                  │
│  {                                                            │
│    "stripe_customer_id": "cus_BOB123XYZ",                    │
│    "email": "bob@bobscorp.com",                              │
│    "name": "Bob's Corp"                                      │
│  }                                                            │
│                                                               │
│  Alice: "Got it! Bob is now a Stripe customer."              │
│                                                               │
│  Step 2: Create Subscription                                │
│  ────────────────────────────────────────────────────────   │
│  POST /api/v1/billing/subscriptions                          │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  ├─ Body: {                                                  │
│  │   "stripe_customer_id": "cus_BOB123XYZ",                  │
│  │   "tier": "growth",  ← Growth tier pricing               │
│  │   "price_id": "price_growth_validations_monthly"          │
│  │ }                                                         │
│  └─ Query: user_id=alice_123&tenant_id=alice_saas_app       │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth + lookup customer: ✅                             │
│    ├─ Stripe API call:                                       │
│    │  POST https://api.stripe.com/v1/subscriptions           │
│    │  {                                                      │
│    │    customer: "cus_BOB123XYZ",                           │
│    │    items: [{                                            │
│    │      price: "price_growth_validations_monthly"          │
│    │    }],                                                  │
│    │    billing_cycle_anchor: <billing start date>           │
│    │  }                                                      │
│    │  ↓ Response:                                            │
│    │  {                                                      │
│    │    id: "sub_BOB456ABC",                                 │
│    │    customer: "cus_BOB123XYZ",                           │
│    │    status: "active",                                    │
│    │    current_period_start: 1704067200,                    │
│    │    current_period_end: 1706745600                       │
│    │  }                                                      │
│    │                                                         │
│    └─ Store in DB:                                           │
│       INSERT INTO stripe_subscriptions (                     │
│         tenant_id, stripe_subscription_id, status, tier      │
│       ) VALUES (                                             │
│         'alice_saas_app', 'sub_BOB456ABC',                   │
│         'active', 'growth'                                   │
│       )                                                      │
│                                                               │
│  Response: HTTP 201 Created                                  │
│  {                                                            │
│    "stripe_subscription_id": "sub_BOB456ABC",                │
│    "status": "active",                                       │
│    "tier": "growth",                                         │
│    "current_period_start": "2025-01-01T00:00:00Z",          │
│    "current_period_end": "2025-02-01T00:00:00Z"             │
│  }                                                            │
│                                                               │
│  Alice: "Bob is now subscribed! Ready to track usage."        │
│                                                               │
└─ END ONBOARDING ──────────────────────────────────────────────┘
```

### Part 3: Usage Tracking (Ongoing)

```
┌─ BOB USES ALICE'S APP ────────────────────────────────────────┐
│                                                               │
│  Bob validates 1,500 records in Alice's app                  │
│                                                               │
│  Alice's backend:                                            │
│    "We need to track this usage for billing"                │
│    ↓                                                          │
│  Report Usage Event                                          │
│  ────────────────────────────────────────────────────────   │
│  POST /api/v1/billing/usage/report                           │
│  ├─ Headers: Authorization: Bearer <metering_api_key>        │
│  ├─ Body: {                                                  │
│  │   "stripe_customer_id": "cus_BOB123XYZ",                  │
│  │   "meter_event_name": "validations",                      │
│  │   "quantity": 1500,                                       │
│  │   "timestamp": 1704067200,                                │
│  │   "idempotency_key": "bob_batch_001_2025_01_31"           │
│  │ }                                                         │
│  └─ (optional) webhook_url: https://alice.com/webhooks      │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth check: ✅ Valid API key                           │
│    ├─ Lookup customer:                                       │
│    │  SELECT stripe_customer_id FROM stripe_customers        │
│    │  WHERE stripe_customer_id = 'cus_BOB123XYZ'             │
│    │  Result: ✅ Found                                       │
│    │                                                         │
│    ├─ Get subscription tier:                                 │
│    │  SELECT tier FROM stripe_subscriptions                  │
│    │  WHERE stripe_customer_id = 'cus_BOB123XYZ'             │
│    │  Result: "growth" tier                                  │
│    │                                                         │
│    ├─ Check idempotency:                                     │
│    │  SELECT * FROM idempotency_registry                     │
│    │  WHERE idempotency_key = "bob_batch_001_..."            │
│    │  Result: ❌ Not seen before (first time)                │
│    │  Action: Register key with 24-hour TTL                 │
│    │                                                         │
│    ├─ Store meter event locally:                             │
│    │  INSERT INTO stripe_meter_events (                      │
│    │    tenant_id, event_name, quantity,                     │
│    │    idempotency_key, status, created_at                  │
│    │  ) VALUES (                                             │
│    │    'alice_saas_app', 'validations', 1500,               │
│    │    'bob_batch_001_...', 'pending', NOW()                │
│    │  )                                                      │
│    │                                                         │
│    └─ Call Stripe Billing API:                               │
│       POST https://api.stripe.com/v1/billing/meter_events    │
│       Headers:                                               │
│         Authorization: Bearer sk_live_...                    │
│         Idempotency-Key: bob_batch_001_...                   │
│       Body: {                                                │
│         event_name: "validations",                           │
│         value: 1500,                                         │
│         timestamp: 1704067200                                │
│       }                                                      │
│       ↓ Stripe Response:                                     │
│       {                                                      │
│         id: "evt_stripe_123",                                │
│         event_name: "validations",                           │
│         value: 1500,                                         │
│         timestamp: 1704067200,                               │
│         livemode: true                                       │
│       }                                                      │
│                                                               │
│    ├─ Update meter event status:                             │
│    │  UPDATE stripe_meter_events                             │
│    │  SET status = 'succeeded', stripe_response = {...}      │
│    │  WHERE idempotency_key = 'bob_batch_001_...'            │
│    │                                                         │
│    └─ Update local usage tracking:                           │
│       (for GetUsage query)                                   │
│       UPDATE token_usage SET ... (for cost calculation)      │
│       UPDATE tenant_usage SET ... (for billing summary)      │
│                                                               │
│  Response: HTTP 200 OK                                       │
│  {                                                            │
│    "meter_event": {                                          │
│      "id": "evt_stripe_123",                                 │
│      "event_name": "validations",                            │
│      "value": 1500,                                          │
│      "status": "succeeded"                                   │
│    },                                                        │
│    "tier": "growth",                                         │
│    "estimated_cost": 1.50  ← $0.001 × 1500 = $1.50          │
│  }                                                            │
│                                                               │
│  Alice: "Great! Usage tracked. Bob is being metered."         │
│                                                               │
│  [Later that day, Bob validates 2,000 more records]          │
│    ↓                                                          │
│  POST /api/v1/billing/usage/report (same flow)               │
│  ├─ quantity: 2000                                           │
│  ├─ idempotency_key: "bob_batch_002_..."                     │
│  └─ Stripe charges Bob for 2,000 more validations            │
│                                                               │
│  [End of billing period: 1,500 + 2,000 = 3,500 validations] │
│                                                               │
└─ END USAGE TRACKING ──────────────────────────────────────────┘
```

### Part 4: Check Usage & Costs

```
┌─ ALICE CHECKS BOB'S USAGE ────────────────────────────────────┐
│                                                               │
│  Alice wants to see: "How much is Bob's usage costing?"      │
│    ↓                                                          │
│  Check Usage Summary                                         │
│  ────────────────────────────────────────────────────────   │
│  GET /api/v1/billing/usage/{tenant_id}                       │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  ├─ Query: period_start=2025-01-01&period_end=2025-01-31    │
│  └─ Path: /api/v1/billing/usage/alice_saas_app              │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth check: ✅ Valid JWT                              │
│    ├─ Lookup subscription:                                   │
│    │  SELECT * FROM stripe_subscriptions                     │
│    │  WHERE tenant_id = 'alice_saas_app'                     │
│    │  Result: subscription with tier='growth'                │
│    │                                                         │
│    ├─ Fetch meter events (this period):                      │
│    │  SELECT * FROM stripe_meter_events                      │
│    │  WHERE tenant_id = 'alice_saas_app'                     │
│    │    AND created_at BETWEEN ? AND ?                       │
│    │    AND status = 'succeeded'                             │
│    │                                                         │
│    │  Result:                                                │
│    │  ├─ validations: 3,500 events                           │
│    │  ├─ batch_exports: 50 events                            │
│    │  └─ (total: 3,550 events)                               │
│    │                                                         │
│    ├─ Calculate costs (Growth tier pricing):                 │
│    │  ├─ validations: 3,500 × $0.001 = $3.50                │
│    │  ├─ batch_exports: 50 × $0.01 = $0.50                  │
│    │  └─ Total: $4.00                                        │
│    │                                                         │
│    ├─ Check sync status:                                     │
│    │  SELECT COUNT(*) FROM stripe_meter_events               │
│    │  WHERE status IN ('pending', 'failed')                  │
│    │  Result: 0 events pending (all synced to Stripe ✅)     │
│    │                                                         │
│    └─ Format response:                                       │
│       [See response below]                                   │
│                                                               │
│  Response: HTTP 200 OK                                       │
│  {                                                            │
│    "period": {                                               │
│      "start": "2025-01-01T00:00:00Z",                        │
│      "end": "2025-01-31T23:59:59Z"                           │
│    },                                                        │
│    "subscription": {                                         │
│      "stripe_subscription_id": "sub_BOB456ABC",              │
│      "tier": "growth",                                       │
│      "status": "active"                                      │
│    },                                                        │
│    "usage_breakdown": [                                      │
│      {                                                       │
│        "event_name": "validations",                          │
│        "total_quantity": 3500,                               │
│        "event_count": 23,                                    │
│        "unit_price": 0.001,                                  │
│        "estimated_cost": 3.50                                │
│      },                                                      │
│      {                                                       │
│        "event_name": "batch_exports",                        │
│        "total_quantity": 50,                                 │
│        "event_count": 1,                                     │
│        "unit_price": 0.01,                                   │
│        "estimated_cost": 0.50                                │
│      }                                                       │
│    ],                                                        │
│    "total_estimated_cost": 4.00,                             │
│    "sync_status": {                                          │
│      "last_sync": "2025-01-31T15:30:45Z",                   │
│      "pending_events": 0,                                    │
│      "failed_events": 0,                                     │
│      "total_synced_events": 24                               │
│    }                                                         │
│  }                                                            │
│                                                               │
│  Alice: "Perfect! Bob's usage is $4.00 this month."          │
│                                                               │
└─ END CHECK USAGE ────────────────────────────────────────────┘
```

### Part 5: Stripe Charges & Invoice

```
┌─ STRIPE PROCESSES BILLING ────────────────────────────────────┐
│                                                               │
│  [End of billing period: Feb 1, 2025]                        │
│                                                               │
│  Stripe (Automatic):                                         │
│    1. Aggregates all meter events (3,500 validations, etc.)  │
│    2. Calculates total: 3,500 × $0.001 = $3.50              │
│    3. Creates invoice for Bob                                │
│    4. Sends webhook to Alice's service                       │
│       POST https://alice.com/webhook/stripe                  │
│       {                                                       │
│         type: "invoice.payment_succeeded",                   │
│         data: {                                              │
│           object: {                                          │
│             id: "in_BOB789DEF",                              │
│             customer: "cus_BOB123XYZ",                       │
│             status: "paid",                                  │
│             amount_paid: 350,  ← $3.50 in cents              │
│             period_start: 1704067200,                        │
│             period_end: 1706745600                           │
│           }                                                  │
│         }                                                    │
│       }                                                      │
│    5. Charges Bob's credit card: $3.50                       │
│                                                               │
│  Alice's Service (Webhook Handler):                          │
│    ├─ Receive webhook from Stripe                            │
│    ├─ Verify signature: HMAC-SHA256                          │
│    │  └─ ✅ Signature valid                                  │
│    ├─ Extract event: invoice.payment_succeeded               │
│    ├─ Extract invoice ID: in_BOB789DEF                       │
│    ├─ Update DB:                                             │
│    │  UPDATE tenant_usage                                    │
│    │  SET billing_status = 'completed',                      │
│    │      invoice_id = 'in_BOB789DEF'                        │
│    │  WHERE tenant_id = 'alice_saas_app'                     │
│    │    AND period = '2025-01'                               │
│    │                                                         │
│    └─ Send email to Bob:                                     │
│       "Your invoice for January 2025 is ready"               │
│       Amount: $3.50                                          │
│       Details: 3,500 validations × $0.001                    │
│                                                               │
│  Result: Bob is billed, Alice gets revenue!                  │
│                                                               │
└─ END BILLING ────────────────────────────────────────────────┘
```

---

## Secondary Flow: Subscription Tier Change

### Scenario
Bob's usage grows. He wants to upgrade from Growth to Professional tier for better pricing.

```
┌─ BOB UPGRADES TIER ───────────────────────────────────────────┐
│                                                               │
│  Bob: "My usage is growing. I want cheaper per-event rates."  │
│    ↓                                                          │
│  Alice (via UI): "Sure! Let me upgrade you."                 │
│    ↓                                                          │
│  Update Subscription                                         │
│  ────────────────────────────────────────────────────────   │
│  PUT /api/v1/billing/subscriptions/alice_saas_app            │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  ├─ Body: {                                                  │
│  │   "tier": "professional",  ← Changed from "growth"       │
│  │   "price_id": "price_pro_validations_monthly"             │
│  │ }                                                         │
│  └─ Query: user_id=alice_123&tenant_id=alice_saas_app       │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth check: ✅                                         │
│    ├─ Fetch current subscription:                            │
│    │  SELECT * FROM stripe_subscriptions                     │
│    │  WHERE tenant_id = 'alice_saas_app'                     │
│    │  Result: tier='growth', sub_id='sub_BOB456ABC'          │
│    │                                                         │
│    ├─ Stripe API call:                                       │
│    │  POST /v1/subscriptions/sub_BOB456ABC/items             │
│    │  {                                                      │
│    │    proration_behavior: "create_prorations",             │
│    │    items: [{                                            │
│    │      id: <current_item_id>,                             │
│    │      price: "price_pro_validations_monthly"             │
│    │    }]                                                   │
│    │  }                                                      │
│    │  ↓ Result:                                              │
│    │  - Stripe calculates prorated credit for unused         │
│    │    portion of Growth tier                               │
│    │  - Pro tier pricing starts immediately                  │
│    │  - Next invoice will reflect pro-rata adjustment        │
│    │                                                         │
│    └─ Update DB:                                             │
│       UPDATE stripe_subscriptions                            │
│       SET tier = 'professional'                              │
│       WHERE tenant_id = 'alice_saas_app'                     │
│                                                               │
│  Response: HTTP 200 OK                                       │
│  {                                                            │
│    "stripe_subscription_id": "sub_BOB456ABC",                │
│    "tier": "professional",  ← Updated                        │
│    "status": "active"                                        │
│  }                                                            │
│                                                               │
│  Alice: "Done! Bob is now on Professional tier."              │
│                                                               │
│  [Next charge will apply pro-rated pricing]                  │
│  Old: 3,500 validations × $0.001 (growth) = $3.50           │
│  New: X validations × $0.0005 (pro) = $X                     │
│  → Pro tier pricing is cheaper! ($0.0005 vs $0.001)         │
│                                                               │
└─ END TIER CHANGE ────────────────────────────────────────────┘
```

---

## Tertiary Flow: Cancellation

### Scenario
Bob decides to stop using the service. Alice cancels his subscription.

```
┌─ BOB CANCELS SUBSCRIPTION ────────────────────────────────────┐
│                                                               │
│  Bob: "I'm moving to a different tool. Cancel my subscription."│
│    ↓                                                          │
│  Cancel Subscription                                         │
│  ────────────────────────────────────────────────────────   │
│  DELETE /api/v1/billing/subscriptions/alice_saas_app         │
│  ├─ Headers: Authorization: Bearer <jwt_token>               │
│  ├─ Query: immediate=false  ← Cancel at period end           │
│  └─ (or: immediate=true ← Cancel now)                        │
│    ↓                                                          │
│  Processing:                                                 │
│    ├─ Auth check: ✅                                         │
│    ├─ Fetch subscription:                                    │
│    │  SELECT * FROM stripe_subscriptions                     │
│    │  WHERE tenant_id = 'alice_saas_app'                     │
│    │  Result: sub_id='sub_BOB456ABC'                         │
│    │                                                         │
│    ├─ Stripe API call (immediate=false):                     │
│    │  PATCH /v1/subscriptions/sub_BOB456ABC                  │
│    │  {                                                      │
│    │    cancel_at_period_end: true  ← Let period finish      │
│    │  }                                                      │
│    │  ↓ Result:                                              │
│    │  - Subscription remains active until period ends        │
│    │  - Bob can still use service through Feb 1              │
│    │  - No charges after Feb 1                               │
│    │                                                         │
│    └─ Update DB:                                             │
│       UPDATE stripe_subscriptions                            │
│       SET cancel_at_period_end = true                        │
│       WHERE tenant_id = 'alice_saas_app'                     │
│                                                               │
│  Response: HTTP 200 OK                                       │
│  {                                                            │
│    "stripe_subscription_id": "sub_BOB456ABC",                │
│    "status": "active",  ← Still active until period end     │
│    "cancel_at_period_end": true,  ← Will cancel soon         │
│    "current_period_end": "2025-02-01T00:00:00Z"             │
│  }                                                            │
│                                                               │
│  Alice: "Bob's subscription will end on Feb 1."              │
│                                                               │
│  [Feb 1 arrives]                                             │
│  Stripe webhook: customer.subscription.deleted               │
│    ├─ POST https://alice.com/webhook/stripe                 │
│    ├─ Event: subscription.deleted                            │
│    └─ Action: Update DB, disable Bob's access                │
│                                                               │
│  Alice: "Bob's service access is now revoked."                │
│                                                               │
└─ END CANCELLATION ────────────────────────────────────────────┘
```

---

## Error Scenarios

### Scenario: Idempotency Key Prevents Double-Charging

```
Situation: Alice reports same usage event twice (network retry)

First Request:
  POST /api/v1/billing/usage/report
  {
    stripe_customer_id: "cus_BOB123XYZ",
    meter_event_name: "validations",
    quantity: 1500,
    idempotency_key: "bob_batch_001_2025_01_31"
  }
  ↓
  Processing:
    ├─ Check idempotency registry: Not seen before ✅
    ├─ Register key: INSERT INTO idempotency_registry
    ├─ Call Stripe: POST /v1/billing/meter_events
    │  Headers: Idempotency-Key: bob_batch_001_...
    │  ↓ Stripe response: { id: "evt_123" }
    └─ Store result: evt_123
  ↓
  Response: HTTP 200 OK
  {
    "meter_event": { id: "evt_123", ... },
    "estimated_cost": 1.50
  }

Network timeout: Alice's client didn't receive response

Retry (Same idempotency key):
  POST /api/v1/billing/usage/report
  {
    stripe_customer_id: "cus_BOB123XYZ",
    meter_event_name: "validations",
    quantity: 1500,
    idempotency_key: "bob_batch_001_2025_01_31"  ← Same!
  }
  ↓
  Processing:
    ├─ Check idempotency registry: FOUND! ✅
    ├─ Key expires in: 23 hours 59 minutes
    ├─ Return cached response: evt_123
    └─ NO second call to Stripe (prevented!)
  ↓
  Response: HTTP 200 OK
  {
    "meter_event": { id: "evt_123", ... },  ← Same as before!
    "estimated_cost": 1.50
  }

Result:
  - Stripe received ONLY ONE meter event
  - Bob charged ONLY $1.50 (not $3.00)
  - ✅ Idempotency key prevented duplicate charge!
```

### Scenario: Transient Stripe Failure (Network Error)

```
Alice's system reports usage
  ↓
POST /api/v1/billing/usage/report
  ├─ Body: 1,500 validations
  ├─ idempotency_key: "bob_batch_001_..."
  └─ Processing:
     ├─ Register idempotency key ✓
     ├─ Call Stripe API
     └─ Error: Connection timeout ❌

Retry Logic (Automatic):
  ├─ Attempt 1: Immediate call → Timeout
  ├─ Attempt 2: Wait 1s, retry → Timeout
  ├─ Attempt 3: Wait 2s, retry → Timeout
  ├─ Attempt 4: Wait 4s, retry → ✓ SUCCESS!
  │  └─ Stripe received request with same idempotency_key
  │  └─ Stripe: "I've seen this key before? No, first time."
  │  └─ Creates meter event: evt_123
  │
  └─ Store result in DB

Response to Alice: HTTP 200 OK
  {
    "meter_event": { id: "evt_123", ... },
    "retry_attempts": 4,
    "status": "succeeded_after_retries"
  }

Result:
  - Usage eventually synced to Stripe ✓
  - Bob charged correctly (only once) ✓
  - Resilient to transient failures ✓
```

### Scenario: Permanent Stripe Error (Invalid Config)

```
Alice misconfigures meter ID

POST /api/v1/billing/usage/report
  {
    meter_event_name: "validations_typo",  ← Doesn't exist!
    quantity: 1500
  }
  ↓
  Processing:
    ├─ Call Stripe API
    └─ Error: 400 Bad Request
       └─ "meter_event_name not found"

Retry Logic:
  ├─ Attempt 1: 400 error → Don't retry (permanent error)
  ├─ Not transient (won't fix on retry)
  └─ Stop retrying

Store error in DB:
  UPDATE stripe_meter_events
  SET status = 'failed',
      error_message = 'meter_event_name not found'

Response to Alice: HTTP 400 Bad Request
  {
    "error": "meter_event_not_found",
    "message": "Meter event 'validations_typo' not configured in Stripe",
    "action": "Check STRIPE_METER_ID configuration"
  }

Alert: Ops team gets notified (bad configuration)

Result:
  - Usage NOT charged (doesn't exist)
  - Alert sent to ops
  - Alice needs to fix configuration
```

---

## Data Transformations

### Usage Event Transformation
```
Raw Event (from Alice's app):
  {
    validation_count: 1500,
    batch_id: "batch_001",
    timestamp: 1704067200
  }

After Metering Service Processing:
  {
    stripe_customer_id: "cus_BOB123XYZ",
    event_name: "validations",
    quantity: 1500,
    idempotency_key: "bob_batch_001_2025_01_31",
    tier: "growth",
    estimated_cost: 1.50
  }

After Stripe Processing:
  {
    stripe_event_id: "evt_123",
    meter_name: "validations",
    value: 1500,
    status: "metered",
    period: { start: 1704067200, end: 1706745600 }
  }

At Period End (Stripe Billing):
  {
    invoice_id: "in_BOB789DEF",
    amount: 350,  ← $3.50 in cents
    line_items: [{
      description: "3,500 validations @ $0.001",
      amount: 350
    }],
    status: "paid"
  }
```

---

## Summary: Complete Workflow

```
1. Setup (One-time)
   └─ Create Stripe account with meters & prices

2. Customer Onboarding (Per customer)
   ├─ Create customer in Stripe
   └─ Create subscription with pricing tier

3. Usage Tracking (Ongoing)
   ├─ Alice reports meter events
   ├─ Metering service validates + stores locally
   ├─ Idempotency prevents duplicates
   ├─ Sends to Stripe (with retries)
   └─ Stores results in DB

4. Billing (Monthly)
   ├─ Stripe aggregates meter events
   ├─ Calculates invoice amount
   ├─ Sends webhook to Alice
   ├─ Charges customer
   └─ Alice receives payment

5. Tier Changes (Optional)
   ├─ Update subscription in Stripe
   ├─ Pro-rata pricing applies
   └─ Updated rates for future charges

6. Cancellation (Optional)
   ├─ Cancel subscription (at period end)
   ├─ Service disabled after period
   └─ No more charges
```

---

## Next Steps

See: **API_SPECIFICATION.md** - Detailed API contracts for all endpoints
