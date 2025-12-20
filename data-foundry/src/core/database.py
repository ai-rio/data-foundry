"""
Database Manager for Cost Service Persistence

Provides secure, reliable persistence for:
- Tenant data and configurations
- Usage tracking and statistics
- Audit records
- Billing events
"""

import logging
import os
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@dataclass
class TenantRecord:
    """Tenant record with billing information."""
    tenant_id: str
    is_active: bool
    billing_enabled: bool
    monthly_limit: Optional[Decimal]
    approved_models: List[str]
    permissions: Dict[str, bool]
    created_at: datetime
    updated_at: datetime


@dataclass
class UsageRecord:
    """Usage tracking record."""
    tenant_id: str
    calculation_id: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_cost: Decimal
    currency: str
    volume_tier: Optional[str]
    calculation_date: datetime
    metadata: Dict[str, Any]


class DatabaseManager:
    """
    Abstract database manager for cost service.
    Implements the interface with both mock and real database support.
    """

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or os.getenv("DATABASE_URL")
        self._connection_pool = None
        self._initialized = False

    async def initialize(self):
        """Initialize database connection and create tables."""
        if self._initialized:
            return

        try:
            # In production, initialize actual database connection
            if self.connection_string and not self.connection_string.startswith("mock://"):
                await self._initialize_real_database()
            else:
                await self._initialize_mock_database()

            self._initialized = True
            logger.info("Database manager initialized")

        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise

    async def _initialize_real_database(self):
        """Initialize real database connection (PostgreSQL, etc.)."""
        # Implementation would depend on the database
        # Example with asyncpg for PostgreSQL:
        try:
            import asyncpg
            self._connection_pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=5,
                max_size=20,
                command_timeout=60
            )

            # Create tables if they don't exist
            await self._create_tables()

        except ImportError:
            logger.warning("asyncpg not available, falling back to mock database")
            await self._initialize_mock_database()

    async def _initialize_mock_database(self):
        """Initialize in-memory mock database for development/testing."""
        self._mock_data = {
            "tenants": {},
            "usage": [],
            "audit_records": [],
            "billing_events": []
        }
        logger.info("Using mock database for persistence")

    async def _create_tables(self):
        """Create necessary database tables."""
        if self._connection_pool:
            # SQL for creating tables would go here
            # This is a placeholder for the actual SQL
            tables_sql = """
                CREATE TABLE IF NOT EXISTS tenants (
                    tenant_id VARCHAR(255) PRIMARY KEY,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    billing_enabled BOOLEAN NOT NULL DEFAULT true,
                    monthly_limit DECIMAL(15, 6),
                    approved_models JSONB,
                    permissions JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS usage_records (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(255) NOT NULL,
                    calculation_id VARCHAR(255) NOT NULL,
                    model VARCHAR(255) NOT NULL,
                    provider VARCHAR(100) NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_cost DECIMAL(15, 6) NOT NULL,
                    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                    volume_tier VARCHAR(50),
                    calculation_date TIMESTAMP WITH TIME ZONE NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(tenant_id, calculation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_usage_tenant_date ON usage_records(tenant_id, calculation_date);
                CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_records(model);

                -- Additional tables for audit, billing, etc.
            """
            # Execute the SQL
            async with self._connection_pool.acquire() as conn:
                await conn.execute(tables_sql)

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant information."""
        await self.initialize()

        try:
            if hasattr(self, '_mock_data'):
                # Mock database
                return self._mock_data["tenants"].get(tenant_id)

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM tenants WHERE tenant_id = $1",
                        tenant_id
                    )
                    if row:
                        return dict(row)

            return None

        except Exception as e:
            logger.error(f"Failed to get tenant {tenant_id}: {str(e)}")
            return None

    async def create_tenant(self, tenant_data: Dict[str, Any]) -> bool:
        """Create a new tenant."""
        await self.initialize()

        try:
            if hasattr(self, '_mock_data'):
                # Mock database
                tenant_record = TenantRecord(
                    tenant_id=tenant_data["tenant_id"],
                    is_active=tenant_data.get("is_active", True),
                    billing_enabled=tenant_data.get("billing_enabled", True),
                    monthly_limit=Decimal(str(tenant_data.get("monthly_limit", 0))) if tenant_data.get("monthly_limit") else None,
                    approved_models=tenant_data.get("approved_models", []),
                    permissions=tenant_data.get("permissions", {}),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self._mock_data["tenants"][tenant_data["tenant_id"]] = asdict(tenant_record)
                return True

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO tenants (
                            tenant_id, is_active, billing_enabled, monthly_limit,
                            approved_models, permissions, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (tenant_id) DO UPDATE SET
                            is_active = EXCLUDED.is_active,
                            billing_enabled = EXCLUDED.billing_enabled,
                            monthly_limit = EXCLUDED.monthly_limit,
                            approved_models = EXCLUDED.approved_models,
                            permissions = EXCLUDED.permissions,
                            updated_at = EXCLUDED.updated_at
                        """,
                        tenant_data["tenant_id"],
                        tenant_data.get("is_active", True),
                        tenant_data.get("billing_enabled", True),
                        Decimal(str(tenant_data.get("monthly_limit", 0))) if tenant_data.get("monthly_limit") else None,
                        json.dumps(tenant_data.get("approved_models", [])),
                        json.dumps(tenant_data.get("permissions", {})),
                        datetime.utcnow(),
                        datetime.utcnow()
                    )
                return True

        except Exception as e:
            logger.error(f"Failed to create tenant {tenant_data.get('tenant_id')}: {str(e)}")
            return False

    async def record_usage(self, usage_data: Dict[str, Any]) -> bool:
        """Record usage data."""
        await self.initialize()

        try:
            if hasattr(self, '_mock_data'):
                # Mock database
                usage_record = UsageRecord(
                    tenant_id=usage_data["tenant_id"],
                    calculation_id=usage_data["calculation_id"],
                    model=usage_data["model"],
                    provider=usage_data["provider"],
                    prompt_tokens=usage_data["prompt_tokens"],
                    completion_tokens=usage_data["completion_tokens"],
                    total_cost=Decimal(usage_data["total_cost"]),
                    currency=usage_data["currency"],
                    volume_tier=usage_data.get("volume_tier"),
                    calculation_date=usage_data["calculation_date"],
                    metadata=usage_data.get("metadata", {})
                )
                self._mock_data["usage"].append(asdict(usage_record))
                return True

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO usage_records (
                            tenant_id, calculation_id, model, provider,
                            prompt_tokens, completion_tokens, total_cost,
                            currency, volume_tier, calculation_date, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (tenant_id, calculation_id) DO NOTHING
                        """,
                        usage_data["tenant_id"],
                        usage_data["calculation_id"],
                        usage_data["model"],
                        usage_data["provider"],
                        usage_data["prompt_tokens"],
                        usage_data["completion_tokens"],
                        Decimal(usage_data["total_cost"]),
                        usage_data["currency"],
                        usage_data.get("volume_tier"),
                        usage_data["calculation_date"],
                        json.dumps(usage_data.get("metadata", {}))
                    )
                return True

        except Exception as e:
            logger.error(f"Failed to record usage: {str(e)}")
            return False

    async def get_monthly_cost(self, tenant_id: str) -> Decimal:
        """Get total cost for current month."""
        await self.initialize()

        try:
            # Calculate first day of current month
            now = datetime.utcnow()
            first_day = datetime(now.year, now.month, 1)

            if hasattr(self, '_mock_data'):
                # Mock database - sum from records
                monthly_usage = [
                    record for record in self._mock_data["usage"]
                    if record["tenant_id"] == tenant_id and
                    record["calculation_date"] >= first_day
                ]
                return sum(Decimal(record["total_cost"]) for record in monthly_usage)

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    result = await conn.fetchval(
                        """
                        SELECT COALESCE(SUM(total_cost), 0) as monthly_cost
                        FROM usage_records
                        WHERE tenant_id = $1
                        AND calculation_date >= $2
                        """,
                        tenant_id,
                        first_day
                    )
                    return Decimal(str(result)) if result else Decimal("0")

        except Exception as e:
            logger.error(f"Failed to get monthly cost for {tenant_id}: {str(e)}")
            return Decimal("0")

    async def get_tenant_usage_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive usage statistics for a tenant."""
        await self.initialize()

        try:
            # Get current month start
            now = datetime.utcnow()
            first_day = datetime(now.year, now.month, 1)

            if hasattr(self, '_mock_data'):
                # Mock database
                tenant_usage = [
                    record for record in self._mock_data["usage"]
                    if record["tenant_id"] == tenant_id
                ]

                monthly_usage = [
                    record for record in tenant_usage
                    if record["calculation_date"] >= first_day
                ]

                # Calculate statistics
                monthly_tokens = sum(
                    record["prompt_tokens"] + record["completion_tokens"]
                    for record in monthly_usage
                )
                monthly_cost = sum(
                    Decimal(record["total_cost"]) for record in monthly_usage
                )
                model_usage = {}
                for record in monthly_usage:
                    model = record["model"]
                    model_usage[model] = model_usage.get(model, 0) + 1

                return {
                    "monthly_tokens": monthly_tokens,
                    "monthly_cost": monthly_cost,
                    "model_usage": model_usage,
                    "total_requests": len(monthly_usage)
                }

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    # Get monthly totals
                    monthly_stats = await conn.fetchrow(
                        """
                        SELECT
                            SUM(prompt_tokens + completion_tokens) as monthly_tokens,
                            SUM(total_cost) as monthly_cost,
                            COUNT(*) as total_requests
                        FROM usage_records
                        WHERE tenant_id = $1
                        AND calculation_date >= $2
                        """,
                        tenant_id,
                        first_day
                    )

                    # Get model breakdown
                    model_stats = await conn.fetch(
                        """
                        SELECT model, COUNT(*) as usage_count
                        FROM usage_records
                        WHERE tenant_id = $1
                        AND calculation_date >= $2
                        GROUP BY model
                        ORDER BY usage_count DESC
                        """,
                        tenant_id,
                        first_day
                    )

                    return {
                        "monthly_tokens": monthly_stats["monthly_tokens"] or 0,
                        "monthly_cost": Decimal(str(monthly_stats["monthly_cost"] or 0)),
                        "total_requests": monthly_stats["total_requests"] or 0,
                        "model_usage": {row["model"]: row["usage_count"] for row in model_stats}
                    }

        except Exception as e:
            logger.error(f"Failed to get usage stats for {tenant_id}: {str(e)}")
            return {
                "monthly_tokens": 0,
                "monthly_cost": Decimal("0"),
                "model_usage": {},
                "total_requests": 0
            }

    async def get_usage_report(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get usage report for a date range."""
        await self.initialize()

        try:
            if hasattr(self, '_mock_data'):
                # Mock database
                usage_records = [
                    record for record in self._mock_data["usage"]
                    if record["tenant_id"] == tenant_id and
                    start_date <= record["calculation_date"] <= end_date
                ]
                # Return sorted by date, limited
                usage_records.sort(key=lambda x: x["calculation_date"], reverse=True)
                return usage_records[:limit]

            elif self._connection_pool:
                # Real database
                async with self._connection_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT *
                        FROM usage_records
                        WHERE tenant_id = $1
                        AND calculation_date BETWEEN $2 AND $3
                        ORDER BY calculation_date DESC
                        LIMIT $4
                        """,
                        tenant_id,
                        start_date,
                        end_date,
                        limit
                    )
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get usage report for {tenant_id}: {str(e)}")
            return []

    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions."""
        if self._connection_pool:
            async with self._connection_pool.acquire() as conn:
                async with conn.transaction():
                    yield conn
        else:
            # Mock database - no transaction needed
            yield None

    async def close(self):
        """Close database connections."""
        if self._connection_pool:
            await self._connection_pool.close()
            logger.info("Database connections closed")


# Singleton instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(connection_string: Optional[str] = None) -> DatabaseManager:
    """Get singleton database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(connection_string)
    return _db_manager


# Export for testing
__all__ = [
    "DatabaseManager",
    "TenantRecord",
    "UsageRecord",
    "get_db_manager"
]