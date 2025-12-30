"""
Pytest configuration and fixtures for Data Foundry tests
"""

import asyncio
import json
import os
import sys
import pytest
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, patch

# CRITICAL: Set test environment variables BEFORE importing src modules
# This ensures database settings are correct for integration tests
os.environ.setdefault('DATABASE_URL', 'postgresql://foundry_user:foundry_password@localhost:5433/data_foundry')

# CRITICAL: Mock problematic modules BEFORE importing src.main
# This prevents import errors when modules are not available
sys.modules['structlog'] = Mock()

# Only mock jose if it's not installed (like asyncpg and redis)
try:
    import jose
    import jose.exceptions
    import jose.jwt
    # jose is installed, don't mock it
except ImportError:
    sys.modules['jose'] = Mock()
    sys.modules['jose.jwt'] = Mock()

# Only mock asyncpg and redis if they are not actually installed
# This allows integration tests to use real database connections
try:
    import asyncpg
    # asyncpg is installed, don't mock it
except ImportError:
    sys.modules['asyncpg'] = Mock()  # PostgreSQL async driver

try:
    import redis
    # redis is installed, don't mock it
except ImportError:
    sys.modules['redis'] = Mock()  # Redis client

# Mock presidio modules (optional PII redaction)
mock_presidio_analyzer = Mock()
mock_presidio_analyzer.AnalyzerEngine = Mock
mock_presidio_analyzer.PatternRecognizer = Mock
sys.modules['presidio_analyzer'] = mock_presidio_analyzer

mock_presidio_anonymizer = Mock()
mock_presidio_anonymizer.AnonymizerEngine = Mock
sys.modules['presidio_anonymizer'] = mock_presidio_anonymizer

# Mock dlt module structure
mock_dlt = Mock()
mock_dlt.pipeline = Mock()
mock_dlt.destinations = Mock()
mock_dlt.destinations.postgres = Mock()
sys.modules['dlt'] = mock_dlt
sys.modules['dlt.pipeline'] = mock_dlt.pipeline
sys.modules['dlt.destinations'] = mock_dlt.destinations

# Mock prefect module structure
mock_prefect = Mock()
mock_prefect.flow = Mock()
mock_prefect.get_run_logger = Mock()
mock_prefect.task = Mock()
sys.modules['prefect'] = mock_prefect

import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from src.main import app
from src.core.config import Settings, get_settings
from src.database.connection import db_connection, DatabaseConnection
from src.models import (
    User, Tenant, DataRecord, ProcessedData, HumanReviewQueue,
    TokenUsage, TenantUsage, AuditLog
)
from src.services.litellm_service import LiteLLMService
from src.services.redis_service import RedisService, CacheStatistics, PerformanceMetrics
from src.core.prompts.prompt_manager import PromptManager
from src.services.cost_service import CostService
# AuditService not available in audit module - using AuditLogger instead


# Note: The event_loop fixture is no longer needed with pytest-asyncio >= 0.17
# It's handled automatically by pytest-asyncio based on asyncio_mode setting
# Uncomment and customize only if you need specific event loop behavior
# @pytest.fixture(scope="session")
# def event_loop():
#     """Create an instance of the default event loop for the test session."""
#     loop = asyncio.get_event_loop_policy().new_event_loop()
#     yield loop
#     loop.close()


@pytest.fixture(scope="session", autouse=True)
def test_settings() -> Settings:
    """Test settings that override production values."""
    # Override environment variables for testing
    original_settings = get_settings()

    # Load real OpenRouter API key from .env.local for TRUE integration tests
    import os
    from dotenv import load_dotenv

    # Load .env.local to get the real OpenRouter API key
    if os.path.exists(".env.local"):
        load_dotenv(dotenv_path=".env.local", override=True)

    # Create a new settings instance with test values
    test_settings = Settings(
        # Database - use port 5433 where the test database container runs
        DATABASE_URL="postgresql://foundry_user:foundry_password@localhost:5433/data_foundry",
        DATABASE_POOL_SIZE=5,
        DATABASE_MAX_OVERFLOW=10,

        # Redis
        REDIS_URL="redis://localhost:6379/0",

        # AI Services
        OPENAI_API_KEY="test_openai_key",
        OPENAI_MODEL="gpt-4o",
        OPENAI_TEMPERATURE=0.3,
        OPENAI_MAX_TOKENS=2048,

        ANTHROPIC_API_KEY="test_anthropic_key",
        ANTHROPIC_MODEL="claude-3-opus-20240229",
        ANTHROPIC_TEMPERATURE=0.3,
        ANTHROPIC_MAX_TOKENS=2048,

        # Label Studio
        LABEL_STUDIO_URL="http://localhost:8080",
        LABEL_STUDIO_API_KEY="test_label_studio_key",
        LABEL_STUDIO_PROJECT_ID=1,

        # Stripe
        STRIPE_SECRET_KEY="test_stripe_key",
        STRIPE_PUBLISHABLE_KEY="test_publishable_key",

        # Security
        SECRET_KEY="test_secret_key_for_testing_only",
        ALGORITHM="HS256",
        ACCESS_TOKEN_EXPIRE_MINUTES=30,

        # Processing settings
        ENABLE_PII_REDACTION=True,
        CONFIDENCE_THRESHOLD=0.85,
        MAX_FILE_SIZE_MB=100,
        ALLOWED_FILE_TYPES=["csv", "json", "xlsx", "parquet"],

        # Application settings
        APP_NAME="Data Foundry Test",
        APP_VERSION="1.0.0-test",
        ENVIRONMENT="test",
        DEBUG=True,
        LOG_LEVEL="DEBUG",
        CORS_ORIGINS=["*"],
        API_V1_STR="/api/v1",
    )

    return test_settings


@pytest_asyncio.fixture
async def db_setup() -> AsyncGenerator[None, None]:
    """Set up test database.

    Note: This fixture is function-scoped to work with pytest-asyncio 1.3.0's
    function-scoped event loops. For performance, we only create tables once.
    """
    # Initialize database connection (idempotent)
    try:
        await db_connection.initialize()
    except Exception:
        # Already initialized, just need to make sure pool is ready
        pass

    # Create tables using SQLModel metadata
    from sqlmodel import SQLModel
    from src.models import (
        User, Tenant, DataRecord, ProcessedData, HumanReviewQueue,
        TokenUsage, TenantUsage, AuditLog
    )
    from src.models.aml_transaction_label import AMLTransactionLabel
    from src.models.aml_expert_review import AMLExpertReview
    from src.models.aml_audit_report import AMLAuditReport
    from src.models.aml_labeling_methodology import AMLLabelingMethodology
    from src.infrastructure.repositories.job_repository import ProcessingJobDB

    # Create all tables
    SQLModel.metadata.create_all(db_connection._sync_engine)

    yield

    # Note: We don't close the connection here to allow other tests to use it
    # The connection will be closed when the test session ends


@pytest_asyncio.fixture
async def db_session(db_setup: None) -> AsyncGenerator[AsyncSession, None]:
    """Get a test database session."""
    async with db_connection.get_session() as session:
        yield session


@pytest.fixture
def sync_db_session(db_setup: None) -> Generator[Session, None, None]:
    """Get a synchronous test database session."""
    with db_connection.get_sync_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create a test tenant."""
    from src.core.security import get_password_hash

    tenant = Tenant(
        tenant_id="test_tenant_001",
        name="Test Organization",
        status="active",
        max_users=100,
        max_data_records=1000000,
        storage_limit_gb=100.0,
        enable_pii_redaction=True,
        enable_ai_labeling=True,
        enable_human_review=True,
    )

    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    return tenant


@pytest_asyncio.fixture
async def test_users(db_session: AsyncSession, test_tenant: Tenant) -> tuple[User, User, User]:
    """Create test users with different roles."""
    from src.core.security import get_password_hash
    from src.models.user import UserRole, UserStatus

    # Admin user
    admin_user = User(
        user_id="test_admin_001",
        email="admin@testcorp.com",
        tenant_id=test_tenant.tenant_id,
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        first_name="Admin",
        last_name="User",
        can_create_data=True,
        can_view_data=True,
        can_modify_data=True,
        can_delete_data=True,
        can_manage_users=True,
    )

    # Analyst user
    analyst_user = User(
        user_id="test_analyst_001",
        email="analyst@testcorp.com",
        tenant_id=test_tenant.tenant_id,
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
        first_name="Data",
        last_name="Analyst",
        can_create_data=True,
        can_view_data=True,
        can_modify_data=False,
        can_delete_data=False,
        can_manage_users=False,
    )

    # Viewer user
    viewer_user = User(
        user_id="test_viewer_001",
        email="viewer@testcorp.com",
        tenant_id=test_tenant.tenant_id,
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.VIEWER,
        status=UserStatus.ACTIVE,
        first_name="View",
        last_name="User",
        can_create_data=False,
        can_view_data=True,
        can_modify_data=False,
        can_delete_data=False,
        can_manage_users=False,
    )

    db_session.add(admin_user)
    db_session.add(analyst_user)
    db_session.add(viewer_user)
    await db_session.commit()
    await db_session.refresh(admin_user)
    await db_session.refresh(analyst_user)
    await db_session.refresh(viewer_user)

    return admin_user, analyst_user, viewer_user


@pytest_asyncio.fixture
async def test_records(db_session: AsyncSession, test_tenant: Tenant) -> list[DataRecord]:
    """Create test data records."""
    from datetime import datetime

    records = []
    sample_data = [
        {
            "record_id": "rec_001",
            "tenant_id": test_tenant.tenant_id,
            "data_source": "csv",
            "status": "raw",
            "raw_data": '{"name": "John Doe", "email": "john@example.com", "phone": "555-1234"}',
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "record_id": "rec_002",
            "tenant_id": test_tenant.tenant_id,
            "data_source": "json",
            "status": "raw",
            "raw_data": '{"name": "Jane Smith", "email": "jane@example.com", "phone": "555-5678"}',
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "record_id": "rec_003",
            "tenant_id": test_tenant.tenant_id,
            "data_source": "csv",
            "status": "processing",
            "raw_data": '{"name": "Bob Johnson", "email": "bob@example.com", "phone": "555-9876"}',
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    ]

    for data in sample_data:
        record = DataRecord(**data)
        db_session.add(record)
        records.append(record)

    await db_session.commit()
    await db_session.refresh(records[0])
    await db_session.refresh(records[1])
    await db_session.refresh(records[2])

    return records


@pytest_asyncio.fixture
async def test_processed_data(db_session: AsyncSession, test_tenant: Tenant) -> list[ProcessedData]:
    """Create test processed data."""
    from datetime import datetime

    processed_records = []
    sample_data = [
        {
            "record_id": "proc_001",
            "tenant_id": test_tenant.tenant_id,
            "confidence_score": 0.95,
            "auto_approved": True,
            "review_required": False,
            "ai_category": "high_value",
            "ai_confidence": 0.95,
            "ai_model": "gpt-4o",
            "cleaned_data": '{"name": "John Doe", "email": "john@example.com", "phone": "555-1234"}',
            "processed_at": datetime.utcnow(),
        },
        {
            "record_id": "proc_002",
            "tenant_id": test_tenant.tenant_id,
            "confidence_score": 0.92,
            "auto_approved": True,
            "review_required": False,
            "ai_category": "medium_value",
            "ai_confidence": 0.92,
            "ai_model": "gpt-4o",
            "cleaned_data": '{"name": "Jane Smith", "email": "jane@example.com", "phone": "555-5678"}',
            "processed_at": datetime.utcnow(),
        },
    ]

    for data in sample_data:
        record = ProcessedData(**data)
        db_session.add(record)
        processed_records.append(record)

    await db_session.commit()
    await db_session.refresh(processed_records[0])
    await db_session.refresh(processed_records[1])

    return processed_records


@pytest_asyncio.fixture
async def test_human_review_queue(db_session: AsyncSession, test_tenant: Tenant) -> list[HumanReviewQueue]:
    """Create test human review queue."""
    from datetime import datetime

    review_records = []
    sample_data = [
        {
            "review_id": "rev_001",
            "record_id": "rev_rec_001",
            "tenant_id": test_tenant.tenant_id,
            "status": "pending",
            "priority": "medium",
            "original_data": '{"name": "Uncertain Record", "email": "uncertain@example.com", "phone": "555-0000"}',
            "ai_confidence": 0.65,
            "ai_category": "uncertain",
            "created_at": datetime.utcnow(),
            "submitted_at": datetime.utcnow(),
        },
        {
            "review_id": "rev_002",
            "record_id": "rev_rec_002",
            "tenant_id": test_tenant.tenant_id,
            "status": "in_progress",
            "priority": "high",
            "original_data": '{"name": "Complex Record", "email": "complex@example.com", "phone": "555-1111"}',
            "ai_confidence": 0.45,
            "ai_category": "low_value",
            "created_at": datetime.utcnow(),
            "submitted_at": datetime.utcnow(),
            "started_at": datetime.utcnow(),
        },
    ]

    for data in sample_data:
        record = HumanReviewQueue(**data)
        db_session.add(record)
        review_records.append(record)

    await db_session.commit()
    await db_session.refresh(review_records[0])
    await db_session.refresh(review_records[1])

    return review_records


@pytest.fixture
def test_client(db_setup: None) -> TestClient:
    """Create a test client for FastAPI."""
    # Override the settings dependency
    app.dependency_overrides[get_settings] = lambda: test_settings()

    with TestClient(app) as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_test_client(db_setup: None) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for FastAPI."""
    # Override the settings dependency
    app.dependency_overrides[get_settings] = lambda: test_settings()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for testing."""
    from unittest.mock import Mock

    mock_client = Mock()
    mock_client.chat.completions.create.return_value = Mock()
    mock_client.chat.completions.create.return_value.choices = [Mock()]
    mock_client.chat.completions.create.return_value.choices[0].message = Mock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Looks like corporate data"}'

    return mock_client


@pytest.fixture
def mock_presidio():
    """Mock Presidio components for testing."""
    from unittest.mock import Mock

    # Mock analyzer
    mock_analyzer = Mock()
    mock_analyzer.analyze.return_value = [
        Mock(type="PERSON", text="John Doe"),
        Mock(type="EMAIL_ADDRESS", text="john@example.com"),
    ]

    # Mock anonymizer
    mock_anonymizer = Mock()
    mock_anonymizer.anonymize.return_value = Mock()
    mock_anonymizer.anonymize.return_value.text = "[REDACTED]"

    return mock_analyzer, mock_anonymizer


@pytest.fixture
def mock_label_studio():
    """Mock Label Studio client for testing."""
    from unittest.mock import Mock

    mock_client = Mock()
    mock_project = Mock()
    mock_client.get_project.return_value = mock_project
    mock_project.import_tasks.return_value = True

    return mock_client


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "tenant_id": "test_tenant_001",
            "created_at": "2023-12-20T12:00:00Z",
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
            "tenant_id": "test_tenant_001",
            "created_at": "2023-12-20T12:01:00Z",
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "555-9876",
            "tenant_id": "test_tenant_002",
            "created_at": "2023-12-20T12:02:00Z",
        },
    ]


@pytest.fixture
def pii_sample_data():
    """Sample data with PII for testing."""
    return [
        {
            "name": "John Doe",
            "email": "john.doe@company.com",
            "phone": "+1 (555) 123-4567",
            "credit_card": "4111-1111-1111-1111",
            "address": "123 Main St, Anytown, USA",
            "ssn": "123-45-6789",
        },
        {
            "name": "Jane Smith",
            "email": "jane.smith@business.org",
            "phone": "555-987-6543",
            "credit_card": "5500-0000-0000-0004",
            "address": "456 Oak Ave, Somewhere, USA",
        },
    ]


@pytest_asyncio.fixture
async def litellm_service():
    """LiteLLM service for testing with mocked completion."""
    service = LiteLLMService()

    # Mock the completion method to return test data
    async def mock_completion_impl(request):
        from src.services.litellm_service import LiteLLMResponse
        from decimal import Decimal
        return LiteLLMResponse(
            content='{"category": "test", "confidence": 0.95}',
            model="gpt-4o",
            provider="openai",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            cost=Decimal("0.01"),
            response_time_ms=100.0,
            cached=False,
            fallback_used=False,
            retry_count=0
        )

    service.completion = mock_completion_impl
    return service


@pytest.fixture
def cost_service():
    """Cost service for testing."""
    service = CostService()
    return service


@pytest_asyncio.fixture
async def live_redis_service():
    """Live Redis service for integration tests with real Redis instance."""
    # Configure Redis service for testing with live instance
    redis_service = RedisService(
        url="redis://localhost:6379/0",
        max_connections=10,
        retry_attempts=3,
        retry_delay=0.1,
        default_ttl=3600,
        enable_metrics=True
    )

    try:
        # Verify Redis is available
        health_check = await redis_service.health_check()
        if not health_check:
            pytest.skip("Redis instance not available at redis://localhost:6379/0")

        # Clear any existing data
        await redis_service.clear_cache()

        yield redis_service

    except Exception as e:
        if "Connection refused" in str(e) or "Could not connect" in str(e):
            pytest.skip(f"Redis instance not available: {e}")
        else:
            pytest.fail(f"Redis connection failed: {e}")

    finally:
        await redis_service.close()


@pytest_asyncio.fixture
async def redis_service():
    """Redis service fixture for integration tests - alias to live_redis_service."""
    # Configure Redis service for testing with live instance
    redis_service = RedisService(
        url="redis://localhost:6379/0",
        max_connections=10,
        retry_attempts=3,
        retry_delay=0.1,
        default_ttl=3600,
        enable_metrics=True
    )

    try:
        # Verify Redis is available
        health_check = await redis_service.health_check()
        if not health_check:
            pytest.skip("Redis instance not available at redis://localhost:6379/0")

        # Clear any existing data
        await redis_service.clear_cache()

        yield redis_service

    except Exception as e:
        if "Connection refused" in str(e) or "Could not connect" in str(e):
            pytest.skip(f"Redis instance not available: {e}")
        else:
            pytest.fail(f"Redis connection failed: {e}")

    finally:
        await redis_service.close()


@pytest_asyncio.fixture
async def litellm_integration_setup():
    """Full LiteLLM service with test configuration and Redis integration."""
    # Mock cost service to avoid actual API calls
    with patch('src.services.cost_service.CostService') as mock_cost_service:
        mock_cost_instance = mock_cost_service.return_value
        mock_cost_instance.calculate_cost = AsyncMock(return_value=Decimal("0.001"))
        mock_cost_instance.get_tenant_usage = AsyncMock(return_value=TenantUsage(
            tenant_id="test_tenant_001",
            total_cost=Decimal("0.01"),
            total_tokens=5000,
            request_count=10,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow()
        ))

        # Create and initialize LiteLLM service
        service = LiteLLMService()
        service._test_connectivity = AsyncMock()  # Mock connectivity test
        service.cost_service = mock_cost_instance

        await service.initialize()

        yield service

        # Cleanup
        await service.close()


@pytest.fixture
async def prompt_manager():
    """Prompt manager with test configuration."""
    # Skip singleton for tests to ensure clean state
    return PromptManager(skip_singleton=True)


@pytest.fixture
async def cost_tracking_setup():
    """Cost calculation service with test pricing models."""
    with patch('src.services.cost_service.CostService') as mock_cost_service:
        mock_cost_instance = mock_cost_service.return_value

        # Configure test pricing
        test_pricing = {
            "gpt-4o": {"input": Decimal("0.0025"), "output": Decimal("0.01")},
            "claude-3-5-sonnet": {"input": Decimal("0.003"), "output": Decimal("0.015")},
            "gpt-4o-mini": {"input": Decimal("0.00015"), "output": Decimal("0.0006")}
        }

        async def mock_calculate_cost(model, prompt_tokens, completion_tokens, tenant_id):
            pricing = test_pricing.get(model, test_pricing["gpt-4o"])
            input_cost = pricing["input"] * (prompt_tokens / 1000)
            output_cost = pricing["output"] * (completion_tokens / 1000)
            return input_cost + output_cost

        mock_cost_instance.calculate_cost = mock_calculate_cost
        yield mock_cost_instance


@pytest.fixture
async def realistic_test_data():
    """Realistic dataset for workflow testing."""
    return {
        "users": [
            {
                "name": "John Smith",
                "email": "john.smith@techcorp.com",
                "phone": "+1 (555) 123-4567",
                "department": "Engineering",
                "title": "Senior Software Engineer",
                "location": "San Francisco, CA"
            },
            {
                "name": "Sarah Johnson",
                "email": "sarah.johnson@finance.co",
                "phone": "+1 (555) 987-6543",
                "department": "Finance",
                "title": "Financial Analyst",
                "location": "New York, NY"
            },
            {
                "name": "Michael Chen",
                "email": "michael.chen@marketing.io",
                "phone": "+1 (555) 456-7890",
                "department": "Marketing",
                "title": "Marketing Director",
                "location": "Chicago, IL"
            },
            {
                "name": "Emily Davis",
                "email": "emily.davis@healthcare.org",
                "phone": "+1 (555) 321-0987",
                "department": "Healthcare",
                "title": "Clinical Research Coordinator",
                "location": "Boston, MA"
            },
            {
                "name": "Robert Wilson",
                "email": "robert.wilson@edu.edu",
                "phone": "+1 (555) 654-3210",
                "department": "Education",
                "title": "Professor",
                "location": "Austin, TX"
            }
        ],
        "categories": [
            "corporate_executive",
            "healthcare_professional",
            "educational_institution",
            "tech_company",
            "financial_services",
            "marketing_agency",
            "research_organization",
            "government_agency"
        ],
        "confidence_thresholds": {
            "high_confidence": 0.9,
            "medium_confidence": 0.7,
            "low_confidence": 0.5
        }
    }


@pytest.fixture
def mock_ai_response():
    """Mock AI response for testing."""
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "category": "corporate_executive",
                    "confidence": 0.95,
                    "priority": "high",
                    "reasoning": "Senior executive at tech company with complete contact information",
                    "metadata": {
                        "department": "Engineering",
                        "seniority": "Senior",
                        "location": "San Francisco"
                    }
                })
            }
        }],
        "usage": {
            "prompt_tokens": 350,
            "completion_tokens": 280,
            "total_tokens": 630
        }
    }


@pytest.fixture
def workflow_test_config():
    """Configuration for workflow testing."""
    return {
        "cache_ttl": 3600,  # 1 hour
        "max_retries": 3,
        "retry_delay": 0.5,
        "confidence_threshold": 0.85,
        "batch_size": 5,
        "parallel_requests": 3,
        "performance_target_seconds": 30,
        "cache_hit_rate_target": 0.8
    }


@pytest.fixture
def ai_request_data():
    """Sample AI request data for testing."""
    return {
        "prompt": "Analyze customer data: {'name': 'John Doe', 'email': 'john@corp.com'}",
        "system_prompt": "You are a data labeling expert. Classify customers and provide confidence scores.",
        "model": "gpt-4o",
        "temperature": 0.3,
        "max_tokens": 500,
        "tenant_id": "test_tenant_001",
        "user_id": "test_user_001",
        "request_id": "test_req_001",
        "metadata": {
            "record_id": "rec_001",
            "data_source": "csv"
        }
    }


# Note: pytestmark = pytest.mark.asyncio is removed because pytest.ini has asyncio_mode = auto
# This avoids conflicts with pytest-asyncio 1.3.0's automatic test detection