# Metering Service - Infrastructure & Deployment Guide

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Technology Stack](#technology-stack)
3. [Deployment Options](#deployment-options)
4. [Local Development Setup](#local-development-setup)
5. [Production Deployment](#production-deployment)
6. [Stripe Configuration](#stripe-configuration)
7. [Environment Configuration](#environment-configuration)
8. [Database Setup](#database-setup)
9. [Docker Configuration](#docker-configuration)
10. [Webhook Management](#webhook-management)
11. [Monitoring & Observability](#monitoring--observability)
12. [Security Best Practices](#security-best-practices)
13. [Scaling & Performance](#scaling--performance)
14. [Troubleshooting](#troubleshooting)

---

## System Architecture

### High-Level Components

```
┌────────────────────────────────────────────────────────────┐
│                  Customer Applications                     │
│          (SaaS Tenants, API Consumers)                     │
└────────────┬─────────────────────────────────────────────┬─┘
             │                                             │
             │         Meter Event Reporting              │ Subscription
             │         (Usage Tracking)                   │ Management
             ▼                                             ▼
┌────────────────────────────────────────────────────────────┐
│              Nginx Reverse Proxy                           │
│         (SSL/TLS, Load Balancing, Rate Limiting)          │
└────────────┬─────────────────────────────────────────────┬─┘
             │                                             │
       ┌─────┴──────┐                               ┌──────┴──────┐
       ▼             ▼                               ▼              ▼
  ┌─────────┐  ┌──────────┐                   ┌──────────┐   ┌──────────┐
  │ FastAPI │  │ FastAPI  │                   │ Stripe   │   │ Webhook  │
  │Instance1│..│InstanceN │                   │ Service  │   │ Handler  │
  │Port8000 │  │Port8000  │                   │Facade    │   │(Async)   │
  └────┬────┘  └────┬─────┘                   └──────┬───┘   └────┬─────┘
       │             │                                │             │
       └─────┬───────┘                                │             │
             │                                       │             │
    ┌────────┴────────┐                             │             │
    ▼                 ▼                             │             │
┌──────────────┐ ┌──────────────────────────────────┼─────────────┘
│ PostgreSQL15 │ │  Stripe API (v2 Billing)         │
│ Multi-Tenant │ │ - Meters                         │
│ Data Storage │ │ - Prices                         │
│ Port: 5432   │ │ - Subscriptions                  │
└──────────────┘ │ - Webhooks                        │
       │         │ - Invoice Management              │
       │         │ - Customer Management             │
       └─────────┴──────────────────────────────────┘
             │
    ┌────────┴─────────┐
    ▼                  ▼
┌────────┐        ┌──────────┐
│ Redis  │        │ Analytics│
│Caching │        │ Views    │
│Port6379│        │(Optional)│
└────────┘        └──────────┘
```

### Service Components

1. **API Gateway Layer**: Nginx + FastAPI middleware
2. **Customer Management**: CRUD operations for Stripe customers
3. **Subscription Management**: Subscription lifecycle (create, upgrade, downgrade, cancel)
4. **Meter Event Service**: Usage event reporting with idempotency
5. **Cost Calculation Engine**: Real-time cost computation
6. **Idempotency Service**: Prevents duplicate charges (24-hour TTL)
7. **Webhook Handler**: Processes Stripe events asynchronously
8. **Billing Synchronization**: Syncs Stripe data to local database
9. **Database Layer**: PostgreSQL with RLS for multi-tenancy
10. **Rate Limiting**: Per-tenant, per-tier request limits

---

## Technology Stack

### Core Framework
- **Web Server**: FastAPI 0.104.0+ with Uvicorn 0.24.0+
- **Python Version**: 3.12
- **Package Manager**: UV (Rust-based)
- **Async Runtime**: asyncio

### Database
- **Primary Database**: PostgreSQL 15 (Alpine variant)
- **ORM**: SQLModel 0.0.27 + SQLAlchemy 2.0.45
- **Async Driver**: asyncpg 0.31.0
- **Sync Driver**: psycopg2-binary 2.9.8
- **Migrations**: Alembic 1.17.2 (with custom async runner)

### Billing Integration
- **Stripe SDK**: stripe>=10.0.0 (v2 Billing API support)
- **Idempotency**: Custom implementation with 24-hour TTL
- **Webhook Verification**: HMAC-SHA256 signature verification
- **Retry Logic**: Exponential backoff with jitter

### Caching & Queuing
- **Cache**: Redis 7-alpine
- **Task Queue**: Celery 5.3.0 (optional for async jobs)
- **Message Broker**: Redis/RabbitMQ

### Data Processing
- **Data Aggregation**: pandas 2.1.0
- **Data Validation**: Pydantic 2.12.0
- **Time Series**: Python datetime libraries

### Monitoring & Observability
- **Structured Logging**: structlog 25.5.0
- **Metrics**: Prometheus (optional)
- **Dashboards**: Grafana (optional)
- **Health Checks**: Built-in health endpoints

### Security
- **Authentication**: python-jose 3.3.0 + JWT
- **Password Hashing**: passlib 1.7.4
- **Encryption**: cryptography 44.0.3
- **Secrets Management**: python-dotenv + SecretManager

---

## Deployment Options

### Option 1: Docker Compose (Development)
**Best For**: Local development, testing, Stripe sandbox
- Single command setup: `docker-compose up -d`
- Auto-reload on code changes
- Sandbox Stripe keys
- Test data seeding

**Time to Deploy**: 5 minutes

### Option 2: Docker Compose (Production)
**Best For**: Small-to-medium teams, single VPS
- Production-optimized containers
- Resource limits and reservations
- Health checks on all services
- Persistent volumes for data
- Nginx reverse proxy with SSL/TLS
- Stripe live keys

**Time to Deploy**: 45 minutes (with Stripe setup)

### Option 3: Kubernetes (Enterprise)
**Best For**: Large-scale deployments, multi-region
- Horizontal pod autoscaling
- Load balancing
- Blue-green deployments
- Advanced networking

**Time to Deploy**: 2-4 hours

### Option 4: Platform as a Service (Simplest)
**Best For**: Indie hackers, fastest time to market
- Railway, Render, Fly.io, Vercel
- Managed database
- Auto-scaling
- Built-in CI/CD

**Time to Deploy**: 15 minutes with git push

---

## Local Development Setup

### Prerequisites

- **Docker & Docker Compose** (or native Python 3.12)
- **Stripe Account** (free tier available)
- **Git**
- **8GB RAM minimum**
- **5GB free disk space**

### Step 1: Create Stripe Sandbox Account

1. Go to https://dashboard.stripe.com/register
2. Create free account
3. Switch to **Test Mode** (toggle in top right)
4. Save your API keys:
   - Publishable Key (pk_test_...)
   - Secret Key (sk_test_...)

### Step 2: Create Stripe Billing Meters (Test Mode)

Navigate to **Billing > Meters** in Stripe Dashboard:

```bash
# Create first meter for AI labels
Name: ai_labels
Event Name: ai_labels

# Create second meter for human audits
Name: human_audits
Event Name: human_audits
```

Save the Meter IDs (mtr_test_...).

### Step 3: Create Price Objects (Test Mode)

Navigate to **Billing > Prices**:

**Gold Tier Prices** (for each meter + monthly fee):
1. AI Labels: $0.08 per 1 (metered)
2. Human Audits: $0.04 per 1 (metered)
3. Monthly Fee: $99 (recurring monthly)

**Silver Tier Prices**:
1. AI Labels: $0.10 per 1 (metered)
2. Human Audits: $0.04 per 1 (metered)
3. Monthly Fee: $49 (recurring monthly)

**Bronze Tier Prices**:
1. AI Labels: $0.12 per 1 (metered)
2. Human Audits: $0.04 per 1 (metered)
3. Monthly Fee: $0 (no fee)

Save all 9 price IDs (price_1Si...).

### Step 4: Setup Webhook Endpoint (Test Mode)

1. Navigate to **Developers > Webhooks**
2. Click **+ Add Endpoint**
3. URL: `http://localhost:8000/api/v1/billing/webhook`
4. Events:
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
5. Click **Add Endpoint**
6. View **Signing Secret** (whsec_test_...)

### Step 5: Clone Repository & Setup

```bash
# Clone
git clone https://github.com/yourusername/data-foundry.git
cd data-foundry/data-foundry

# Copy environment
cp .env.example .env
```

### Step 6: Configure .env for Development

```env
# Core Settings
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=development-secret-key-min-32-chars

# Database
DATABASE_URL=postgresql://foundry_user:foundry_password@db:5432/data_foundry
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis
REDIS_URL=redis://redis:6379/0

# Stripe (from Test Mode)
STRIPE_SECRET_KEY=sk_test_your_secret_key_here
STRIPE_PUBLISHABLE_KEY=pk_test_your_publishable_key
STRIPE_WEBHOOK_SECRET=whsec_test_your_webhook_secret

# Stripe Meters (from Stripe Dashboard)
STRIPE_AI_LABELS_METER_ID=mtr_test_ai_labels_id_here
STRIPE_HUMAN_AUDITS_METER_ID=mtr_test_human_audits_id_here

# Stripe Price IDs (from Stripe Dashboard - 9 total)
# Gold Tier
STRIPE_GOLD_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_GOLD_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_GOLD_PLATFORM_FEE_PRICE_ID=price_1Si...

# Silver Tier
STRIPE_SILVER_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_SILVER_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_SILVER_PLATFORM_FEE_PRICE_ID=price_1Si...

# Bronze Tier
STRIPE_BRONZE_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_BRONZE_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_BRONZE_PLATFORM_FEE_PRICE_ID=price_1Si...

# Stripe Configuration
STRIPE_MAX_RETRIES=5
STRIPE_INITIAL_RETRY_DELAY_MS=1000
STRIPE_MAX_RETRY_DELAY_MS=32000
STRIPE_METER_EVENT_BATCH_SIZE=100
STRIPE_SYNC_INTERVAL_MINUTES=60
```

### Step 7: Start Services

```bash
# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f app

# Initialize database
docker-compose exec app python -m src.database.migrations.run_migrations upgrade

# Verify Stripe connection
curl http://localhost:8000/api/v1/billing/health
```

### Step 8: Test Stripe Integration

```bash
# Create test customer
curl -X POST http://localhost:8000/api/v1/billing/customers \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant-1",
    "email": "customer@example.com",
    "name": "Test Customer"
  }'

# Subscribe to Gold tier
curl -X POST http://localhost:8000/api/v1/billing/subscriptions \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant-1",
    "subscription_tier": "GOLD"
  }'

# Report meter event
curl -X POST http://localhost:8000/api/v1/billing/usage/report \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant-1",
    "meter_event": "ai_labels",
    "value": 100
  }'
```

### Step 9: Access Application

- **API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/billing/health
- **Stripe Dashboard**: https://dashboard.stripe.com (Test Mode)

---

## Production Deployment

### Prerequisites

- **Server**: VPS with 2GB+ RAM, 2+ CPUs
- **Domain Name**: With DNS configured
- **SSL Certificate**: Let's Encrypt (free) or commercial
- **Stripe Account**: Production tier with live keys
- **Payment Method**: On file for Stripe
- **Monitoring**: Basic health checks and alerts

### Step 1: Stripe Production Setup

**1. Upgrade to Production Mode**
- In Stripe Dashboard, complete identity verification
- Activate live mode
- Live keys will be available (sk_live_..., pk_live_...)

**2. Recreate Resources in Live Mode**
- Create meters (same as test)
- Create prices (same as test, but on live mode)
- Setup webhook endpoint with production URL

**3. Payment Methods**
- Add payment method on file
- Set up billing alerts

### Step 2: Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker-compose --version
```

### Step 3: Configure Production Environment

```bash
# Create secure environment file
nano .env.production

# Set production values:
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-strong-random-key>

# Database (production instance)
DATABASE_URL=postgresql://prod_user:VERY_STRONG_PASSWORD@db:5432/data_foundry_prod
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100

# Redis
REDIS_URL=redis://redis:6379/0

# Stripe LIVE KEYS (not test)
STRIPE_SECRET_KEY=sk_live_your_live_secret_key
STRIPE_PUBLISHABLE_KEY=pk_live_your_live_key
STRIPE_WEBHOOK_SECRET=whsec_live_your_webhook_secret

# All 9 Price IDs from LIVE mode
STRIPE_GOLD_AI_LABELS_PRICE_ID=price_live...
# ... etc for all 9 prices

# Stripe Meter IDs from LIVE mode
STRIPE_AI_LABELS_METER_ID=mtr_live...
STRIPE_HUMAN_AUDITS_METER_ID=mtr_live...

# Domain and CORS
CORS_ORIGINS=["https://yourdomain.com"]
DOMAIN_NAME=yourdomain.com

# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### Step 4: Deploy with Docker Compose

```bash
# Use production configuration
docker-compose -f docker-compose.prod.yml up -d

# Verify services
docker-compose ps

# Run migrations
docker-compose -f docker-compose.prod.yml exec app \
  python -m src.database.migrations.run_migrations upgrade

# Verify Stripe connection
docker-compose exec app curl http://localhost:8000/api/v1/billing/health
```

### Step 5: Configure Nginx & SSL

```bash
# Nginx configuration automatically:
# - Terminates SSL/TLS with Let's Encrypt cert
# - Proxies to FastAPI on port 8000
# - Enforces HTTPS redirect
# - Sets security headers

# Verify
curl https://yourdomain.com/api/v1/billing/health
```

### Step 6: Update Stripe Webhook Endpoint

```bash
# Update webhook URL in Stripe Dashboard:
# Old: https://yourdomain.com/webhook (development)
# New: https://yourdomain.com/api/v1/billing/webhook (production)

# Verify webhook is receiving events:
# In Stripe Dashboard > Webhooks > [Endpoint]
# Check recent event logs
```

### Step 7: Monitor Initial Transactions

```bash
# Watch logs for webhook processing
docker-compose logs -f app

# Check Stripe Dashboard for:
# - Customer creation events
# - Subscription events
# - Meter events recorded
# - Invoice generation

# Monitor database
docker-compose exec app psql -U prod_user -d data_foundry_prod \
  -c "SELECT * FROM stripe_customers LIMIT 5;"
```

### Production Deployment Checklist

- [ ] Stripe upgraded to production
- [ ] All 11 resources created (2 meters, 9 prices)
- [ ] Live API keys configured
- [ ] Webhook endpoint set to production URL
- [ ] Payment method on file with Stripe
- [ ] SSL/TLS certificate installed
- [ ] Nginx reverse proxy configured
- [ ] Database initialized and migrated
- [ ] Firewall rules configured (80, 443)
- [ ] Backup strategy in place
- [ ] Monitoring and alerts configured
- [ ] Load testing completed
- [ ] Incident response plan documented

---

## Stripe Configuration

### Stripe Resource Architecture

```
┌─────────────────────────────────────────┐
│         Stripe Workspace                │
├─────────────────────────────────────────┤
│                                         │
│  Customers (Multi-tenant)               │
│  ├─ customer_1 (Stripe ID: cus_...)    │
│  ├─ customer_2 (Stripe ID: cus_...)    │
│  └─ customer_N (Stripe ID: cus_...)    │
│                                         │
│  Subscriptions (Meter-based)            │
│  ├─ sub_1 (Customer 1, Gold Tier)      │
│  ├─ sub_2 (Customer 2, Silver Tier)    │
│  └─ sub_N (Customer N, Bronze Tier)    │
│                                         │
│  Billing Meters (Usage Tracking)        │
│  ├─ meter: ai_labels (events/month)    │
│  └─ meter: human_audits (events/month) │
│                                         │
│  Prices (9 Total)                       │
│  ├─ Gold Tier                           │
│  │  ├─ AI Labels: $0.08 (metered)      │
│  │  ├─ Human Audits: $0.04 (metered)   │
│  │  └─ Monthly Fee: $99 (recurring)     │
│  ├─ Silver Tier                         │
│  │  ├─ AI Labels: $0.10 (metered)      │
│  │  ├─ Human Audits: $0.04 (metered)   │
│  │  └─ Monthly Fee: $49 (recurring)     │
│  └─ Bronze Tier                         │
│     ├─ AI Labels: $0.12 (metered)      │
│     ├─ Human Audits: $0.04 (metered)   │
│     └─ Monthly Fee: $0 (no fee)         │
│                                         │
│  Webhooks                               │
│  └─ Endpoint: /api/v1/billing/webhook  │
│                                         │
└─────────────────────────────────────────┘
```

### Creating Resources Programmatically (Optional)

```python
import stripe

stripe.api_key = "sk_live_..."

# Create meters
ai_meter = stripe.billing.Meter.create(
    event_name="ai_labels",
    display_name="AI Labels",
)

audit_meter = stripe.billing.Meter.create(
    event_name="human_audits",
    display_name="Human Audits",
)

# Create prices (example for Gold tier)
price_ai = stripe.Price.create(
    currency="usd",
    unit_amount=8,  # $0.08 in cents
    recurring={
        "interval": "month",
        "usage_type": "metered",
        "meter": ai_meter.id,
    },
    billing_scheme="per_unit",
)

price_platform = stripe.Price.create(
    currency="usd",
    unit_amount=9900,  # $99 in cents
    recurring={
        "interval": "month",
    },
    billing_scheme="tiered",
)
```

### Webhook Event Handling

```
Stripe Sends Event → Verify Signature → Route Handler → Update Database

Events Handled:
1. invoice.payment_succeeded
   → Mark subscription as active
   → Update last payment date

2. invoice.payment_failed
   → Mark subscription as past_due
   → Trigger retry logic
   → Send customer notification

3. customer.subscription.created
   → Create local subscription record
   → Set tier and pricing
   → Enable service access

4. customer.subscription.updated
   → Update local subscription
   → Handle tier changes
   → Trigger prorated calculations

5. customer.subscription.deleted
   → Mark subscription as canceled
   → Disable service access
   → Archive usage data
```

### Idempotency Implementation

Every meter event includes an idempotency key:

```
Format: {meter_event}_{tenant_id}_{value}_{timestamp}_{uuid_short}_{batch_id}
Example: ai_labels_tenant123_100_1704067200_abc123_batch456

Key Properties:
- Unique per event (cannot retry with same key)
- 24-hour TTL (Stripe default)
- Prevents duplicate billing
- Automatic retry detection
```

---

## Environment Configuration

### Critical Variables (Production Must-Have)

```env
# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<32+ character random string>

# Database
DATABASE_URL=postgresql://prod_user:PASSWORD@host:5432/data_foundry
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100

# Redis
REDIS_URL=redis://host:6379/0

# Stripe LIVE KEYS (Critical)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_live_...
```

### Stripe Resource IDs (All 11 Required)

```env
# Meter IDs (2)
STRIPE_AI_LABELS_METER_ID=mtr_live_...
STRIPE_HUMAN_AUDITS_METER_ID=mtr_live_...

# Price IDs (9)
# Gold Tier
STRIPE_GOLD_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_GOLD_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_GOLD_PLATFORM_FEE_PRICE_ID=price_1Si...

# Silver Tier
STRIPE_SILVER_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_SILVER_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_SILVER_PLATFORM_FEE_PRICE_ID=price_1Si...

# Bronze Tier
STRIPE_BRONZE_AI_LABELS_PRICE_ID=price_1Si...
STRIPE_BRONZE_HUMAN_AUDITS_PRICE_ID=price_1Si...
STRIPE_BRONZE_PLATFORM_FEE_PRICE_ID=price_1Si...
```

### Recommended Configuration

```env
# Stripe Retry & Batch
STRIPE_MAX_RETRIES=5
STRIPE_INITIAL_RETRY_DELAY_MS=1000
STRIPE_MAX_RETRY_DELAY_MS=32000
STRIPE_METER_EVENT_BATCH_SIZE=100
STRIPE_SYNC_INTERVAL_MINUTES=60
STRIPE_SYNC_LOCK_TTL_SECONDS=300

# Security
CORS_ORIGINS=["https://yourdomain.com"]
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### See Complete Reference

See `.env.example` for all 60+ configuration options.

---

## Database Setup

### Schema for Billing

**Main Tables**:
- `stripe_customers` - Maps tenant to Stripe customer
- `stripe_subscriptions` - Subscription status and tier
- `stripe_meter_events` - All meter events (audit trail)
- `billing_events` - Stripe webhook events
- `invoice_data` - Cached invoice information

### Initialize Database

```bash
# Run migrations
docker-compose exec app python -m src.database.migrations.run_migrations upgrade

# Verify tables created
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "\dt stripe_*"
```

### Connection Pool Tuning

**Production**:
```
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600
```

Adjust based on:
- Number of concurrent customers
- Meter event reporting frequency
- Webhook processing concurrency

---

## Docker Configuration

### Production Services

```yaml
# docker-compose.prod.yml includes:
- PostgreSQL 15 (persistent data)
- Redis 7 (meter event queue)
- FastAPI app (Stripe integration)
- Nginx (SSL/TLS + reverse proxy)
- Prometheus (metrics, optional)
- Grafana (dashboards, optional)
```

### Resource Limits (Production)

```yaml
app:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 4G
      reservations:
        cpus: '1.0'
        memory: 2G

db:
  deploy:
    resources:
      limits:
        cpus: '1.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 1G
```

---

## Webhook Management

### Webhook Endpoint Security

1. **Signature Verification**
   ```python
   # Stripe header format
   t=1704067200,v1=signature_hash

   # Verify using stripe.Webhook.construct_event()
   # - Validates timestamp (15-min tolerance)
   # - Verifies HMAC-SHA256 signature
   # - Prevents replay attacks
   ```

2. **Idempotent Processing**
   ```python
   # Each webhook has unique event ID
   # Even if received multiple times, only processes once
   # Event tracking in database
   ```

3. **Async Processing**
   ```python
   # Return 200 OK immediately
   # Process event asynchronously
   # Retry on failure with exponential backoff
   ```

### Testing Webhooks Locally

```bash
# Use Stripe CLI for local testing
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Trigger test events
stripe trigger invoice.payment_succeeded
stripe trigger customer.subscription.created

# View logs
docker-compose logs -f app
```

### Webhook Event Retry

Stripe automatically retries failed webhooks:
- Initial: Immediately
- 5 seconds later
- 5 minutes later
- 30 minutes later
- 2 hours later
- 5 hours later
- 10 hours later
- 24 hours later

Our system prevents duplicates via idempotency keys.

---

## Monitoring & Observability

### Built-in Health Checks

```bash
# Application health
GET /api/v1/billing/health

# Response includes:
{
  "status": "healthy",
  "stripe_connected": true,
  "database": "connected",
  "redis": "connected"
}
```

### Stripe-Specific Metrics

```
- Meter events reported (success rate)
- Webhook events processed (latency)
- Subscription creations/upgrades/cancellations
- Failed payment attempts
- Idempotency key cache hit rate
- API rate limit usage
```

### Structured Logging

All events logged as JSON:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "service": "metering",
  "event": "meter_event_reported",
  "tenant_id": "tenant_123",
  "meter_event": "ai_labels",
  "value": 100,
  "stripe_customer_id": "cus_...",
  "idempotency_key": "ai_labels_tenant_123_100_...",
  "result": "success"
}
```

### Optional: Prometheus Metrics

Enable monitoring profile:
```bash
docker-compose -f docker-compose.prod.yml --profile monitoring up -d
```

Access at: http://localhost:9090

Metrics tracked:
- API request duration
- Stripe API latency
- Database query time
- Redis operations
- Webhook processing time

---

## Security Best Practices

### API Security

1. **JWT Authentication**
   - Token expiry: 30 minutes
   - Refresh tokens: 7 days
   - Stored in HTTP-only cookies

2. **API Key Authentication** (for meter reporting)
   - Long-lived keys for tenants
   - Rotation every 90 days
   - Separate read/write permissions

3. **Rate Limiting**
   - Per-tenant limits
   - Per-tier request limits
   - Burst handling

### Stripe Security

1. **Webhook Signature Verification**
   - Mandatory for all incoming webhooks
   - Rejects unsigned events
   - Timestamp validation (15-min window)

2. **API Key Management**
   - Live keys never in code
   - Encrypted in environment
   - Rotation support built-in

3. **PCI Compliance**
   - No credit card data stored locally
   - All payments via Stripe
   - No sensitive data in logs

### Database Security

1. **Row-Level Security (RLS)**
   - Tenants isolated at database level
   - Cannot access other tenant data

2. **Encryption at Rest** (optional)
   - Enable in PostgreSQL
   - Backup encryption

3. **Backup Security**
   - Automated daily backups
   - Encrypted backups
   - 30-day retention

### Network Security

1. **HTTPS/TLS**
   - Enforced via Nginx
   - Let's Encrypt certificates
   - Auto-renewal

2. **Firewall**
   - Only 80 and 443 open
   - Database not exposed
   - Redis not exposed

3. **CORS**
   - Explicit allowed origins
   - No wildcard in production
   - Credentials handling

---

## Scaling & Performance

### Horizontal Scaling

Add more instances:
```yaml
app:
  deploy:
    replicas: 3  # Run 3 instances
```

Nginx automatically load-balances across instances.

### Database Performance

1. **Connection Pooling**
   - Per instance: 50 connections
   - 3 instances = 150 total
   - Adjust based on load

2. **Indexes**
   ```sql
   CREATE INDEX idx_tenant_id ON stripe_customers(tenant_id);
   CREATE INDEX idx_meter_events ON stripe_meter_events(created_at);
   ```

3. **Query Optimization**
   - Bulk inserts for meter events
   - Batch webhook processing
   - Async event handling

### Caching Strategy

1. **Redis Cache**
   - Customer data (10min TTL)
   - Subscription data (5min TTL)
   - Price cache (1hr TTL)

2. **Database Indexes**
   - On tenant_id (most queries)
   - On created_at (time-series data)
   - On stripe_customer_id (lookups)

### Performance Targets

- Meter event reporting: < 100ms
- Webhook processing: < 500ms
- Customer creation: < 200ms
- Database query: < 50ms

---

## Troubleshooting

### Common Issues

#### 1. Stripe Connection Fails

```bash
# Verify API key
docker-compose exec app echo $STRIPE_SECRET_KEY | head -c 8

# Test Stripe connection
curl https://api.stripe.com/v1/ping \
  -u sk_test_YOUR_KEY:

# Check logs
docker-compose logs app | grep stripe
```

#### 2. Webhook Events Not Received

```bash
# Verify endpoint URL
curl https://yourdomain.com/api/v1/billing/webhook -X POST

# Check Stripe Dashboard
# Developers > Webhooks > [Endpoint] > Logs

# Test locally with Stripe CLI
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Trigger test event
stripe trigger invoice.payment_succeeded
```

#### 3. Meter Events Not Reported

```bash
# Check meter IDs configured
docker-compose exec app env | grep STRIPE_.*_METER_ID

# Verify meters exist in Stripe
stripe meter list

# Check database for events
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM stripe_meter_events ORDER BY created_at DESC LIMIT 10;"
```

#### 4. Subscription Creation Fails

```bash
# Verify price IDs configured
docker-compose exec app env | grep STRIPE_.*_PRICE_ID

# Check prices exist in Stripe
stripe price list

# Test subscription creation
curl -X POST http://localhost:8000/api/v1/billing/subscriptions \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test","subscription_tier":"GOLD"}'
```

### Debug Commands

```bash
# Check Stripe health
docker-compose exec app curl -H "Authorization: Bearer $STRIPE_SECRET_KEY" \
  https://api.stripe.com/v1/ping

# View all customers
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM stripe_customers;"

# View subscriptions
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM stripe_subscriptions;"

# View meter events
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM stripe_meter_events ORDER BY created_at DESC LIMIT 20;"

# View webhook events
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM billing_events ORDER BY created_at DESC LIMIT 20;"
```

---

## Deployment Verification

### Post-Deployment Checklist

```bash
# 1. All services running
docker-compose ps
# Expected: all services in "Up" state

# 2. API responding
curl http://localhost:8000/api/v1/billing/health
# Expected: {"status": "healthy", "stripe_connected": true}

# 3. Database connectivity
docker-compose exec app psql $DATABASE_URL -c "SELECT 1;"
# Expected: returns 1

# 4. Stripe connection
docker-compose logs app | grep "Stripe connected"
# Expected: "Stripe connected successfully"

# 5. Webhook endpoint accessible
curl https://yourdomain.com/api/v1/billing/webhook
# Expected: HTTP 405 (Method Not Allowed, which is OK for GET)

# 6. Database migrations applied
docker-compose exec app python -m src.database.migrations.run_migrations status
# Expected: "All migrations applied"

# 7. No error logs
docker-compose logs app | grep ERROR | wc -l
# Expected: 0 (or very few)
```

---

## Next Steps

1. **Load Testing**: Test meter event throughput (target: 10K events/min)
2. **Failover Testing**: Test webhook retry behavior
3. **Backup Testing**: Verify restore procedure
4. **Cost Optimization**: Monitor Stripe API usage
5. **Observability**: Set up dashboards and alerts

---

## Support & Resources

- **Stripe API Docs**: https://stripe.com/docs/billing/meter-billing
- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **PostgreSQL Docs**: https://www.postgresql.org/docs/
- **Docker Docs**: https://docs.docker.com/
- **Stripe CLI**: https://stripe.com/docs/stripe-cli
- **Project Repository**: [your-repo-url]

---

## Financial Projections (Reference)

### Year 1 Revenue Potential

**Conservative Estimate**: $100K-150K ARR
- 50-100 customers by end of month 3
- Average customer: $1,200-1,500 MRR
- Churn: 5% monthly

**Optimistic Estimate**: $150K-200K ARR
- 150-200 customers by end of month 3
- Average customer: $800-1,000 MRR
- Churn: 3% monthly

### Monthly Cost

- **Infrastructure**: $50-150/month (VPS + Stripe processing)
- **Services**: $20-50/month (monitoring, backups)
- **Total**: $70-200/month

### Profitability Timeline

- Month 1: -$150 (setup costs)
- Month 2: +$500 (first customers)
- Month 3: +$3,000-8,000 (scaling)
- Month 6: Break-even + positive cash flow
