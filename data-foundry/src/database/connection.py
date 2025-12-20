"""
Database connection management with multi-tenancy support
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import asyncpg
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.config import settings


class DatabaseConnection:
    """Database connection manager with tenant support."""

    def __init__(self):
        """Initialize database connection."""
        # Synchronous engine for dlt and certain operations
        self._sync_engine = create_engine(
            settings.database_url_sync,
            echo=settings.DEBUG,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
        )

        # Asynchronous engine for FastAPI
        self._async_engine = create_async_engine(
            settings.database_url_async,
            echo=settings.DEBUG,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
        )

        # Connection pool for PostgreSQL
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        """Initialize database connections and create tables."""
        # Create async connection pool
        self._pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )

        # Create SQLModel tables
        SQLModel.metadata.create_all(self._sync_engine)

    async def close(self):
        """Close database connections."""
        if self._pool:
            await self._pool.close()
        await self._async_engine.dispose()

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get a database connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database connection pool not initialized")

        async with self._pool.acquire() as connection:
            # Set tenant context if provided
            try:
                yield connection
            finally:
                pass

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session."""
        if not self._async_engine:
            raise RuntimeError("Database async engine not initialized")

        async with AsyncSession(
            self._async_engine,
            expire_on_commit=False,
        ) as session:
            yield session

    @asynccontextmanager
    def get_sync_session(self) -> AsyncGenerator[Session, None]:
        """Get a synchronous database session."""
        if not self._sync_engine:
            raise RuntimeError("Database sync engine not initialized")

        with Session(
            self._sync_engine,
            expire_on_commit=False,
        ) as session:
            yield session

    @asynccontextmanager
    async def get_tenant_connection(
        self, tenant_id: str
    ) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get a tenant-aware database connection."""
        async with self.get_connection() as connection:
            # Set tenant context using RLS
            await connection.execute(
                "SET LOCAL app.tenant_id = $1", tenant_id
            )
            yield connection


# Global database connection instance
db_connection = DatabaseConnection()


# Convenience functions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency for FastAPI."""
    async with db_connection.get_session() as session:
        yield session


def get_db_session() -> AsyncGenerator[Session, None]:
    """Get synchronous database session."""
    with db_connection.get_sync_session() as session:
        yield session


async def get_tenant_db(tenant_id: str) -> AsyncGenerator[Session, None]:
    """Get tenant-aware database session."""
    async with db_connection.get_tenant_connection(tenant_id) as connection:
        # Create session from tenant connection
        with Session(connection) as session:
            yield session