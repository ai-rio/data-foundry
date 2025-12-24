"""
Test Tenant Isolation (PostgreSQL RLS)
Verify that Tenant A cannot access Tenant B's data
"""
import asyncio
import sys
sys.path.insert(0, '/home/carlos/projects/data_foundry/data-foundry')

import asyncpg
from datetime import datetime, timezone
import uuid

async def test_tenant_isolation():
    """Verify Tenant A cannot access Tenant B's data"""

    # Use the database connection from Docker
    DATABASE_URL = "postgresql://foundry_user:foundry_password@localhost:5433/data_foundry"

    # Generate test tenant IDs (using tenant_id VARCHAR field, not id INTEGER)
    tenant_a_id = str(uuid.uuid4())
    tenant_b_id = str(uuid.uuid4())
    # Use naive datetime for PostgreSQL timestamp without time zone columns
    now = datetime.utcnow()

    print(f"Testing tenant isolation:")
    print(f"  Tenant A ID: {tenant_a_id}")
    print(f"  Tenant B ID: {tenant_b_id}")

    try:
        # Step 1: Create tenants using raw asyncpg connection (no RLS needed for setup)
        conn = await asyncpg.connect(DATABASE_URL)

        try:
            # Create Tenant A with all required fields
            await conn.execute(
                """INSERT INTO tenants (tenant_id, name, status, max_users, max_data_records, storage_limit_gb,
                   enable_pii_redaction, enable_ai_labeling, enable_human_review, billing_plan, features, preferences,
                   created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                tenant_a_id, "Test Tenant A", "ACTIVE", 10, 100000, 10.0, True, True, True, "free", "{}", "{}", now, now
            )

            # Create Tenant B with all required fields
            await conn.execute(
                """INSERT INTO tenants (tenant_id, name, status, max_users, max_data_records, storage_limit_gb,
                   enable_pii_redaction, enable_ai_labeling, enable_human_review, billing_plan, features, preferences,
                   created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                tenant_b_id, "Test Tenant B", "ACTIVE", 10, 100000, 10.0, True, True, True, "free", "{}", "{}", now, now
            )
            print("✅ Created test tenants")

            # Step 2: Create data record for Tenant A (using SET LOCAL for RLS)
            async with conn.transaction():
                # Set tenant context for Tenant A
                # NOTE: SET LOCAL does not support parameterized queries, use escaped literal
                escaped_tenant_a_id = tenant_a_id.replace("'", "''")
                await conn.execute(f"SET LOCAL app.tenant_id = '{escaped_tenant_a_id}'")

                # Insert record - RLS policy allows this because tenant_id matches
                record_id = str(uuid.uuid4())
                await conn.execute(
                    """INSERT INTO data_records
                       (record_id, tenant_id, raw_data, status, data_source,
                        pii_detected, pii_redacted, retry_count, created_at, updated_at,
                        access_count, requires_review, gdpr_relevant, legal_hold)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
                    record_id, tenant_a_id, '{"field": "tenant A sensitive data"}', "RAW", "API",
                    False, False, 0, now, now, 0, False, False, False
                )
                print("✅ Created data record for Tenant A")

            # Step 3: Verify Tenant A can see their own data
            async with conn.transaction():
                # Set tenant context for Tenant A
                escaped_tenant_a_id = tenant_a_id.replace("'", "''")
                await conn.execute(f"SET LOCAL app.tenant_id = '{escaped_tenant_a_id}'")

                records = await conn.fetch(
                    "SELECT * FROM data_records WHERE tenant_id = $1",
                    tenant_a_id
                )

                if len(records) >= 1:
                    print(f"✅ Tenant A can see their own data ({len(records)} record(s))")
                else:
                    print(f"⚠️  Tenant A sees {len(records)} records (expected >= 1)")

            # Step 4: Try to read as Tenant B - should return 0 records due to RLS
            async with conn.transaction():
                # Set tenant context for Tenant B
                escaped_tenant_b_id = tenant_b_id.replace("'", "''")
                await conn.execute(f"SET LOCAL app.tenant_id = '{escaped_tenant_b_id}'")

                # This should return 0 records (RLS enforced)
                records = await conn.fetch(
                    "SELECT * FROM data_records WHERE tenant_id = $1",
                    tenant_a_id  # Explicitly query for Tenant A's data
                )

                if len(records) == 0:
                    print("✅ Tenant B CANNOT see Tenant A's data (RLS working!)")
                    print("✅ TENANT ISOLATION TEST PASSED!")
                    return True
                else:
                    print(f"❌ CRITICAL: Tenant B can see Tenant A's data! Found {len(records)} records")
                    for record in records:
                        print(f"   Leaked record: {record}")
                    print("❌ TENANT ISOLATION TEST FAILED!")
                    return False

        finally:
            await conn.close()

    except Exception as e:
        print(f"❌ Error during tenant isolation test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_tenant_isolation())
    sys.exit(0 if result else 1)
