# Phase 6.5 Docker Testing Setup Guide

## Overview

This guide covers the Docker configuration for Phase 6.5 validation testing, including GDPR compliance load testing and production deployment configurations.

## 🐳 Docker Configuration Files

### 1. Development & Testing (`docker-compose.yml`)
- **Purpose**: Development environment with all services
- **Services**: API, Database, Redis, Label Studio, Prefect
- **GDPR Features**: Enabled with development settings

### 2. Load Testing (`docker-compose.loadtest.yml`)
- **Purpose**: Load testing with K6 integration
- **Services**: Full stack + K6 testing services
- **Profiles**: `general-load` and `gdpr-load`

### 3. Production (`docker-compose.prod.yml`)
- **Purpose**: Production-ready deployment
- **Features**: Enhanced security, monitoring, performance optimization

## 🚀 Quick Start Commands

### Start Development Environment
```bash
# Start all development services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Run Load Testing

#### General Load Testing
```bash
# Start full stack with general load testing
docker-compose -f docker-compose.loadtest.yml --profile general-load up -d

# Run general load test
docker-compose -f docker-compose.loadtest.yml run --rm k6

# Stop services
docker-compose -f docker-compose.loadtest.yml down
```

#### GDPR Compliance Load Testing
```bash
# Start full stack with GDPR load testing
docker-compose -f docker-compose.loadtest.yml --profile gdpr-load up -d

# Generate test token first
curl http://localhost:8000/test-token

# Run GDPR compliance test (replace TOKEN with actual token)
API_TOKEN=your_token_here docker-compose -f docker-compose.loadtest.yml run --rm k6-gdpr

# View results
ls -la results/gdpr-compliance.json
```

### Production Deployment
```bash
# Start production environment
docker-compose -f docker-compose.prod.yml up -d

# Start with monitoring
docker-compose -f docker-compose.prod.yml --profile monitoring up -d

# Production health checks
curl http://localhost/health
```

## 🔧 Environment Configuration

### Required Environment Variables

Create `.env` file for production:

```bash
# Database Configuration
DB_USER=foundry_user
DB_PASSWORD=your_secure_password_here
DB_NAME=data_foundry

# Security (REQUIRED for GDPR)
SECRET_KEY=your_production_secret_key_min_32_chars
IP_HASH_SALT=your_gdpr_compliance_salt_min_32_chars

# API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Label Studio
LABEL_STUDIO_USERNAME=admin
LABEL_STUDIO_PASSWORD=secure_password

# Monitoring (optional)
GRAFANA_PASSWORD=secure_grafana_password
```

### GDPR Compliance Settings

All Docker configurations include these GDPR settings:

```yaml
environment:
  - IP_HASH_SALT=gdpr-compliance-salt-min-32-chars
  - ENABLE_GDPR_AUDIT_LOGGING=true
  - GDPR_CONSENT_STORAGE_RETENTION_DAYS=2555
  - DATABASE_POOL_SIZE=20-50
  - ENABLE_RATE_LIMITING=true
  - RATE_LIMIT_REQUESTS_PER_MINUTE=100-1000
```

## 📊 Load Testing Details

### General Load Test (`k6-ramp-up.js`)
- **Pattern**: 50→500 RPS over 20 minutes
- **Endpoint**: `/api/v1/process`
- **SLAs**: P99 <2200ms, error rate <0.05%
- **Output**: `results/general-load.json`

### GDPR Compliance Load Test (`gdpr-compliance-k6.js`)
- **Endpoints**:
  - `POST /api/v1/consent/record` (Article 7)
  - `GET /api/v1/consent/verify`
  - `POST /api/v1/data-subject/erasure` (Article 17)
  - `GET /api/v1/audit/trail`
  - `POST /api/v1/consent/withdraw` (Article 7.3)
- **SLAs**: P99 <1500ms, error rate <0.1%
- **Output**: `results/gdpr-compliance.json`

### Test Execution Commands

```bash
# Test token generation (development only)
curl http://localhost:8000/test-token

# Run with custom parameters
docker-compose -f docker-compose.loadtest.yml run \
  -e BASE_URL=http://api:8000 \
  -e API_TOKEN=your_token \
  --rm k6-gdpr

# Run specific test duration
docker-compose -f docker-compose.loadtest.yml run \
  k6 run --duration 5m tests/load/gdpr-compliance-k6.js
```

## 🔍 Health Checks & Monitoring

### Service Health Endpoints

```bash
# API Health
curl http://localhost:8000/health

# Database Health (from container)
docker-compose exec db pg_isready -U foundry_user -d data_foundry

# Redis Health
docker-compose exec redis redis-cli ping

# All services status
docker-compose ps
```

### Log Monitoring

```bash
# Follow API logs
docker-compose logs -f api

# Follow GDPR audit logs
docker-compose logs api | grep AUDIT

# Database logs
docker-compose logs -f db

# Error logs only
docker-compose logs api | grep ERROR
```

### Performance Monitoring (Production)

```bash
# Access Grafana Dashboard
open http://localhost:3000
# Username: admin
# Password: (from GRAFANA_PASSWORD env var)

# Access Prometheus
open http://localhost:9090

# System resource usage
docker stats
```

## 🛠️ Troubleshooting

### Common Issues

#### Port Conflicts
```bash
# Check what's using ports
netstat -tulpn | grep :8000
sudo lsof -i :8000

# Kill conflicting processes
sudo kill -9 <PID>
```

#### Database Connection Issues
```bash
# Check database container
docker-compose exec db psql -U foundry_user -d data_foundry -c "SELECT 1;"

# Reset database
docker-compose down -v
docker-compose up -d db
```

#### Permission Issues
```bash
# Fix log directory permissions
sudo mkdir -p logs
sudo chown -R $USER:$USER logs

# Fix results directory permissions
mkdir -p results
chmod 755 results
```

#### Memory Issues
```bash
# Check system resources
docker system df
docker system prune -a

# Increase Docker memory limits (Docker Desktop settings)
# Settings > Resources > Memory > 4GB+
```

### Debug Mode

```bash
# Start with debug logs
docker-compose up --build

# Enter container for debugging
docker-compose exec api sh

# View detailed container info
docker inspect data_foundry_api
```

## 📈 Performance Tuning

### Database Optimization
```bash
# Check database connections
docker-compose exec db psql -U foundry_user -d data_foundry -c "
SELECT count(*) FROM pg_stat_activity;
"

# Monitor slow queries
docker-compose exec db psql -U foundry_user -d data_foundry -c "
SELECT query, mean_time, calls
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"
```

### API Performance
```bash
# Monitor response times
curl -w "@curl-format.txt" http://localhost:8000/api/v1/consent/record

# Concurrent requests testing
for i in {1..10}; do
  curl -s http://localhost:8000/health &
done
wait
```

## 🚨 Security Notes

### Production Security Checklist
- [ ] Change default passwords
- [ ] Use SSL/TLS certificates
- [ ] Enable firewall rules
- [ ] Set up log rotation
- [ ] Configure backup strategy
- [ ] Enable audit logging
- [ ] Set up monitoring alerts
- [ ] Review resource limits

### GDPR Compliance Validation
```bash
# Verify IP hash salt is configured
docker-compose exec api env | grep IP_HASH_SALT

# Check audit logging
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/audit/trail?limit=5

# Verify consent storage duration
docker-compose exec api env | grep GDPR_CONSENT_STORAGE_RETENTION_DAYS
```

## 📚 Additional Resources

- [Phase 6.5 Validation Roadmap](../docs/project-management/PHASE_6_5_VALIDATION_ROADMAP.md)
- [GDPR Implementation Matrix](../docs/compliance/gdpr-implementation/GDPR_IMPLEMENTATION_MATRIX.md)
- [Security Controls Documentation](../docs/security/SECURITY_CONTROLS.md)
- [Development Methodology](../docs/development/DEVELOPMENT_METHODOLOGY.md)

---

**Next Steps**: Execute Week 1 of Phase 6.5 validation plan using the provided Docker infrastructure.