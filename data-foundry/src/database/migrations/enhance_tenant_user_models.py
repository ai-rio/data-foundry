"""
Database migration to enhance tenant and user models with additional fields.

This migration adds new fields to support billing, feature flags, MFA,
and enhanced user management capabilities.
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings


async def upgrade():
    """Enhance tenant and user tables with new fields."""
    async with db_connection.get_session() as session:
        try:
            # Add new fields to tenants table
            await session.execute(text("""
                ALTER TABLE tenants
                ADD COLUMN IF NOT EXISTS monthly_cost_limit NUMERIC(19,6),
                ADD COLUMN IF NOT EXISTS alert_thresholds JSONB,
                ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100),
                ADD COLUMN IF NOT EXISTS billing_email VARCHAR(255),
                ADD COLUMN IF NOT EXISTS billing_address JSONB,
                ADD COLUMN IF NOT EXISTS features JSONB,
                ADD COLUMN IF NOT EXISTS preferences JSONB,
                ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS notes TEXT;
            """))

            # Add new fields to users table
            await session.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS auth_method VARCHAR(20) DEFAULT 'password',
                ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR(255),
                ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500),
                ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC',
                ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
                ADD COLUMN IF NOT EXISTS department VARCHAR(100),
                ADD COLUMN IF NOT EXISTS job_title VARCHAR(100),
                ADD COLUMN IF NOT EXISTS manager_id VARCHAR(50),
                ADD COLUMN IF NOT EXISTS can_view_billing BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS can_manage_billing BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS can_export_data BOOLEAN DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS api_key_expires_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS allowed_ips JSONB,
                ADD COLUMN IF NOT EXISTS preferences JSONB,
                ADD COLUMN IF NOT EXISTS notifications JSONB,
                ADD COLUMN IF NOT EXISTS data_records_created INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS data_records_processed INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP,
                ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS invitation_token VARCHAR(255),
                ADD COLUMN IF NOT EXISTS invitation_expires_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS notes TEXT;
            """))

            # Create new indexes for tenants table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenants_status_created
                ON tenants(status, created_at);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenants_domain_active
                ON tenants(domain, status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer
                ON tenants(stripe_customer_id);
            """))

            # Create new indexes for users table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_tenant_status
                ON users(tenant_id, status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_tenant_role
                ON users(tenant_id, role);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_email_tenant
                ON users(email, tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_manager
                ON users(manager_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_last_login
                ON users(last_login);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_api_key
                ON users(api_key);
            """))

            # Add constraints
            await session.execute(text("""
                ALTER TABLE tenants
                ADD CONSTRAINT IF NOT EXISTS check_tenant_storage_limit
                CHECK (storage_limit_gb >= 0);
            """))

            await session.execute(text("""
                ALTER TABLE tenants
                ADD CONSTRAINT IF NOT EXISTS check_tenant_max_users
                CHECK (max_users > 0);
            """))

            await session.execute(text("""
                ALTER TABLE tenants
                ADD CONSTRAINT IF NOT EXISTS check_tenant_cost_limit
                CHECK (monthly_cost_limit IS NULL OR monthly_cost_limit >= 0);
            """))

            await session.execute(text("""
                ALTER TABLE users
                ADD CONSTRAINT IF NOT EXISTS check_user_records_created
                CHECK (data_records_created >= 0);
            """))

            await session.execute(text("""
                ALTER TABLE users
                ADD CONSTRAINT IF NOT EXISTS check_user_records_processed
                CHECK (data_records_processed >= 0);
            """))

            # Add comments to new columns
            await session.execute(text("""
                COMMENT ON COLUMN tenants.monthly_cost_limit IS 'Monthly spending limit for the tenant';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN tenants.stripe_customer_id IS 'Stripe customer ID for billing integration';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN tenants.features IS 'Feature flags enabled for this tenant';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN users.auth_method IS 'Primary authentication method (password, sso, oauth)';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN users.mfa_enabled IS 'Whether multi-factor authentication is enabled';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN users.manager_id IS 'ID of the user''s manager for organizational hierarchy';
            """))

            await session.execute(text("""
                COMMENT ON COLUMN users.allowed_ips IS 'Whitelisted IP addresses for API access';
            """))

            # Update default values for existing records
            await session.execute(text("""
                UPDATE users
                SET auth_method = 'password'
                WHERE auth_method IS NULL;
            """))

            await session.execute(text("""
                UPDATE users
                SET timezone = 'UTC'
                WHERE timezone IS NULL;
            """))

            await session.execute(text("""
                UPDATE users
                SET language = 'en'
                WHERE language IS NULL;
            """))

            await session.commit()
            print("Tenant and user models enhanced successfully")

        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {str(e)}")
            raise


async def downgrade():
    """Remove enhanced fields from tenant and user tables."""
    async with db_connection.get_session() as session:
        try:
            # Drop indexes first
            await session.execute(text("DROP INDEX IF EXISTS idx_tenants_status_created;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_tenants_domain_active;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_tenants_stripe_customer;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_tenant_status;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_tenant_role;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_email_tenant;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_manager;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_last_login;"))
            await session.execute(text("DROP INDEX IF EXISTS idx_users_api_key;"))

            # Drop constraints
            await session.execute(text("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS check_tenant_storage_limit;"))
            await session.execute(text("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS check_tenant_max_users;"))
            await session.execute(text("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS check_tenant_cost_limit;"))
            await session.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_user_records_created;"))
            await session.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS check_user_records_processed;"))

            # Remove columns from tenants table
            await session.execute(text("""
                ALTER TABLE tenants
                DROP COLUMN IF EXISTS monthly_cost_limit,
                DROP COLUMN IF EXISTS alert_thresholds,
                DROP COLUMN IF EXISTS stripe_customer_id,
                DROP COLUMN IF EXISTS billing_email,
                DROP COLUMN IF EXISTS billing_address,
                DROP COLUMN IF EXISTS features,
                DROP COLUMN IF EXISTS preferences,
                DROP COLUMN IF EXISTS suspended_at,
                DROP COLUMN IF EXISTS notes;
            """))

            # Remove columns from users table
            await session.execute(text("""
                ALTER TABLE users
                DROP COLUMN IF EXISTS auth_method,
                DROP COLUMN IF EXISTS mfa_enabled,
                DROP COLUMN IF EXISTS mfa_secret,
                DROP COLUMN IF EXISTS avatar_url,
                DROP COLUMN IF EXISTS timezone,
                DROP COLUMN IF EXISTS language,
                DROP COLUMN IF EXISTS department,
                DROP COLUMN IF EXISTS job_title,
                DROP COLUMN IF EXISTS manager_id,
                DROP COLUMN IF EXISTS can_view_billing,
                DROP COLUMN IF EXISTS can_manage_billing,
                DROP COLUMN IF EXISTS can_export_data,
                DROP COLUMN IF EXISTS api_key_expires_at,
                DROP COLUMN IF EXISTS allowed_ips,
                DROP COLUMN IF EXISTS preferences,
                DROP COLUMN IF EXISTS notifications,
                DROP COLUMN IF EXISTS data_records_created,
                DROP COLUMN IF EXISTS data_records_processed,
                DROP COLUMN IF EXISTS last_activity,
                DROP COLUMN IF EXISTS password_changed_at,
                DROP COLUMN IF EXISTS suspended_at,
                DROP COLUMN IF EXISTS deactivated_at,
                DROP COLUMN IF EXISTS invitation_token,
                DROP COLUMN IF EXISTS invitation_expires_at,
                DROP COLUMN IF EXISTS notes;
            """))

            await session.commit()
            print("Downgrade completed successfully")

        except Exception as e:
            await session.rollback()
            print(f"Downgrade failed: {str(e)}")
            raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        asyncio.run(downgrade())
    else:
        asyncio.run(upgrade())