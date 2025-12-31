# Stripe Metered Billing Integration - Requirements Elicitation

**Project**: Data Foundry Backend
**Date**: 2024-12-24
**Version**: 1.0.0
**Author**: Requirements Analysis Team

---

## Executive Summary

This document outlines the requirements for integrating Stripe metered billing into Data Foundry's existing FastAPI backend. The integration enables usage-based billing for AI labeling and data processing services, tracking two primary usage metrics: `AI_LABELS` and `HUMAN_AUDITS`.

**Business Context**:
- Pricing Tiers: Gold ($0.08/label), Silver ($0.10/label), Bronze ($0.12/label)
- All tiers maintain >95% profit margins
- Usage tracked per-tenant with tenant isolation
- Existing PostgreSQL-based usage tracking needs Stripe synchronization

---

## 1. Business Requirements

### 1.1 Primary Objectives
| ID | Requirement | Priority |
|----|-------------|----------|
| BR-001 | Track AI labeling usage per tenant and report to Stripe | High |
| BR-002 | Track human review (audit) usage per tenant and report to Stripe | High |
| BR-003 | Map Data Foundry tenants to Stripe customers | High |
| BR-004 | Support tiered pricing based on usage volume | Medium |
| BR-005 | Generate accurate invoices based on actual usage | High |
| BR-006 | Handle billing failures and retry logic | Medium |

### 1.2 Billing Metrics

The system must track and report the following usage metrics to Stripe:

| Metric Name | Stripe Event Name | Unit | Description |
|-------------|------------------|------|-------------|
| `AI_LABELS` | `ai_labels` | count (integer) | Number of records processed by AI (auto-approved) |
| `HUMAN_AUDITS` | `human_audits` | count (integer) | Number of records sent for human review |

**Usage Calculation**:
- `AI_LABELS` = Count of records where `confidence >= CONFIDENCE_THRESHOLD` (0.85)
- `HUMAN_AUDITS` = Count of records where `confidence < CONFIDENCE_THRESHOLD` (0.85)

### 1.3 Pricing Structure

Based on margin analysis, the following pricing tiers apply:

| Tier | Price per Label | AI Ratio | Human Ratio | Monthly Platform Fee |
|------|-----------------|----------|-------------|----------------------|
| **Gold** | $0.08 | 95% | 3% | $99 |
| **Silver** | $0.10 | 90% | 8% | $49 |
| **Bronze** | $0.12 | 85% | 13% | $0 (all-inclusive) |

**Stripe Implementation**:
- Usage-based pricing for `AI_LABELS` and `HUMAN_AUDITS`
- Separate meter events for each metric
- Platform fee as fixed recurring subscription item

---

## 2. Functional Requirements

### 2.1 Stripe Customer Management

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-001 | **Create Stripe Customer** | When a new tenant is created, automatically create a corresponding Stripe customer |
| FR-002 | **Customer Metadata Mapping** | Store `tenant_id` in Stripe customer metadata for bidirectional lookup |
| FR-003 | **Customer Synchronization** | Sync tenant name, email, and billing email to Stripe customer |
| FR-004 | **Retrieve Stripe Customer** | Fetch Stripe customer ID from `tenant_id` via metadata query |
| FR-005 | **Update Customer** | Update Stripe customer when tenant information changes |

**API Endpoints Required**:
```python
POST   /api/v1/billing/customers          # Create Stripe customer for tenant
GET    /api/v1/billing/customers/{id}     # Get Stripe customer info
PUT    /api/v1/billing/customers/{id}     # Update Stripe customer
DELETE /api/v1/billing/customers/{id}     # Delete Stripe customer (cascade)
```

### 2.2 Meter Event Reporting

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-010 | **Report AI Labels** | Send meter event for each batch of AI-labeled records |
| FR-011 | **Report Human Audits** | Send meter event for each batch of human-reviewed records |
| FR-012 | **Batch Reporting** | Aggregate multiple usage events into single API call for efficiency |
| FR-013 | **Idempotent Events** | Use unique `idempotency_key` to prevent duplicate billing |
| FR-014 | **Error Handling** | Retry failed meter event reports with exponential backoff |
| FR-015 | **Event Timestamping** | Include timestamp in meter event payload for accurate billing periods |

**Meter Event Format**:
```python
# AI Labels Event
{
    "event_name": "ai_labels",
    "payload": {
        "stripe_customer_id": "cus_xxx",
        "value": "150",  # Number of AI labels
        "tenant_id": "tenant_abc",
        "timestamp": "2024-12-24T10:30:00Z",
        "batch_id": "batch_123"
    },
    "idempotency_key": "ai_labels_tenant_abc_batch_123"
}

# Human Audits Event
{
    "event_name": "human_audits",
    "payload": {
        "stripe_customer_id": "cus_xxx",
        "value": "25",  # Number of human audits
        "tenant_id": "tenant_abc",
        "timestamp": "2024-12-24T10:30:00Z",
        "batch_id": "batch_123"
    },
    "idempotency_key": "human_audits_tenant_abc_batch_123"
}
```

### 2.3 Subscription Management

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-020 | **Create Subscription** | Create Stripe subscription with metered billing for tenant |
| FR-021 | **Tier-Based Pricing** | Assign correct price IDs based on tenant tier (Gold/Silver/Bronze) |
| FR-022 | **Meter Configuration** | Configure meters for `ai_labels` and `human_audits` |
| FR-023 | **Update Subscription** | Handle tier upgrades/downgrades |
| FR-024 | **Cancel Subscription** | Gracefully cancel subscription when tenant is deleted |
| FR-025 | **Subscription Status Sync** | Track subscription status (active, past_due, canceled, etc.) |

**Subscription Configuration**:
```python
subscription_items = [
    {
        "price": "price_gold_ai_labels",      # Metered: $0.08 per unit
        "billing_scheme": "per_unit",
        "meter": "meter_ai_labels"
    },
    {
        "price": "price_gold_human_audits",   # Metered: included up to % or overage
        "billing_scheme": "per_unit",
        "meter": "meter_human_audits"
    },
    {
        "price": "price_gold_platform_fee",   # Recurring: $99/month
        "quantity": 1
    }
]
```

### 2.4 Usage Tracking Integration

| ID | Requirement | Description |
|----|-------------|-------------|
| FR-030 | **Post-Processing Hook** | Trigger meter event after data processing completes |
| FR-031 | **Batch Aggregation** | Aggregate usage within processing batches before reporting |
| FR-032 | **Async Reporting** | Report usage asynchronously to avoid blocking processing pipeline |
| FR-033 | **Usage Reconciliation** | Periodically reconcile internal usage tracking with Stripe records |
| FR-034 | **Audit Trail** | Log all meter event reports for audit purposes |

**Integration Points**:
- `src/tasks/ingestion.py` - After record classification
- `src/core/approval_workflow_engine.py` - After human review completion
- New `src/services/stripe_service.py` - Dedicated billing service

---

## 3. Non-Functional Requirements

### 3.1 Performance

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-101 | **Meter Event Latency** | Report usage within 5 seconds of processing completion |
| NFR-102 | **API Rate Limiting** | Handle Stripe rate limits (100 req/sec for meter stream) |
| NFR-103 | **Batch Size** | Support reporting up to 10,000 events per batch |
| NFR-104 | **Throughput** | Process 1,000 meter events per second |

### 3.2 Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-201 | **Delivery Guarantee** | At-least-once delivery with idempotency keys |
| NFR-202 | **Retry Policy** | Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 5 attempts) |
| NFR-203 | **Failure Recovery** | Queue failed events for offline retry |
| NFR-204 | **Data Consistency** | Ensure usage counts match between internal DB and Stripe |

### 3.3 Security

| ID | Requirement | Description |
|----|-------------|-------------|
| NFR-301 | **API Key Security** | Store Stripe API keys in SecretManager (never in code) |
| NFR-302 | **Webhook Verification** | Verify webhook signatures using Stripe secret |
| NFR-303 | **PCI Compliance** | Never store full payment methods (handle via Stripe only) |
| NFR-304 | **Audit Logging** | Log all billing operations without sensitive data |
| NFR-305 | **Tenant Isolation** | Ensure meter events cannot cross tenant boundaries |

### 3.4 Scalability

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-401 | **Multi-Tenant Support** | Support 10,000+ concurrent tenants |
| NFR-402 | **Event Volume** | Handle 1M+ meter events per day |
| NFR-403 | **Horizontal Scaling** | Support multiple FastAPI instances reporting usage |

---

## 4. Technical Architecture

### 4.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Foundry Backend                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐     │
│  │   Ingestion  │─────▶│    Quality   │─────▶│  ML Predictor │     │
│  │    Service   │      │    Service   │      │    Service    │     │
│  └──────────────┘      └──────────────┘      └──────────────┘     │
│         │                     │                      │              │
│         ▼                     ▼                      ▼              │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              Usage Tracking Service (NEW)               │      │
│  │  - Aggregate AI labels vs human audits                  │      │
│  │  - Calculate batch usage                                │      │
│  │  - Queue meter events                                   │      │
│  └──────────────────────────────────────────────────────────┘      │
│                             │                                    │
│                             ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │            Stripe Billing Service (NEW)                 │      │
│  │  - Customer management (CRUD)                            │      │
│  │  - Meter event reporting (v2 API)                        │      │
│  │  - Subscription management                               │      │
│  │  - Webhook handling                                      │      │
│  └──────────────────────────────────────────────────────────┘      │
│                             │                                    │
│                             ▼                                    │
│                      ┌──────────┐                                │
│                      │  Stripe  │                                │
│                      │   API    │                                │
│                      └──────────┘                                │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.2 Data Model Extensions

**New Table: `stripe_customers`**
```sql
CREATE TABLE stripe_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_customer_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Lookup optimization
    CONSTRAINT fk_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);
CREATE INDEX idx_stripe_customers_tenant ON stripe_customers(tenant_id);
```

**New Table: `stripe_subscriptions`**
```sql
CREATE TABLE stripe_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255) UNIQUE NOT NULL,
    stripe_customer_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- active, past_due, canceled, etc.
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_stripe_subscriptions_tenant ON stripe_subscriptions(tenant_id);
```

**New Table: `stripe_meter_events`** (Audit trail)
```sql
CREATE TABLE stripe_meter_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    event_name VARCHAR(100) NOT NULL,  -- ai_labels, human_audits
    quantity INTEGER NOT NULL,
    batch_id VARCHAR(255),
    idempotency_key VARCHAR(255) UNIQUE NOT NULL,
    stripe_response JSONB,  -- Store API response
    status VARCHAR(50) NOT NULL,  -- pending, success, failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    retried_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0
);
CREATE INDEX idx_stripe_meter_events_tenant ON stripe_meter_events(tenant_id);
CREATE INDEX idx_stripe_meter_events_status ON stripe_meter_events(status);
```

### 4.3 Service Architecture

**New File: `src/services/stripe_service.py`**

```python
"""
Stripe Billing Service for Data Foundry

Handles all Stripe API interactions including:
- Customer management
- Subscription management
- Meter event reporting
- Webhook handling

Uses Stripe Python SDK v10+ with v2 billing APIs.
"""

import stripe
from stripe import StripeClient
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timezone

from src.core.secret_manager import SecretManager
from src.models.tenant import Tenant
from src.database.session import get_db


class StripeService:
    """Service for Stripe billing operations."""

    # Meter event names (must match Stripe meter configuration)
    METER_AI_LABELS = "ai_labels"
    METER_HUMAN_AUDITS = "human_audits"

    def __init__(self):
        self._client: Optional[StripeClient] = None
        self._api_key: Optional[str] = None

    async def initialize(self):
        """Initialize Stripe client with API key from SecretManager."""
        self._api_key = await SecretManager.get_secret("STRIPE_API_KEY")
        if not self._api_key:
            raise ValueError("STRIPE_API_KEY not configured")

        stripe.api_key = self._api_key
        self._client = StripeClient(self._api_key)

    # Customer Management
    async def create_customer(
        self,
        tenant: Tenant,
        email: str,
        name: Optional[str] = None
    ) -> str:
        """Create Stripe customer for tenant."""
        pass

    async def get_customer_by_tenant(self, tenant_id: str) -> Optional[Dict]:
        """Retrieve Stripe customer by tenant_id from metadata."""
        pass

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Update Stripe customer."""
        pass

    # Subscription Management
    async def create_subscription(
        self,
        stripe_customer_id: str,
        tier: str,  # gold, silver, bronze
        trial_days: Optional[int] = None
    ) -> Dict:
        """Create subscription with metered billing."""
        pass

    async def update_subscription_tier(
        self,
        stripe_subscription_id: str,
        new_tier: str
    ) -> Dict:
        """Update subscription to different pricing tier."""
        pass

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
        at_period_end: bool = True
    ) -> Dict:
        """Cancel subscription."""
        pass

    # Meter Event Reporting
    async def report_usage(
        self,
        tenant_id: str,
        event_name: str,
        quantity: int,
        batch_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """
        Report metered usage to Stripe.

        Args:
            tenant_id: Internal tenant ID
            event_name: METER_AI_LABELS or METER_HUMAN_AUDITS
            quantity: Number of units consumed
            batch_id: Optional batch identifier for idempotency
            timestamp: When the usage occurred (defaults to now)

        Returns:
            True if successfully reported
        """
        pass

    async def report_usage_batch(
        self,
        usage_records: List[Dict]
    ) -> Dict[str, bool]:
        """
        Report multiple usage events in batch.

        Args:
            usage_records: List of dicts with tenant_id, event_name, quantity, etc.

        Returns:
            Dict mapping idempotency_key to success status
        """
        pass

    # Webhook Handling
    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
        webhook_secret: str
    ) -> Dict:
        """
        Handle Stripe webhook events.

        Processes events like:
        - invoice.payment_succeeded
        - invoice.payment_failed
        - customer.subscription.updated
        - customer.subscription.deleted
        """
        pass
```

---

## 5. API Specifications

### 5.1 Billing Management Endpoints

#### POST /api/v1/billing/customers
Create Stripe customer for tenant

**Request Body**:
```json
{
  "tenant_id": "uuid",
  "email": "billing@example.com",
  "name": "Acme Corp"
}
```

**Response**: 201 Created
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "stripe_customer_id": "cus_xxx",
  "email": "billing@example.com",
  "name": "Acme Corp",
  "created_at": "2024-12-24T10:00:00Z"
}
```

#### GET /api/v1/billing/customers/{tenant_id}
Get Stripe customer information

**Response**: 200 OK
```json
{
  "tenant_id": "uuid",
  "stripe_customer_id": "cus_xxx",
  "email": "billing@example.com",
  "name": "Acme Corp",
  "subscriptions": [
    {
      "stripe_subscription_id": "sub_xxx",
      "status": "active",
      "tier": "gold",
      "current_period_start": "2024-12-01T00:00:00Z",
      "current_period_end": "2025-01-01T00:00:00Z"
    }
  ],
  "created_at": "2024-12-24T10:00:00Z"
}
```

#### POST /api/v1/billing/subscriptions
Create subscription for tenant

**Request Body**:
```json
{
  "tenant_id": "uuid",
  "tier": "gold",
  "trial_days": 14
}
```

**Response**: 201 Created
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "stripe_subscription_id": "sub_xxx",
  "stripe_customer_id": "cus_xxx",
  "status": "trialing",
  "tier": "gold",
  "current_period_start": "2024-12-24T10:00:00Z",
  "current_period_end": "2025-01-07T10:00:00Z",
  "created_at": "2024-12-24T10:00:00Z"
}
```

#### PUT /api/v1/billing/subscriptions/{subscription_id}
Update subscription (tier change)

**Request Body**:
```json
{
  "tier": "silver"
}
```

**Response**: 200 OK
```json
{
  "id": "uuid",
  "stripe_subscription_id": "sub_xxx",
  "status": "active",
  "tier": "silver",
  "schedule": [
    {
      "phase": "current",
      "end_date": "2024-12-31T23:59:59Z"
    },
    {
      "phase": "new",
      "start_date": "2025-01-01T00:00:00Z",
      "tier": "silver"
    }
  ]
}
```

#### POST /api/v1/billing/webhook
Handle Stripe webhooks

**Headers**:
- `Stripe-Signature`: Webhook signature

**Request Body**: Raw Stripe event payload

**Response**: 200 OK

#### GET /api/v1/billing/usage/{tenant_id}
Get usage summary for billing period

**Query Parameters**:
- `period_start`: ISO 8601 timestamp
- `period_end`: ISO 8601 timestamp

**Response**: 200 OK
```json
{
  "tenant_id": "uuid",
  "period_start": "2024-12-01T00:00:00Z",
  "period_end": "2024-12-31T23:59:59Z",
  "usage": {
    "ai_labels": 15000,
    "human_audits": 450,
    "total_labels": 15450
  },
  "estimated_cost": {
    "ai_labels_cost": 1200.00,
    "human_audits_cost": 18.00,
    "platform_fee": 99.00,
    "total": 1317.00
  },
  "stripe_sync_status": {
    "last_sync": "2024-12-24T10:30:00Z",
    "pending_events": 0,
    "failed_events": 0
  }
}
```

---

## 6. Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `STRIPE_API_KEY` | Stripe secret API key | Yes | `sk_test_...` or `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret | Yes | `whsec_...` |
| `STRIPE_PUBLISHABLE_KEY` | Publishable key for frontend | Yes | `pk_test_...` |
| `STRIPE_GOLD_AI_LABELS_PRICE_ID` | Price ID for Gold AI labels | Yes | `price_...` |
| `STRIPE_GOLD_HUMAN_AUDITS_PRICE_ID` | Price ID for Gold human audits | Yes | `price_...` |
| `STRIPE_GOLD_PLATFORM_FEE_PRICE_ID` | Price ID for Gold platform fee | Yes | `price_...` |
| `STRIPE_SILVER_AI_LABELS_PRICE_ID` | Price ID for Silver AI labels | Yes | `price_...` |
| `STRIPE_SILVER_HUMAN_AUDITS_PRICE_ID` | Price ID for Silver human audits | Yes | `price_...` |
| `STRIPE_SILVER_PLATFORM_FEE_PRICE_ID` | Price ID for Silver platform fee | Yes | `price_...` |
| `STRIPE_BRONZE_AI_LABELS_PRICE_ID` | Price ID for Bronze AI labels | Yes | `price_...` |
| `STRIPE_BRONZE_HUMAN_AUDITS_PRICE_ID` | Price ID for Bronze human audits | Yes | `price_...` |
| `STRIPE_METER_EVENT_RETRY_ATTEMPTS` | Max retry attempts for meter events | No | `5` |
| `STRIPE_METER_EVENT_BATCH_SIZE` | Batch size for meter events | No | `100` |

---

## 7. Dependencies

### 7.1 Python Packages

```toml
[tool.poetry.dependencies]
stripe = "^10.0.0"  # Stripe Python SDK with v2 billing support
```

### 7.2 Stripe Configuration Requirements

**Meters to Create in Stripe Dashboard**:

1. **AI Labels Meter**
   - Display Name: "AI Labels"
   - Event Name: `ai_labels`
   - Value Type: `integer`
   - Aggregation: `sum`
   - Time Grain: `daily`

2. **Human Audits Meter**
   - Display Name: "Human Audits"
   - Event Name: `human_audits`
   - Value Type: `integer`
   - Aggregation: `sum`
   - Time Grain: `daily`

**Prices to Create**:

For each tier (Gold, Silver, Bronze), create:

| Price Type | Meter | Billing Scheme | Unit Amount |
|------------|-------|---------------|-------------|
| Metered | AI Labels | Per unit | $0.08 / $0.10 / $0.12 |
| Metered | Human Audits | Per unit | $0.04 / $0.04 / $0.04 (same) |
| Recurring | Platform Fee | - | $99 / $49 / $0 |

---

## 8. Implementation Phases

### Phase 1: Foundation (Week 1)
| ID | Task | Deliverable |
|----|------|-------------|
| P1-001 | Create database tables | Migration script |
| P1-002 | Implement StripeService base | Customer CRUD operations |
| P1-003 | Environment setup | Configured .env variables |
| P1-004 | SecretManager integration | Encrypted API keys |
| P1-005 | Unit tests for customer management | Test suite |

### Phase 2: Meter Reporting (Week 1-2)
| ID | Task | Deliverable |
|----|------|-------------|
| P2-001 | Implement meter event reporting | StripeService.report_usage() |
| P2-002 | Batch reporting support | StripeService.report_usage_batch() |
| P2-003 | Retry logic with exponential backoff | Retry mechanism |
| P2-004 | Idempotency key generation | Unique key strategy |
| P2-005 | Integration with ingestion pipeline | Usage tracking hooks |
| P2-006 | Unit tests for meter reporting | Test suite |

### Phase 3: Subscriptions (Week 2)
| ID | Task | Deliverable |
|----|------|-------------|
| P3-001 | Subscription creation | StripeService.create_subscription() |
| P3-002 | Tier management | Update/cancel subscriptions |
| P3-003 | Price ID configuration | Tier-based pricing |
| P3-004 | Subscription sync service | Background sync job |
| P3-005 | Unit tests for subscriptions | Test suite |

### Phase 4: Webhooks & API (Week 2-3)
| ID | Task | Deliverable |
|----|------|-------------|
| P4-001 | Webhook endpoint | /api/v1/billing/webhook |
| P4-002 | Signature verification | Security implementation |
| P4-003 | Event handlers | invoice.*, subscription.* |
| P4-004 | Billing API endpoints | Customer/subscription CRUD |
| P4-005 | Usage summary endpoint | GET /billing/usage/{tenant_id} |
| P4-006 | Integration tests | End-to-end tests |

### Phase 5: Testing & Documentation (Week 3)
| ID | Task | Deliverable |
|----|------|-------------|
| P5-001 | Load testing | Meter event throughput |
| P5-002 | Failure scenario testing | Retry logic validation |
| P5-003 | Security audit | Penetration testing |
| P5-004 | API documentation | OpenAPI specs |
| P5-005 | Developer guide | Setup instructions |
| P5-006 | QA sign-off | Validation report |

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/unit/services/test_stripe_service.py

class TestStripeService:
    """Unit tests for Stripe billing service."""

    @pytest.fixture
    async def stripe_service(self):
        service = StripeService()
        await service.initialize()
        return service

    @pytest.mark.asyncio
    async def test_create_customer(self, stripe_service):
        """Test Stripe customer creation."""
        pass

    @pytest.mark.asyncio
    async def test_report_ai_labels_usage(self, stripe_service):
        """Test AI labels meter event reporting."""
        pass

    @pytest.mark.asyncio
    async def test_report_human_audits_usage(self, stripe_service):
        """Test human audits meter event reporting."""
        pass

    @pytest.mark.asyncio
    async def test_idempotent_meter_events(self, stripe_service):
        """Test that duplicate events with same idempotency key are rejected."""
        pass

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, stripe_service):
        """Test retry logic with exponential backoff."""
        pass
```

### 9.2 Integration Tests

```python
# tests/integration/test_stripe_billing_e2e.py

class TestStripeBillingE2E:
    """End-to-end tests for Stripe billing integration."""

    @pytest.mark.e2e
    async def test_full_billing_cycle(self):
        """
        Test complete billing cycle:
        1. Create tenant and Stripe customer
        2. Create subscription
        3. Process data (mix of AI and human review)
        4. Report usage
        5. Verify usage recorded in Stripe
        """
        pass

    @pytest.mark.e2e
    async def test_webhook_invoice_payment(self):
        """Test invoice payment webhook handling."""
        pass

    @pytest.mark.e2e
    async def test_tier_upgrade(self):
        """Test subscription tier upgrade flow."""
        pass
```

### 9.3 Validation Tests

Based on backend validation prompt:

```python
# tests/validation/test_stripe_billing.py

async def test_stripe_metered_billing():
    """
    Verify Stripe meter tracking works end-to-end.

    Success Criteria:
    - Usage tracked correctly (AI_LABELS vs HUMAN_AUDITS)
    - Stripe meter API receives correct values
    - Billing calculation matches actual usage
    """

    # Process dataset with known AI/human split
    test_data = generate_test_dataset(
        total_records=1000,
        ai_ratio=0.95,
        human_ratio=0.03,
        reject_ratio=0.02
    )

    # Process through pipeline
    result = await client.post(
        "/api/v1/data/process",
        json={"records": test_data},
        headers={"Authorization": f"Bearer {token}"}
    )

    # Verify usage tracking
    usage_response = await client.get(
        f"/api/v1/billing/usage/{tenant_id}"
    )

    assert usage_response.status_code == 200
    usage = usage_response.json()

    # Verify AI labels count
    assert usage["usage"]["ai_labels"] == 950

    # Verify human audits count
    assert usage["usage"]["human_audits"] == 30

    # Verify Stripe sync
    stripe_usage = await get_stripe_meter_usage(
        stripe_customer_id,
        period_start,
        period_end
    )

    assert stripe_usage["ai_labels"] == 950
    assert stripe_usage["human_audits"] == 30

    print(f"✅ Stripe billing verified:")
    print(f"   AI Labels: {usage['usage']['ai_labels']}")
    print(f"   Human Audits: {usage['usage']['human_audits']}")
    print(f"   Total Cost: ${usage['estimated_cost']['total']:.2f}")
```

---

## 10. Open Questions / Decisions Needed

### 10.1 Resolved Decisions

| ID | Question | Decision | Rationale |
|----|----------|----------|-----------|
| OQ-001 | Should meter events be reported in real-time or batched? | **Batched** | More efficient API usage, reduces rate limit pressure, aligns with existing batch processing workflow |
| OQ-002 | How to handle usage reporting when Stripe API is down? | **Offline retry queue** | Failed events queued with exponential backoff retry (1s, 2s, 4s, 8s, 16s), max 5 attempts before manual intervention |
| OQ-003 | Should we use Stripe's meter event stream v2 or legacy usage records? | **Meter event stream v2** | Modern Stripe billing API, better meter support, future-proof, legacy usage records deprecated |
| OQ-004 | How to handle existing tenants without Stripe customers? | **N/A** | No existing tenants - greenfield deployment |
| OQ-005 | Should platform fee be separate invoice or combined line item? | **Combined line item** | Single invoice with platform fee + metered usage items, simpler customer experience |
| OQ-006 | Do we need to support multiple payment methods per customer? | **Yes** | Support multiple cards with primary + backup fallback if primary payment fails |
| OQ-007 | Should invoices be paid automatically (charge_automatically) or send_invoice? | **Charge Automatically** | Faster payment collection, better cash flow, standard for SaaS billing |
| OQ-008 | How to handle proration when changing tiers mid-cycle? | **Prorate now** | Charge difference immediately, update billing for rest of cycle, transparent to customer |

### 10.2 Pending Decisions

All open questions have been resolved. ✅

---

## 11. Success Criteria

The integration is considered complete when:

1. **Functional Completeness**
   - [ ] All tenants can be mapped to Stripe customers
   - [ ] AI labels usage is accurately tracked and reported
   - [ ] Human audits usage is accurately tracked and reported
   - [ ] Subscriptions can be created, updated, and canceled
   - [ ] Webhooks are properly handled and verified

2. **Performance Targets**
   - [ ] Meter events reported within 5 seconds of processing
   - [ ] 1000+ events per second throughput
   - [ ] 99.9% API call success rate (after retries)

3. **Data Integrity**
   - [ ] Usage counts match between internal DB and Stripe (reconciliation)
   - [ ] No duplicate meter events (idempotency)
   - [ ] No orphaned customers (cleanup on tenant delete)

4. **Security & Compliance**
   - [ ] API keys encrypted in SecretManager
   - [ ] Webhook signatures verified
   - [ ] Audit trail maintained for all billing operations
   - [ ] PCI compliance (no card data stored)

5. **Testing**
   - [ ] Unit test coverage >90% for billing code
   - [ ] Integration tests pass for all billing flows
   - [ ] Load tests handle expected volume
   - [ ] Security audit passes

---

## 12. Appendices

### Appendix A: Stripe Meter Event Flow Diagram

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Ingestion  │    │    Quality  │    │   Predict   │
│   Service    │───▶│    Service  │───▶│    Service   │
└─────────────┘    └─────────────┘    └─────────────┘
                                              │
                    ┌─────────────────────────┴───────────────────────┐
                    │                                                 │
                    ▼                                                 │
              ┌──────────────┐                                        │
              │ Classification│                                        │
              │  High/Low    │                                        │
              │  Confidence   │                                        │
              └──────────────┘                                        │
                    │                                                 │
        ┌───────────┴──────────┐                                      │
        │                      │                                      │
        ▼                      ▼                                      │
   ┌─────────┐           ┌─────────┐                                  │
   │   AI    │           │ Human   │                                  │
   │Approved │           │ Review  │                                  │
   └────┬────┘           └────┬────┘                                  │
        │                     │                                       │
        │                     │                                       │
        ▼                     ▼                                       │
   ┌────────────────────────────────────────┐                           │
   │     Record Usage (Internal DB)        │                           │
   │  - tenant_id, event_type, quantity   │                           │
   │  - batch_id, timestamp               │                           │
   └─────────────────┬──────────────────────┘                           │
                     │                                                  │
                     ▼                                                  │
          ┌──────────────────┐                                          │
          │ Usage Aggregation │                                          │
          │ (Async Worker)   │                                          │
          └─────────┬─────────┘                                          │
                    │                                                  │
                    ▼                                                  │
          ┌─────────────────────┐                                       │
          │  Stripe Service     │                                       │
          │  report_usage()     │                                       │
          └─────────┬───────────┘                                       │
                    │                                                  │
                    ▼                                                  │
    ┌──────────────────────────────────────────────┐                    │
    │      Meter Event to Stripe API (v2)          │                    │
    │  POST /v2/billing/meter_event_stream         │                    │
    │  {                                           │                    │
    │    "event_name": "ai_labels",                │                    │
    │    "payload": {                              │                    │
    │      "stripe_customer_id": "cus_xxx",        │                    │
    │      "value": "150"                          │                    │
    │    },                                         │                    │
    │    "idempotency_key": "unique_key"            │                    │
    │  }                                           │                    │
    └───────────────────────────────────────────────┘                    │
                                                                       │
                                                                       │
┌──────────────────────────────────────────────────────────────────────┐
│                          STRIPE PLATFORM                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │   Meters     │  │   Prices     │  │Subscriptions │               │
│  │              │  │              │  │              │               │
│  │ ai_labels    │  │ Gold: $0.08  │  │ Customer A   │               │
│  │ human_audits │  │ Silver: $0.10│  │ Customer B   │               │
│  │              │  │ Bronze: $0.12│  │ Customer C   │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│         │                  │                  │                        │
│         └──────────────────┴──────────────────┘                        │
│                            │                                           │
│                     ▼───────┴───────▼                                  │
│              ┌─────────────────────┐                                 │
│              │   Invoice Generation│                                 │
│              │   (Daily/Monthly)   │                                 │
│              └─────────┬───────────┘                                 │
│                        │                                             │
│                 ┌──────┴──────┐                                       │
│                 ▼             ▼                                       │
│          ┌─────────┐    ┌─────────┐                                   │
│          │  Email  │    │Payment  │                                   │
│          │ Invoice │    │Collect  │                                   │
│          └────┬────┘    └────┬────┘                                   │
│               │              │                                       │
│               ▼              ▼                                       │
│      ┌─────────────────────────┐                                      │
│      │   Webhook Events        │                                      │
│      │   invoice.*             │───────────┐                          │
│      │   subscription.*        │           │                          │
│      └─────────────────────────┘           │                          │
└────────────────────────────────────────────┼──────────────────────────┘
                                               │
                                               ▼
                                ┌─────────────────────────────────┐
                                │   Data Foundry Backend          │
                                │   /api/v1/billing/webhook       │
                                │                                 │
                                │  Handle Events:                 │
                                │  - payment_succeeded            │
                                │  - payment_failed               │
                                │  - subscription.updated         │
                                │  - subscription.deleted         │
                                └─────────────────────────────────┘
```

### Appendix B: Example Meter Event Payloads

**AI Labels Event (Batch)**
```json
{
  "events": [
    {
      "event_name": "ai_labels",
      "payload": {
        "stripe_customer_id": "cus_NffrFeUfNV2Hib",
        "value": "500",
        "tenant_id": "tenant_abc123",
        "batch_id": "batch_20241224_001",
        "timestamp": "2024-12-24T10:30:00Z",
        "model_version": "gpt-4o-mini-v1"
      },
      "idempotency_key": "ai_labels_tenant_abc123_batch_20241224_001"
    }
  ]
}
```

**Human Audits Event (Single)**
```json
{
  "events": [
    {
      "event_name": "human_audits",
      "payload": {
        "stripe_customer_id": "cus_NffrFeUfNV2Hib",
        "value": "1",
        "tenant_id": "tenant_abc123",
        "record_id": "rec_xyz789",
        "timestamp": "2024-12-24T10:31:00Z",
        "reviewer_id": "reviewer_123"
      },
      "idempotency_key": "human_audit_tenant_abc123_rec_xyz789"
    }
  ]
}
```

### Appendix C: Error Handling Matrix

| Error Type | Retry Strategy | Max Retries | Fallback Action |
|------------|----------------|-------------|-----------------|
| Network timeout | Exponential backoff | 5 | Queue for offline retry |
| Rate limit (429) | Exponential backoff (respect Retry-After) | Unlimited | Queue with delay |
| Invalid customer | No retry | 0 | Alert ops team |
| Invalid meter | No retry | 0 | Alert ops team |
| Authentication fail | No retry | 0 | Alert ops team (key rotation) |
| Server error (5xx) | Exponential backoff | 5 | Queue for offline retry |

---

## Document Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2024-12-24 | Requirements Team | Initial requirements elicitation |

---

**Next Steps**:
1. Review and approve requirements
2. Answer open questions (OQ-001 through OQ-008)
3. Create Stripe test account and configure meters/prices
4. Begin Phase 1 implementation
