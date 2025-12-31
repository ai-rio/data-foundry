# Data Quality Service - Infrastructure & Deployment Guide

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Technology Stack](#technology-stack)
3. [Deployment Options](#deployment-options)
4. [Local Development Setup](#local-development-setup)
5. [Production Deployment](#production-deployment)
6. [Environment Configuration](#environment-configuration)
7. [Database Setup](#database-setup)
8. [Docker Configuration](#docker-configuration)
9. [Monitoring & Observability](#monitoring--observability)
10. [Security Best Practices](#security-best-practices)
11. [Scaling & Performance](#scaling--performance)
12. [Troubleshooting](#troubleshooting)

---

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────┐
│                    Client Applications                  │
│              (Web, Mobile, API Consumers)               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Nginx Reverse Proxy                        │
│         (SSL/TLS, Load Balancing, Rate Limiting)       │
└────────────────────┬────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
    ┌─────────────┐      ┌─────────────┐
    │  FastAPI    │      │  FastAPI    │
    │  Instance 1 │ ...  │  Instance N │
    │  (Port 8000)│      │  (Port 8000)│
    └──────┬──────┘      └──────┬──────┘
           │                    │
           └────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │   PostgreSQL 15      │
         │  (Data Persistence)  │
         │  Port: 5432          │
         └──────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    ┌─────────┐          ┌──────────┐
    │  Redis  │          │ Analytics│
    │ Caching │          │  Views   │
    │Port 6379│          │(Optional)│
    └─────────┘          └──────────┘
```

### Service Components

1. **API Gateway Layer**: Nginx + FastAPI middleware
2. **Validation Engine**: Core quality validation logic
3. **Quota Manager**: Rate limiting and resource management
4. **Analytics Service**: Quality metrics and reporting
5. **Webhook Dispatcher**: Event notification system
6. **Database Layer**: PostgreSQL with RLS (Row-Level Security)
7. **Authentication**: JWT Bearer tokens + Tenant isolation
8. **Rate Limiting**: Token bucket algorithm

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

### Caching & Queuing
- **Cache**: Redis 7-alpine
- **Task Queue**: Celery 5.3.0 (optional for async jobs)
- **Message Broker**: Redis/RabbitMQ

### Data Processing
- **Data Loading**: dlt 1.20.0
- **Data Analysis**: pandas 2.1.0
- **Data Validation**: Pydantic 2.12.0

### Monitoring & Observability
- **Structured Logging**: structlog 25.5.0
- **Metrics**: Prometheus (optional)
- **Dashboards**: Grafana (optional)
- **Health Checks**: Built-in health check endpoints

### Security
- **Authentication**: python-jose 3.3.0 + JWT
- **Password Hashing**: passlib 1.7.4
- **Encryption**: cryptography 44.0.3
- **Secrets Management**: python-dotenv + custom SecretManager

### Development Tools
- **Testing**: pytest 9.0.2, pytest-asyncio 1.3.0
- **Linting**: ruff 0.14.10, flake8 7.3.0
- **Code Formatting**: black 25.12.0, isort 5.13.2
- **Type Checking**: mypy 1.19.1

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
- Nginx reverse proxy with SSL/TLS

**Time to Deploy**: 30 minutes (with environment setup)

### Option 3: Kubernetes (Enterprise)
**Best For**: Large-scale deployments, multi-region, DevOps teams
- Horizontal pod autoscaling
- Load balancing
- Blue-green deployments
- Advanced networking

**Time to Deploy**: 2-4 hours (requires K8s cluster)

### Option 4: Platform as a Service (Easiest)
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

### Step 3: Update .env for Development

```env
# Core Settings
ENVIRONMENT=development
DEBUG=true
APP_NAME=Data Foundry

# Database (Docker will provide this)
DATABASE_URL=postgresql://foundry_user:foundry_password@db:5432/data_foundry
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Redis (Docker will provide this)
REDIS_URL=redis://redis:6379/0

# JWT Secret (generate a random string)
SECRET_KEY=your-random-secret-key-here-min-32-chars

# Quality Service Settings
ENABLE_DATA_VALIDATION=true
MIN_QUALITY_SCORE=0.5
CONFIDENCE_THRESHOLD=0.85
MAX_FILE_SIZE_MB=100

# Optional: API Keys (if using external services)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=ant-...
```

### Step 4: Start Services with Docker Compose

```bash
# Start all services
docker-compose up -d

# Watch logs
docker-compose logs -f app

# Check service status
docker-compose ps
```

### Step 5: Initialize Database

```bash
# Run migrations
docker-compose exec app python -m src.database.migrations.run_migrations upgrade

# Check migration status
docker-compose exec app python -m src.database.migrations.run_migrations status

# Seed test data (dev only)
docker-compose exec app python -m src.database.seed_dev_data
```

### Step 6: Access Application

- **API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Development Workflow

```bash
# Run tests
docker-compose exec app pytest

# Run with code coverage
docker-compose exec app pytest --cov=src

# Format code
docker-compose exec app black src/ tests/

# Lint code
docker-compose exec app ruff check src/ tests/

# Type checking
docker-compose exec app mypy src/

# Or use Makefile shortcuts
make test
make lint
make format
make type-check
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

- **Server**: VPS with 2GB+ RAM, 2+ CPUs
- **Domain Name**: With DNS configured
- **SSL Certificate**: Let's Encrypt (free) or commercial
- **PostgreSQL Backup Strategy**: Automated backups
- **Monitoring**: Basic health checks

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
```

### Step 2: Prepare Environment Variables

```bash
# Create secure environment file
nano .env.production

# Critical variables to set:
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<generate-strong-random-key>
DATABASE_URL=postgresql://prod_user:STRONG_PASSWORD@db:5432/data_foundry_prod
REDIS_URL=redis://redis:6379/0

# HTTPS Configuration
DOMAIN_NAME=yourdomain.com
SSL_EMAIL=ssl@yourdomain.com

# Cors origins for production
CORS_ORIGINS=["https://yourdomain.com"]

# Rate limiting
SECURITY_RATE_LIMIT_RPM=1000

# Monitoring
ENVIRONMENT=production
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### Step 3: Deploy with Docker Compose

```bash
# Use production configuration
docker-compose -f docker-compose.prod.yml up -d

# Verify all services running
docker-compose ps

# Check logs
docker-compose logs -f app

# Run migrations
docker-compose -f docker-compose.prod.yml exec app \
  python -m src.database.migrations.run_migrations upgrade
```

### Step 4: Configure Nginx (SSL/TLS)

```bash
# Nginx configuration is in docker-compose.prod.yml
# It automatically:
# - Terminates SSL/TLS
# - Proxies to FastAPI on port 8000
# - Handles rate limiting
# - Sets security headers

# Verify nginx is proxying correctly
curl https://yourdomain.com/health
```

### Step 5: Setup Automated Backups

```bash
# Create backup script
cat > backup-postgres.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T db pg_dump -U foundry_user data_foundry | \
  gzip > $BACKUP_DIR/backup_$TIMESTAMP.sql.gz
# Keep only last 7 backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
EOF

chmod +x backup-postgres.sh

# Add to crontab (daily at 2 AM)
(crontab -l; echo "0 2 * * * /path/to/backup-postgres.sh") | crontab -
```

### Step 6: Monitor Application

```bash
# Health check endpoint
curl https://yourdomain.com/health

# Check database connectivity
curl https://yourdomain.com/api/v1/health/db

# View logs in real-time
docker-compose logs -f app

# Check resource usage
docker stats
```

### Deployment Checklist

- [ ] Environment variables configured
- [ ] Database initialized and migrated
- [ ] SSL/TLS certificate installed
- [ ] Nginx reverse proxy configured
- [ ] Firewall rules configured (80, 443 open)
- [ ] Backup strategy in place
- [ ] Monitoring and alerts configured
- [ ] Health checks passing
- [ ] Load testing completed (optional)
- [ ] Incident response plan documented

---

## Environment Configuration

### Required Variables (Production)

```env
# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=<32+ character random string>
APP_NAME=Data Foundry
API_V1_STR=/api/v1

# Database
DATABASE_URL=postgresql://user:password@host:5432/database
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
DATABASE_POOL_TIMEOUT=30

# Redis
REDIS_URL=redis://host:6379/0

# JWT/Security
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

### Optional but Recommended

```env
# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
METRICS_PORT=9090

# CORS
CORS_ORIGINS=["https://yourdomain.com"]

# Rate Limiting
SECURITY_RATE_LIMIT_RPM=1000
SECURITY_RATE_LIMIT_BURST=100

# Data Validation
ENABLE_DATA_VALIDATION=true
MIN_QUALITY_SCORE=0.5
MAX_FILE_SIZE_MB=100
```

### Complete Reference

See `.env.example` for all 60+ configuration options with descriptions.

---

## Database Setup

### PostgreSQL Initialization

The database is automatically initialized via `docker-compose` with:
- User creation
- Database creation
- Extensions enabled (UUID, JSON, etc.)
- Initial schema

### Migrations

```bash
# Run all pending migrations
docker-compose exec app python -m src.database.migrations.run_migrations upgrade

# Run specific migration
docker-compose exec app python -m src.database.migrations.run_migrations upgrade migration_name

# Rollback last migration
docker-compose exec app python -m src.database.migrations.run_migrations downgrade

# Check status
docker-compose exec app python -m src.database.migrations.run_migrations status

# Reset database (WARNING: destructive)
docker-compose exec app python -m src.database.migrations.run_migrations reset
```

### Connection Pool Tuning

**Development** (docker-compose.yml):
```
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

**Production** (docker-compose.prod.yml):
```
DATABASE_POOL_SIZE=50
DATABASE_MAX_OVERFLOW=100
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=3600
```

Adjust based on:
- Expected concurrent users
- API endpoint response times
- Database server resources

---

## Docker Configuration

### Development (docker-compose.yml)

Includes:
- PostgreSQL 15 (port 5433)
- Redis 7 (port 6380)
- FastAPI app (port 8000)
- Hot-reload volumes
- Test data seeding
- Debug mode enabled

### Production (docker-compose.prod.yml)

Includes:
- PostgreSQL 15 (port 5432)
- Redis 7 (port 6379)
- FastAPI app (no external port, accessed via Nginx)
- Nginx reverse proxy (ports 80, 443)
- Resource limits
- Restart policies
- Health checks
- Prometheus metrics (optional)
- Grafana dashboards (optional)

### Service Configuration

```yaml
# FastAPI Application
app:
  build: .
  image: data-foundry:latest
  ports:
    - "8000:8000"
  environment:
    - ENVIRONMENT=production
  volumes:
    - ./logs:/app/logs
  depends_on:
    - db
    - redis

# PostgreSQL Database
db:
  image: postgres:15-alpine
  environment:
    POSTGRES_USER: foundry_user
    POSTGRES_PASSWORD: ${DB_PASSWORD}
    POSTGRES_DB: data_foundry
  volumes:
    - postgres_data:/var/lib/postgresql/data

# Redis Cache
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data

# Nginx Reverse Proxy (Production only)
nginx:
  image: nginx:latest
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./docker/nginx.conf:/etc/nginx/nginx.conf
    - ./certs:/etc/nginx/certs
```

---

## Monitoring & Observability

### Built-in Health Checks

```bash
# Application health
GET /health
GET /health/db
GET /health/redis

# Response includes:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

### Structured Logging

All logs are structured JSON:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "service": "data-quality",
  "request_id": "uuid-here",
  "message": "Request processed",
  "duration_ms": 45
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
    - prometheus_data:/prometheus
  profiles:
    - monitoring
```

Access metrics at: http://localhost:9090

### Optional: Grafana Dashboards

```yaml
grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
  environment:
    GF_SECURITY_ADMIN_PASSWORD: admin
  profiles:
    - monitoring
```

Enable optional services:
```bash
docker-compose -f docker-compose.prod.yml --profile monitoring up -d
```

---

## Security Best Practices

### Network Security

1. **Firewall Rules** (Recommended)
   ```bash
   # Allow only 80 and 443
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw default deny incoming
   ```

2. **HTTPS/TLS**
   - Nginx auto-enables HTTPS
   - Use Let's Encrypt (free, automated)
   - Certificate auto-renewal via certbot

3. **Database Security**
   - Non-root user: `foundry_user`
   - Strong password (32+ characters)
   - Network isolated (not exposed externally)
   - RLS (Row-Level Security) enabled per tenant

### Application Security

1. **Secrets Management**
   - Never commit `.env` to git
   - Use `.env.example` for templates
   - All secrets encrypted in `.env.local`
   - Access via SecretManager

2. **Authentication**
   - JWT tokens with 30-minute expiry
   - Refresh tokens for long-lived sessions
   - Tenant isolation via RLS
   - API key rotation support

3. **Input Validation**
   - Pydantic schemas validate all inputs
   - File size limits enforced
   - File type whitelist
   - Rate limiting per tenant

4. **CORS Configuration**
   - Explicit allowed origins (production only)
   - No wildcard * in production
   - Credentials not shared cross-origin

### Operational Security

1. **Backup & Recovery**
   - Daily automated backups
   - Test restore procedure monthly
   - Keep backups off-server
   - 30-day retention minimum

2. **Access Control**
   - SSH key-based authentication (no passwords)
   - Non-root Docker containers
   - Least-privilege permissions
   - Audit logging of admin actions

3. **Monitoring & Alerting**
   - Real-time error rate monitoring
   - Database performance alerts
   - Disk space warnings
   - Uptime monitoring

---

## Scaling & Performance

### Horizontal Scaling

**Add More Instances**:
```yaml
# docker-compose.prod.yml
app:
  deploy:
    replicas: 3
  # Nginx automatically load-balances
```

**Load Balancing**:
- Nginx round-robin across instances
- Sticky sessions via JWT
- Connection pooling to database

### Vertical Scaling

**Increase Resources**:
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
```

### Caching Strategy

1. **Query Results** (Redis)
   ```python
   @cache(ttl=3600)
   async def get_validation_stats():
       # Cached for 1 hour
   ```

2. **Database Indexes** (PostgreSQL)
   ```sql
   CREATE INDEX idx_quality_scores ON validation_results(score);
   CREATE INDEX idx_tenant_date ON validation_results(tenant_id, created_at);
   ```

3. **Connection Pooling**
   ```
   DATABASE_POOL_SIZE=50      # Tune based on load
   REDIS_MAX_CONNECTIONS=20
   ```

### Performance Optimization

1. **Batch Operations**
   - Process multiple validations per request
   - Bulk insert to database
   - Async task processing

2. **Pagination**
   - Limit: 100 results per page
   - Offset or cursor-based
   - Indexed columns only

3. **Query Optimization**
   - Use appropriate indexes
   - Avoid N+1 queries
   - Denormalize when needed

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Fails
```bash
# Check PostgreSQL is running
docker-compose ps db

# View database logs
docker-compose logs db

# Test connection
docker-compose exec app psql postgresql://foundry_user:password@db:5432/data_foundry

# Reset database
docker-compose down -v
docker-compose up -d
docker-compose exec app python -m src.database.migrations.run_migrations upgrade
```

#### 2. Redis Connection Fails
```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec app redis-cli -h redis ping
# Should output: PONG

# Clear Redis cache (if needed)
docker-compose exec redis redis-cli FLUSHALL
```

#### 3. API Returns 500 Errors
```bash
# Check application logs
docker-compose logs -f app

# Check for missing environment variables
docker-compose exec app env | grep DATABASE_URL

# Verify database schema
docker-compose exec app python -m src.database.migrations.run_migrations status
```

#### 4. High Memory Usage
```bash
# Check Docker stats
docker stats

# Check if migrations completed
docker-compose logs app | grep "migration"

# Reduce connection pool if needed
DATABASE_POOL_SIZE=20  # from 50
```

#### 5. Slow Queries
```bash
# Enable SQL logging (development only)
LOG_LEVEL=DEBUG
DATABASE_ECHO_SQL=true

# View slow query logs
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"

# Add indexes if needed
docker-compose exec db psql -U foundry_user -d data_foundry \
  -c "CREATE INDEX idx_column ON table(column);"
```

### Debug Commands

```bash
# Interactive shell in application
docker-compose exec app bash

# View environment variables
docker-compose exec app env

# Test database from app
docker-compose exec app python -c "from src.core.database import db_connection; print(db_connection.test_connection())"

# Check dependencies
docker-compose exec app pip list

# Run tests with verbose output
docker-compose exec app pytest -v --tb=short
```

### Log Analysis

```bash
# Filter by service
docker-compose logs app

# Follow live logs
docker-compose logs -f app

# Last 100 lines
docker-compose logs --tail=100 app

# Errors only
docker-compose logs app | grep ERROR

# Search by timestamp
docker-compose logs app --since 2024-01-01T00:00:00
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
# Expected: {"status": "healthy"}

# 3. API responding
curl http://localhost:8000/api/v1/quality
# Expected: HTTP 200 (or 401 if auth required)

# 4. Swagger documentation available
curl http://localhost:8000/docs
# Expected: HTML Swagger UI

# 5. No error logs
docker-compose logs app | grep ERROR | wc -l
# Expected: 0 (or very few)

# 6. Database migrations applied
docker-compose exec app python -m src.database.migrations.run_migrations status
# Expected: "All migrations applied"

# 7. Redis connectivity
docker-compose exec redis redis-cli ping
# Expected: PONG
```

---

## Next Steps

1. **Configure Monitoring**: Set up health checks and alerts
2. **Setup Backups**: Implement automated PostgreSQL backups
3. **Configure CI/CD**: Add GitHub Actions or GitLab CI
4. **Load Testing**: Use k6 or Apache JMeter to test scalability
5. **Documentation**: Customize this guide for your infrastructure

---

## Support & Resources

- **Docker Documentation**: https://docs.docker.com/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Project Repository**: [your-repo-url]
- **Issue Tracker**: [your-issue-tracker]
