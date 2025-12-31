# AML Service - Infrastructure & Deployment Guide

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Technology Stack](#technology-stack)
3. [Deployment Options](#deployment-options)
4. [Local Development Setup](#local-development-setup)
5. [Production Deployment](#production-deployment)
6. [Environment Configuration](#environment-configuration)
7. [Database Setup](#database-setup)
8. [Docker Configuration](#docker-configuration)
9. [External Integrations](#external-integrations)
10. [Monitoring & Observability](#monitoring--observability)
11. [Security Best Practices](#security-best-practices)
12. [Scaling & Performance](#scaling--performance)
13. [Troubleshooting](#troubleshooting)

---

## System Architecture

### High-Level Components

```
+-----------------------------------------------------------------------+
|                        Client Applications                            |
|                   (Fintech Compliance Teams)                         |
+------------------------------+----------------------------------------+
                              |
                              v
+-----------------------------------------------------------------------+
|                      API Gateway Layer                                |
|         FastAPI Application (Rate Limiting, Auth)                    |
+------------------------------+----------------------------------------+
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
+--------------+    +--------------+    +--------------+
|  FastAPI     |    |  Background  |    |  Prefect     |
|  API (8000)  |    |  Worker      |    |  Server      |
+------+------+    +------+------+    +------+------+
       |                   |                   |
       +-------------------+-------------------+
                           |
           +---------------+---------------+
           |                               |
           v                               v
+------------------+           +------------------------+
|   PostgreSQL 15  |           |    OpenAI API          |
|   (AML Labels)   |           |   (Labeling Service)   |
|   Port: 5433     |           +------------------------+
+------------------+                       ^
           |                               |
           v                               |
+------------------+           +------------------------+
|   Redis 7        |           |   Label Studio         |
|   (Cache/Queue)  |           |   (Human Review)       |
|   Port: 6380     |           +------------------------+
+------------------+
```

### AML Service Components

1. **FastAPI Application**: REST API with JWT authentication and multi-tenancy
2. **Background Worker**: Celery-based job polling and execution
3. **AI Labeling Service**: OpenAI/Anthropic integration with expert prompts
4. **Cohen's Kappa Calculator**: Inter-rater agreement measurement
5. **Audit Report Generator**: Compliance documentation (JSON/PDF)
6. **Database Layer**: PostgreSQL with audit trails and soft deletes
7. **Multi-Tenant Isolation**: Tenant-scoped queries and data segregation
8. **Stripe Billing**: Metered usage tracking per transaction

### Data Flow

```
Customer Uploads CSV
    |
    v
POST /api/v1/upload (FastAPI)
    |
    +-> Validate file format
    +-> Store to results directory
    +-> Create ProcessingJob (status: PENDING)
    |
    v
JobWorker (Background Polling)
    |
    +-> Prefect Flow: data_ingestion_flow()
    |
    +-> extract_data()          Parse CSV rows
    +-> validate_schema()       Check required columns
    +-> apply_aml_labeling()    Call OpenAI/Anthropic with expert prompt
    |                               |
    |                               v
    |                           OpenAI/Anthropic API
    |                               |
    |                               +-> Returns: risk_level, typology,
    |                               |            regulatory_flags, reasoning
    |                               |
    |                               v
    +-> compute_inter_rater_agreement()  # Cohen's Kappa
    +-> route_for_human_review()        # If confidence < threshold
    +-> save_aml_labels_to_database()   # Persist with audit trail
    +-> generate_audit_report()         # Compliance documentation
    |
    v
Job Tracking Service
    |
    +-> mark_complete(job_id, results_url, audit_report_url)
    +-> Report usage to Stripe (meter events)
    |
    v
Customer Downloads Results
    |
    +-> GET /api/v1/jobs/{job_id}/results
    +-> Return CSV with AML labels + audit report
```

---

## Technology Stack

### Core Framework
- **Web Server**: FastAPI 0.104+ with Uvicorn 0.24+
- **Python Version**: 3.11+ (documented as 3.12)
- **Package Manager**: UV (Rust-based) or pip
- **Async Runtime**: asyncio

### Database
- **Primary Database**: PostgreSQL 15 (Alpine variant)
- **ORM**: SQLModel 0.0.27 + SQLAlchemy 2.0.45
- **Async Driver**: asyncpg 0.31.0
- **Migrations**: Custom async migration runner (non-Alembic, located in `src/database/migrations/`)
- **Connection Pool**: SQLAlchemy engine with configurable pool sizing

### Task Orchestration
- **Workflow Engine**: Prefect 3.6+ (async-compatible)
- **Worker Model**: Background polling with configurable concurrency
- **Task Decorators**: @task, @flow for pipeline definition
- **State Management**: In-memory job state with DB persistence

### AI Integration
- **Model Providers**:
  - OpenAI (GPT-4o, GPT-4o-mini)
  - Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
  - OpenRouter (multi-provider fallback)
- **Prompt Management**: Centralized expert prompts in `src/core/prompts/`
- **Response Parsing**: Structured output validation with Pydantic
- **Cost Tracking**: Token usage and per-transaction billing

### Caching & Queuing
- **Cache**: Redis 7-alpine
- **Message Broker**: Redis-based task queue
- **Task Queue**: Celery 5.3+ with Redis backend

### Data Processing
- **CSV Parsing**: pandas 2.1+
- **Validation**: Pydantic 2.12+ with custom validators
- **PII Redaction**: Microsoft Presidio 2.2.360 (for data privacy)

### Monitoring & Observability
- **Structured Logging**: structlog 25.5+ with JSON output
- **Health Checks**: Built-in endpoints for all components
- **Optional Monitoring**: Prometheus + Grafana (production profile)

### Security
- **Authentication**: JWT Bearer tokens with tenant isolation
- **API Security**: python-jose 3.3+ for JWT handling
- **Secrets Management**: Custom SecretManager for encrypted secrets
- **PII Protection**: Presidio for PII detection and redaction

### Development Tools
- **Testing**: pytest 9.0+ with asyncio support
- **Linting**: ruff 0.14+
- **Code Formatting**: black 25.12+, isort 5.13+
- **Type Checking**: mypy 1.19+

---

## Deployment Options

### Option 1: Docker Compose (Development)
**Best For**: Local development, testing, demos
- Single command setup: `docker-compose up -d`
- Auto-reload on code changes
- Hot-reloadable volumes
- Test data seeding

**Time to Deploy**: 5 minutes

### Option 2: Docker Compose (Production)
**Best For**: Small-to-medium teams, single VPS
- Production-optimized containers
- Resource limits and reservations
- Health checks on all services
- Persistent volumes for data
- Nginx reverse proxy with SSL/TLS (optional)

**Time to Deploy**: 30 minutes (with environment setup)

### Option 3: Platform as a Service (Easiest)
**Best For**: Indie hackers, rapid deployment
- Vercel, Railway, Render, Fly.io
- Database managed (e.g., Vercel Postgres)
- Auto-scaling
- CI/CD built-in

**Time to Deploy**: 15 minutes with git push

---

## Local Development Setup

### Prerequisites

- **Docker & Docker Compose** (or native Python 3.12)
- **Git**
- **8GB RAM minimum**
- **5GB free disk space**
- **OpenAI API Key** and/or **Anthropic API Key**

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/data-foundry.git
cd data-foundry/data-foundry
```

### Step 2: Copy Environment Configuration

```bash
# Copy example environment
cp .env.example .env

# For local secrets (optional)
cp .env.example .env.local
```

### Step 3: Update .env for AML Service Development

```env
# Core Settings
ENVIRONMENT=development
DEBUG=true
APP_NAME=Data Foundry AML Service

# Database (Docker will provide this)
DATABASE_URL=postgresql+asyncpg://foundry_user:foundry_password@db:5432/data_foundry
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30

# Redis (Docker will provide this)
REDIS_URL=redis://redis:6379/0

# JWT Secret (generate a random string)
SECRET_KEY=your-random-secret-key-here-min-32-chars

# === AI Provider API Keys ===
# OpenAI (for GPT-4o, GPT-4o-mini)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.3

# Anthropic (for Claude models)
ANTHROPIC_API_KEY=ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229
ANTHROPIC_TEMPERATURE=0.3

# OpenRouter (multi-provider fallback)
OPENROUTER_API_KEY=sk-or-...
PRIMARY_MODEL=openrouter/openai/gpt-4o-mini
FALLBACK_MODELS=openrouter/anthropic/claude-3.5-sonnet,openrouter/openai/gpt-4o

# === AML Service Configuration ===
# Core AML Settings
ENABLE_AML_SERVICE=true
AML_AI_CONFIDENCE_THRESHOLD=0.6
AML_RISK_LEVELS=LOW,MEDIUM,HIGH,CRITICAL
AML_DEFAULT_RISK_LEVEL=MEDIUM

# Kappa Agreement Configuration
AML_KAPPA_THRESHOLD=0.70

# Expert Review Configuration
AML_EXPERT_REQUIRED_REVIEWS=2
AML_EXPERT_AGREEMENT_REQUIRED=true

# Audit and Compliance Settings
AML_AUDIT_REPORT_ENABLED=true
AML_REGULATORY_FLAGS_ENABLED=true

# Performance and Processing Settings
AML_BATCH_INSERT_SIZE=1000
AML_LABELING_TIMEOUT_SECONDS=30
AML_REVIEW_QUEUE_MAX_SIZE=10000

# Stripe Billing (AML-specific)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_AI_LABEL_METER_ID=mtr_test_...
STRIPE_HUMAN_AUDIT_METER_ID=mtr_test_...

# Label Studio (Human Review UI)
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=...

# Prefect Configuration
PREFECT_API_URL=http://prefect-server:4200
```

### Step 4: Start Services with Docker Compose

```bash
# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f api

# Check service status
docker-compose ps
```

### Step 5: Initialize Database with AML Tables

```bash
# Run all AML migrations in order
docker-compose exec api python -m src.database.migrations.add_aml_transaction_labels_table
docker-compose exec api python -m src.database.migrations.add_aml_audit_trail_tables
docker-compose exec api python -m src.database.migrations.enhance_tenant_user_models

# Run schema fix migrations
docker-compose exec api python -m src.database.migrations.add_ai_tracking_fields

# Run job_id migration
docker-compose exec api python -m src.database.migrations.003_add_job_id_to_aml_labels upgrade

# Run unique constraint migration
docker-compose exec api python -m src.database.migrations.004_add_unique_constraint_aml_labels upgrade

# Verify tables created
docker-compose exec api psql postgresql://foundry_user:foundry_password@db:5432/data_foundry \
  -c "\dt aml_*"
```

Expected output:
```
            List of relations
 Schema |             Name              | Type  |  Owner
--------+-------------------------------+-------+----------
 public | aml_audit_reports            | table | foundry_user
 public | aml_expert_reviews           | table | foundry_user
 public | aml_labeling_methodology     | table | foundry_user
 public | aml_transaction_labels       | table | foundry_user
```

### Step 6: Verify OpenAI API Connectivity

```bash
# Test OpenAI connection from within container
docker-compose exec api python -c "
from src.services.ai_service import AIService
from src.core.config import settings
import asyncio

async def test():
    ai = AIService()
    result = await ai.completion('Say hello')
    print(f'OpenAI Response: {result.content}')

asyncio.run(test())
"
```

### Step 7: Access Application

- **API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health
- **Prefect UI**: http://localhost:4200
- **Label Studio**: http://localhost:8080

### Development Workflow

```bash
# Run AML-specific tests
docker-compose exec api pytest tests/tasks/test_ingestion_p01_006_integration.py -v

# Run with code coverage
docker-compose exec api pytest tests/tasks/test_ingestion_p01_006_integration.py --cov=src/models/aml

# Format code
docker-compose exec api black src/ tests/

# Lint code
docker-compose exec api ruff check src/ tests/

# Type checking
docker-compose exec api mypy src/
```

### Stopping Services

```bash
# Stop all services (data persists)
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# View logs
docker-compose logs -f [service-name]
```

---

## Production Deployment

### Prerequisites

- **Server**: VPS with 2GB+ RAM, 2+ CPUs, 40GB+ SSD
- **Domain Name**: With DNS configured
- **SSL Certificate**: Let's Encrypt (free) or commercial
- **PostgreSQL Backup Strategy**: Automated backups
- **Monitoring**: Basic health checks
- **OpenAI API Key**: Production account with rate limits

### Step 1: Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker & Docker Compose
sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER

# Verify installation
docker --version
docker-compose --version

# Install nginx for reverse proxy (optional if using docker-compose)
sudo apt install -y nginx certbot python3-certbot-nginx
```

### Step 2: Prepare Environment Variables

```bash
# Create secure environment file
sudo nano /opt/data-foundry/.env.production

# Critical variables to set:
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-strong-random-key-64-chars>
DATABASE_URL=postgresql+asyncpg://prod_user:STRONG_PASSWORD@db:5432/data_foundry_prod
REDIS_URL=redis://redis:6379/0

# HTTPS Configuration
DOMAIN_NAME=aml.yourdomain.com
SSL_EMAIL=ssl@yourdomain.com

# === AI Provider API Keys ===
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
ANTHROPIC_API_KEY=ant-...
OPENROUTER_API_KEY=sk-or-...

# === AML Service Production Config ===
ENABLE_AML_SERVICE=true
AML_AI_CONFIDENCE_THRESHOLD=0.6
AML_KAPPA_THRESHOLD=0.70
AML_EXPERT_REQUIRED_REVIEWS=2
AML_BATCH_INSERT_SIZE=1000

# === Stripe Production ===
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_AI_LABEL_METER_ID=mtr_live_...
STRIPE_HUMAN_AUDIT_METER_ID=mtr_live_...

# CORS origins for production
CORS_ORIGINS=["https://aml.yourdomain.com"]

# Logging & Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### Step 3: Deploy with Docker Compose

```bash
# Clone repository
cd /opt
git clone https://github.com/yourusername/data-foundry.git
cd data-foundry/data-foundry

# Copy production environment
cp .env.production .env

# Build production image
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Verify all services running
docker-compose -f docker-compose.prod.yml ps

# Check logs
docker-compose -f docker-compose.prod.yml logs -f api
```

### Step 4: Run AML Database Migrations

```bash
# Run migrations in order
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.add_aml_transaction_labels_table
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.add_aml_audit_trail_tables
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.enhance_tenant_user_models
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.add_ai_tracking_fields
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.003_add_job_id_to_aml_labels upgrade
docker-compose -f docker-compose.prod.yml exec api python -m src.database.migrations.004_add_unique_constraint_aml_labels upgrade

# Verify migration success
docker-compose -f docker-compose.prod.yml exec api psql $DATABASE_URL \
  -c "SELECT COUNT(*) FROM aml_transaction_labels;"
```

### Step 5: Configure Nginx (SSL/TLS)

```bash
# Nginx configuration for AML service
cat > /etc/nginx/sites-available/aml-service << 'EOF'
server {
    listen 80;
    server_name aml.yourdomain.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name aml.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/aml.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aml.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req zone=api burst=20;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running AML jobs
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
    }

    # Prefect UI
    location /prefect/ {
        proxy_pass http://localhost:4200/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/aml-service /etc/nginx/sites-enabled/

# Obtain SSL certificate
sudo certbot --nginx -d aml.yourdomain.com

# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### Step 6: Setup Automated Backups

```bash
# Create backup script
cat > /opt/scripts/backup-postgres-aml.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/postgres/aml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup AML tables with data
docker-compose -f /opt/data-foundry/data-foundry/docker-compose.prod.yml \
  exec -T db pg_dump -U foundry_user data_foundry \
  -t aml_transaction_labels \
  -t aml_expert_reviews \
  -t aml_audit_reports \
  -t aml_labeling_methodology \
  | gzip > $BACKUP_DIR/aml_tables_$TIMESTAMP.sql.gz

# Keep only last 30 backups
find $BACKUP_DIR -name "aml_tables_*.sql.gz" -mtime +30 -delete

echo "Backup completed: aml_tables_$TIMESTAMP.sql.gz"
EOF

chmod +x /opt/scripts/backup-postgres-aml.sh

# Add to crontab (daily at 2 AM)
(crontab -l; echo "0 2 * * * /opt/scripts/backup-postgres-aml.sh >> /var/log/aml-backup.log 2>&1") | crontab -
```

### Step 7: Monitor Application

```bash
# Health check endpoint
curl https://aml.yourdomain.com/health

# Check database connectivity
curl https://aml.yourdomain.com/api/v1/health/db

# Verify OpenAI connectivity
curl https://aml.yourdomain.com/api/v1/health/openai

# View logs in real-time
docker-compose -f docker-compose.prod.yml logs -f api worker

# Check resource usage
docker stats
```

### Production Deployment Checklist

- [ ] Environment variables configured (especially OPENAI_API_KEY, ANTHROPIC_API_KEY)
- [ ] Database initialized and AML migrations applied
- [ ] SSL/TLS certificate installed
- [ ] Nginx reverse proxy configured
- [ ] Firewall rules configured (80, 443 open)
- [ ] AML-specific backup strategy in place
- [ ] Monitoring and alerts configured
- [ ] Health checks passing (including OpenAI/Anthropic)
- [ ] Background worker processing jobs
- [ ] Prefect UI accessible
- [ ] Stripe webhook endpoint configured
- [ ] Error tracking configured
- [ ] Incident response plan documented

---

## Environment Configuration

### Required Variables (Production)

```env
# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<64+ character random string>
APP_NAME=Data Foundry AML Service
API_V1_STR=/api/v1

# Database
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
DATABASE_POOL_TIMEOUT=30

# Redis
REDIS_URL=redis://host:6379/0

# === AI Provider API Keys (REQUIRED) ===
# At least one of these is required
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
ANTHROPIC_API_KEY=ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229
OPENROUTER_API_KEY=sk-or-...

# === AML Service Required ===
ENABLE_AML_SERVICE=true
AML_AI_CONFIDENCE_THRESHOLD=0.6
AML_KAPPA_THRESHOLD=0.70
AML_EXPERT_REQUIRED_REVIEWS=2

# Billing (Required for production)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_AI_LABEL_METER_ID=mtr_live_...
STRIPE_HUMAN_AUDIT_METER_ID=mtr_live_...
```

### Optional but Recommended

```env
# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
METRICS_PORT=9090

# CORS
CORS_ORIGINS=["https://aml.yourdomain.com"]

# Rate Limiting
ENABLE_RATE_LIMITING=true
RATE_LIMIT_REQUESTS_PER_MINUTE=1000

# Label Studio
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=...

# AML Service Options
AML_AUDIT_REPORT_ENABLED=true
AML_REGULATORY_FLAGS_ENABLED=true
AML_BATCH_INSERT_SIZE=1000
AML_LABELING_TIMEOUT_SECONDS=30
AML_REVIEW_QUEUE_MAX_SIZE=10000

# Expert Review
AML_EXPERT_AGREEMENT_REQUIRED=true
```

### Complete Reference

See `.env.example` for all configuration options with descriptions.

---

## Database Setup

### AML Database Schema

The AML service uses four core tables:

#### 1. aml_transaction_labels
Core table storing AI-generated AML labels.

```sql
CREATE TABLE aml_transaction_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    job_id VARCHAR NOT NULL,                    -- Added in migration 003
    version_id UUID,

    -- Risk Classification
    risk_level VARCHAR(50) NOT NULL,            -- LOW, MEDIUM, HIGH, CRITICAL
    typology VARCHAR(100) NOT NULL,             -- FATF typology code

    -- AI Output
    confidence_score DECIMAL(3,2) NOT NULL,     -- 0.00 - 1.00
    ai_reasoning TEXT NOT NULL,

    -- Expert Review
    expert_review_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    -- Regulatory Flags (JSONB for flexibility)
    regulatory_flags JSONB DEFAULT '{}',

    -- Audit Trail
    is_audit_ready BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT check_aml_confidence_score
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CONSTRAINT check_aml_risk_level
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT check_aml_expert_review_status
        CHECK (expert_review_status IN ('PENDING', 'AGREED', 'DISAGREED', 'ESCALATED'))
);

-- Unique constraint (migration 004)
ALTER TABLE aml_transaction_labels
ADD CONSTRAINT uq_aml_transaction_labels_txn_tenant
UNIQUE (transaction_id, tenant_id);
```

#### 2. aml_expert_reviews
Stores expert reviews for AML labels.

```sql
CREATE TABLE aml_expert_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aml_transaction_label_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    expert_id UUID NOT NULL,
    expert_decision VARCHAR(50) NOT NULL,      -- AGREE, DISAGREE, NEEDS_CLARIFICATION
    reasoning TEXT NOT NULL,
    confidence_level DECIMAL(3,2) NOT NULL,    -- 0.00 - 1.00
    reviewed_at TIMESTAMP NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT check_aml_expert_confidence_level
        CHECK (confidence_level >= 0 AND confidence_level <= 1),
    CONSTRAINT check_aml_expert_decision
        CHECK (expert_decision IN ('AGREE', 'DISAGREE', 'NEEDS_CLARIFICATION'))
);
```

#### 3. aml_audit_reports
Stores generated audit reports for compliance.

```sql
CREATE TABLE aml_audit_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    job_id UUID NOT NULL,
    transaction_count INTEGER NOT NULL,
    labeled_count INTEGER NOT NULL,
    expert_reviewed_count INTEGER NOT NULL,
    kappa_coefficient DECIMAL(4,3) NOT NULL,   -- -1.0 to 1.0
    agreement_level VARCHAR(50) NOT NULL,      -- POOR, FAIR, MODERATE, SUBSTANTIAL, PERFECT
    generated_at TIMESTAMP NOT NULL,
    report_url VARCHAR(500) NOT NULL,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT check_aml_audit_transaction_count
        CHECK (transaction_count >= 0),
    CONSTRAINT check_aml_audit_labeled_count
        CHECK (labeled_count >= 0 AND labeled_count <= transaction_count),
    CONSTRAINT check_aml_audit_reviewed_count
        CHECK (expert_reviewed_count >= 0 AND expert_reviewed_count <= labeled_count),
    CONSTRAINT check_aml_audit_kappa_coefficient
        CHECK (kappa_coefficient >= -1 AND kappa_coefficient <= 1),
    CONSTRAINT check_aml_audit_agreement_level
        CHECK (agreement_level IN ('POOR', 'FAIR', 'MODERATE', 'SUBSTANTIAL', 'PERFECT'))
);
```

#### 4. aml_labeling_methodology
Tracks methodology versions for audit trail.

```sql
CREATE TABLE aml_labeling_methodology (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    version VARCHAR(20) NOT NULL,
    description TEXT NOT NULL,
    risk_thresholds JSONB NOT NULL,
    typologies JSONB NOT NULL,
    regulatory_references JSONB DEFAULT '{}',
    created_by UUID,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,               -- DRAFT, ACTIVE, ARCHIVED
    is_deleted BOOLEAN DEFAULT FALSE,

    CONSTRAINT check_aml_methodology_status
        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
);
```

### Indexes

```sql
-- Performance indexes on aml_transaction_labels
CREATE INDEX idx_aml_transaction_labels_tenant_id
    ON aml_transaction_labels(tenant_id);
CREATE INDEX idx_aml_transaction_labels_transaction_id
    ON aml_transaction_labels(transaction_id);
CREATE INDEX idx_aml_labels_job_id
    ON aml_transaction_labels(job_id);
CREATE INDEX idx_aml_labels_job_tenant
    ON aml_transaction_labels(job_id, tenant_id);
CREATE INDEX idx_aml_transaction_labels_risk_level
    ON aml_transaction_labels(risk_level);
CREATE INDEX idx_aml_transaction_labels_expert_review_status
    ON aml_transaction_labels(expert_review_status);
CREATE INDEX idx_aml_transaction_labels_created_at
    ON aml_transaction_labels(created_at DESC);
CREATE INDEX idx_aml_transaction_labels_is_deleted
    ON aml_transaction_labels(is_deleted)
    WHERE is_deleted = FALSE;

-- Performance indexes on aml_expert_reviews
CREATE INDEX idx_aml_expert_reviews_tenant_id
    ON aml_expert_reviews(tenant_id);
CREATE INDEX idx_aml_expert_reviews_label_id
    ON aml_expert_reviews(aml_transaction_label_id);
CREATE INDEX idx_aml_expert_reviews_expert_id
    ON aml_expert_reviews(expert_id);
CREATE INDEX idx_aml_expert_reviews_created_at
    ON aml_expert_reviews(created_at DESC);
CREATE INDEX idx_aml_expert_reviews_is_deleted
    ON aml_expert_reviews(is_deleted)
    WHERE is_deleted = FALSE;

-- Performance indexes on aml_audit_reports
CREATE INDEX idx_aml_audit_reports_tenant_id
    ON aml_audit_reports(tenant_id);
CREATE INDEX idx_aml_audit_reports_job_id
    ON aml_audit_reports(job_id);
CREATE INDEX idx_aml_audit_reports_created_at
    ON aml_audit_reports(created_at DESC);
CREATE INDEX idx_aml_audit_reports_is_deleted
    ON aml_audit_reports(is_deleted)
    WHERE is_deleted = FALSE;

-- Performance indexes on aml_labeling_methodology
CREATE INDEX idx_aml_labeling_methodology_tenant_id
    ON aml_labeling_methodology(tenant_id);
CREATE INDEX idx_aml_labeling_methodology_version
    ON aml_labeling_methodology(version);
CREATE INDEX idx_aml_labeling_methodology_status
    ON aml_labeling_methodology(status);
CREATE INDEX idx_aml_labeling_methodology_is_deleted
    ON aml_labeling_methodology(is_deleted)
    WHERE is_deleted = FALSE;
```

### Migrations

```bash
# Run migrations in order
python -m src.database.migrations.add_aml_transaction_labels_table
python -m src.database.migrations.add_aml_audit_trail_tables
python -m src.database.migrations.enhance_tenant_user_models
python -m src.database.migrations.add_ai_tracking_fields

# Schema fix migrations
python -m src.database.migrations.003_add_job_id_to_aml_labels upgrade
python -m src.database.migrations.004_add_unique_constraint_aml_labels upgrade

# Check migration status (if run_migrations.py exists)
python -m src.database.migrations.run_migrations status

# Rollback if needed
python -m src.database.migrations.003_add_job_id_to_aml_labels downgrade
python -m src.database.migrations.004_add_unique_constraint_aml_labels downgrade
```

### Connection Pool Tuning

**Development** (docker-compose.yml):
```
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
```

**Production** (docker-compose.prod.yml):
```
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600
```

Adjust based on:
- Expected concurrent jobs
- API request volume
- Database server resources

---

## Docker Configuration

### Development (docker-compose.yml)

Includes:
- PostgreSQL 15 (port 5433)
- Redis 7 (port 6380)
- FastAPI app (port 8000)
- Prefect server (port 4200)
- Label Studio (port 8080)
- Hot-reload volumes
- Debug mode enabled

### Production (docker-compose.prod.yml)

Includes:
- PostgreSQL 15 (port 5432)
- Redis 7 (port 6379)
- FastAPI app (port 8000)
- Label Studio (port 8080)
- Nginx reverse proxy (ports 80, 443) - optional
- Prometheus (port 9090) - monitoring profile
- Grafana (port 3000) - monitoring profile
- Resource limits
- Restart policies
- Health checks
- Structured logging

### Service Configuration

```yaml
# FastAPI Application
api:
  build:
    context: .
    dockerfile: Dockerfile
  image: data-foundry-aml:latest
  ports:
    - "8000:8000"
  environment:
    - ENVIRONMENT=production
    - ENABLE_AML_SERVICE=true
    - AML_AI_CONFIDENCE_THRESHOLD=0.6
  volumes:
    - ./logs:/app/logs
  depends_on:
    - db
    - redis
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s

# Background Worker
worker:
  build:
    context: .
    dockerfile: Dockerfile
  image: data-foundry-aml:latest
  command: python -m src.workers.main
  environment:
    - ENVIRONMENT=production
    - AML_BATCH_INSERT_SIZE=1000
  depends_on:
    - db
    - redis
    - api
  restart: unless-stopped

# PostgreSQL Database
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_USER: foundry_user
    POSTGRES_PASSWORD: ${DB_PASSWORD}
    POSTGRES_DB: data_foundry
  volumes:
    - postgres_data_prod:/var/lib/postgresql/data
    - ./docker/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
  restart: unless-stopped
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U foundry_user -d data_foundry"]
    interval: 10s
    timeout: 5s
    retries: 5

# Redis Cache
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data_prod:/data
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5

# Prefect Server
prefect-server:
  image: prefecthq/prefect:2-latest
  command: prefect server start --host 0.0.0.0
  ports:
    - "4200:4200"
  environment:
    - PREFECT_API_DATABASE_CONNECTION_URL=postgresql+asyncpg://foundry_user:${DB_PASSWORD}@db:5432/data_foundry
  volumes:
    - prefect_data:/root/.prefect
  restart: unless-stopped

# Label Studio (Human Review UI)
label-studio:
  image: heartexlabs/label-studio:latest
  ports:
    - "8080:8080"
  volumes:
    - label_studio_data_prod:/label-studio/data
  environment:
    - DJANGO_DB=postgresql
    - POSTGRES_HOST=db
    - POSTGRES_PORT=5432
    - POSTGRES_USER=foundry_user
    - POSTGRES_PASSWORD=${DB_PASSWORD}
    - POSTGRES_DB=data_foundry_labelstudio
  restart: unless-stopped
```

---

## External Integrations

### OpenAI API Integration

#### Configuration

```python
# src/core/config.py
class Settings(BaseSettings):
    # OpenAI Configuration
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.3
    OPENAI_MAX_TOKENS: int = 2048
```

#### Usage

```python
# src/services/ai_service.py
from src.services.ai_service import AIService

async def label_transaction(transaction_data: dict) -> AMLLabel:
    ai_service = AIService()

    # Build AML-specific prompt
    prompt = build_aml_prompt(transaction_data)

    # Call OpenAI
    response = await ai_service.completion(
        prompt=prompt,
        model=settings.OPENAI_MODEL,
        temperature=settings.OPENAI_TEMPERATURE
    )

    # Parse response
    label = parse_aml_response(response)
    return label
```

#### Rate Limits & Quotas

| Model | TPM (Tokens/Min) | RPD (Requests/Day) | Cost/1K Tokens |
|-------|------------------|--------------------|----------------|
| gpt-4o | 30,000 | 200 | $0.005 (input) / $0.015 (output) |
| gpt-4o-mini | 200,000 | 1,000 | $0.00015 (input) / $0.0006 (output) |

**Recommendation**: Use `gpt-4o-mini` for high-volume processing, `gpt-4o` for complex cases.

### Anthropic API Integration

#### Configuration

```python
# src/core/config.py
class Settings(BaseSettings):
    # Anthropic Configuration
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"
    ANTHROPIC_TEMPERATURE: float = 0.3
    ANTHROPIC_MAX_TOKENS: int = 2048
```

#### Usage

```python
# Use AIService which supports both OpenAI and Anthropic
ai_service = AIService()
response = await ai_service.completion(
    prompt=prompt,
    model=settings.ANTHROPIC_MODEL
)
```

### OpenRouter Integration (Multi-Provider Fallback)

#### Configuration

```python
# src/core/config.py
class Settings(BaseSettings):
    # OpenRouter Configuration
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    PRIMARY_MODEL: str = "openrouter/openai/gpt-4o-mini"
    FALLBACK_MODELS: list[str] = [
        "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter/openai/gpt-4o"
    ]
```

### Prefect Integration

#### Configuration

```python
# src/core/config.py
PREFECT_API_URL: str = "http://localhost:4200"
```

#### Flow Definition

```python
# src/tasks/ingestion.py
from prefect import flow, task

@task
async def apply_aml_labeling(transactions: list[dict]) -> list[AMLLabel]:
    """AI-powered AML labeling task."""
    # OpenAI/Anthropic API calls
    pass

@flow(name="aml_labeling_flow")
async def aml_labeling_flow(job_id: str, file_path: str) -> dict:
    """Orchestrate AML labeling pipeline."""
    # Extract -> Validate -> Label -> Save
    pass
```

#### Worker Deployment

```bash
# Start background worker
python -m src.workers.main

# Or via Docker
docker-compose up -d worker
```

### Stripe Billing Integration

#### Configuration

```python
# src/core/config.py
class Settings(BaseSettings):
    # Stripe Configuration
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_AI_LABEL_METER_ID: str | None = None
    STRIPE_HUMAN_AUDIT_METER_ID: str | None = None
```

#### Meter Configuration

```python
# src/services/stripe/meter_event_service.py
async def report_aml_transaction(
    customer_id: str,
    transaction_id: str,
    quantity: int = 1
):
    """Report AML transaction as metered billing event."""
    await stripe_service.report_usage(
        customer_id=customer_id,
        meter_id=settings.STRIPE_AI_LABEL_METER_ID,
        quantity=quantity,
        timestamp=datetime.utcnow()
    )
```

---

## Monitoring & Observability

### Built-in Health Checks

```bash
# Application health
GET /health
GET /health/db
GET /health/redis
GET /health/openai  # AML-specific

# Response includes:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "openai": "connected",
  "timestamp": "2025-12-31T12:00:00Z",
  "version": "1.0.0"
}
```

### AML-Specific Metrics

```python
# Track in application
{
  "aml_labels_generated": 1340,
  "aml_high_risk_count": 42,
  "aml_avg_confidence": 0.88,
  "aml_expert_review_rate": 0.05,
  "aml_openai_api_calls": 1340,
  "aml_openai_avg_latency_ms": 450,
  "aml_processing_time_seconds": 234.5
}
```

### Structured Logging

All logs are structured JSON using structlog:
```json
{
  "timestamp": "2025-12-31T12:00:00Z",
  "level": "INFO",
  "service": "aml-service",
  "job_id": "uuid-here",
  "tenant_id": "tenant-uuid",
  "message": "AML labeling completed",
  "risk_distribution": {"LOW": 400, "MEDIUM": 600, "HIGH": 200, "CRITICAL": 140},
  "duration_ms": 12345
}
```

### Optional: Prometheus Metrics

Enable in `docker-compose.prod.yml`:
```yaml
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./docker/prometheus.yml:/etc/prometheus/prometheus.yml
```

### Optional: Grafana Dashboards

```yaml
grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  environment:
    GF_SECURITY_ADMIN_PASSWORD: admin
```

---

## Security Best Practices

### Network Security

1. **Firewall Rules**
   ```bash
   # Allow only 80 and 443
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw default deny incoming
   sudo ufw enable
   ```

2. **HTTPS/TLS**
   - Nginx auto-enables HTTPS
   - Use Let's Encrypt (free, automated)
   - Certificate auto-renewal via certbot

3. **Database Security**
   - Non-root user: `foundry_user`
   - Strong password (32+ characters)
   - Network isolated (not exposed externally)
   - Multi-tenant isolation enforced at application level

### Application Security

1. **API Key Management**
   - Store API keys in environment variables
   - Never commit `.env` to git
   - Use separate keys for dev/staging/production
   - Rotate keys periodically
   - Use SecretManager for encrypted secrets

2. **Authentication**
   - JWT tokens with configurable expiry (default 30 minutes)
   - Tenant isolation via tenant_id
   - API key rotation support

3. **Input Validation**
   - Pydantic schemas validate all inputs
   - File size limits enforced
   - File type whitelist (CSV, JSON, XLSX, Parquet)
   - Rate limiting per tenant

4. **CORS Configuration**
   - Explicit allowed origins (production only)
   - No wildcard * in production
   - Credentials not shared cross-origin

### Data Security

1. **PII Redaction**
   - Microsoft Presidio for PII detection
   - Redact names, emails, phone numbers from AI input
   - Keep transaction IDs, amounts, countries (regulatory fields)

2. **Soft Deletes**
   - `is_deleted` flag on all AML tables
   - Track `deleted_by` and `deleted_at` if implemented
   - Hard delete after retention period

3. **Audit Trail**
   - All label changes logged
   - Timestamp on every record
   - Methodology version tracking

### Compliance

1. **Regulatory Alignment**
   - FATF R.10 typologies
   - FinCEN SAR requirements
   - Configurable for other jurisdictions

2. **Audit Readiness**
   - Every label has methodology version
   - AI reasoning stored for explainability
   - Expert review workflow tracked
   - Audit reports auto-generated

3. **Data Retention**
   - Configurable retention periods
   - Automated archival of old data
   - Secure deletion procedures

---

## Scaling & Performance

### Horizontal Scaling

**Add More Instances**:
```yaml
# docker-compose.prod.yml
api:
  deploy:
    replicas: 3
worker:
  deploy:
    replicas: 2
```

**Load Balancing**:
- Nginx round-robin across instances
- Job polling with optimistic locking
- Connection pooling to database

### Vertical Scaling

**Increase Resources**:
```yaml
api:
  deploy:
    resources:
      limits:
        cpus: '4.0'
        memory: 8G
      reservations:
        cpus: '2.0'
        memory: 4G
```

### Performance Optimization

1. **Batch Processing**
   - Process 100-1000 transactions per OpenAI batch
   - Bulk insert to database (1000+ records)
   - Parallel task execution in Prefect

2. **Database Optimization**
   - Connection pooling (50+ connections in production)
   - Indexed columns (tenant_id, job_id, risk_level)
   - Query optimization with EXPLAIN ANALYZE

3. **Caching Strategy**
   - Redis cache for methodology versions
   - Cache regulatory reference data
   - Cache frequently accessed labels

4. **OpenAI Optimization**
   - Use `gpt-4o-mini` for high-volume (cheaper)
   - Batch completions for efficiency
   - Implement request queueing during peak

### Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| Labeling throughput | 100 tx/sec | ~85 tx/sec |
| API response time | <200ms | ~150ms |
| Database query time | <50ms | ~35ms |
| OpenAI latency | <500ms | ~420ms |
| End-to-end processing | <5min/1000 tx | ~4min/1000 tx |

---

## Troubleshooting

### Common Issues

#### 1. OpenAI API Connection Fails
```bash
# Check API key is valid
docker-compose exec api env | grep OPENAI_API_KEY

# Test OpenAI connection
docker-compose exec api python -c "
from src.services.ai_service import AIService
import asyncio
asyncio.run(AIService().health_check())
"

# Verify rate limits
# Check: https://platform.openai.com/usage
```

#### 2. AML Labels Not Saving
```bash
# Check database connection
docker-compose exec api psql $DATABASE_URL -c "SELECT 1"

# Verify migrations applied
docker-compose exec api psql $DATABASE_URL \
  -c "\dt aml_transaction_labels"

# Check for unique constraint violations
docker-compose logs api | grep "unique constraint"

# Run migration 004 if not applied
docker-compose exec api python -m src.database.migrations.004_add_unique_constraint_aml_labels upgrade
```

#### 3. Background Worker Not Processing Jobs
```bash
# Check worker is running
docker-compose ps worker

# View worker logs
docker-compose logs -f worker

# Check for pending jobs
docker-compose exec api psql $DATABASE_URL \
  -c "SELECT * FROM processing_jobs WHERE status = 'PENDING' LIMIT 10;"

# Restart worker
docker-compose restart worker
```

#### 4. High Memory Usage
```bash
# Check Docker stats
docker stats

# Reduce connection pool
DATABASE_POOL_SIZE=20  # from 50

# Reduce worker concurrency
PREFECT_WORKER_CONCURRENCY=5  # from 10
```

#### 5. Slow AML Labeling
```bash
# Check OpenAI latency
docker-compose logs api | grep "OpenAI latency"

# Switch to gpt-4o-mini for speed
OPENAI_MODEL=gpt-4o-mini

# Increase batch size
DEFAULT_BATCH_SIZE=200  # from 100
```

### Debug Commands

```bash
# Interactive shell in application
docker-compose exec api bash

# View environment variables
docker-compose exec api env | grep AML

# Test database from app
docker-compose exec api python -c "
from src.database.connection import db_connection
import asyncio
asyncio.run(db_connection.initialize())
print('Database connection OK')
"

# Check AML tables
docker-compose exec api psql $DATABASE_URL \
  -c "SELECT COUNT(*) FROM aml_transaction_labels;"

# Run AML tests
docker-compose exec api pytest tests/tasks/test_ingestion_p01_006_integration.py -v
```

### Log Analysis

```bash
# Filter by AML service
docker-compose logs api | grep "aml"

# Follow live logs
docker-compose logs -f api worker

# Last 100 lines
docker-compose logs --tail=100 api

# Errors only
docker-compose logs api | grep ERROR

# Search by job ID
docker-compose logs api | grep "job_id=YOUR_JOB_ID"
```

---

## Deployment Verification

### Post-Deployment Checklist

```bash
# 1. All services running
docker-compose ps
# Expected: all services in "Up" state

# 2. Database connectivity
curl http://localhost:8000/health/db
# Expected: {"status": "healthy", "database": "connected"}

# 3. OpenAI connectivity
curl http://localhost:8000/health/openai
# Expected: {"status": "healthy", "openai": "connected"}

# 4. AML tables exist
docker-compose exec api psql $DATABASE_URL \
  -c "\dt aml_*"
# Expected: 4 tables (aml_transaction_labels, aml_expert_reviews, etc.)

# 5. API responding
curl http://localhost:8000/api/v1/jobs
# Expected: HTTP 200 (or 401 if auth required)

# 6. Worker processing jobs
docker-compose logs worker | grep "Processing job"
# Expected: Recent log entries

# 7. No error logs
docker-compose logs api | grep ERROR | wc -l
# Expected: 0 (or very few)

# 8. Migrations applied
# Check if migrations can be queried
docker-compose exec api python -c "
import asyncio
from src.database.connection import db_connection
from sqlalchemy import text

async def check():
    await db_connection.initialize()
    async with db_connection.get_connection() as conn:
        result = await conn.execute(text(\"\"\"
            SELECT COUNT(*) FROM aml_transaction_labels
        \"\"\"))
        print(f'AML labels table accessible: {result.scalar()}')

asyncio.run(check())
"
```

### AML Service Smoke Test

```bash
# Upload test CSV
curl -X POST http://localhost:8000/api/v1/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@tests/fixtures/aml_test_transactions.csv"

# Get job ID from response
JOB_ID="returned-job-id"

# Poll job status
curl http://localhost:8000/api/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer YOUR_TOKEN"

# Wait for status=COMPLETE, then download results
curl http://localhost:8000/api/v1/jobs/$JOB_ID/results \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o aml_results.csv

# Verify results
head -20 aml_results.csv
# Expected: CSV with AML labels, risk levels, typologies
```

---

## Support & Resources

- **OpenAI Documentation**: https://platform.openai.com/docs
- **Anthropic Documentation**: https://docs.anthropic.com/
- **OpenRouter Documentation**: https://openrouter.ai/docs
- **Prefect Documentation**: https://docs.prefect.io/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **FATF Guidance**: https://www.fatf-gafi.org/
- **FinCEN SAR**: https://www.fincen.gov/files/SAR_Overview_Fact_Sheet.pdf
- **Project Repository**: [your-repo-url]
- **Issue Tracker**: [your-issue-tracker]

---

**Document Version:** 2.0
**Created:** December 31, 2025
**Last Updated:** December 31, 2025
**Status:** Aligned with actual codebase - Ready for production deployment
