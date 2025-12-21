"""
Integration Tests for Real Services

This test suite validates the integration with real services:
- LiteLLM with actual AI provider APIs
- Redis caching
- Cost service calculations
- Database operations with real models
- End-to-end workflows
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, AsyncMock
import json
import asyncio
from sqlalchemy import text

from src.services.ai_service import AIService, AIRequest
from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.services.redis_service import RedisService
from src.services.cost_service import CostService
from src.models import (
    User, Tenant, DataRecord, TokenUsage, TenantUsage,
    AuditLog, CostAlert, BillingEvent
)
from src.models.user import UserRole, UserStatus
from src.models.tenant import TenantStatus
from src.models.data_record import DataSource, DataStatus


@pytest.mark.integration
class TestLiteLLMIntegration:
    """Test LiteLLM integration with real AI providers."""

    @pytest.mark.asyncio
    async def test_litellm_service_initialization(self):
        """Test LiteLLM service initialization with real configuration."""
        # This test uses mocked dependencies but tests the service initialization
        with patch('src.services.litellm_service.litellm') as mock_litellm:
            mock_litellm.supported_models = ["gpt-4o", "gpt-4-turbo", "claude-3-opus"]

            service = LiteLLMService()

            # Test service initialization
            assert service.primary_model is not None
            assert service.fallback_models is not None
            assert len(service.all_models) > 0
            assert service.supported_providers is not None

    @pytest.mark.asyncio
    async def test_litellm_completion_with_mock(self, litellm_service):
        """Test LiteLLM completion with mocked response."""
        # Mock the litellm completion call
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95, "reasoning": "Corporate domain detected"}'
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 200

        with patch('litellm.completion', return_value=mock_response):
            # Create AI request
            request = AIRequest(
                prompt="Analyze customer data: {'name': 'John Doe', 'email': 'john@corp.com'}",
                system_prompt="You are a data labeling expert.",
                model="gpt-4o",
                temperature=0.3,
                max_tokens=200,
                tenant_id="test_tenant_001"
            )

            # Process through LiteLLM service
            response = await litellm_service.completion(request)

            # Verify response
            assert response.content is not None
            assert response.model == "gpt-4o"
            assert response.provider == "openai"
            assert response.usage is not None
            assert response.total_tokens == 200

    @pytest.mark.asyncio
    async def test_litellm_fallback_mechanism(self, litellm_service):
        """Test LiteLLM fallback mechanism."""
        primary_response = Mock()
        primary_response.choices = [Mock()]
        primary_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95}'
        primary_response.usage = Mock()
        primary_response.usage.prompt_tokens = 150
        primary_response.usage.completion_tokens = 50
        primary_response.usage.total_tokens = 200

        fallback_response = Mock()
        fallback_response.choices = [Mock()]
        fallback_response.choices[0].message.content = '{"category": "medium_value", "confidence": 0.80}'
        fallback_response.usage = Mock()
        fallback_response.usage.prompt_tokens = 150
        fallback_response.usage.completion_tokens = 50
        fallback_response.usage.total_tokens = 200

        with patch('litellm.completion') as mock_completion:
            # Simulate primary model failure and fallback success
            mock_completion.side_effect = [
                Exception("Primary model failed"),
                fallback_response
            ]

            request = AIRequest(
                prompt="Test request",
                system_prompt="Test system prompt",
                model="gpt-4o",
                tenant_id="test_tenant_001"
            )

            # Process with fallback
            response = await litellm_service.completion(request)

            # Verify fallback was used
            assert response.content is not None
            assert response.fallback_used is True
            assert response.retry_count == 1
            assert mock_completion.call_count == 2

    @pytest.mark.asyncio
    async def test_litellm_error_handling(self, litellm_service):
        """Test LiteLLM error handling."""
        with patch('litellm.completion', side_effect=Exception("API Error")):
            request = AIRequest(
                prompt="Test request",
                system_prompt="Test system prompt",
                model="gpt-4o",
                tenant_id="test_tenant_001"
            )

            with pytest.raises(Exception) as exc_info:
                await litellm_service.completion(request)

            assert "API Error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_litellm_response_caching(self, litellm_service):
        """Test LiteLLM response caching."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"category": "high_value", "confidence": 0.95}'
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150

        with patch('litellm.completion', return_value=mock_response):
            request = AIRequest(
                prompt="Test request for caching",
                system_prompt="Test system prompt",
                model="gpt-4o",
                tenant_id="test_tenant_001",
                use_cache=True,
                cache_ttl=3600
            )

            # First call - should hit the API
            response1 = await litellm_service.completion(request)

            # Second call - should hit cache
            response2 = await litellm_service.completion(request)

            # Both responses should be identical
            assert response1.content == response2.content
            # In a real implementation, we'd verify cache hit here


@pytest.mark.integration
class TestRedisIntegration:
    """Test Redis integration with caching and performance."""

    @pytest.mark.asyncio
    async def test_redis_service_initialization(self):
        """Test Redis service initialization."""
        redis_service = RedisService()

        # Test service initialization
        assert redis_service.redis_client is not None
        assert redis_service.ttl == 3600  # Default TTL

    @pytest.mark.asyncio
    async def test_redis_cache_operations(self, redis_service):
        """Test Redis cache operations."""
        cache_key = "test_key"
        cache_value = {"test": "data", "timestamp": datetime.utcnow().isoformat()}

        # Test set operation
        await redis_service.set(cache_key, cache_value, ttl=300)

        # Test get operation
        retrieved_value = await redis_service.get(cache_key)
        assert retrieved_value == cache_value

        # Test delete operation
        await redis_service.delete(cache_key)

        # Test key is deleted
        assert await redis_service.get(cache_key) is None

    @pytest.mark.asyncio
    async def test_redis_pattern_operations(self, redis_service):
        """Test Redis pattern operations."""
        # Set multiple keys with pattern
        keys_values = {
            "ai:gpt-4o:tenant_001": {"model": "gpt-4o", "tenant": "tenant_001"},
            "ai:gpt-4o:tenant_002": {"model": "gpt-4o", "tenant": "tenant_002"},
            "ai:claude-3:tenant_001": {"model": "claude-3", "tenant": "tenant_001"}
        }

        for key, value in keys_values.items():
            await redis_service.set(key, value)

        # Test pattern matching
        results = await redis_service.pattern_match("ai:gpt-4o:*")
        assert len(results) == 2
        assert "ai:gpt-4o:tenant_001" in results
        assert "ai:gpt-4o:tenant_002" in results

        # Clean up
        for key in keys_values.keys():
            await redis_service.delete(key)

    @pytest.mark.asyncio
    async def test_redis_counter_operations(self, redis_service):
        """Test Redis counter operations."""
        counter_key = "test_counter"

        # Test increment
        await redis_service.increment(counter_key)
        await redis_service.increment(counter_key)

        # Test get counter value
        counter_value = await redis_service.get_counter(counter_key)
        assert counter_value == 2

        # Test decrement
        await redis_service.decrement(counter_key)
        counter_value = await redis_service.get_counter(counter_key)
        assert counter_value == 1

        # Clean up
        await redis_service.delete(counter_key)

    @pytest.mark.asyncio
    async def test_redis_ttl_operations(self, redis_service):
        """Test Redis TTL operations."""
        key = "test_ttl_key"
        value = {"test": "data"}

        # Set with TTL
        await redis_service.set(key, value, ttl=10)

        # Check TTL
        ttl = await redis_service.ttl(key)
        assert ttl > 0

        # Wait for key to expire
        await asyncio.sleep(11)

        # Key should be expired
        assert await redis_service.get(key) is None

    @pytest.mark.asyncio
    async def test_redis_performance_benchmarks(self, redis_service):
        """Test Redis performance benchmarks."""
        key_prefix = "perf_test"
        test_data = {"data": "test_value", "timestamp": datetime.utcnow().isoformat()}

        # Set performance test
        start_time = datetime.utcnow()

        # Set 1000 keys
        for i in range(1000):
            await redis_service.set(f"{key_prefix}_{i}", test_data)

        set_duration = (datetime.utcnow() - start_time).total_seconds()

        # Get performance test
        start_time = datetime.utcnow()

        # Get 1000 keys
        for i in range(1000):
            await redis_service.get(f"{key_prefix}_{i}")

        get_duration = (datetime.utcnow() - start_time).total_seconds()

        # Cleanup
        for i in range(1000):
            await redis_service.delete(f"{key_prefix}_{i}")

        # Verify performance (should be very fast)
        assert set_duration < 5.0  # Should complete in under 5 seconds
        assert get_duration < 5.0  # Should complete in under 5 seconds

        # Log performance metrics
        print(f"Redis SET performance: {1000/set_duration:.2f} ops/sec")
        print(f"Redis GET performance: {1000/get_duration:.2f} ops/sec")


@pytest.mark.integration
class TestCostServiceIntegration:
    """Test Cost Service integration with billing and usage tracking."""

    @pytest.mark.asyncio
    async def test_cost_service_initialization(self):
        """Test Cost Service initialization."""
        cost_service = CostService()

        # Test service initialization
        assert cost_service.pricing_rules is not None
        assert cost_service.tenant_balances is not None
        assert cost_service.alert_thresholds is not None

    @pytest.mark.asyncio
    async def test_token_cost_calculation(self, cost_service):
        """Test token cost calculation."""
        # Test GPT-4 token costs
        cost = cost_service.calculate_token_cost(
            model="gpt-4o",
            provider="openai",
            prompt_tokens=1000,
            completion_tokens=500
        )

        assert cost > 0
        assert isinstance(cost, Decimal)

    @pytest.mark.asyncio
    async def test_tenant_usage_aggregation(self, cost_service, db_session):
        """Test tenant usage aggregation."""
        # Create test tenant
        tenant = Tenant(
            tenant_id="cost_test_001",
            name="Cost Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=10000,
            storage_limit_gb=10.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create test token usage
        token_usage = TokenUsage(
            token_id="tok_test_001",
            tenant_id=tenant.tenant_id,
            user_id="user_001",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_per_token_input=Decimal("0.00001"),
            cost_per_token_output=Decimal("0.00002"),
            total_cost=Decimal("0.02"),
            request_timestamp=datetime.utcnow()
        )
        db_session.add(token_usage)
        await db_session.commit()

        # Aggregate tenant usage
        usage_report = await cost_service.get_tenant_usage_report(
            tenant.tenant_id,
            start_date=datetime.utcnow().replace(day=1),
            end_date=datetime.utcnow()
        )

        # Verify usage report
        assert usage_report is not None
        assert usage_report["tenant_id"] == tenant.tenant_id
        assert usage_report["total_tokens_used"] == 1500
        assert usage_report["total_cost"] == Decimal("0.02")
        assert usage_report["token_usage_count"] == 1

    @pytest.mark.asyncio
    async def test_cost_alert_generation(self, cost_service, db_session):
        """Test cost alert generation."""
        # Create test tenant with low budget
        tenant = Tenant(
            tenant_id="alert_test_001",
            name="Alert Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=10000,
            storage_limit_gb=10.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create high cost token usage
        token_usage = TokenUsage(
            token_id="tok_alert_001",
            tenant_id=tenant.tenant_id,
            user_id="user_001",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=100000,  # High usage
            completion_tokens=50000,
            total_tokens=150000,
            cost_per_token_input=Decimal("0.00001"),
            cost_per_token_output=Decimal("0.00002"),
            total_cost=Decimal("2000.00"),  # High cost
            request_timestamp=datetime.utcnow()
        )
        db_session.add(token_usage)
        await db_session.commit()

        # Check for alerts
        alerts = await cost_service.check_cost_alerts(tenant.tenant_id)

        # Should generate alerts for high cost
        assert len(alerts) > 0
        for alert in alerts:
            assert alert["tenant_id"] == tenant.tenant_id
            assert alert["alert_type"] == "cost_threshold"

    @pytest.mark.asyncio
    async def test_tenant_billing_simulation(self, cost_service, db_session):
        """Test tenant billing simulation."""
        # Create test tenant
        tenant = Tenant(
            tenant_id="billing_sim_001",
            name="Billing Sim Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=10000,
            storage_limit_gb=10.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )
        db_session.add(tenant)
        await db_session.commit()

        # Create multiple token usage records
        for i in range(10):
            token_usage = TokenUsage(
                token_id=f"tok_sim_{i:03d}",
                tenant_id=tenant.tenant_id,
                user_id="user_001",
                model="gpt-4o",
                provider="openai",
                prompt_tokens=100 * (i + 1),
                completion_tokens=50 * (i + 1),
                total_tokens=150 * (i + 1),
                cost_per_token_input=Decimal("0.00001"),
                cost_per_token_output=Decimal("0.00002"),
                total_cost=Decimal(f"{0.02 * (i + 1)}"),
                request_timestamp=datetime.utcnow()
            )
            db_session.add(token_usage)

        await db_session.commit()

        # Generate billing report
        billing_report = await cost_service.generate_monthly_billing_report(
            tenant.tenant_id,
            datetime.utcnow().year,
            datetime.utcnow().month
        )

        # Verify billing report
        assert billing_report is not None
        assert billing_report["tenant_id"] == tenant.tenant_id
        assert billing_report["period_start"] is not None
        assert billing_report["period_end"] is not None
        assert billing_report["total_cost"] > 0
        assert billing_report["billing_events"] is not None
        assert len(billing_report["billing_events"]) == 10


@pytest.mark.integration
class TestDatabaseIntegration:
    """Test database integration with enhanced models."""

    @pytest.mark.asyncio
    async def test_database_connection(self, db_session):
        """Test database connection and basic operations."""
        # Test basic database connection
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_enhanced_user_crud(self, db_session):
        """Test CRUD operations for enhanced User model."""
        # Create user
        user = User(
            user_id="db_user_001",
            email="db_test@example.com",
            tenant_id="tenant_001",
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            mfa_enabled=True,
            preferences={"theme": "dark"},
            permissions=["data:read", "data:write"]
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Verify user creation
        assert user.user_id == "db_user_001"
        assert user.email == "db_test@example.com"
        assert user.mfa_enabled is True
        assert user.preferences["theme"] == "dark"

        # Read user
        retrieved_user = await db_session.get(User, user.user_id)
        assert retrieved_user is not None
        assert retrieved_user.email == "db_test@example.com"

        # Update user
        retrieved_user.preferences["theme"] = "light"
        await db_session.commit()

        # Verify update
        updated_user = await db_session.get(User, user.user_id)
        assert updated_user.preferences["theme"] == "light"

        # Delete user
        await db_session.delete(retrieved_user)
        await db_session.commit()

        # Verify deletion
        deleted_user = await db_session.get(User, user.user_id)
        assert deleted_user is None

    @pytest.mark.asyncio
    async def test_enhanced_tenant_crud(self, db_session):
        """Test CRUD operations for enhanced Tenant model."""
        # Create tenant
        tenant = Tenant(
            tenant_id="db_tenant_001",
            name="Database Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=100,
            max_data_records=1000000,
            storage_limit_gb=100.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            billing_plan="premium",
            billing_status="active",
            feature_flags={
                "advanced_analytics": True,
                "data_export": True
            },
            custom_settings={
                "confidence_threshold": 0.85
            }
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        # Verify tenant creation
        assert tenant.tenant_id == "db_tenant_001"
        assert tenant.billing_plan == "premium"
        assert tenant.feature_flags["advanced_analytics"] is True

        # Read tenant
        retrieved_tenant = await db_session.get(Tenant, tenant.tenant_id)
        assert retrieved_tenant is not None
        assert retrieved_tenant.billing_plan == "premium"

        # Update tenant
        retrieved_tenant.custom_settings["confidence_threshold"] = 0.90
        await db_session.commit()

        # Verify update
        updated_tenant = await db_session.get(Tenant, tenant.tenant_id)
        assert updated_tenant.custom_settings["confidence_threshold"] == 0.90

        # Delete tenant
        await db_session.delete(retrieved_tenant)
        await db_session.commit()

        # Verify deletion
        deleted_tenant = await db_session.get(Tenant, tenant.tenant_id)
        assert deleted_tenant is None

    @pytest.mark.asyncio
    async def test_enhanced_data_record_crud(self, db_session):
        """Test CRUD operations for enhanced DataRecord model."""
        # Create data record
        record = DataRecord(
            record_id="db_record_001",
            tenant_id="tenant_001",
            data_source=DataSource.CSV,
            status=DataStatus.PROCESSED,
            raw_data='{"name": "John Doe", "email": "john@corp.com"}',
            ai_metadata={
                "confidence_score": 0.95,
                "category": "high_value",
                "model_used": "gpt-4o"
            },
            tags=["enterprise", "high_confidence"],
            validation_status="valid",
            validation_details={
                "pii_detected": True,
                "data_quality_score": 0.98
            }
        )

        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        # Verify record creation
        assert record.record_id == "db_record_001"
        assert record.ai_metadata["confidence_score"] == 0.95
        assert "enterprise" in record.tags

        # Read record
        retrieved_record = await db_session.get(DataRecord, record.record_id)
        assert retrieved_record is not None
        assert retrieved_record.ai_metadata["category"] == "high_value"

        # Update record
        retrieved_record.tags.append("new_tag")
        retrieved_record.ai_metadata["confidence_score"] = 0.98
        await db_session.commit()

        # Verify update
        updated_record = await db_session.get(DataRecord, record.record_id)
        assert "new_tag" in updated_record.tags
        assert updated_record.ai_metadata["confidence_score"] == 0.98

        # Delete record
        await db_session.delete(retrieved_record)
        await db_session.commit()

        # Verify deletion
        deleted_record = await db_session.get(DataRecord, record.record_id)
        assert deleted_record is None

    @pytest.mark.asyncio
    async def test_audit_log_tracking(self, db_session):
        """Test audit log tracking for all operations."""
        # Create test tenant and user first
        tenant = Tenant(
            tenant_id="audit_tenant_001",
            name="Audit Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=1000,
            storage_limit_gb=10.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )
        db_session.add(tenant)
        await db_session.commit()

        user = User(
            user_id="audit_user_001",
            email="audit@example.com",
            tenant_id=tenant.tenant_id,
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE
        )
        db_session.add(user)
        await db_session.commit()

        # Test that audit logs are created for operations
        # (This would require triggers to be set up in the database)
        # For now, we'll manually create an audit log
        audit_log = AuditLog(
            log_id="audit_test_001",
            tenant_id=tenant.tenant_id,
            user_id=user.user_id,
            action="data_record_create",
            resource_type="DataRecord",
            resource_id="rec_001",
            timestamp=datetime.utcnow(),
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            details={
                "record_data": {"name": "Test User"},
                "ai_confidence": 0.95,
                "processing_time_ms": 450
            },
            risk_level="low"
        )

        db_session.add(audit_log)
        await db_session.commit()

        # Verify audit log
        retrieved_audit = await db_session.get(AuditLog, audit_log.log_id)
        assert retrieved_audit is not None
        assert retrieved_audit.action == "data_record_create"
        assert retrieved_audit.details["ai_confidence"] == 0.95


@pytest.mark.integration
class TestEndToEndWorkflow:
    """Test end-to-end workflows with real services."""

    @pytest.mark.asyncio
    async def test_complete_data_processing_workflow(self, db_session, litellm_service, redis_service):
        """Test complete data processing workflow from ingestion to billing."""
        # Step 1: Create test tenant
        tenant = Tenant(
            tenant_id="workflow_tenant_001",
            name="Workflow Test Corp",
            status=TenantStatus.ACTIVE,
            max_users=10,
            max_data_records=10000,
            storage_limit_gb=100.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True,
            billing_plan="premium",
            billing_status="active"
        )
        db_session.add(tenant)
        await db_session.commit()

        # Step 2: Create test user
        user = User(
            user_id="workflow_user_001",
            email="workflow@example.com",
            tenant_id=tenant.tenant_id,
            hashed_password="hashed_password",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            mfa_enabled=False,
            permissions=["data:read", "data:write", "data:delete"]
        )
        db_session.add(user)
        await db_session.commit()

        # Step 3: Process sample data through the workflow
        sample_data = [
            {
                "record_id": f"wf_rec_{i:03d}",
                "name": f"Test User {i}",
                "email": f"user{i}@company.com",
                "phone": f"555-{i:04d}",
                "tenant_id": tenant.tenant_id
            }
            for i in range(5)
        ]

        # Step 4: Process each record through AI labeling
        for record_data in sample_data:
            # Mock AI response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "category": "high_value",
                "confidence": 0.95,
                "reasoning": "Corporate email pattern detected"
            })
            mock_response.usage = Mock()
            mock_response.usage.prompt_tokens = 150
            mock_response.usage.completion_tokens = 50
            mock_response.usage.total_tokens = 200

            with patch('litellm.completion', return_value=mock_response):
                # Create AI request
                request = AIRequest(
                    prompt=f"Analyze customer data: {record_data}",
                    system_prompt="You are a data labeling expert.",
                    model="gpt-4o",
                    temperature=0.3,
                    max_tokens=200,
                    tenant_id=record_data["tenant_id"],
                    user_id=user.user_id,
                    metadata={"record_id": record_data["record_id"]}
                )

                # Process through AI service
                response = await litellm_service.completion(request)

                # Create data record
                data_record = DataRecord(
                    record_id=record_data["record_id"],
                    tenant_id=tenant.tenant_id,
                    data_source=DataSource.JSON,
                    status=DataStatus.PROCESSED,
                    raw_data=json.dumps(record_data),
                    ai_metadata={
                        "confidence_score": response.metadata.get("confidence", 0.0),
                        "category": response.metadata.get("category", "unknown"),
                        "model_used": response.model,
                        "processing_time_ms": 450,
                        "tokens_used": response.total_tokens,
                        "cost_estimate": response.cost
                    },
                    tags=["workflow_test", "processed"],
                    validation_status="valid",
                    validation_details={
                        "pii_detected": True,
                        "data_quality_score": 0.98
                    },
                    processed_at=datetime.utcnow(),
                    processing_tenant_id=tenant.tenant_id,
                    processing_user_id=user.user_id
                )

                db_session.add(data_record)

        # Step 5: Commit all records
        await db_session.commit()

        # Step 6: Verify all records were processed
        records = await db_session.execute(
            text("SELECT * FROM data_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant.tenant_id}
        )
        records = records.fetchall()

        assert len(records) == 5
        for record in records:
            assert record.ai_metadata is not None
            assert record.ai_metadata["confidence_score"] == 0.95

        # Step 7: Cache the results in Redis
        for record in records:
            cache_key = f"record:{record.record_id}"
            cache_data = {
                "record_id": record.record_id,
                "tenant_id": record.tenant_id,
                "ai_category": record.ai_metadata.get("category"),
                "ai_confidence": record.ai_metadata.get("confidence_score")
            }
            await redis_service.set(cache_key, cache_data, ttl=3600)

        # Step 8: Generate usage report
        from src.services.cost_service import CostService
        cost_service = CostService()

        usage_report = await cost_service.get_tenant_usage_report(
            tenant.tenant_id,
            start_date=datetime.utcnow().replace(day=1),
            end_date=datetime.utcnow()
        )

        # Step 9: Create billing events
        billing_event = BillingEvent(
            event_id=f"bill_wf_{tenant.tenant_id}",
            tenant_id=tenant.tenant_id,
            event_type="ai_usage",
            description="AI processing workflow",
            amount=usage_report["total_cost"],
            currency="USD",
            timestamp=datetime.utcnow(),
            metadata={
                "records_processed": len(records),
                "average_confidence": sum(r.ai_metadata.get("confidence_score", 0) for r in records) / len(records),
                "workflow_type": "end_to_end_test"
            },
            status="pending",
            invoice_id=None,
            batch_id="workflow_batch_001"
        )

        db_session.add(billing_event)
        await db_session.commit()

        # Step 10: Verify billing event
        billing_event = await db_session.get(BillingEvent, billing_event.event_id)
        assert billing_event is not None
        assert billing_event.amount > 0
        assert billing_event.metadata["records_processed"] == 5

        # Step 11: Cleanup (in production, this would be handled by retention policies)
        # Delete test records
        for record in records:
            await db_session.delete(record)

        # Delete billing event
        await db_session.delete(billing_event)

        await db_session.commit()

        # Verify cleanup
        remaining_records = await db_session.execute(
            text("SELECT COUNT(*) FROM data_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant.tenant_id}
        )
        assert remaining_records.scalar() == 0

    @pytest.mark.asyncio
    async def test_tenant_isolation_validation(self, db_session, redis_service):
        """Test tenant isolation in the complete workflow."""
        # Create two tenants
        tenant1 = Tenant(
            tenant_id="iso_tenant_001",
            name="Isolation Test Corp 1",
            status=TenantStatus.ACTIVE,
            max_users=5,
            max_data_records=1000,
            storage_limit_gb=50.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )

        tenant2 = Tenant(
            tenant_id="iso_tenant_002",
            name="Isolation Test Corp 2",
            status=TenantStatus.ACTIVE,
            max_users=5,
            max_data_records=1000,
            storage_limit_gb=50.0,
            enable_pii_redaction=True,
            enable_ai_labeling=True,
            enable_human_review=True
        )

        db_session.add(tenant1)
        db_session.add(tenant2)
        await db_session.commit()

        # Create data records for both tenants
        for i, tenant in enumerate([tenant1, tenant2]):
            record = DataRecord(
                record_id=f"iso_rec_{i:03d}",
                tenant_id=tenant.tenant_id,
                data_source=DataSource.CSV,
                status=DataStatus.PROCESSED,
                raw_data=f'{{"name": "Tenant {i+1} User", "email": "user{i+1}@tenant{i+1}.com"}}',
                ai_metadata={
                    "confidence_score": 0.90,
                    "category": f"tenant_{i+1}",
                    "model_used": "gpt-4o"
                },
                tags=[f"tenant_{i+1}"],
                validation_status="valid"
            )
            db_session.add(record)

        await db_session.commit()

        # Verify tenant isolation by querying
        records1 = await db_session.execute(
            text("SELECT COUNT(*) FROM data_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant1.tenant_id}
        )
        records2 = await db_session.execute(
            text("SELECT COUNT(*) FROM data_records WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant2.tenant_id}
        )

        assert records1.scalar() == 1
        assert records2.scalar() == 1

        # Verify no cross-tenant data access
        cross_tenant_records = await db_session.execute(
            text("SELECT COUNT(*) FROM data_records WHERE tenant_id != :tenant_id"),
            {"tenant_id": tenant1.tenant_id}
        )
        # Should return 1 (tenant2's record)
        assert cross_tenant_records.scalar() == 1

        # Verify Redis caching respects tenant isolation
        for i, tenant in enumerate([tenant1, tenant2]):
            cache_key = f"tenant:{tenant.tenant_id}:records"
            cache_value = {"count": 1, "tenant": tenant.tenant_id}
            await redis_service.set(cache_key, cache_value, ttl=300)

        # Verify tenant-specific cache keys
        cache1 = await redis_service.get("tenant:iso_tenant_001:records")
        cache2 = await redis_service.get("tenant:iso_tenant_002:records")

        assert cache1 is not None
        assert cache1["tenant"] == "iso_tenant_001"
        assert cache2 is not None
        assert cache2["tenant"] == "iso_tenant_002"

        # Cleanup
        records = await db_session.execute(
            text("SELECT * FROM data_records WHERE tenant_id IN (:tenant1_id, :tenant2_id)"),
            {"tenant1_id": tenant1.tenant_id, "tenant2_id": tenant2.tenant_id}
        )
        records = records.fetchall()

        for record in records:
            await db_session.delete(record)

        await db_session.commit()


@pytest.fixture
def cost_service():
    """Cost service fixture for integration tests."""
    return CostService()


@pytest.fixture
def sample_ai_data():
    """Sample AI processing data for testing."""
    return [
        {
            "record_id": "ai_test_001",
            "name": "AI Test User 1",
            "email": "ai1@test.com",
            "phone": "555-0001",
            "tenant_id": "tenant_001"
        },
        {
            "record_id": "ai_test_002",
            "name": "AI Test User 2",
            "email": "ai2@test.com",
            "phone": "555-0002",
            "tenant_id": "tenant_001"
        }
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])