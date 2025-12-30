# AML Database Migrations - Quick Reference

**Task:** P01-002 - Create Alembic Migrations
**Status:** ✅ Complete - Ready for QA
**Created:** December 30, 2025

---

## Migration Files

### Migration 001: `add_aml_transaction_labels_table.py`
Creates the core AML transaction labels table with:
- 14 columns (UUID, VARCHAR, DECIMAL, TEXT, JSONB, BOOLEAN, TIMESTAMP)
- 7 indexes (tenant_id, transaction_id, risk_level, expert_review_status, created_at, is_deleted partial, unique transaction)
- 3 CHECK constraints (confidence_score 0-1, risk_level enum, expert_review_status enum)
- 3 foreign keys (tenant CASCADE, transaction CASCADE, version SET NULL)

### Migration 002: `add_aml_audit_trail_tables.py`
Creates three audit trail tables:
1. **aml_expert_reviews** (10 columns, 5 indexes, 2 CHECK constraints, 3 FKs)
2. **aml_audit_reports** (12 columns, 4 indexes, 5 CHECK constraints, 2 FKs)
3. **aml_labeling_methodology** (11 columns, 5 indexes, 1 CHECK constraint, 2 FKs)

---

## Running Migrations

### Prerequisites
1. PostgreSQL database running and accessible
2. Database connection configured in `.env`
3. Base schema tables exist (tenants, users, processing_jobs)

### Execute Migrations

**Run Migration 001:**
```bash
cd /home/carlos/projects/data_foundry/data-foundry
python3 src/database/migrations/add_aml_transaction_labels_table.py
```

**Run Migration 002:**
```bash
python3 src/database/migrations/add_aml_audit_trail_tables.py
```

### Rollback Migrations

**Rollback Migration 002:**
```bash
python3 src/database/migrations/add_aml_audit_trail_tables.py downgrade
```

**Rollback Migration 001:**
```bash
python3 src/database/migrations/add_aml_transaction_labels_table.py downgrade
```

**Note:** Always rollback Migration 002 before Migration 001 (dependency order).

---

## Testing

### Run Test Suite
```bash
python3 test_aml_migrations.py
```

This will test:
- ✅ Table creation and structure
- ✅ All 21 indexes
- ✅ All 11 CHECK constraints
- ✅ All 10 foreign key relationships
- ✅ Idempotency (can re-run safely)
- ✅ Rollback functionality

### Manual Verification

**Check Tables:**
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_name LIKE 'aml_%';
```

**Check Indexes:**
```sql
SELECT indexname
FROM pg_indexes
WHERE indexname LIKE 'idx_aml_%';
```

**Check Constraints:**
```sql
SELECT constraint_name, table_name
FROM information_schema.table_constraints
WHERE constraint_name LIKE 'check_aml_%';
```

---

## Schema Reference

### aml_transaction_labels
```sql
id                      UUID PRIMARY KEY
transaction_id          UUID FK → aml_transactions(id)
tenant_id               UUID FK → tenants(id)
risk_level              VARCHAR(50) CHECK IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
typology                VARCHAR(100)
confidence_score        DECIMAL(3,2) CHECK (0 to 1)
ai_reasoning            TEXT
expert_review_status    VARCHAR(50) CHECK IN ('PENDING', 'AGREED', 'DISAGREED', 'ESCALATED')
regulatory_flags        JSONB
is_audit_ready          BOOLEAN
is_deleted              BOOLEAN
created_at              TIMESTAMP DEFAULT NOW()
updated_at              TIMESTAMP DEFAULT NOW()
version_id              UUID FK → aml_labeling_methodology(id)
```

### aml_expert_reviews
```sql
id                          UUID PRIMARY KEY
aml_transaction_label_id    UUID FK → aml_transaction_labels(id)
tenant_id                   UUID FK → tenants(id)
expert_id                   UUID FK → users(user_id)
expert_decision             VARCHAR(50) CHECK IN ('AGREE', 'DISAGREE', 'NEEDS_CLARIFICATION')
reasoning                   TEXT
confidence_level            DECIMAL(3,2) CHECK (0 to 1)
reviewed_at                 TIMESTAMP
is_deleted                  BOOLEAN
created_at                  TIMESTAMP DEFAULT NOW()
```

### aml_audit_reports
```sql
id                      UUID PRIMARY KEY
tenant_id               UUID FK → tenants(id)
job_id                  UUID FK → processing_jobs(id)
transaction_count       INTEGER CHECK (>= 0)
labeled_count           INTEGER CHECK (>= 0, <= transaction_count)
expert_reviewed_count   INTEGER CHECK (>= 0, <= labeled_count)
kappa_coefficient       DECIMAL(4,3) CHECK (-1 to 1)
agreement_level         VARCHAR(50) CHECK IN ('POOR', 'FAIR', 'MODERATE', 'SUBSTANTIAL', 'PERFECT')
generated_at            TIMESTAMP
report_url              VARCHAR(500)
is_deleted              BOOLEAN
created_at              TIMESTAMP DEFAULT NOW()
```

### aml_labeling_methodology
```sql
id                      UUID PRIMARY KEY
tenant_id               UUID FK → tenants(id)
version                 VARCHAR(20) UNIQUE (per tenant, when ACTIVE)
description             TEXT
risk_thresholds         JSONB
typologies              JSONB
regulatory_references   JSONB
created_by              UUID FK → users(user_id)
created_at              TIMESTAMP DEFAULT NOW()
status                  VARCHAR(50) CHECK IN ('DRAFT', 'ACTIVE', 'ARCHIVED')
is_deleted              BOOLEAN
```

---

## Troubleshooting

### Migration Fails: "Table already exists"
**Solution:** This is expected if migration was run before. Migrations are idempotent (safe to re-run).

### Migration Fails: "Foreign key constraint violation"
**Cause:** Referenced table doesn't exist (e.g., `tenants`, `aml_transactions`)
**Solution:** Create base schema first, or ignore FK errors (migrations use conditional FK creation)

### Migration Fails: "Connection refused"
**Cause:** PostgreSQL not running or wrong port
**Solution:**
```bash
docker ps | grep postgres
# Check port mapping (5432 or 5433)
# Update DATABASE_URL in .env if needed
```

### Rollback Fails: "Cannot drop table, dependent objects exist"
**Cause:** Other tables reference this table
**Solution:** Rollback dependent migrations first (e.g., rollback 002 before 001)

---

## Production Deployment

### Pre-deployment Checklist
- [ ] Backup database before migration
- [ ] Test migrations in staging environment
- [ ] Verify all dependent tables exist
- [ ] Schedule maintenance window for migration
- [ ] Prepare rollback plan

### Deployment Steps
1. Stop application services
2. Backup database: `pg_dump data_foundry > backup.sql`
3. Run Migration 001
4. Run Migration 002
5. Verify schema: `python3 test_aml_migrations.py`
6. Restart application services
7. Monitor logs for errors

### Rollback Plan
If deployment fails:
1. Stop application services
2. Run Migration 002 downgrade
3. Run Migration 001 downgrade
4. Restore from backup if needed: `psql data_foundry < backup.sql`
5. Investigate errors
6. Fix issues and retry

---

## Integration with Application

### Importing Migrations
```python
from src.database.migrations.add_aml_transaction_labels_table import upgrade as upgrade_001
from src.database.migrations.add_aml_audit_trail_tables import upgrade as upgrade_002

# Run migrations programmatically
import asyncio
asyncio.run(upgrade_001())
asyncio.run(upgrade_002())
```

### Using Created Tables
```python
from sqlalchemy import select
from src.database.connection import db_connection

# Example: Query AML labels
async with db_connection.get_session() as session:
    result = await session.execute(
        select("*").select_from("aml_transaction_labels")
        .where("tenant_id = :tenant_id")
        .where("is_deleted = FALSE")
        .params(tenant_id="tenant_001")
    )
    labels = result.fetchall()
```

---

## Documentation Links

- **Schema Design:** `docs/planning/SCHEMA_DESIGN.md`
- **Implementation Report:** `docs/planning/P01-002_MIGRATION_IMPLEMENTATION.md`
- **Test Script:** `test_aml_migrations.py`

---

**For Questions or Issues:**
- Review implementation report in `docs/planning/P01-002_MIGRATION_IMPLEMENTATION.md`
- Check schema design spec in `docs/planning/SCHEMA_DESIGN.md`
- Run test suite: `python3 test_aml_migrations.py`
- Contact: data-engineer agent (P01-002)
