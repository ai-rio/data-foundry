-- Data Foundry Database Initialization
-- Enables Row-Level Security for Multi-Tenancy

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create tenant schema for RLS policies
CREATE SCHEMA IF NOT EXISTS tenant;

-- Enable RLS on all tables by default
ALTER DEFAULT PRIVILEGES IN SCHEMA tenant ENABLE ROW LEVEL SECURITY;

-- Create a function to set tenant context
CREATE OR REPLACE FUNCTION tenant.set_current_tenant(tenant_id uuid)
RETURNS void AS $$
BEGIN
    SET session.claims.tenant_id = tenant_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to check tenant access
CREATE OR REPLACE FUNCTION tenant.check_tenant_access()
RETURNS boolean AS $$
BEGIN
    RETURN (
        session.claims.tenant_id IS NULL OR
        session.claims.tenant_id = current_setting('app.current_tenant_id', true)::uuid
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create indices for performance
CREATE INDEX IF NOT EXISTS idx_tenant_id ON tenant.tenant_id;