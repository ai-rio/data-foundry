"""
Database connection and session management
"""

from .connection import get_db, get_db_session, get_tenant_db
from .session import DatabaseSession

# Import migration functions directly from migrations.py to avoid circular imports
# Note: migrations directory contains individual migration files
import sys
from pathlib import Path
migrations_module_path = Path(__file__).parent / "migrations.py"
if migrations_module_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_migrations", migrations_module_path)
    _migrations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_migrations)
    create_tables = _migrations.create_tables
    create_indexes = _migrations.create_indexes
    create_rls_policies = _migrations.create_rls_policies
else:
    # Fallback if migrations.py doesn't exist
    create_tables = None
    create_indexes = None
    create_rls_policies = None

__all__ = [
    "get_db",
    "get_db_session",
    "get_tenant_db",
    "create_tables",
    "create_indexes",
    "create_rls_policies",
    "DatabaseSession",
]