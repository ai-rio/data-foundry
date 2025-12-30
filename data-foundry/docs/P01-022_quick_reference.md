# P01-022: Deploy to Staging - Quick Reference

## Quick Commands

### Start Services
```bash
cd /home/carlos/projects/data_foundry/data-foundry
docker compose up -d
```

### Stop Services
```bash
docker compose down
```

### Check Status
```bash
docker ps --filter "name=data_foundry"
```

### View Logs
```bash
# API logs
docker logs data_foundry_api -f

# Worker logs
docker logs data_foundry_worker -f

# Database logs
docker logs data_foundry_db -f
```

### Run Migrations
```bash
# Migration 001
docker exec data_foundry_api python -m src.database.migrations.add_aml_transaction_labels_table

# Migration 002
docker exec data_foundry_api python -m src.database.migrations.add_aml_audit_trail_tables

# Migration 003 (direct SQL)
docker exec data_foundry_db psql -U foundry_user -d data_foundry -c "
  ALTER TABLE aml_transaction_labels ADD COLUMN IF NOT EXISTS job_id VARCHAR;
  CREATE INDEX IF NOT EXISTS idx_aml_labels_job_id ON aml_transaction_labels(job_id);
  CREATE INDEX IF NOT EXISTS idx_aml_labels_job_tenant ON aml_transaction_labels(job_id, tenant_id);
"
```

### Verify Deployment
```bash
# Run automated verification
./scripts/deploy_staging.sh --verify-only

# Manual health check
curl http://localhost:8000/health

# Check AML endpoint
curl http://localhost:8000/api/v1/regulatory/aml-context

# Check database tables
docker exec data_foundry_db psql -U foundry_user -d data_foundry -c "\dt aml*"
```

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| API | http://localhost:8000 | - |
| API Docs | http://localhost:8000/docs | - |
| Database | localhost:5433 | foundry_user / foundry_password |
| Redis | localhost:6380 | - |
| Prefect UI | http://localhost:4200 | - |
| Label Studio | http://localhost:8080 | admin@datafoundry.com / admin123 |

## AML Tables

- `aml_transaction_labels` - Core labeling table with job_id
- `aml_expert_reviews` - Expert reviews for Cohen's Kappa
- `aml_audit_reports` - Generated compliance reports
- `aml_labeling_methodology` - Versioned AML rules

## Health Checks

### API Health
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "Data Foundry",
  "version": "1.0.0",
  "environment": "development"
}
```

### Database Health
```bash
docker exec data_foundry_db pg_isready -U foundry_user -d data_foundry
```

### Container Health
```bash
docker ps --filter "name=data_foundry" --format "table {{.Names}}\t{{.Status}}"
```

## Troubleshooting

### API Not Starting
```bash
# Check logs
docker logs data_foundry_api --tail 100

# Restart services
docker compose restart api

# Verify database is healthy
docker exec data_foundry_db pg_isready -U foundry_user -d data_foundry
```

### Database Connection Issues
```bash
# Verify database is running
docker ps | grep data_foundry_db

# Check database logs
docker logs data_foundry_db --tail 50

# Test connection
docker exec data_foundry_db psql -U foundry_user -d data_foundry -c "SELECT 1"
```

### Worker Not Processing Jobs
```bash
# Check worker logs
docker logs data_foundry_worker --tail 100

# Verify database connection
docker exec data_foundry_worker python -c "import asyncio; from src.database.connection import db_connection; asyncio.run(db_connection.initialize())"

# Check worker config
docker exec data_foundry_worker env | grep WORKER
```

### Migration Failures
```bash
# Check if tables exist
docker exec data_foundry_db psql -U foundry_user -d data_foundry -c "\dt aml*"

# Manually add job_id column
docker exec data_foundry_db psql -U foundry_user -d data_foundry -c "\d aml_transaction_labels"
```

## File Locations

- **Deployment Script:** `./scripts/deploy_staging.sh`
- **Deployment Report:** `./docs/P01-022_deployment_report.md`
- **Docker Compose:** `./docker-compose.yml`
- **Dockerfile:** `./Dockerfile`
- **Migrations:** `./src/database/migrations/`
- **AML Service Code:** `./src/api/v1/regulatory/`

## Quality Gates Checklist

- [✅] Docker image builds
- [✅] Migrations run successfully
- [✅] Services start without errors
- [✅] All endpoints respond
- [✅] Background worker active
- [✅] No critical errors

## Support

For issues or questions:
1. Check logs: `docker logs <container_name>`
2. Run verification: `./scripts/deploy_staging.sh --verify-only`
3. Review deployment report: `./docs/P01-022_deployment_report.md`
