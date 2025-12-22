"""
Configuration and Fixtures for Integration Tests

This module provides shared fixtures and configuration for all integration tests,
including database setup, service initialization, and test utilities.
"""

import asyncio
import logging
import os
import pytest
import tempfile
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Any, Optional
from unittest.mock import Mock, AsyncMock

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
import redis.asyncio as redis

# Import system components
from src.core.database import DatabaseManager
from src.core.audit_service import AuditService
from src.core.consent_manager import ConsentManager
from src.core.security import SecurityManager
from src.models.consent import ConsentRecordDB
from src.models.enums import ConsentStatus


# Configure logging for tests
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# Test configuration
TEST_CONFIG = {
    "database": {
        "url": os.getenv("TEST_DATABASE_URL", "sqlite:///./test_consent_integration.db"),
        "echo": os.getenv("TEST_DB_ECHO", "false").lower() == "true",
    },
    "redis": {
        "url": os.getenv("TEST_REDIS_URL", "redis://localhost:6380/1"),
        "decode_responses": True,
    },
    "security": {
        "jwt_secret": os.getenv("TEST_JWT_SECRET", "test_secret_for_integration_32_chars_min"),
        "jwt_algorithm": "HS256",
        "jwt_expiry_hours": 1,
    },
    "audit": {
        "enabled": True,
        "retention_days": 30,
    },
    "consent": {
        "ip_hash_salt": os.getenv("TEST_IP_HASH_SALT", "test_salt_for_integration_32_characters_min"),
    }
}


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment variables and configurations."""
    # Set environment variables for tests
    os.environ["IP_HASH_SALT"] = TEST_CONFIG["consent"]["ip_hash_salt"]
    os.environ["DATABASE_URL"] = TEST_CONFIG["database"]["url"]
    os.environ["JWT_SECRET"] = TEST_CONFIG["security"]["jwt_secret"]
    os.environ["REDIS_URL"] = TEST_CONFIG["redis"]["url"]

    yield

    # Cleanup after tests
    for key in ["IP_HASH_SALT", "DATABASE_URL", "JWT_SECRET", "REDIS_URL"]:
        os.environ.pop(key, None)


@pytest.fixture(scope="function")
async def test_database_engine():
    """Create a test database engine and session."""
    # Create in-memory SQLite database for tests
    engine = create_engine(
        TEST_CONFIG["database"]["url"],
        echo=TEST_CONFIG["database"]["echo"],
        connect_args={"check_same_thread": False} if "sqlite" in TEST_CONFIG["database"]["url"] else {}
    )

    # Create all tables
    SQLModel.metadata.create_all(engine)

    # Create session factory
    session_factory = sessionmaker(bind=engine, class_=Session)

    yield engine, session_factory

    # Cleanup: Drop all tables
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
async def test_redis():
    """Create a test Redis connection."""
    try:
        # Try to connect to Redis
        redis_client = redis.from_url(
            TEST_CONFIG["redis"]["url"],
            decode_responses=TEST_CONFIG["redis"]["decode_responses"]
        )

        # Test connection
        await redis_client.ping()

        # Clear database
        await redis_client.flushdb()

        yield redis_client

        # Cleanup
        await redis_client.flushdb()
        await redis_client.close()

    except Exception as e:
        logger.warning(f"Redis not available for tests: {e}")
        # Create mock Redis for tests
        mock_redis = Mock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)
        mock_redis.exists = AsyncMock(return_value=False)
        mock_redis.flushdb = AsyncMock(return_value=True)
        mock_redis.close = AsyncMock()

        yield mock_redis


@pytest.fixture(scope="function")
async def db_manager(test_database_engine):
    """Create a DatabaseManager instance for tests."""
    engine, _ = test_database_engine

    # Override the database URL for testing
    test_db_url = TEST_CONFIG["database"]["url"]

    # Create manager with test database
    manager = DatabaseManager(test_db_url)
    await manager.initialize()

    # Mock connection pool if needed
    if not hasattr(manager, '_connection_pool') or manager._connection_pool is None:
        manager._connection_pool = Mock()
        manager._connection_pool.fetch = AsyncMock(return_value=[])
        manager._connection_pool.fetchrow = AsyncMock(return_value=None)
        manager._connection_pool.execute = AsyncMock(return_value=None)

    yield manager

    # Cleanup
    if hasattr(manager, '_connection_pool') and manager._connection_pool:
        try:
            await manager._connection_pool.close()
        except:
            pass


@pytest.fixture(scope="function")
async def audit_service(test_redis):
    """Create an AuditService instance for tests."""
    service = AuditService(enable_audit=TEST_CONFIG["audit"]["enabled"])

    # Mock the audit logger if Redis is not available
    if not isinstance(test_redis, redis.Redis):
        service.audit_logger = Mock()
        service.audit_logger.log_cost_calculation = AsyncMock()
        service.audit_logger.log_error = AsyncMock()
        service.audit_logger.store_audit_record = AsyncMock()

    yield service


@pytest.fixture(scope="function")
async def security_manager():
    """Create a SecurityManager instance for tests."""
    manager = SecurityManager()

    # Configure with test settings
    manager.jwt_secret = TEST_CONFIG["security"]["jwt_secret"]
    manager.jwt_algorithm = TEST_CONFIG["security"]["jwt_algorithm"]
    manager.jwt_expiry_hours = TEST_CONFIG["security"]["jwt_expiry_hours"]

    return manager


@pytest.fixture(scope="function")
async def consent_manager(db_manager, audit_service):
    """Create a ConsentManager instance for tests."""
    manager = ConsentManager(db_manager, audit_service)

    yield manager


@pytest.fixture(scope="function")
def test_user_data():
    """Generate test user data."""
    import uuid

    return {
        "user_id": f"test_user_{uuid.uuid4().hex[:8]}",
        "tenant_id": f"test_tenant_{uuid.uuid4().hex[:8]}",
        "email": "test@example.com",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0 (Test Browser) IntegrationTest/1.0",
        "session_id": f"session_{uuid.uuid4().hex[:16]}",
        "device_id": f"device_{uuid.uuid4().hex[:12]}",
    }


@pytest.fixture(scope="function")
def sample_consent_text():
    """Provide a sample GDPR-compliant consent text."""
    return """
    I hereby provide my explicit consent for the processing of my personal data.

    Purpose: To provide personalized services and improve user experience
    Data Types: Usage patterns, preferences, and interaction analytics
    Processing: Collection, storage, and analysis of anonymized usage data
    Retention: Data will be retained for 24 months then automatically deleted
    Legal Basis: Article 6(1)(a) GDPR - Explicit consent
    Rights: I understand I can withdraw consent at any time

    This consent is given freely, specifically, informedly, and unambiguously.
    """


@pytest.fixture(scope="function")
async def populated_consent_data(consent_manager, test_user_data, sample_consent_text):
    """Create pre-populated consent data for tests."""
    consent_types = ["analytics", "marketing", "personalization", "research"]
    created_records = []

    metadata = {
        "ip": test_user_data["ip_address"],
        "user_agent": test_user_data["user_agent"],
        "source": "integration_test",
        "version": "1.0.0"
    }

    for consent_type in consent_types:
        record = await consent_manager.record_consent(
            user_id=test_user_data["user_id"],
            consent_type=consent_type,
            consent_text=sample_consent_text,
            metadata=metadata
        )
        created_records.append(record)

    # Withdraw one consent to test mixed states
    await consent_manager.withdraw_consent(test_user_data["user_id"], "marketing")

    return {
        "user_id": test_user_data["user_id"],
        "records": created_records,
        "active_consents": ["analytics", "personalization", "research"],
        "withdrawn_consents": ["marketing"]
    }


@pytest.fixture(scope="function")
def mock_audit_events():
    """Mock audit events for testing."""
    events = []

    def capture_event(event_type, *args, **kwargs):
        events.append({
            "type": event_type,
            "args": args,
            "kwargs": kwargs,
            "timestamp": datetime.now(timezone.utc)
        })

    return events, capture_event


# Performance testing utilities
class PerformanceMonitor:
    """Monitor performance during tests."""

    def __init__(self):
        self.metrics = {}
        self.start_times = {}

    def start_timer(self, operation: str):
        """Start timing an operation."""
        self.start_times[operation] = datetime.now(timezone.utc)

    def end_timer(self, operation: str):
        """End timing an operation and record duration."""
        if operation in self.start_times:
            duration = (datetime.now(timezone.utc) - self.start_times[operation]).total_seconds()
            if operation not in self.metrics:
                self.metrics[operation] = []
            self.metrics[operation].append(duration)
            return duration
        return None

    def get_stats(self, operation: str) -> Optional[Dict[str, float]]:
        """Get statistics for an operation."""
        if operation not in self.metrics or not self.metrics[operation]:
            return None

        durations = self.metrics[operation]
        return {
            "count": len(durations),
            "total": sum(durations),
            "average": sum(durations) / len(durations),
            "min": min(durations),
            "max": max(durations),
        }


@pytest.fixture(scope="function")
def performance_monitor():
    """Provide a performance monitor for tests."""
    return PerformanceMonitor()


# Test data factories
class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def create_user(**overrides):
        """Create test user data with optional overrides."""
        import uuid

        defaults = {
            "user_id": f"user_{uuid.uuid4().hex[:8]}",
            "tenant_id": f"tenant_{uuid.uuid4().hex[:8]}",
            "email": "test@example.com",
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0 TestBrowser/1.0",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        defaults.update(overrides)
        return defaults

    @staticmethod
    def create_consent_record(**overrides):
        """Create a consent record for testing."""
        import uuid

        defaults = {
            "id": None,
            "user_id": f"user_{uuid.uuid4().hex[:8]}",
            "consent_type": "test_consent",
            "consent_text": "Test consent for integration testing",
            "granted_at": datetime.now(timezone.utc),
            "ip_address": "192.168.1.100",
            "user_agent": "TestBrowser/1.0",
            "status": ConsentStatus.ACTIVE,
            "withdrawn_at": None,
            "consent_metadata": {"source": "test"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        defaults.update(overrides)
        return ConsentRecordDB(**defaults)

    @staticmethod
    def create_bulk_consents(count: int, user_id: str = None) -> List[ConsentRecordDB]:
        """Create multiple consent records."""
        records = []

        for i in range(count):
            record = TestDataFactory.create_consent_record(
                user_id=user_id or f"user_{uuid.uuid4().hex[:8]}",
                consent_type=f"bulk_test_{i}",
                consent_text=f"Bulk test consent number {i}",
                consent_metadata={"batch_id": f"batch_{uuid.uuid4().hex[:8]}"}
            )
            records.append(record)

        return records


@pytest.fixture(scope="function")
def test_data_factory():
    """Provide a test data factory."""
    return TestDataFactory


# Custom pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "security: mark test as security test"
    )
    config.addinivalue_line(
        "markers", "gdpr: mark test as GDPR compliance test"
    )