"""
Database session management with context managers
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlmodel import Session
from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseSession:
    """Database session manager with automatic cleanup."""

    @contextmanager
    def session(self, engine) -> Generator[Session, None, None]:
        """Context manager for database sessions."""
        session = Session(engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def async_session(self, async_engine) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for async database sessions."""
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()