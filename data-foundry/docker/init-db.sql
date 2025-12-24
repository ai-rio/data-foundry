-- Data Foundry Database Initialization
-- Enables Row-Level Security for Multi-Tenancy

-- Enable required extensions FIRST (before removing superuser)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- IMPORTANT: Remove BYPASSRLS and SUPERUSER from foundry_user for RLS to work
-- PostgreSQL RLS is bypassed by superusers and users with BYPASSRLS privilege
-- Order matters: must remove BYPASSRLS first while user is still superuser
ALTER ROLE foundry_user NOBYPASSRLS;
ALTER ROLE foundry_user NOSUPERUSER;
