# Metering Service - API Specification

## Table of Contents
1. [Overview](#overview)
2. [Authentication & Authorization](#authentication--authorization)
3. [Rate Limiting](#rate-limiting)
4. [Endpoints](#endpoints)
5. [Data Models](#data-models)
6. [Meter Event Names](#meter-event-names)
7. [Error Codes & Responses](#error-codes--responses)
8. [Idempotency](#idempotency)
9. [Stripe Integration Details](#stripe-integration-details)
10. [Client Implementation Examples](#client-implementation-examples)
11. [Common Patterns](#common-patterns)
12. [Webhook Handling](#webhook-handling)
13. [Testing/Sandbox](#testingsandbox)
14. [Rate Limiting & Quotas](#rate-limiting--quotas)

---

## Overview

### Base URL
```
Production:  https://api.metering-service.com
Sandbox:     https://sandbox.metering-service.com
```

### API Version
```
Current version: v1
Base path: /api/v1/billing
```

### Response Format
All responses are in JSON format with the following structure:

**Success Response:**
```json
{
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

**Error Response:**
```json
{
  "error": {
    "code": "error_code",
    "message": "Human-readable error message",
    "details": { ... }
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

### Common Headers

**Request Headers:**
```http
Authorization: Bearer <jwt_token>        # For customer management endpoints
X-API-Key: <api_key>                     # For meter reporting endpoints
Content-Type: application/json
Idempotency-Key: <unique_key>            # For POST requests (recommended)
X-Request-ID: <client_request_id>        # Optional, for tracing
```

**Response Headers:**
```http
Content-Type: application/json
X-Request-ID: req_abc123                 # Server-generated or echo client ID
X-RateLimit-Limit: 100                   # Max requests per window
X-RateLimit-Remaining: 95                # Remaining requests
X-RateLimit-Reset: 1704067200            # Unix timestamp when limit resets
```

---

## Authentication & Authorization

### Two Authentication Methods

#### Method 1: JWT Bearer Token (Customer Management)

Used for:
- Creating/updating/deleting customers
- Managing subscriptions
- Viewing usage summaries
- Administrative operations

**Token Format:**
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token Claims:**
```json
{
  "user_id": "user_abc123",
  "tenant_id": "tenant_xyz789",
  "tier": "growth",
  "exp": 1704067200,
  "iat": 1704063600,
  "iss": "metering-service",
  "aud": "metering-api"
}
```

**Token Lifecycle:**
- **Access Token TTL:** 1 hour
- **Refresh Token TTL:** 7 days
- **Algorithm:** RS256 (asymmetric)
- **Rotation:** On refresh

**Example JWT Token (decoded):**
```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT"
  },
  "payload": {
    "user_id": "user_alice_123",
    "tenant_id": "alice_saas_app",
    "tier": "growth",
    "exp": 1704067200,
    "iat": 1704063600,
    "iss": "metering-service",
    "aud": "metering-api"
  },
  "signature": "..."
}
```

#### Method 2: API Key (Meter Reporting)

Used for:
- Reporting meter events (POST /usage/report)
- High-frequency programmatic access
- Server-to-server communication

**API Key Format:**
```
X-API-Key: mk_live_abc123def456xyz789ghijkl
```

**API Key Types:**
```
Test Mode:  mk_test_...
Live Mode:  mk_live_...
```

**Example Usage:**
```bash
curl -X POST https://api.metering-service.com/api/v1/billing/usage/report \
  -H "X-API-Key: mk_live_abc123def456xyz789" \
  -H "Content-Type: application/json" \
  -d '{
    "stripe_customer_id": "cus_ABC123",
    "meter_event_name": "ai_labels",
    "quantity": 1500
  }'
```

### Tenant Isolation Mechanism

All endpoints enforce strict tenant isolation:

1. **JWT Token Validation:**
   ```
   Request: GET /api/v1/billing/customers/tenant_xyz789
   Token Claims: { tenant_id: "tenant_xyz789" }

   Validation:
   ├─ Extract tenant_id from token → "tenant_xyz789"
   ├─ Extract tenant_id from path → "tenant_xyz789"
   ├─ Compare: token.tenant_id == path.tenant_id
   └─ If match: ✅ Proceed
      If mismatch: ❌ Return 403 Forbidden
   ```

2. **Database Query Scoping:**
   ```sql
   -- All queries are scoped to tenant
   SELECT * FROM stripe_customers
   WHERE tenant_id = :tenant_id  -- From JWT token
   ```

3. **Cross-Tenant Access Prevention:**
   ```
   Attempt: User from tenant_A tries to access tenant_B data

   Request: GET /api/v1/billing/usage/tenant_B
   Token: { tenant_id: "tenant_A" }

   Result: 403 Forbidden
   {
     "error": {
       "code": "forbidden",
       "message": "Cross-tenant access denied"
     }
   }
   ```

---

## Rate Limiting

### Per-Tier Limits

| Tier | Requests/Minute | Requests/Hour | Burst Allowance |
|------|-----------------|---------------|-----------------|
| **Free/Starter** | 10 | 100 | 20 |
| **Growth** | 100 | 1,000 | 200 |
| **Professional** | 500 | 5,000 | 1,000 |
| **Enterprise** | Custom | Custom | Custom |

### Rate Limit Headers

Every response includes rate limit information:

```http
X-RateLimit-Limit: 100           # Max requests per window
X-RateLimit-Remaining: 95        # Remaining requests in window
X-RateLimit-Reset: 1704067200    # Unix timestamp when window resets
```

### Behavior When Exceeded

**Response:**
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1704067200

{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Max 100 requests per minute.",
    "details": {
      "limit": 100,
      "remaining": 0,
      "reset_at": "2025-01-31T12:30:00Z"
    }
  }
}
```

**Recommended Client Behavior:**
```python
import time

response = requests.post(url, headers=headers, json=data)

if response.status_code == 429:
    retry_after = int(response.headers.get('Retry-After', 60))
    print(f"Rate limited. Retrying after {retry_after} seconds...")
    time.sleep(retry_after)
    response = requests.post(url, headers=headers, json=data)
```

---

## Endpoints

### Customer Management

#### POST /api/v1/billing/customers

Create a new Stripe customer.

**Authentication:** JWT Bearer Token

**Request:**
```http
POST /api/v1/billing/customers
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "email": "customer@example.com",
  "name": "Customer Name",
  "metadata": {
    "company_id": "comp_123",
    "plan": "growth"
  }
}
```

**Request Schema:**
```typescript
{
  email: string;           // Required, valid email
  name: string;            // Required, 1-255 chars
  metadata?: {             // Optional key-value pairs
    [key: string]: string;
  };
}
```

**Response (201 Created):**
```json
{
  "data": {
    "stripe_customer_id": "cus_ABC123XYZ",
    "email": "customer@example.com",
    "name": "Customer Name",
    "metadata": {
      "company_id": "comp_123",
      "plan": "growth"
    },
    "created_at": "2025-01-31T12:00:00Z",
    "updated_at": "2025-01-31T12:00:00Z"
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

**Status Codes:**
- `201 Created` - Customer created successfully
- `400 Bad Request` - Invalid email, missing required fields
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `409 Conflict` - Customer already exists for this tenant
- `429 Too Many Requests` - Rate limit exceeded

**Example cURL:**
```bash
curl -X POST https://api.metering-service.com/api/v1/billing/customers \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "email": "bob@bobscorp.com",
    "name": "Bob'\''s Corp",
    "metadata": {
      "company_id": "comp_bob_123",
      "industry": "fintech"
    }
  }'
```

---

#### GET /api/v1/billing/customers/{tenant_id}

Retrieve customer details.

**Authentication:** JWT Bearer Token

**Request:**
```http
GET /api/v1/billing/customers/tenant_xyz789
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "data": {
    "stripe_customer_id": "cus_ABC123XYZ",
    "tenant_id": "tenant_xyz789",
    "email": "customer@example.com",
    "name": "Customer Name",
    "metadata": {
      "company_id": "comp_123"
    },
    "created_at": "2025-01-31T12:00:00Z",
    "updated_at": "2025-01-31T12:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Customer found
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Customer not found

---

#### PUT /api/v1/billing/customers/{tenant_id}

Update customer details.

**Authentication:** JWT Bearer Token

**Request:**
```http
PUT /api/v1/billing/customers/tenant_xyz789
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "email": "newemail@example.com",
  "name": "Updated Customer Name",
  "metadata": {
    "company_id": "comp_456"
  }
}
```

**Request Schema:**
```typescript
{
  email?: string;          // Optional, valid email
  name?: string;           // Optional, 1-255 chars
  metadata?: {             // Optional, replaces existing metadata
    [key: string]: string;
  };
}
```

**Response (200 OK):**
```json
{
  "data": {
    "stripe_customer_id": "cus_ABC123XYZ",
    "email": "newemail@example.com",
    "name": "Updated Customer Name",
    "metadata": {
      "company_id": "comp_456"
    },
    "updated_at": "2025-01-31T13:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Customer updated successfully
- `400 Bad Request` - Invalid email format
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Customer not found

---

#### DELETE /api/v1/billing/customers/{tenant_id}

Delete (soft-delete) a customer.

**Authentication:** JWT Bearer Token

**Request:**
```http
DELETE /api/v1/billing/customers/tenant_xyz789
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "data": {
    "status": "deleted",
    "stripe_customer_id": "cus_ABC123XYZ",
    "deleted_at": "2025-01-31T13:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Customer deleted successfully
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Customer not found

**Note:** This is a soft delete. The customer record is marked as deleted but not removed from the database. Active subscriptions are cancelled.

---

### Subscription Management

#### POST /api/v1/billing/subscriptions

Create a new subscription.

**Authentication:** JWT Bearer Token

**Request:**
```http
POST /api/v1/billing/subscriptions
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "stripe_customer_id": "cus_ABC123XYZ",
  "tier": "growth",
  "price_id": "price_growth_monthly"
}
```

**Request Schema:**
```typescript
{
  stripe_customer_id: string;  // Required, cus_*
  tier: SubscriptionTier;      // Required: starter|growth|professional|enterprise
  price_id?: string;           // Optional, Stripe price ID (auto-resolved if omitted)
}
```

**Subscription Tiers:**
- `starter` - Basic tier with standard pricing
- `growth` - Mid-tier with volume discounts
- `professional` - Advanced tier with better rates
- `enterprise` - Custom pricing and limits

**Response (201 Created):**
```json
{
  "data": {
    "stripe_subscription_id": "sub_DEF456GHI",
    "stripe_customer_id": "cus_ABC123XYZ",
    "status": "active",
    "tier": "growth",
    "current_period_start": "2025-01-31T12:00:00Z",
    "current_period_end": "2025-02-28T12:00:00Z",
    "cancel_at_period_end": false,
    "created_at": "2025-01-31T12:00:00Z"
  }
}
```

**Status Codes:**
- `201 Created` - Subscription created successfully
- `400 Bad Request` - Invalid tier, missing customer_id
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Customer not found
- `409 Conflict` - Active subscription already exists
- `429 Too Many Requests` - Rate limit exceeded

**Example:**
```bash
curl -X POST https://api.metering-service.com/api/v1/billing/subscriptions \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "stripe_customer_id": "cus_BOB123XYZ",
    "tier": "growth",
    "price_id": "price_growth_validations_monthly"
  }'
```

---

#### GET /api/v1/billing/subscriptions/{tenant_id}

Get subscription details.

**Authentication:** JWT Bearer Token

**Request:**
```http
GET /api/v1/billing/subscriptions/tenant_xyz789
Authorization: Bearer <jwt_token>
```

**Response (200 OK):**
```json
{
  "data": {
    "stripe_subscription_id": "sub_DEF456GHI",
    "stripe_customer_id": "cus_ABC123XYZ",
    "status": "active",
    "tier": "growth",
    "current_period_start": "2025-01-31T12:00:00Z",
    "current_period_end": "2025-02-28T12:00:00Z",
    "cancel_at_period_end": false,
    "created_at": "2025-01-31T12:00:00Z",
    "updated_at": "2025-01-31T12:00:00Z"
  }
}
```

**Subscription Status Values:**
- `active` - Currently active and billing
- `trialing` - In trial period, not yet billing
- `past_due` - Payment failed, retrying
- `canceled` - Subscription cancelled
- `incomplete` - Initial payment pending
- `incomplete_expired` - Initial payment failed

**Status Codes:**
- `200 OK` - Subscription found
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Subscription not found

---

#### PUT /api/v1/billing/subscriptions/{tenant_id}

Update subscription (tier change).

**Authentication:** JWT Bearer Token

**Request:**
```http
PUT /api/v1/billing/subscriptions/tenant_xyz789
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "tier": "professional",
  "price_id": "price_pro_validations_monthly"
}
```

**Request Schema:**
```typescript
{
  tier?: SubscriptionTier;  // Optional: starter|growth|professional|enterprise
  price_id?: string;        // Optional, Stripe price ID
}
```

**Response (200 OK):**
```json
{
  "data": {
    "stripe_subscription_id": "sub_DEF456GHI",
    "status": "active",
    "tier": "professional",
    "current_period_start": "2025-01-31T12:00:00Z",
    "current_period_end": "2025-02-28T12:00:00Z",
    "proration": {
      "prorated_amount": -15.50,
      "new_amount": 49.00,
      "effective_date": "2025-01-31T13:00:00Z"
    },
    "updated_at": "2025-01-31T13:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Subscription updated successfully
- `400 Bad Request` - Invalid tier
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Subscription not found

**Note:** Tier changes are prorated. The customer receives credit for unused time on the old tier and is charged for the new tier starting immediately.

---

#### DELETE /api/v1/billing/subscriptions/{tenant_id}

Cancel subscription.

**Authentication:** JWT Bearer Token

**Request:**
```http
DELETE /api/v1/billing/subscriptions/tenant_xyz789?immediate=false
Authorization: Bearer <jwt_token>
```

**Query Parameters:**
- `immediate` (boolean, default: `false`)
  - `false` - Cancel at period end (recommended, allows customer to finish billing cycle)
  - `true` - Cancel immediately (effective now, no refund)

**Response (200 OK) - Cancel at Period End:**
```json
{
  "data": {
    "status": "canceling_at_period_end",
    "stripe_subscription_id": "sub_DEF456GHI",
    "cancel_at_period_end": true,
    "cancels_at": "2025-02-28T12:00:00Z",
    "access_until": "2025-02-28T12:00:00Z"
  }
}
```

**Response (200 OK) - Immediate Cancellation:**
```json
{
  "data": {
    "status": "canceled",
    "stripe_subscription_id": "sub_DEF456GHI",
    "canceled_at": "2025-01-31T13:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Subscription cancelled successfully
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt
- `404 Not Found` - Subscription not found

**Example:**
```bash
# Cancel at period end (recommended)
curl -X DELETE "https://api.metering-service.com/api/v1/billing/subscriptions/tenant_xyz789?immediate=false" \
  -H "Authorization: Bearer <jwt_token>"

# Cancel immediately
curl -X DELETE "https://api.metering-service.com/api/v1/billing/subscriptions/tenant_xyz789?immediate=true" \
  -H "Authorization: Bearer <jwt_token>"
```

---

### Usage & Metering

#### POST /api/v1/billing/usage/report

Report a meter event to Stripe.

**Authentication:** API Key (X-API-Key header)

**Request:**
```http
POST /api/v1/billing/usage/report
X-API-Key: mk_live_abc123def456xyz789
Content-Type: application/json
Idempotency-Key: batch_001_2025_01_31

{
  "stripe_customer_id": "cus_ABC123XYZ",
  "meter_event_name": "ai_labels",
  "quantity": 1500,
  "timestamp": 1704067200,
  "idempotency_key": "batch_001_2025_01_31",
  "metadata": {
    "batch_id": "batch_001",
    "source": "aml_pipeline"
  }
}
```

**Request Schema:**
```typescript
{
  stripe_customer_id: string;    // Required, cus_*
  meter_event_name: string;      // Required, valid meter name (see Meter Event Names)
  quantity: number;              // Required, positive integer
  timestamp?: number;            // Optional, Unix timestamp (default: now)
  idempotency_key?: string;      // Optional but STRONGLY recommended
  metadata?: {                   // Optional key-value pairs
    [key: string]: string;
  };
}
```

**Response (200 OK):**
```json
{
  "data": {
    "meter_event": {
      "id": "evt_stripe_abc123",
      "event_name": "ai_labels",
      "value": 1500,
      "timestamp": 1704067200,
      "status": "succeeded"
    },
    "tier": "growth",
    "estimated_cost": 1.50,
    "sync_status": "synced",
    "idempotency": {
      "key": "batch_001_2025_01_31",
      "is_replay": false
    }
  }
}
```

**Response (200 OK) - Idempotent Replay:**
```json
{
  "data": {
    "meter_event": {
      "id": "evt_stripe_abc123",
      "event_name": "ai_labels",
      "value": 1500,
      "timestamp": 1704067200,
      "status": "succeeded"
    },
    "tier": "growth",
    "estimated_cost": 1.50,
    "sync_status": "synced",
    "idempotency": {
      "key": "batch_001_2025_01_31",
      "is_replay": true,
      "first_seen": "2025-01-31T12:00:00Z"
    }
  }
}
```

**Status Codes:**
- `200 OK` - Meter event reported successfully (includes idempotent replays)
- `400 Bad Request` - Invalid meter event name, negative quantity, malformed request
- `401 Unauthorized` - Invalid or missing API key
- `404 Not Found` - Customer not found
- `422 Unprocessable Entity` - Invalid meter event name (not configured in Stripe)
- `429 Too Many Requests` - Rate limit exceeded
- `502 Bad Gateway` - Stripe API error (transient, retry)

**Example cURL:**
```bash
curl -X POST https://api.metering-service.com/api/v1/billing/usage/report \
  -H "X-API-Key: mk_live_abc123def456xyz789" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: bob_batch_001_2025_01_31" \
  -d '{
    "stripe_customer_id": "cus_BOB123XYZ",
    "meter_event_name": "ai_labels",
    "quantity": 1500,
    "metadata": {
      "batch_id": "batch_001",
      "pipeline": "aml_labeling"
    }
  }'
```

**Idempotency Behavior:**

The `idempotency_key` ensures the same event is never charged twice:

1. **First Request:**
   - Key not seen before
   - Event sent to Stripe
   - Response stored in cache (24-hour TTL)
   - Customer charged

2. **Retry/Duplicate Request (same key):**
   - Key found in cache
   - Cached response returned immediately
   - NO second call to Stripe
   - Customer NOT charged again

**Best Practices:**
- Always include `idempotency_key` for production usage
- Use format: `{tenant_id}_{batch_id}_{date}`
- Keys expire after 24 hours
- Safe to retry with same key on network failures

---

#### GET /api/v1/billing/usage/{tenant_id}

Get usage summary for a billing period.

**Authentication:** JWT Bearer Token

**Request:**
```http
GET /api/v1/billing/usage/tenant_xyz789?period_start=2025-01-01&period_end=2025-01-31
Authorization: Bearer <jwt_token>
```

**Query Parameters:**
- `period_start` (ISO 8601 date, optional) - Start of period (default: current billing cycle start)
- `period_end` (ISO 8601 date, optional) - End of period (default: now)

**Response (200 OK):**
```json
{
  "data": {
    "period": {
      "start": "2025-01-01T00:00:00Z",
      "end": "2025-01-31T23:59:59Z"
    },
    "subscription": {
      "stripe_subscription_id": "sub_DEF456GHI",
      "tier": "growth",
      "status": "active"
    },
    "usage_breakdown": [
      {
        "event_name": "ai_labels",
        "total_quantity": 3500,
        "event_count": 23,
        "unit_price": 0.001,
        "estimated_cost": 3.50
      },
      {
        "event_name": "human_audits",
        "total_quantity": 50,
        "event_count": 5,
        "unit_price": 0.01,
        "estimated_cost": 0.50
      },
      {
        "event_name": "batch_exports",
        "total_quantity": 10,
        "event_count": 2,
        "unit_price": 0.05,
        "estimated_cost": 0.50
      }
    ],
    "total_estimated_cost": 4.50,
    "sync_status": {
      "last_sync": "2025-01-31T15:30:45Z",
      "pending_events": 0,
      "failed_events": 0,
      "total_synced_events": 30
    }
  }
}
```

**Status Codes:**
- `200 OK` - Usage summary retrieved successfully
- `400 Bad Request` - Invalid date format
- `401 Unauthorized` - Invalid or missing JWT token
- `403 Forbidden` - Cross-tenant access attempt

**Example:**
```bash
curl -X GET "https://api.metering-service.com/api/v1/billing/usage/tenant_xyz789?period_start=2025-01-01&period_end=2025-01-31" \
  -H "Authorization: Bearer <jwt_token>"
```

---

### Webhooks

#### POST /api/v1/billing/webhook

Receive Stripe webhook events.

**Authentication:** Stripe Signature (HMAC-SHA256)

**Request:**
```http
POST /api/v1/billing/webhook
stripe-signature: t=1704067200,v1=abc123def456...
Content-Type: application/json

{
  "id": "evt_stripe_webhook_123",
  "object": "event",
  "type": "invoice.payment_succeeded",
  "data": {
    "object": {
      "id": "in_ABC123DEF",
      "customer": "cus_BOB123XYZ",
      "status": "paid",
      "amount_paid": 450,
      "period_start": 1704067200,
      "period_end": 1706745600
    }
  }
}
```

**Handled Event Types:**
- `invoice.payment_succeeded` - Payment successful
- `invoice.payment_failed` - Payment failed
- `customer.subscription.created` - Subscription created
- `customer.subscription.updated` - Subscription updated
- `customer.subscription.deleted` - Subscription cancelled
- `customer.subscription.trial_will_end` - Trial ending soon
- `billing.meter_event.created` - Meter event recorded

**Response (200 OK):**
```json
{
  "data": {
    "status": "received",
    "event_id": "evt_stripe_webhook_123",
    "processed_at": "2025-01-31T12:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - Webhook received and processed
- `400 Bad Request` - Malformed webhook payload
- `401 Unauthorized` - Invalid signature (HMAC verification failed)

**Signature Verification:**

Stripe signs webhooks with HMAC-SHA256. You MUST verify the signature to ensure the webhook is from Stripe.

**Python Example:**
```python
import hmac
import hashlib

def verify_stripe_signature(payload: bytes, signature_header: str, webhook_secret: str) -> bool:
    """
    Verify Stripe webhook signature.

    Args:
        payload: Raw request body (bytes)
        signature_header: Value of stripe-signature header
        webhook_secret: Your Stripe webhook secret (whsec_...)

    Returns:
        True if signature is valid, False otherwise
    """
    # Extract timestamp and signature
    parts = signature_header.split(',')
    timestamp = None
    signatures = []

    for part in parts:
        if part.startswith('t='):
            timestamp = part[2:]
        elif part.startswith('v1='):
            signatures.append(part[3:])

    if not timestamp or not signatures:
        return False

    # Construct signed payload
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"

    # Calculate expected signature
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures (constant-time comparison)
    return any(
        hmac.compare_digest(expected_signature, sig)
        for sig in signatures
    )

# Usage in FastAPI endpoint
@app.post("/api/v1/billing/webhook")
async def webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if not verify_stripe_signature(payload, signature, STRIPE_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(payload)
    # Process event...
    return {"status": "received", "event_id": event["id"]}
```

**Example Webhook Payloads:**

**invoice.payment_succeeded:**
```json
{
  "id": "evt_123",
  "type": "invoice.payment_succeeded",
  "data": {
    "object": {
      "id": "in_123",
      "customer": "cus_ABC123",
      "amount_paid": 450,
      "status": "paid"
    }
  }
}
```

**customer.subscription.updated:**
```json
{
  "id": "evt_456",
  "type": "customer.subscription.updated",
  "data": {
    "object": {
      "id": "sub_DEF456",
      "customer": "cus_ABC123",
      "status": "active",
      "cancel_at_period_end": true
    }
  }
}
```

---

### Health

#### GET /api/v1/billing/health

Service health check.

**Authentication:** None (public endpoint)

**Request:**
```http
GET /api/v1/billing/health
```

**Response (200 OK):**
```json
{
  "data": {
    "status": "healthy",
    "checks": {
      "stripe_api": {
        "status": "ok",
        "latency_ms": 120
      },
      "database": {
        "status": "ok",
        "latency_ms": 5
      },
      "redis": {
        "status": "ok",
        "latency_ms": 2
      }
    },
    "version": "1.0.0",
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

**Response (503 Service Unavailable):**
```json
{
  "data": {
    "status": "unhealthy",
    "checks": {
      "stripe_api": {
        "status": "error",
        "error": "Connection timeout"
      },
      "database": {
        "status": "ok",
        "latency_ms": 5
      }
    },
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

**Status Codes:**
- `200 OK` - All systems operational
- `503 Service Unavailable` - One or more critical systems down

---

## Data Models

### Pydantic Schemas

#### StripeCustomer

```python
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Dict

class StripeCustomer(BaseModel):
    stripe_customer_id: str
    tenant_id: str
    email: EmailStr
    name: str
    metadata: Optional[Dict[str, str]] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "stripe_customer_id": "cus_ABC123XYZ",
                "tenant_id": "tenant_xyz789",
                "email": "customer@example.com",
                "name": "Customer Name",
                "metadata": {"company_id": "comp_123"},
                "created_at": "2025-01-31T12:00:00Z",
                "updated_at": "2025-01-31T12:00:00Z"
            }
        }
```

#### StripeSubscription

```python
from enum import Enum

class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"

class SubscriptionTier(str, Enum):
    STARTER = "starter"
    GROWTH = "growth"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

class StripeSubscription(BaseModel):
    stripe_subscription_id: str
    stripe_customer_id: str
    tenant_id: str
    status: SubscriptionStatus
    tier: SubscriptionTier
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    created_at: datetime
    updated_at: datetime
    canceled_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "stripe_subscription_id": "sub_DEF456GHI",
                "stripe_customer_id": "cus_ABC123XYZ",
                "tenant_id": "tenant_xyz789",
                "status": "active",
                "tier": "growth",
                "current_period_start": "2025-01-31T12:00:00Z",
                "current_period_end": "2025-02-28T12:00:00Z",
                "cancel_at_period_end": false
            }
        }
```

#### MeterEvent

```python
class MeterEventStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class MeterEvent(BaseModel):
    id: str
    event_name: str
    value: int
    timestamp: int  # Unix timestamp
    status: MeterEventStatus

    class Config:
        json_schema_extra = {
            "example": {
                "id": "evt_stripe_abc123",
                "event_name": "ai_labels",
                "value": 1500,
                "timestamp": 1704067200,
                "status": "succeeded"
            }
        }
```

#### UsageBreakdown

```python
class UsageBreakdown(BaseModel):
    event_name: str
    total_quantity: int
    event_count: int
    unit_price: float
    estimated_cost: float

    class Config:
        json_schema_extra = {
            "example": {
                "event_name": "ai_labels",
                "total_quantity": 3500,
                "event_count": 23,
                "unit_price": 0.001,
                "estimated_cost": 3.50
            }
        }
```

#### SyncStatus

```python
class SyncStatus(BaseModel):
    last_sync: datetime
    pending_events: int
    failed_events: int
    total_events: int

    class Config:
        json_schema_extra = {
            "example": {
                "last_sync": "2025-01-31T15:30:45Z",
                "pending_events": 0,
                "failed_events": 0,
                "total_events": 30
            }
        }
```

#### UsageSummary

```python
class UsageSummary(BaseModel):
    period: Dict[str, datetime]
    subscription: StripeSubscription
    usage_breakdown: List[UsageBreakdown]
    total_estimated_cost: float
    sync_status: SyncStatus
```

#### MeterEventRequest

```python
class MeterEventRequest(BaseModel):
    stripe_customer_id: str
    meter_event_name: str
    quantity: int
    timestamp: Optional[int] = None
    idempotency_key: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "stripe_customer_id": "cus_ABC123XYZ",
                "meter_event_name": "ai_labels",
                "quantity": 1500,
                "idempotency_key": "batch_001_2025_01_31",
                "metadata": {"batch_id": "batch_001"}
            }
        }
```

#### CreateSubscriptionRequest

```python
class CreateSubscriptionRequest(BaseModel):
    stripe_customer_id: str
    tier: SubscriptionTier
    price_id: Optional[str] = None
```

#### UpdateSubscriptionRequest

```python
class UpdateSubscriptionRequest(BaseModel):
    tier: Optional[SubscriptionTier] = None
    price_id: Optional[str] = None
```

#### CreateCustomerRequest

```python
class CreateCustomerRequest(BaseModel):
    email: EmailStr
    name: str
    metadata: Optional[Dict[str, str]] = None
```

#### UpdateCustomerRequest

```python
class UpdateCustomerRequest(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
```

---

## Meter Event Names

### Valid Meter Event Types

| Event Name | Description | Use Case |
|------------|-------------|----------|
| `ai_labels` | AI-generated labels | High-confidence automated labeling |
| `human_audits` | Human review/audit | Low-confidence or manual review |
| `batch_exports` | Data export operations | Bulk data exports |
| `api_calls` | API requests | General API usage |
| `data_validations` | Data validation checks | Data quality checks |
| `model_inferences` | Model inference calls | ML model predictions |
| `embeddings_generated` | Vector embeddings | Embedding generation |
| `documents_processed` | Document processing | PDF/document processing |

### Pricing Per Tier

#### Starter Tier Pricing

| Event Name | Unit Price | Notes |
|------------|-----------|--------|
| `ai_labels` | $0.002 | Per label |
| `human_audits` | $0.020 | Per audit |
| `batch_exports` | $0.100 | Per export |
| `api_calls` | $0.001 | Per call |
| `data_validations` | $0.002 | Per validation |
| `model_inferences` | $0.003 | Per inference |
| `embeddings_generated` | $0.001 | Per embedding |
| `documents_processed` | $0.050 | Per document |

#### Growth Tier Pricing (50% discount)

| Event Name | Unit Price | Notes |
|------------|-----------|--------|
| `ai_labels` | $0.001 | 50% off |
| `human_audits` | $0.010 | 50% off |
| `batch_exports` | $0.050 | 50% off |
| `api_calls` | $0.0005 | 50% off |
| `data_validations` | $0.001 | 50% off |
| `model_inferences` | $0.0015 | 50% off |
| `embeddings_generated` | $0.0005 | 50% off |
| `documents_processed` | $0.025 | 50% off |

#### Professional Tier Pricing (75% discount)

| Event Name | Unit Price | Notes |
|------------|-----------|--------|
| `ai_labels` | $0.0005 | 75% off |
| `human_audits` | $0.005 | 75% off |
| `batch_exports` | $0.025 | 75% off |
| `api_calls` | $0.00025 | 75% off |
| `data_validations` | $0.0005 | 75% off |
| `model_inferences` | $0.00075 | 75% off |
| `embeddings_generated` | $0.00025 | 75% off |
| `documents_processed` | $0.0125 | 75% off |

#### Enterprise Tier

Custom pricing negotiated per contract. Contact sales for volume discounts.

---

## Error Codes & Responses

### 400 Bad Request

**Invalid meter event:**
```json
{
  "error": {
    "code": "invalid_meter_event",
    "message": "Invalid meter event name 'ai_labels_typo'",
    "details": {
      "field": "meter_event_name",
      "valid_values": ["ai_labels", "human_audits", "batch_exports", "..."]
    }
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-01-31T12:00:00Z"
  }
}
```

**Missing required fields:**
```json
{
  "error": {
    "code": "validation_error",
    "message": "Missing required field 'stripe_customer_id'",
    "details": {
      "field": "stripe_customer_id",
      "reason": "required"
    }
  }
}
```

**Malformed request:**
```json
{
  "error": {
    "code": "malformed_request",
    "message": "Invalid JSON payload",
    "details": {
      "line": 3,
      "column": 15,
      "error": "Unexpected token }"
    }
  }
}
```

### 401 Unauthorized

**Invalid JWT token:**
```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid or expired JWT token",
    "details": {
      "reason": "token_expired",
      "expired_at": "2025-01-31T11:00:00Z"
    }
  }
}
```

**Missing authentication:**
```json
{
  "error": {
    "code": "unauthorized",
    "message": "Missing authentication header",
    "details": {
      "expected_header": "Authorization: Bearer <token>"
    }
  }
}
```

**Invalid API key:**
```json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid API key",
    "details": {
      "header": "X-API-Key",
      "reason": "key_not_found"
    }
  }
}
```

### 403 Forbidden

**Cross-tenant access:**
```json
{
  "error": {
    "code": "forbidden",
    "message": "Cross-tenant access denied",
    "details": {
      "token_tenant_id": "tenant_A",
      "requested_tenant_id": "tenant_B"
    }
  }
}
```

**Tier limitation:**
```json
{
  "error": {
    "code": "forbidden",
    "message": "Feature not available for your tier",
    "details": {
      "current_tier": "starter",
      "required_tier": "growth",
      "feature": "human_audits"
    }
  }
}
```

### 404 Not Found

**Customer not found:**
```json
{
  "error": {
    "code": "customer_not_found",
    "message": "Customer not found",
    "details": {
      "stripe_customer_id": "cus_ABC123XYZ"
    }
  }
}
```

**Subscription not found:**
```json
{
  "error": {
    "code": "subscription_not_found",
    "message": "No active subscription found",
    "details": {
      "tenant_id": "tenant_xyz789"
    }
  }
}
```

### 422 Unprocessable Entity

**Invalid meter event name:**
```json
{
  "error": {
    "code": "invalid_meter_event_name",
    "message": "Meter event 'ai_labels_typo' not configured in Stripe",
    "details": {
      "meter_event_name": "ai_labels_typo",
      "valid_events": ["ai_labels", "human_audits", "batch_exports"],
      "action": "Check Stripe meter configuration"
    }
  }
}
```

### 429 Too Many Requests

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Max 100 requests per minute.",
    "details": {
      "limit": 100,
      "remaining": 0,
      "reset_at": "2025-01-31T12:30:00Z",
      "retry_after_seconds": 30
    }
  }
}
```

### 502 Bad Gateway

**Stripe API error (transient):**
```json
{
  "error": {
    "code": "stripe_api_error",
    "message": "Stripe API temporarily unavailable",
    "details": {
      "stripe_error": "Connection timeout",
      "is_transient": true,
      "retry_recommended": true
    }
  }
}
```

### 503 Service Unavailable

```json
{
  "error": {
    "code": "service_unavailable",
    "message": "Service temporarily unavailable",
    "details": {
      "reason": "database_unavailable",
      "retry_after_seconds": 60
    }
  }
}
```

---

## Idempotency

### Overview

Idempotency ensures the same operation can be retried safely without duplicate side effects. This is critical for meter events to prevent double-charging customers.

### Idempotency-Key Header

**Format:**
```
Idempotency-Key: <unique_string>
```

**Recommended Format:**
```
{tenant_id}_{operation}_{batch_id}_{date}
```

**Examples:**
```
Idempotency-Key: tenant_xyz_report_batch001_20250131
Idempotency-Key: alice_saas_app_usage_b123_2025_01_31
```

### TTL (Time-To-Live)

- **Duration:** 24 hours
- **Storage:** Redis (primary), PostgreSQL (fallback)
- **Cleanup:** Automatic via TTL expiration

### How It Works

#### First Request

```http
POST /api/v1/billing/usage/report
Idempotency-Key: batch_001_2025_01_31

{
  "stripe_customer_id": "cus_ABC123",
  "meter_event_name": "ai_labels",
  "quantity": 1500
}
```

**Processing:**
1. Check idempotency registry: `batch_001_2025_01_31` → Not found
2. Register key with 24-hour TTL
3. Call Stripe API
4. Store response in cache
5. Return response to client

**Response:**
```json
{
  "data": {
    "meter_event": {
      "id": "evt_123",
      "status": "succeeded"
    },
    "idempotency": {
      "key": "batch_001_2025_01_31",
      "is_replay": false
    }
  }
}
```

#### Retry/Duplicate Request (Same Key)

```http
POST /api/v1/billing/usage/report
Idempotency-Key: batch_001_2025_01_31

{
  "stripe_customer_id": "cus_ABC123",
  "meter_event_name": "ai_labels",
  "quantity": 1500
}
```

**Processing:**
1. Check idempotency registry: `batch_001_2025_01_31` → Found!
2. Return cached response immediately
3. NO call to Stripe API
4. Customer NOT charged again

**Response:**
```json
{
  "data": {
    "meter_event": {
      "id": "evt_123",
      "status": "succeeded"
    },
    "idempotency": {
      "key": "batch_001_2025_01_31",
      "is_replay": true,
      "first_seen": "2025-01-31T12:00:00Z",
      "expires_at": "2025-02-01T12:00:00Z"
    }
  }
}
```

### Benefits

1. **Prevents Double-Charging:** Same event never charged twice
2. **Network Resilience:** Safe to retry on timeouts
3. **Client Simplicity:** No complex retry logic needed
4. **Consistency:** Same input = same output

### Best Practices

1. **Always use idempotency keys** for production meter reporting
2. **Generate keys deterministically** (same input = same key)
3. **Include timestamp** in key to prevent collisions across days
4. **Don't reuse keys** for different operations
5. **Handle 200 OK as success** even if it's a replay

### Example: Generating Idempotency Keys

**Python:**
```python
import hashlib
from datetime import datetime

def generate_idempotency_key(
    tenant_id: str,
    batch_id: str,
    meter_event_name: str,
    timestamp: datetime
) -> str:
    """Generate deterministic idempotency key."""
    date_str = timestamp.strftime('%Y%m%d')
    components = f"{tenant_id}_{batch_id}_{meter_event_name}_{date_str}"

    # Optional: Hash for shorter keys
    hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]

    return f"{tenant_id}_{batch_id}_{hash_digest}"

# Usage
key = generate_idempotency_key(
    tenant_id="alice_saas_app",
    batch_id="batch_001",
    meter_event_name="ai_labels",
    timestamp=datetime.now()
)
# Output: alice_saas_app_batch_001_abc123def456
```

**JavaScript:**
```javascript
import crypto from 'crypto';

function generateIdempotencyKey(tenantId, batchId, meterEventName, timestamp) {
  const dateStr = timestamp.toISOString().split('T')[0].replace(/-/g, '');
  const components = `${tenantId}_${batchId}_${meterEventName}_${dateStr}`;

  // Optional: Hash for shorter keys
  const hash = crypto
    .createHash('sha256')
    .update(components)
    .digest('hex')
    .substring(0, 16);

  return `${tenantId}_${batchId}_${hash}`;
}

// Usage
const key = generateIdempotencyKey(
  'alice_saas_app',
  'batch_001',
  'ai_labels',
  new Date()
);
// Output: alice_saas_app_batch_001_abc123def456
```

---

## Stripe Integration Details

### Stripe Authentication

**API Key:**
```bash
STRIPE_SECRET_KEY=sk_live_abc123def456xyz789...
```

**Test Mode:**
```bash
STRIPE_SECRET_KEY=sk_test_abc123def456xyz789...
```

**Using API Key:**
```http
POST https://api.stripe.com/v1/customers
Authorization: Bearer sk_live_abc123def456xyz789...
Content-Type: application/x-www-form-urlencoded
```

### Meter ID Configuration

Meters must be created in Stripe Dashboard before use.

**Environment Variables:**
```bash
STRIPE_METER_AI_LABELS_ID=mtr_abc123
STRIPE_METER_HUMAN_AUDITS_ID=mtr_def456
STRIPE_METER_BATCH_EXPORTS_ID=mtr_ghi789
```

**Creating Meters (Stripe Dashboard):**
1. Go to: Billing → Meters
2. Click "Create meter"
3. Set meter name (e.g., "ai_labels")
4. Set display name (e.g., "AI Labels")
5. Set default aggregation: Sum
6. Save and copy meter ID

### Price ID Configuration

**Environment Variables:**
```bash
# Starter tier
PRICE_STARTER_AI_LABELS=price_starter_ai_labels_monthly
PRICE_STARTER_HUMAN_AUDITS=price_starter_human_audits_monthly

# Growth tier
PRICE_GROWTH_AI_LABELS=price_growth_ai_labels_monthly
PRICE_GROWTH_HUMAN_AUDITS=price_growth_human_audits_monthly

# Professional tier
PRICE_PRO_AI_LABELS=price_pro_ai_labels_monthly
PRICE_PRO_HUMAN_AUDITS=price_pro_human_audits_monthly
```

**Creating Prices (Stripe Dashboard):**
1. Go to: Products → Create product
2. Set product name (e.g., "AI Labels - Growth Tier")
3. Add pricing:
   - Type: Metered billing
   - Price: $0.001 per unit
   - Billing period: Monthly
   - Meter: Select "ai_labels"
4. Save and copy price ID

### Meter Event Flow to Stripe

```
Application
  ↓ Report usage
MeteringService
  ↓ POST /api/v1/billing/usage/report
  ├─ Validate customer
  ├─ Check idempotency
  ├─ Store event locally (pending)
  ↓
Stripe API
  ↓ POST /v1/billing/meter_events
  {
    event_name: "ai_labels",
    value: 1500,
    timestamp: 1704067200,
    identifier: "cus_ABC123"  # Stripe customer ID
  }
  ↓ Response
  {
    id: "evt_stripe_123",
    livemode: true,
    created: 1704067200
  }
  ↓
MeteringService
  └─ Update event status: succeeded
```

### Subscription Creation in Stripe

```
Application
  ↓ Create subscription
MeteringService
  ↓ POST /api/v1/billing/subscriptions
  ├─ Validate customer
  ├─ Resolve price_id from tier
  ↓
Stripe API
  ↓ POST /v1/subscriptions
  {
    customer: "cus_ABC123",
    items: [{
      price: "price_growth_ai_labels_monthly"
    }],
    billing_cycle_anchor: 1704067200
  }
  ↓ Response
  {
    id: "sub_DEF456",
    status: "active",
    current_period_start: 1704067200,
    current_period_end: 1706745600
  }
  ↓
MeteringService
  └─ Store subscription in DB
```

### Webhook Signature Verification

**Stripe Signature Header:**
```
stripe-signature: t=1704067200,v1=abc123def456...
```

**Verification (Python):**
```python
import stripe

def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: str
) -> stripe.Event:
    """
    Verify Stripe webhook signature and parse event.

    Raises:
        stripe.error.SignatureVerificationError: If signature is invalid
    """
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=webhook_secret
        )
        return event
    except stripe.error.SignatureVerificationError as e:
        raise ValueError("Invalid signature") from e

# Usage in FastAPI
@app.post("/api/v1/billing/webhook")
async def webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = verify_webhook_signature(
            payload=payload,
            signature_header=signature,
            webhook_secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Process event
    if event.type == "invoice.payment_succeeded":
        handle_payment_succeeded(event.data.object)

    return {"status": "received", "event_id": event.id}
```

---

## Client Implementation Examples

### cURL Examples

#### Create Customer

```bash
curl -X POST https://api.metering-service.com/api/v1/billing/customers \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "email": "customer@example.com",
    "name": "Customer Name",
    "metadata": {
      "company_id": "comp_123"
    }
  }'
```

#### Create Subscription

```bash
curl -X POST https://api.metering-service.com/api/v1/billing/subscriptions \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "stripe_customer_id": "cus_ABC123XYZ",
    "tier": "growth",
    "price_id": "price_growth_validations_monthly"
  }'
```

#### Report Usage

```bash
curl -X POST https://api.metering-service.com/api/v1/billing/usage/report \
  -H "X-API-Key: mk_live_abc123def456xyz789" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: batch_001_2025_01_31" \
  -d '{
    "stripe_customer_id": "cus_ABC123XYZ",
    "meter_event_name": "ai_labels",
    "quantity": 1500,
    "metadata": {
      "batch_id": "batch_001",
      "pipeline": "aml_labeling"
    }
  }'
```

#### Get Usage Summary

```bash
curl -X GET "https://api.metering-service.com/api/v1/billing/usage/tenant_xyz789?period_start=2025-01-01&period_end=2025-01-31" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

#### Cancel Subscription

```bash
# Cancel at period end (recommended)
curl -X DELETE "https://api.metering-service.com/api/v1/billing/subscriptions/tenant_xyz789?immediate=false" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

# Cancel immediately
curl -X DELETE "https://api.metering-service.com/api/v1/billing/subscriptions/tenant_xyz789?immediate=true" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### Python SDK Example

Complete client class with all methods, retry logic, and idempotency handling.

```python
import requests
import hashlib
import time
from typing import Optional, Dict, List
from datetime import datetime
from dataclasses import dataclass

@dataclass
class MeteringConfig:
    base_url: str
    api_key: Optional[str] = None
    jwt_token: Optional[str] = None
    max_retries: int = 3
    retry_delay: float = 1.0

class MeteringClient:
    """
    Python SDK for Metering Service.

    Example:
        client = MeteringClient(
            base_url="https://api.metering-service.com",
            api_key="mk_live_abc123...",
            jwt_token="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
        )

        # Report usage
        response = client.report_usage(
            stripe_customer_id="cus_ABC123",
            meter_event_name="ai_labels",
            quantity=1500
        )
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        jwt_token: Optional[str] = None,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.jwt_token = jwt_token
        self.max_retries = max_retries
        self.session = requests.Session()

    def _get_headers(self, use_api_key: bool = False) -> Dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}

        if use_api_key and self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        return headers

    def _retry_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """Execute request with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, **kwargs)

                # Don't retry on client errors (4xx)
                if 400 <= response.status_code < 500:
                    return response

                # Don't retry on success
                if response.status_code < 400:
                    return response

                # Retry on 5xx errors
                if attempt < self.max_retries - 1:
                    delay = (2 ** attempt) * 1.0  # Exponential backoff
                    time.sleep(delay)
                    continue

                return response

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    delay = (2 ** attempt) * 1.0
                    time.sleep(delay)
                    continue
                raise

        return response

    def generate_idempotency_key(
        self,
        tenant_id: str,
        batch_id: str,
        timestamp: Optional[datetime] = None
    ) -> str:
        """Generate idempotency key."""
        if timestamp is None:
            timestamp = datetime.now()

        date_str = timestamp.strftime('%Y%m%d')
        components = f"{tenant_id}_{batch_id}_{date_str}"
        hash_digest = hashlib.sha256(components.encode()).hexdigest()[:16]

        return f"{tenant_id}_{batch_id}_{hash_digest}"

    # Customer Management

    def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """Create Stripe customer."""
        url = f"{self.base_url}/api/v1/billing/customers"
        payload = {
            "email": email,
            "name": name,
            "metadata": metadata or {}
        }

        response = self._retry_request(
            "POST",
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()["data"]

    def get_customer(self, tenant_id: str) -> Dict:
        """Get customer details."""
        url = f"{self.base_url}/api/v1/billing/customers/{tenant_id}"

        response = self._retry_request(
            "GET",
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()["data"]

    def update_customer(
        self,
        tenant_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """Update customer details."""
        url = f"{self.base_url}/api/v1/billing/customers/{tenant_id}"
        payload = {}

        if email:
            payload["email"] = email
        if name:
            payload["name"] = name
        if metadata is not None:
            payload["metadata"] = metadata

        response = self._retry_request(
            "PUT",
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()["data"]

    def delete_customer(self, tenant_id: str) -> Dict:
        """Delete customer."""
        url = f"{self.base_url}/api/v1/billing/customers/{tenant_id}"

        response = self._retry_request(
            "DELETE",
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()["data"]

    # Subscription Management

    def create_subscription(
        self,
        stripe_customer_id: str,
        tier: str,
        price_id: Optional[str] = None
    ) -> Dict:
        """Create subscription."""
        url = f"{self.base_url}/api/v1/billing/subscriptions"
        payload = {
            "stripe_customer_id": stripe_customer_id,
            "tier": tier
        }

        if price_id:
            payload["price_id"] = price_id

        response = self._retry_request(
            "POST",
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()["data"]

    def get_subscription(self, tenant_id: str) -> Dict:
        """Get subscription details."""
        url = f"{self.base_url}/api/v1/billing/subscriptions/{tenant_id}"

        response = self._retry_request(
            "GET",
            url,
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()["data"]

    def update_subscription(
        self,
        tenant_id: str,
        tier: Optional[str] = None,
        price_id: Optional[str] = None
    ) -> Dict:
        """Update subscription (tier change)."""
        url = f"{self.base_url}/api/v1/billing/subscriptions/{tenant_id}"
        payload = {}

        if tier:
            payload["tier"] = tier
        if price_id:
            payload["price_id"] = price_id

        response = self._retry_request(
            "PUT",
            url,
            headers=self._get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()["data"]

    def cancel_subscription(
        self,
        tenant_id: str,
        immediate: bool = False
    ) -> Dict:
        """Cancel subscription."""
        url = f"{self.base_url}/api/v1/billing/subscriptions/{tenant_id}"
        params = {"immediate": str(immediate).lower()}

        response = self._retry_request(
            "DELETE",
            url,
            headers=self._get_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()["data"]

    # Usage & Metering

    def report_usage(
        self,
        stripe_customer_id: str,
        meter_event_name: str,
        quantity: int,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        Report meter event.

        Args:
            stripe_customer_id: Stripe customer ID
            meter_event_name: Meter event name (e.g., "ai_labels")
            quantity: Quantity of events
            idempotency_key: Optional idempotency key (auto-generated if omitted)
            metadata: Optional metadata

        Returns:
            Response data
        """
        url = f"{self.base_url}/api/v1/billing/usage/report"

        payload = {
            "stripe_customer_id": stripe_customer_id,
            "meter_event_name": meter_event_name,
            "quantity": quantity,
            "metadata": metadata or {}
        }

        headers = self._get_headers(use_api_key=True)

        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
            payload["idempotency_key"] = idempotency_key

        response = self._retry_request(
            "POST",
            url,
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()["data"]

    def get_usage(
        self,
        tenant_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None
    ) -> Dict:
        """
        Get usage summary.

        Args:
            tenant_id: Tenant ID
            period_start: ISO 8601 date (optional)
            period_end: ISO 8601 date (optional)

        Returns:
            Usage summary
        """
        url = f"{self.base_url}/api/v1/billing/usage/{tenant_id}"
        params = {}

        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end

        response = self._retry_request(
            "GET",
            url,
            headers=self._get_headers(),
            params=params
        )
        response.raise_for_status()
        return response.json()["data"]

# Usage Example
if __name__ == "__main__":
    client = MeteringClient(
        base_url="https://api.metering-service.com",
        api_key="mk_live_abc123...",
        jwt_token="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
    )

    # Create customer
    customer = client.create_customer(
        email="bob@example.com",
        name="Bob's Corp",
        metadata={"company_id": "comp_123"}
    )
    print(f"Created customer: {customer['stripe_customer_id']}")

    # Create subscription
    subscription = client.create_subscription(
        stripe_customer_id=customer["stripe_customer_id"],
        tier="growth"
    )
    print(f"Created subscription: {subscription['stripe_subscription_id']}")

    # Report usage with idempotency
    idempotency_key = client.generate_idempotency_key(
        tenant_id="alice_saas_app",
        batch_id="batch_001"
    )

    usage = client.report_usage(
        stripe_customer_id=customer["stripe_customer_id"],
        meter_event_name="ai_labels",
        quantity=1500,
        idempotency_key=idempotency_key,
        metadata={"batch_id": "batch_001"}
    )
    print(f"Reported usage: {usage['estimated_cost']}")

    # Get usage summary
    summary = client.get_usage(
        tenant_id="alice_saas_app",
        period_start="2025-01-01",
        period_end="2025-01-31"
    )
    print(f"Total cost: ${summary['total_estimated_cost']}")
```

---

### JavaScript/TypeScript SDK Example

Async/await examples with error handling.

```typescript
import axios, { AxiosInstance, AxiosResponse } from 'axios';
import crypto from 'crypto';

interface MeteringConfig {
  baseUrl: string;
  apiKey?: string;
  jwtToken?: string;
  maxRetries?: number;
}

interface CustomerData {
  email: string;
  name: string;
  metadata?: Record<string, string>;
}

interface SubscriptionData {
  stripe_customer_id: string;
  tier: 'starter' | 'growth' | 'professional' | 'enterprise';
  price_id?: string;
}

interface UsageData {
  stripe_customer_id: string;
  meter_event_name: string;
  quantity: number;
  idempotency_key?: string;
  metadata?: Record<string, string>;
}

class MeteringClient {
  private client: AxiosInstance;
  private apiKey?: string;
  private jwtToken?: string;
  private maxRetries: number;

  constructor(config: MeteringConfig) {
    this.apiKey = config.apiKey;
    this.jwtToken = config.jwtToken;
    this.maxRetries = config.maxRetries || 3;

    this.client = axios.create({
      baseURL: config.baseUrl,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const config = error.config;

        // Don't retry on client errors (4xx)
        if (error.response && error.response.status >= 400 && error.response.status < 500) {
          throw error;
        }

        // Retry on 5xx errors
        if (!config._retryCount) {
          config._retryCount = 0;
        }

        if (config._retryCount < this.maxRetries) {
          config._retryCount += 1;

          // Exponential backoff
          const delay = Math.pow(2, config._retryCount - 1) * 1000;
          await this.sleep(delay);

          return this.client(config);
        }

        throw error;
      }
    );
  }

  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private getHeaders(useApiKey: boolean = false): Record<string, string> {
    const headers: Record<string, string> = {};

    if (useApiKey && this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    } else if (this.jwtToken) {
      headers['Authorization'] = `Bearer ${this.jwtToken}`;
    }

    return headers;
  }

  public generateIdempotencyKey(
    tenantId: string,
    batchId: string,
    timestamp?: Date
  ): string {
    const date = timestamp || new Date();
    const dateStr = date.toISOString().split('T')[0].replace(/-/g, '');
    const components = `${tenantId}_${batchId}_${dateStr}`;

    const hash = crypto
      .createHash('sha256')
      .update(components)
      .digest('hex')
      .substring(0, 16);

    return `${tenantId}_${batchId}_${hash}`;
  }

  // Customer Management

  async createCustomer(data: CustomerData): Promise<any> {
    const response = await this.client.post(
      '/api/v1/billing/customers',
      data,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async getCustomer(tenantId: string): Promise<any> {
    const response = await this.client.get(
      `/api/v1/billing/customers/${tenantId}`,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async updateCustomer(
    tenantId: string,
    data: Partial<CustomerData>
  ): Promise<any> {
    const response = await this.client.put(
      `/api/v1/billing/customers/${tenantId}`,
      data,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async deleteCustomer(tenantId: string): Promise<any> {
    const response = await this.client.delete(
      `/api/v1/billing/customers/${tenantId}`,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  // Subscription Management

  async createSubscription(data: SubscriptionData): Promise<any> {
    const response = await this.client.post(
      '/api/v1/billing/subscriptions',
      data,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async getSubscription(tenantId: string): Promise<any> {
    const response = await this.client.get(
      `/api/v1/billing/subscriptions/${tenantId}`,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async updateSubscription(
    tenantId: string,
    data: { tier?: string; price_id?: string }
  ): Promise<any> {
    const response = await this.client.put(
      `/api/v1/billing/subscriptions/${tenantId}`,
      data,
      { headers: this.getHeaders() }
    );
    return response.data.data;
  }

  async cancelSubscription(
    tenantId: string,
    immediate: boolean = false
  ): Promise<any> {
    const response = await this.client.delete(
      `/api/v1/billing/subscriptions/${tenantId}`,
      {
        headers: this.getHeaders(),
        params: { immediate: immediate.toString() },
      }
    );
    return response.data.data;
  }

  // Usage & Metering

  async reportUsage(data: UsageData): Promise<any> {
    const headers = this.getHeaders(true);

    if (data.idempotency_key) {
      headers['Idempotency-Key'] = data.idempotency_key;
    }

    const response = await this.client.post(
      '/api/v1/billing/usage/report',
      data,
      { headers }
    );
    return response.data.data;
  }

  async getUsage(
    tenantId: string,
    periodStart?: string,
    periodEnd?: string
  ): Promise<any> {
    const params: Record<string, string> = {};

    if (periodStart) params.period_start = periodStart;
    if (periodEnd) params.period_end = periodEnd;

    const response = await this.client.get(
      `/api/v1/billing/usage/${tenantId}`,
      {
        headers: this.getHeaders(),
        params,
      }
    );
    return response.data.data;
  }
}

// Usage Example
async function main() {
  const client = new MeteringClient({
    baseUrl: 'https://api.metering-service.com',
    apiKey: 'mk_live_abc123...',
    jwtToken: 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...',
  });

  try {
    // Create customer
    const customer = await client.createCustomer({
      email: 'bob@example.com',
      name: "Bob's Corp",
      metadata: { company_id: 'comp_123' },
    });
    console.log(`Created customer: ${customer.stripe_customer_id}`);

    // Create subscription
    const subscription = await client.createSubscription({
      stripe_customer_id: customer.stripe_customer_id,
      tier: 'growth',
    });
    console.log(`Created subscription: ${subscription.stripe_subscription_id}`);

    // Report usage with idempotency
    const idempotencyKey = client.generateIdempotencyKey(
      'alice_saas_app',
      'batch_001'
    );

    const usage = await client.reportUsage({
      stripe_customer_id: customer.stripe_customer_id,
      meter_event_name: 'ai_labels',
      quantity: 1500,
      idempotency_key: idempotencyKey,
      metadata: { batch_id: 'batch_001' },
    });
    console.log(`Reported usage: $${usage.estimated_cost}`);

    // Get usage summary
    const summary = await client.getUsage(
      'alice_saas_app',
      '2025-01-01',
      '2025-01-31'
    );
    console.log(`Total cost: $${summary.total_estimated_cost}`);

  } catch (error: any) {
    if (error.response) {
      // API error
      console.error('API Error:', error.response.data);

      // Handle rate limit
      if (error.response.status === 429) {
        const retryAfter = error.response.headers['retry-after'];
        console.log(`Rate limited. Retry after ${retryAfter} seconds.`);
      }
    } else {
      // Network error
      console.error('Network Error:', error.message);
    }
  }
}

main();
```

---

## Common Patterns

### Pattern 1: Complete Customer Onboarding Flow

Create customer → Create subscription

```python
from metering_client import MeteringClient

client = MeteringClient(
    base_url="https://api.metering-service.com",
    jwt_token="<your_jwt_token>"
)

# Step 1: Create customer
customer = client.create_customer(
    email="new_customer@example.com",
    name="New Customer Corp",
    metadata={
        "company_id": "comp_new_123",
        "industry": "fintech",
        "source": "website_signup"
    }
)

print(f"✓ Customer created: {customer['stripe_customer_id']}")

# Step 2: Create subscription
subscription = client.create_subscription(
    stripe_customer_id=customer["stripe_customer_id"],
    tier="growth"  # or "starter", "professional", "enterprise"
)

print(f"✓ Subscription created: {subscription['stripe_subscription_id']}")
print(f"✓ Tier: {subscription['tier']}")
print(f"✓ Status: {subscription['status']}")
print(f"✓ Billing period: {subscription['current_period_start']} to {subscription['current_period_end']}")

# Customer is now ready to use your service!
```

---

### Pattern 2: Reporting Usage with Idempotency

Prevent duplicate charges with idempotency keys.

```python
from metering_client import MeteringClient
import hashlib
from datetime import datetime

client = MeteringClient(
    base_url="https://api.metering-service.com",
    api_key="mk_live_abc123..."
)

def process_batch_and_report_usage(
    batch_id: str,
    customer_id: str,
    events: list
):
    """
    Process batch and report usage to Stripe.
    Safe to retry - idempotency prevents double-charging.
    """
    # Generate deterministic idempotency key
    idempotency_key = client.generate_idempotency_key(
        tenant_id="alice_saas_app",
        batch_id=batch_id,
        timestamp=datetime.now()
    )

    # Count events by type
    event_counts = {
        "ai_labels": sum(1 for e in events if e["confidence"] >= 0.85),
        "human_audits": sum(1 for e in events if e["confidence"] < 0.85)
    }

    # Report each meter type
    for meter_name, quantity in event_counts.items():
        if quantity == 0:
            continue

        try:
            result = client.report_usage(
                stripe_customer_id=customer_id,
                meter_event_name=meter_name,
                quantity=quantity,
                idempotency_key=f"{idempotency_key}_{meter_name}",
                metadata={
                    "batch_id": batch_id,
                    "pipeline": "aml_labeling",
                    "timestamp": datetime.now().isoformat()
                }
            )

            if result["idempotency"]["is_replay"]:
                print(f"⚠ Duplicate request detected (idempotency key: {idempotency_key}_{meter_name})")
                print(f"  Original request at: {result['idempotency']['first_seen']}")
                print(f"  No double-charge occurred ✓")
            else:
                print(f"✓ Reported {quantity} {meter_name} events")
                print(f"  Estimated cost: ${result['estimated_cost']}")

        except Exception as e:
            print(f"✗ Error reporting {meter_name}: {e}")
            # Safe to retry with same idempotency key
            raise

# Usage
events = [
    {"id": "evt_1", "confidence": 0.92},  # ai_label
    {"id": "evt_2", "confidence": 0.88},  # ai_label
    {"id": "evt_3", "confidence": 0.75},  # human_audit
    # ... more events
]

process_batch_and_report_usage(
    batch_id="batch_001",
    customer_id="cus_ABC123XYZ",
    events=events
)
```

---

### Pattern 3: Handling Tier Changes

Upgrade/downgrade subscription tier.

```python
from metering_client import MeteringClient

client = MeteringClient(
    base_url="https://api.metering-service.com",
    jwt_token="<your_jwt_token>"
)

def upgrade_customer_tier(tenant_id: str, new_tier: str):
    """Upgrade customer to new tier with prorated pricing."""

    # Get current subscription
    current_sub = client.get_subscription(tenant_id)
    print(f"Current tier: {current_sub['tier']}")
    print(f"Current period: {current_sub['current_period_start']} to {current_sub['current_period_end']}")

    # Update to new tier
    updated_sub = client.update_subscription(
        tenant_id=tenant_id,
        tier=new_tier
    )

    print(f"\n✓ Upgraded to {updated_sub['tier']}")

    # Prorated amount
    if "proration" in updated_sub:
        proration = updated_sub["proration"]
        print(f"\nProration details:")
        print(f"  Credit for unused time: ${abs(proration['prorated_amount'])}")
        print(f"  New tier monthly cost: ${proration['new_amount']}")
        print(f"  Effective date: {proration['effective_date']}")

    # New pricing takes effect immediately
    print(f"\n✓ New pricing active starting now")
    return updated_sub

# Example: Upgrade from Growth to Professional
upgraded_sub = upgrade_customer_tier(
    tenant_id="alice_saas_app",
    new_tier="professional"
)

# Future usage will be billed at Professional tier rates
```

---

### Pattern 4: Checking Current Usage and Costs

Monitor usage and estimated costs.

```python
from metering_client import MeteringClient
from datetime import datetime, timedelta

client = MeteringClient(
    base_url="https://api.metering-service.com",
    jwt_token="<your_jwt_token>"
)

def get_current_month_usage(tenant_id: str):
    """Get usage summary for current billing period."""

    # Current month
    now = datetime.now()
    period_start = now.replace(day=1).strftime('%Y-%m-%d')
    period_end = now.strftime('%Y-%m-%d')

    summary = client.get_usage(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end
    )

    print(f"Usage Summary for {tenant_id}")
    print(f"Period: {summary['period']['start']} to {summary['period']['end']}")
    print(f"\nSubscription: {summary['subscription']['tier']} tier ({summary['subscription']['status']})")

    print(f"\nUsage Breakdown:")
    for usage in summary["usage_breakdown"]:
        print(f"  {usage['event_name']}:")
        print(f"    Total quantity: {usage['total_quantity']:,}")
        print(f"    Event count: {usage['event_count']}")
        print(f"    Unit price: ${usage['unit_price']}")
        print(f"    Estimated cost: ${usage['estimated_cost']:.2f}")

    print(f"\nTotal Estimated Cost: ${summary['total_estimated_cost']:.2f}")

    print(f"\nSync Status:")
    print(f"  Last sync: {summary['sync_status']['last_sync']}")
    print(f"  Pending events: {summary['sync_status']['pending_events']}")
    print(f"  Failed events: {summary['sync_status']['failed_events']}")
    print(f"  Total synced: {summary['sync_status']['total_synced_events']}")

    # Warning if nearing limits
    if summary["total_estimated_cost"] > 100:
        print(f"\n⚠ Warning: High usage this month (${summary['total_estimated_cost']:.2f})")

    return summary

# Usage
usage = get_current_month_usage("alice_saas_app")
```

---

### Pattern 5: Graceful Subscription Cancellation

Cancel at period end (recommended) to let customer finish billing cycle.

```python
from metering_client import MeteringClient
from datetime import datetime

client = MeteringClient(
    base_url="https://api.metering-service.com",
    jwt_token="<your_jwt_token>"
)

def cancel_subscription_gracefully(tenant_id: str):
    """
    Cancel subscription at period end.
    Customer retains access until end of current billing cycle.
    """

    # Get current subscription
    current_sub = client.get_subscription(tenant_id)

    print(f"Current subscription:")
    print(f"  ID: {current_sub['stripe_subscription_id']}")
    print(f"  Tier: {current_sub['tier']}")
    print(f"  Status: {current_sub['status']}")
    print(f"  Current period ends: {current_sub['current_period_end']}")

    # Cancel at period end (not immediate)
    result = client.cancel_subscription(
        tenant_id=tenant_id,
        immediate=False  # Keep access until period end
    )

    print(f"\n✓ Subscription will cancel at period end")
    print(f"  Status: {result['status']}")
    print(f"  Access until: {result['access_until']}")
    print(f"  Cancels at: {result['cancels_at']}")

    # Calculate days remaining
    cancels_at = datetime.fromisoformat(result["cancels_at"].replace('Z', '+00:00'))
    days_remaining = (cancels_at - datetime.now()).days

    print(f"\n⏳ Customer has {days_remaining} days of access remaining")
    print(f"   After that, no more charges will occur")

    return result

# Usage
cancel_subscription_gracefully("alice_saas_app")

# For immediate cancellation (not recommended):
# client.cancel_subscription(tenant_id="alice_saas_app", immediate=True)
```

---

## Webhook Handling

### Stripe Webhook Events to Handle

| Event Type | Description | Action |
|------------|-------------|--------|
| `invoice.payment_succeeded` | Payment successful | Mark invoice as paid, send receipt |
| `invoice.payment_failed` | Payment failed | Retry payment, notify customer |
| `customer.subscription.created` | Subscription created | Sync to local DB |
| `customer.subscription.updated` | Subscription updated | Update tier, status, cancel_at_period_end |
| `customer.subscription.deleted` | Subscription cancelled | Mark as canceled, revoke access |
| `customer.subscription.trial_will_end` | Trial ending soon | Notify customer (3 days before) |
| `billing.meter_event.created` | Meter event recorded | Confirmation (optional logging) |

### Webhook Payload Verification

**Python (FastAPI):**
```python
import stripe
from fastapi import FastAPI, Request, HTTPException
import os

app = FastAPI()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@app.post("/api/v1/billing/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.

    CRITICAL: Must verify signature to prevent spoofing.
    """
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature")

    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing signature header")

    try:
        # Verify signature
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=401, detail="Invalid signature")
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")

    # Handle event
    event_type = event["type"]
    event_data = event["data"]["object"]

    if event_type == "invoice.payment_succeeded":
        handle_payment_succeeded(event_data)
    elif event_type == "invoice.payment_failed":
        handle_payment_failed(event_data)
    elif event_type == "customer.subscription.updated":
        handle_subscription_updated(event_data)
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(event_data)
    else:
        print(f"Unhandled event type: {event_type}")

    return {"status": "received", "event_id": event["id"]}

def handle_payment_succeeded(invoice):
    """Handle successful payment."""
    customer_id = invoice["customer"]
    amount_paid = invoice["amount_paid"] / 100  # Convert cents to dollars

    print(f"✓ Payment succeeded for customer {customer_id}: ${amount_paid}")

    # Update database
    # UPDATE tenant_usage SET billing_status = 'completed', invoice_id = ?
    # WHERE tenant_id = (SELECT tenant_id FROM stripe_customers WHERE stripe_customer_id = ?)

    # Send receipt email
    # send_receipt_email(customer_id, invoice)

def handle_payment_failed(invoice):
    """Handle failed payment."""
    customer_id = invoice["customer"]
    amount_due = invoice["amount_due"] / 100

    print(f"✗ Payment failed for customer {customer_id}: ${amount_due}")

    # Notify customer
    # send_payment_failed_email(customer_id, invoice)

    # Stripe will automatically retry payment

def handle_subscription_updated(subscription):
    """Handle subscription update."""
    subscription_id = subscription["id"]
    customer_id = subscription["customer"]
    status = subscription["status"]
    cancel_at_period_end = subscription["cancel_at_period_end"]

    print(f"✓ Subscription updated: {subscription_id}")
    print(f"  Status: {status}")
    print(f"  Cancel at period end: {cancel_at_period_end}")

    # Update database
    # UPDATE stripe_subscriptions
    # SET status = ?, cancel_at_period_end = ?
    # WHERE stripe_subscription_id = ?

def handle_subscription_deleted(subscription):
    """Handle subscription cancellation."""
    subscription_id = subscription["id"]
    customer_id = subscription["customer"]

    print(f"✓ Subscription canceled: {subscription_id}")

    # Update database
    # UPDATE stripe_subscriptions
    # SET status = 'canceled', canceled_at = NOW()
    # WHERE stripe_subscription_id = ?

    # Revoke customer access
    # revoke_access(customer_id)
```

### Example Webhook Payloads

**invoice.payment_succeeded:**
```json
{
  "id": "evt_webhook_123",
  "type": "invoice.payment_succeeded",
  "data": {
    "object": {
      "id": "in_ABC123",
      "customer": "cus_BOB123XYZ",
      "amount_paid": 450,
      "amount_due": 450,
      "status": "paid",
      "period_start": 1704067200,
      "period_end": 1706745600,
      "lines": {
        "data": [
          {
            "description": "3,500 × AI Labels (Growth tier)",
            "amount": 350
          },
          {
            "description": "50 × Human Audits (Growth tier)",
            "amount": 100
          }
        ]
      }
    }
  },
  "created": 1706745600
}
```

**customer.subscription.updated:**
```json
{
  "id": "evt_webhook_456",
  "type": "customer.subscription.updated",
  "data": {
    "object": {
      "id": "sub_DEF456",
      "customer": "cus_BOB123XYZ",
      "status": "active",
      "cancel_at_period_end": true,
      "current_period_start": 1704067200,
      "current_period_end": 1706745600,
      "items": {
        "data": [
          {
            "price": {
              "id": "price_growth_validations_monthly",
              "unit_amount": 100
            }
          }
        ]
      }
    }
  },
  "created": 1704070000
}
```

### Retry Logic (Exponential Backoff)

Stripe retries webhook delivery automatically:
- Initial delivery attempt
- Retry after 5 minutes
- Retry after 30 minutes
- Retry after 2 hours
- Retry after 12 hours
- Stops after ~3 days

**Your webhook endpoint should:**
1. Return `200 OK` quickly (within 5 seconds)
2. Be idempotent (handle duplicate webhooks gracefully)
3. Process heavy tasks asynchronously

**Example: Idempotent Webhook Processing**
```python
import redis

redis_client = redis.Redis()

@app.post("/api/v1/billing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature_header = request.headers.get("stripe-signature")

    # Verify signature
    event = stripe.Webhook.construct_event(payload, signature_header, STRIPE_WEBHOOK_SECRET)

    # Check if already processed (idempotency)
    event_id = event["id"]
    cache_key = f"webhook_processed:{event_id}"

    if redis_client.get(cache_key):
        print(f"⚠ Webhook {event_id} already processed")
        return {"status": "received", "event_id": event_id}

    # Process event
    handle_event(event)

    # Mark as processed (24-hour TTL)
    redis_client.setex(cache_key, 86400, "1")

    return {"status": "received", "event_id": event_id}
```

---

## Testing/Sandbox

### Sandbox Environment

```
Sandbox URL: https://sandbox.metering-service.com
```

**Differences from Production:**
- Uses Stripe test mode
- No real charges
- Faster webhook delivery (for testing)
- Relaxed rate limits

### Test Mode

**Stripe Test API Keys:**
```bash
STRIPE_SECRET_KEY=sk_test_abc123def456xyz789...
STRIPE_WEBHOOK_SECRET=whsec_test_abc123def456...
```

**Test Mode Behavior:**
- All API calls use `sk_test_...` key
- Stripe creates test customers/subscriptions (prefix: `cus_test_`, `sub_test_`)
- No real money charged
- Webhooks delivered to test endpoint

### Example Test Data

**Test Customer:**
```json
{
  "email": "test+customer@example.com",
  "name": "Test Customer",
  "metadata": {
    "test_mode": "true",
    "environment": "sandbox"
  }
}
```

**Test Credit Cards (Stripe):**
```
Success: 4242 4242 4242 4242
Decline: 4000 0000 0000 0002
Expired: 4000 0000 0000 0069
```

### Creating Test Customers/Subscriptions

**Python:**
```python
from metering_client import MeteringClient

# Use sandbox URL and test API key
client = MeteringClient(
    base_url="https://sandbox.metering-service.com",
    jwt_token="<test_jwt_token>",
    api_key="mk_test_abc123..."
)

# Create test customer
customer = client.create_customer(
    email="test+alice@example.com",
    name="Test Alice",
    metadata={"test": "true"}
)

# Create test subscription
subscription = client.create_subscription(
    stripe_customer_id=customer["stripe_customer_id"],
    tier="growth"
)

# Report test usage
usage = client.report_usage(
    stripe_customer_id=customer["stripe_customer_id"],
    meter_event_name="ai_labels",
    quantity=100,
    idempotency_key="test_batch_001",
    metadata={"test": "true"}
)

print(f"Test usage reported: ${usage['estimated_cost']}")
```

---

## Rate Limiting & Quotas

### Per-Tier Request Limits

| Tier | Requests/Min | Requests/Hour | Burst | Meter Events/Min |
|------|--------------|---------------|-------|------------------|
| **Starter** | 10 | 100 | 20 | 50 |
| **Growth** | 100 | 1,000 | 200 | 500 |
| **Professional** | 500 | 5,000 | 1,000 | 2,000 |
| **Enterprise** | Custom | Custom | Custom | Custom |

### Meter Event Rate Limits

Separate limits for meter event reporting (POST /usage/report):

- **Starter:** 50 events/min
- **Growth:** 500 events/min
- **Professional:** 2,000 events/min
- **Enterprise:** Custom

### Checking Remaining Quota

**From Response Headers:**
```python
response = requests.post(url, headers=headers, json=data)

rate_limit = {
    "limit": int(response.headers.get("X-RateLimit-Limit", 0)),
    "remaining": int(response.headers.get("X-RateLimit-Remaining", 0)),
    "reset_at": int(response.headers.get("X-RateLimit-Reset", 0))
}

print(f"Rate limit: {rate_limit['remaining']}/{rate_limit['limit']} remaining")

if rate_limit["remaining"] < 10:
    print(f"⚠ Warning: Low rate limit quota")
```

### Best Practices for Batch Reporting

**Batch Events Together:**
```python
# ❌ Bad: Reporting one at a time (100 API calls)
for event in events:
    client.report_usage(
        stripe_customer_id=customer_id,
        meter_event_name="ai_labels",
        quantity=1
    )

# ✅ Good: Batch events (1 API call)
total_quantity = len(events)
client.report_usage(
    stripe_customer_id=customer_id,
    meter_event_name="ai_labels",
    quantity=total_quantity,
    idempotency_key=f"batch_{batch_id}"
)
```

**Handle Rate Limits Gracefully:**
```python
import time

def report_usage_with_backoff(client, data, max_retries=3):
    """Report usage with exponential backoff on rate limits."""
    for attempt in range(max_retries):
        try:
            return client.report_usage(**data)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 60))
                print(f"⚠ Rate limited. Retrying after {retry_after}s...")
                time.sleep(retry_after)
                continue
            raise

    raise Exception("Max retries exceeded")
```

---

## Summary

This API specification provides complete documentation for integrating with the Metering Service. Key takeaways:

1. **Two Auth Methods:** JWT for management, API Key for meter reporting
2. **Idempotency is Critical:** Always use idempotency keys for meter events
3. **Tier-Based Pricing:** Costs decrease with higher tiers
4. **Webhook Verification Required:** HMAC-SHA256 signature verification prevents spoofing
5. **Retry Logic Built-In:** Exponential backoff on transient failures
6. **Rate Limits Enforced:** Batch events to stay within limits
7. **Test Mode Available:** Use sandbox environment for development

For architecture details, see [ARCHITECTURE.md](./ARCHITECTURE.md).
For end-to-end flows, see [E2E_FLOW.md](./E2E_FLOW.md).
