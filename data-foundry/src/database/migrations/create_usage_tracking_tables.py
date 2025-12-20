"""
Database migration to create usage tracking and billing tables.

This migration creates all the tables needed for comprehensive usage tracking,
billing integration, cost monitoring, and audit trails.
"""

import asyncio
from sqlalchemy import text
from src.database.connection import db_connection
from src.core.config import settings


async def upgrade():
    """Create usage tracking tables and indexes."""
    async with db_connection.get_session() as session:
        try:
            # Create token_usage table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    user_id VARCHAR(50),
                    request_id VARCHAR(100) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    input_cost NUMERIC(19,6) NOT NULL,
                    output_cost NUMERIC(19,6) NOT NULL,
                    total_cost NUMERIC(19,6) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    response_content TEXT,
                    response_time_ms FLOAT NOT NULL,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    from_cache BOOLEAN DEFAULT FALSE,
                    fallback_used BOOLEAN DEFAULT FALSE,
                    retry_count INTEGER DEFAULT 0,
                    additional_metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))

            # Create tenant_usage table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS tenant_usage (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    period_type VARCHAR(20) NOT NULL,
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    total_requests INTEGER DEFAULT 0,
                    successful_requests INTEGER DEFAULT 0,
                    failed_requests INTEGER DEFAULT 0,
                    cached_requests INTEGER DEFAULT 0,
                    total_prompt_tokens INTEGER DEFAULT 0,
                    total_completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    total_cost NUMERIC(19,6) DEFAULT 0,
                    cost_by_model JSONB,
                    model_usage JSONB,
                    billing_status VARCHAR(20) DEFAULT 'pending',
                    billing_event_id VARCHAR(100),
                    invoice_id VARCHAR(100),
                    cost_limit NUMERIC(19,6),
                    token_limit INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))

            # Create audit_logs table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    user_id VARCHAR(50),
                    session_id VARCHAR(100),
                    operation VARCHAR(100) NOT NULL,
                    resource_type VARCHAR(50) NOT NULL,
                    resource_id VARCHAR(100),
                    request_method VARCHAR(10),
                    request_path VARCHAR(500),
                    request_data JSONB,
                    response_status INTEGER,
                    response_data JSONB,
                    success BOOLEAN NOT NULL,
                    error_message TEXT,
                    duration_ms FLOAT,
                    cpu_time_ms FLOAT,
                    memory_used_mb FLOAT,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    auth_method VARCHAR(50),
                    audit_metadata JSONB,
                    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))

            # Create cost_alerts table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS cost_alerts (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    message TEXT NOT NULL,
                    threshold_type VARCHAR(50) NOT NULL,
                    threshold_value NUMERIC(19,6) NOT NULL,
                    actual_value NUMERIC(19,6) NOT NULL,
                    period_start TIMESTAMP NOT NULL,
                    period_end TIMESTAMP NOT NULL,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    acknowledged_by VARCHAR(50),
                    acknowledged_at TIMESTAMP,
                    notification_sent BOOLEAN DEFAULT FALSE,
                    notification_channels JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    resolved_at TIMESTAMP
                );
            """))

            # Create billing_events table
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS billing_events (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) NOT NULL,
                    event_id VARCHAR(100) UNIQUE NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    meter_id VARCHAR(100) NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit_amount NUMERIC(19,6) NOT NULL,
                    total_cost NUMERIC(19,6) NOT NULL,
                    currency VARCHAR(3) DEFAULT 'USD',
                    usage_period_start TIMESTAMP NOT NULL,
                    usage_period_end TIMESTAMP NOT NULL,
                    usage_data JSONB,
                    status VARCHAR(20) DEFAULT 'pending',
                    stripe_event_id VARCHAR(100),
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    invoice_id VARCHAR(100),
                    invoice_created BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    processed_at TIMESTAMP
                );
            """))

            # Create indexes for token_usage table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_id
                ON token_usage(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_user_id
                ON token_usage(user_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_request_id
                ON token_usage(request_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_created_at
                ON token_usage(created_at);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_model
                ON token_usage(tenant_id, model);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_created
                ON token_usage(tenant_id, created_at);
            """))

            # Create indexes for tenant_usage table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant_period
                ON tenant_usage(tenant_id, period_type, period_start);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenant_usage_period_end
                ON tenant_usage(period_end);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenant_usage_billing_status
                ON tenant_usage(billing_status);
            """))

            # Create indexes for audit_logs table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_id
                ON audit_logs(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id
                ON audit_logs(user_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
                ON audit_logs(timestamp);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_operation
                ON audit_logs(operation);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_resource
                ON audit_logs(resource_type, resource_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
                ON audit_logs(tenant_id, timestamp);
            """))

            # Create indexes for cost_alerts table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cost_alerts_tenant_id
                ON cost_alerts(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cost_alerts_acknowledged
                ON cost_alerts(acknowledged);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cost_alerts_created_at
                ON cost_alerts(created_at);
            """))

            # Create indexes for billing_events table
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_billing_events_tenant_id
                ON billing_events(tenant_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_billing_events_event_id
                ON billing_events(event_id);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_billing_events_status
                ON billing_events(status);
            """))

            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_billing_events_period
                ON billing_events(usage_period_start, usage_period_end);
            """))

            # Add comments to tables
            await session.execute(text("""
                COMMENT ON TABLE token_usage IS 'Tracks individual AI API usage for billing and analytics';
            """))

            await session.execute(text("""
                COMMENT ON TABLE tenant_usage IS 'Aggregated usage data per tenant for billing periods';
            """))

            await session.execute(text("""
                COMMENT ON TABLE audit_logs IS 'Comprehensive audit trail for all platform operations';
            """))

            await session.execute(text("""
                COMMENT ON TABLE cost_alerts IS 'Cost monitoring and alert notifications';
            """))

            await session.execute(text("""
                COMMENT ON TABLE billing_events IS 'Integration with Stripe billing system';
            """))

            await session.commit()
            print("Usage tracking tables created successfully")

        except Exception as e:
            await session.rollback()
            print(f"Migration failed: {str(e)}")
            raise


async def downgrade():
    """Drop usage tracking tables."""
    async with db_connection.get_session() as session:
        try:
            # Drop tables in reverse order to handle foreign keys
            await session.execute(text("DROP TABLE IF EXISTS billing_events CASCADE;"))
            await session.execute(text("DROP TABLE IF EXISTS cost_alerts CASCADE;"))
            await session.execute(text("DROP TABLE IF EXISTS audit_logs CASCADE;"))
            await session.execute(text("DROP TABLE IF EXISTS tenant_usage CASCADE;"))
            await session.execute(text("DROP TABLE IF EXISTS token_usage CASCADE;"))

            await session.commit()
            print("Usage tracking tables dropped successfully")

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