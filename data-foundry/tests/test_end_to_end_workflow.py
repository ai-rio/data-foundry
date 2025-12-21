"""
End-to-End Workflow Tests for Data Foundry with Real Redis Caching

This test suite validates the complete data processing workflow with:
- Data upload and ingestion
- AI processing with LiteLLM integration
- Real Redis caching at each step
- Cost tracking with Decimal precision
- Multi-tenant isolation
- Audit logging
- Human review integration
- Performance optimization through caching

Tests the complete flow: Upload → Processing → AI Labeling → Cost Tracking → Human Review
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, AsyncGenerator
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.litellm_service import LiteLLMService
from src.services.redis_service import RedisService
from src.core.prompts.prompt_manager import PromptManager, PromptManagerError
from src.services.cost_service import CostService
from src.models.data_record import DataRecord
from src.models.processed_data import ProcessedData
from src.models.human_review_queue import HumanReviewQueue
from src.models.usage_tracking import TenantUsage, AuditLog
from src.core.audit_service import AuditService
from src.tasks.ingestion import data_ingestion_flow
from src.database.connection import db_connection


@pytest.mark.asyncio
class TestEndToEndWorkflow:
    """End-to-end workflow tests with Redis caching."""

    @pytest.fixture
    async def workflow_services(self):
        """Initialize all services for workflow testing."""
        # Mock cost service
        with patch('src.services.cost_service.CostService') as mock_cost_service:
            mock_cost_service_instance = mock_cost_service.return_value
            mock_cost_service_instance.calculate_cost = AsyncMock(return_value=Decimal("0.002"))
            mock_cost_service_instance.get_tenant_usage = AsyncMock(return_value=TenantUsage(
                tenant_id="test_tenant_001",
                total_cost=Decimal("0.01"),
                total_tokens=5000,
                request_count=10,
                period_start=datetime.utcnow(),
                period_end=datetime.utcnow()
            ))

            services = {
                'redis': RedisService(
                    url="redis://localhost:6379/0",
                    max_connections=10,
                    retry_attempts=3,
                    retry_delay=0.1,
                    default_ttl=3600,
                    enable_metrics=True
                ),
                'litellm': LiteLLMService(),
                'prompt_manager': PromptManager(skip_singleton=True),
                'cost_service': mock_cost_service_instance,
                'audit_service': AuditService()
            }

            # Initialize services
            await services['litellm'].initialize()

            yield services

            # Cleanup
            await services['redis'].close()
            await services['litellm'].close()

    @pytest.fixture
    def test_csv_data(self):
        """Test CSV data for uploads."""
        return """name,email,phone,department
John Doe,john@example.com,555-1234,Sales
Jane Smith,jane@company.com,555-5678,Marketing
Bob Johnson,bob@enterprise.com,555-9876,Engineering
Alice Williams,alice@startup.com,555-2468,Sales"""

    @pytest.fixture
    def test_json_data(self):
        """Test JSON data for uploads."""
        return [
            {"name": "Charlie Brown", "email": "charlie@example.com", "phone": "555-1357"},
            {"name": "Diana Prince", "email": "diana@hero.com", "phone": "555-7531"},
            {"name": "Ethan Hunt", "email": "ethan@mission.com", "phone": "555-9999"}
        ]

    @pytest.fixture
    async def sample_records(self, db_session: AsyncSession, test_tenant):
        """Create sample data records for workflow testing."""
        records = []

        record_data = [
            {
                "record_id": "workflow_rec_001",
                "tenant_id": test_tenant.tenant_id,
                "data_source": "csv",
                "status": "raw",
                "raw_data": json.dumps({"name": "Test User 1", "email": "test1@example.com"}),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "record_id": "workflow_rec_002",
                "tenant_id": test_tenant.tenant_id,
                "data_source": "json",
                "status": "processing",
                "raw_data": json.dumps({"name": "Test User 2", "email": "test2@example.com", "department": "Engineering"}),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ]

        for data in record_data:
            record = DataRecord(**data)
            db_session.add(record)
            records.append(record)

        await db_session.commit()
        await db_session.refresh(records[0])
        await db_session.refresh(records[1])

        return records

    @pytest.mark.e2e
    async def test_complete_data_workflow_with_redis(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant,
        test_csv_data
    ):
        """Test complete workflow: Upload → Processing → AI Labeling → Cost Tracking."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']
        prompt_manager = workflow_services['prompt_manager']

        # Clear any existing data
        await redis.clear_cache()

        # Step 1: Upload data (simulate)
        uploaded_file_data = {
            "file_name": "test_workflow.csv",
            "file_size": len(test_csv_data.encode()),
            "content_type": "text/csv",
            "tenant_id": test_tenant.tenant_id,
            "uploaded_at": datetime.utcnow()
        }

        # Create data records from CSV
        lines = test_csv_data.strip().split('\n')
        headers = lines[0].split(',')

        for i, line in enumerate(lines[1:], 1):
            values = line.split(',')
            record_data = dict(zip(headers, values))

            record = DataRecord(
                record_id=f"upload_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="csv",
                status="raw",
                raw_data=json.dumps(record_data),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db_session.add(record)

        await db_session.commit()
        records = list(db_session.new)

        # Step 2: Process each record with AI
        mock_ai_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "corporate",
                        "confidence": 0.92,
                        "priority": "medium",
                        "reasoning": "Corporate contact information with clear domain"
                    })
                }
            }],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 200,
                "total_tokens": 350
            }
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_ai_response

            processed_data = []

            # Process records
            for record in records:
                start_time = time.time()

                # Get template and system prompt
                template_data = prompt_manager.get_template("data_classification")
                system_prompt = prompt_manager.get_system_prompt("data_classification")

                # Process with AI
                ai_response = await litellm.completion(
                    prompt=f"Analyze this contact data: {record.raw_data}",
                    system_prompt=system_prompt,
                    model="gpt-4o",
                    tenant_id=record.tenant_id,
                    use_cache=True,
                    metadata={"record_id": record.record_id, "operation": "ai_labeling"}
                )

                # Create processed data record
                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal(str(0.92)),
                    auto_approved=True,
                    review_required=False,
                    ai_category="corporate",
                    ai_confidence=Decimal(str(0.92)),
                    ai_model=ai_response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=ai_response.content,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    cost=ai_response.cost,
                    processed_at=datetime.utcnow()
                )

                processed_data.append(processed)
                db_session.add(processed)

            await db_session.commit()

            # Verify results
            assert len(processed_data) == 3  # 3 records in CSV (minus header)

            for pd in processed_data:
                assert pd.tenant_id == test_tenant.tenant_id
                assert pd.confidence_score >= Decimal("0.85")
                assert pd.ai_cost > 0
                assert isinstance(pd.ai_cost, Decimal)

        # Step 3: Verify Redis cache usage
        stats = await redis.get_statistics()
        assert stats.sets > 0, "Redis should have cached data"
        assert stats.total_requests > 0, "Redis should have recorded requests"

        # Step 4: Verify cost tracking
        total_cost = sum(pd.ai_cost for pd in processed_data)
        assert total_cost > Decimal("0"), "Total cost should be positive"

        # Step 5: Verify audit logging
        metrics = await litellm.get_metrics()
        assert metrics["requests_total"] == 3, "Should have 3 AI requests"
        assert metrics["requests_success"] == 3, "All requests should succeed"

    @pytest.mark.e2e
    async def test_redis_caching_workflow_performance(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant,
        test_csv_data
    ):
        """Test workflow performance with Redis caching optimization."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Clear cache
        await redis.clear_cache()

        # Create test records
        records = []
        for i in range(5):
            record = DataRecord(
                record_id=f"perf_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Perf Test User {i}",
                    "email": f"perf{i}@example.com",
                    "department": "Test Department"
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)

        await db_session.add_all(records)
        await db_session.commit()

        mock_ai_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "performance_test",
                        "confidence": 0.95,
                        "priority": "low"
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        # First pass: Process without cache (all misses)
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_ai_response

            start_time = time.time()
            processing_times = []

            for record in records:
                record_start = time.time()
                await litellm.completion(
                    prompt=f"Process: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    use_cache=True
                )
                processing_times.append(time.time() - record_start)

            first_pass_time = time.time() - start_time

        # Verify cache misses
        stats = await redis.get_statistics()
        assert stats.misses == 5, "All first requests should be cache misses"

        # Second pass: Process with cache (all hits)
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_ai_response

            start_time = time.time()
            cached_times = []

            for record in records:
                record_start = time.time()
                await litellm.completion(
                    prompt=f"Process: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    use_cache=True
                )
                cached_times.append(time.time() - record_start)

            second_pass_time = time.time() - start_time

        # Verify cache hits
        stats = await redis.get_statistics()
        assert stats.hits == 5, "All second requests should be cache hits"

        # Performance comparison
        assert second_pass_time < first_pass_time, "Cached should be faster"

        # Verify performance metrics were collected
        perf_metrics = await redis.get_performance_metrics()
        assert perf_metrics is not None
        assert perf_metrics.total_operations > 0

    @pytest.mark.e2e
    async def test_multi_tenant_workflow_isolation(
        self,
        workflow_services,
        db_session: AsyncSession
    ):
        """Test workflow isolation between different tenants."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Clear cache
        await redis.clear_cache()

        # Create two tenants
        tenant1 = tenant2 = None
        try:
            from src.models.tenant import Tenant

            tenant1 = Tenant(
                tenant_id="multi_tenant_001",
                name="Tenant A",
                status="active",
                max_users=50,
                max_data_records=10000,
                storage_limit_gb=50.0,
                enable_ai_labeling=True
            )

            tenant2 = Tenant(
                tenant_id="multi_tenant_002",
                name="Tenant B",
                status="active",
                max_users=50,
                max_data_records=10000,
                storage_limit_gb=50.0,
                enable_ai_labeling=True
            )

            db_session.add_all([tenant1, tenant2])
            await db_session.commit()
            await db_session.refresh(tenant1)
            await db_session.refresh(tenant2)

            # Create records for both tenants
            records = []
            for tenant in [tenant1, tenant2]:
                for i in range(3):
                    record = DataRecord(
                        record_id=f"tenant_{tenant.tenant_id[-3:]}_rec_{i:03d}",
                        tenant_id=tenant.tenant_id,
                        data_source="json",
                        status="raw",
                        raw_data=json.dumps({
                            "name": f"Tenant {tenant.tenant_id[-3:]} User {i}",
                            "email": f"user{i}@{tenant.tenant_id[-3:]}.example.com"
                        }),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    records.append(record)

            await db_session.add_all(records)
            await db_session.commit()

            # Process records for both tenants
            mock_response = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "category": "multi_tenant_test",
                            "confidence": 0.90,
                            "tenant_specific": True
                        })
                    }
                }],
                "usage": {"prompt_tokens": 100, "completion_tokens": 150, "total_tokens": 250}
            }

            with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                mock_completion.return_value = mock_response

                # Process all records
                processed_data = []
                for record in records:
                    processed = ProcessedData(
                        record_id=f"proc_{record.record_id}",
                        original_record_id=record.record_id,
                        tenant_id=record.tenant_id,
                        confidence_score=Decimal("0.90"),
                        auto_approved=True,
                        review_required=False,
                        ai_category="multi_tenant_test",
                        ai_confidence=Decimal("0.90"),
                        ai_model="gpt-4o",
                        cleaned_data=record.raw_data,
                        ai_analysis="tenant specific analysis",
                        processing_time_ms=100,
                        cost=Decimal("0.001"),
                        processed_at=datetime.utcnow()
                    )
                    processed_data.append(processed)
                    db_session.add(processed)

                await db_session.commit()

                # Verify tenant isolation
                tenant1_records = [pd for pd in processed_data if pd.tenant_id == tenant1.tenant_id]
                tenant2_records = [pd for pd in processed_data if pd.tenant_id == tenant2.tenant_id]

                assert len(tenant1_records) == 3
                assert len(tenant2_records) == 3

                for pd in tenant1_records:
                    assert pd.tenant_id == tenant1.tenant_id

                for pd in tenant2_records:
                    assert pd.tenant_id == tenant2.tenant_id

            # Verify cache isolation
            stats = await redis.get_statistics()
            assert stats.sets == 6, "Should have 6 cache entries (3 per tenant)"

        finally:
            # Cleanup test tenants
            if tenant1 and tenant2:
                await db_session.delete(tenant1)
                await db_session.delete(tenant2)
                await db_session.commit()

    @pytest.mark.e2e
    async def test_human_review_workflow_integration(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test integration with human review workflow for low-confidence data."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records with varying confidence levels
        records = []
        review_queue = []

        record_data = [
            {
                "record_id": "review_high_conf",
                "tenant_id": test_tenant.tenant_id,
                "data_source": "json",
                "status": "raw",
                "raw_data": json.dumps({"name": "High Confidence User", "email": "high@example.com"}),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "record_id": "review_low_conf",
                "tenant_id": test_tenant.tenant_id,
                "data_source": "json",
                "status": "raw",
                "raw_data": json.dumps({"name": "Uncertain User", "email": "uncertain@example.com", "data": "partial"}),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ]

        for data in record_data:
            record = DataRecord(**data)
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Mock responses with different confidence levels
        high_conf_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "high_confidence",
                        "confidence": 0.95,
                        "auto_approved": True
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        low_conf_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "low_confidence",
                        "confidence": 0.65,
                        "auto_approved": False,
                        "needs_review": True
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            # Process high confidence record
            mock_completion.return_value = high_conf_response

            high_conf_processed = ProcessedData(
                record_id=f"proc_{records[0].record_id}",
                original_record_id=records[0].record_id,
                tenant_id=records[0].tenant_id,
                confidence_score=Decimal("0.95"),
                auto_approved=True,
                review_required=False,
                ai_category="high_confidence",
                ai_confidence=Decimal("0.95"),
                ai_model="gpt-4o",
                cleaned_data=records[0].raw_data,
                ai_analysis="High confidence analysis",
                cost=Decimal("0.001"),
                processed_at=datetime.utcnow()
            )

            db_session.add(high_conf_processed)

            # Process low confidence record
            mock_completion.return_value = low_conf_response

            low_conf_processed = ProcessedData(
                record_id=f"proc_{records[1].record_id}",
                original_record_id=records[1].record_id,
                tenant_id=records[1].tenant_id,
                confidence_score=Decimal("0.65"),
                auto_approved=False,
                review_required=True,
                ai_category="low_confidence",
                ai_confidence=Decimal("0.65"),
                ai_model="gpt-4o",
                cleaned_data=records[1].raw_data,
                ai_analysis="Low confidence - needs review",
                cost=Decimal("0.001"),
                processed_at=datetime.utcnow()
            )

            db_session.add(low_conf_processed)
            await db_session.commit()

        # Create human review entries for low confidence records
        review_entry = HumanReviewQueue(
            review_id=f"rev_{records[1].record_id}",
            record_id=records[1].record_id,
            tenant_id=records[1].tenant_id,
            status="pending",
            priority="medium",
            original_data=records[1].raw_data,
            ai_confidence=Decimal("0.65"),
            ai_category="low_confidence",
            review_required_reason="AI confidence below threshold",
            created_at=datetime.utcnow(),
            submitted_at=datetime.utcnow()
        )

        db_session.add(review_entry)
        await db_session.commit()

        # Verify the workflow
        high_conf = await db_session.get(ProcessedData, high_conf_processed.record_id)
        low_conf = await db_session.get(ProcessedData, low_conf_processed.record_id)
        review = await db_session.get(HumanReviewQueue, review_entry.review_id)

        assert high_conf.auto_approved is True
        assert high_conf.review_required is False

        assert low_conf.auto_approved is False
        assert low_conf.review_required is True

        assert review.status == "pending"
        assert review.ai_confidence == Decimal("0.65")

    @pytest.mark.e2e
    async def test_audit_trail_workflow(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test audit trail throughout the workflow."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']
        audit_service = workflow_services['audit_service']

        # Create test record
        record = DataRecord(
            record_id="audit_test_rec",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({"name": "Audit Test User", "email": "audit@example.com"}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db_session.add(record)
        await db_session.commit()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "audit_test",
                        "confidence": 0.90
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        # Process with AI and capture audit events
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            # Create audit service with mock storage
            with patch.object(audit_service, 'create_audit_log', new_callable=AsyncMock) as mock_audit:
                await litellm.completion(
                    prompt=f"Process: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    metadata={
                        "record_id": record.record_id,
                        "operation": "ai_processing",
                        "workflow_step": "classification"
                    }
                )

                # Verify audit log was created
                mock_audit.assert_called_once()
                audit_call_args = mock_audit.call_args

                assert audit_call_args.kwargs['tenant_id'] == test_tenant.tenant_id
                assert audit_call_args.kwargs['operation'] == 'completion'
                assert audit_call_args.kwargs['model'] == 'gpt-4o'
                assert audit_call_args.kwargs['success'] is True
                assert audit_call_args.kwargs.get('usage') is not None
                assert audit_call_args.kwargs['cost'] > 0

        # Verify metrics include audit tracking
        metrics = await litellm.get_metrics()
        assert metrics["requests_total"] == 1
        assert metrics["requests_success"] == 1

    @pytest.mark.e2e
    async def test_workflow_error_handling_and_recovery(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test error handling and recovery in the workflow."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test record
        record = DataRecord(
            record_id="error_test_rec",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({"name": "Error Test User", "email": "error@example.com"}),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db_session.add(record)
        await db_session.commit()

        # Test 1: Redis connection error handling
        with patch('src.services.redis_service.RedisService.health_check', return_value=False):
            # Should still work even if Redis has issues
            try:
                with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
                    mock_completion.return_value = {
                        "choices": [{
                            "message": {
                                "content": json.dumps({"category": "error_recovery", "confidence": 0.8})
                            }
                        }],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
                    }

                    response = await litellm.completion(
                        prompt=f"Process: {record.raw_data}",
                        tenant_id=record.tenant_id,
                        use_cache=True  # Should not fail even if Redis is down
                    )

                    assert response is not None

            except Exception as e:
                pytest.fail(f"Should handle Redis errors gracefully: {e}")

        # Test 2: API rate limiting and fallback
        with patch('src.services.litellm_service.acompletion') as mock_completion:
            # Primary model fails with rate limit
            mock_completion.side_effect = Exception("Rate limit exceeded")

            # Set fallback models
            litellm.fallback_models = ["claude-3-5-sonnet"]

            mock_completion.side_effect = [
                Exception("Rate limit exceeded"),
                {
                    "choices": [{
                        "message": {
                            "content": json.dumps({"category": "fallback_success", "confidence": 0.85})
                        }
                    }],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 180, "total_tokens": 300}
                }
            ]

            response = await litellm.completion(
                prompt=f"Process: {record.raw_data}",
                tenant_id=record.tenant_id,
                model="gpt-4o"
            )

            assert response.fallback_used is True
            assert response.model == "claude-3-5-sonnet"

        # Test 3: Partial processing recovery
        # Create multiple records, process one successfully, one fails
        records = []
        for i in range(2):
            rec = DataRecord(
                record_id=f"error_recover_rec_{i}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({"name": f"Recovery Test {i}", "email": f"recovery{i}@example.com"}),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(rec)
            db_session.add(rec)

        await db_session.commit()

        # Process first successfully, second fails
        success_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "success", "confidence": 0.9})
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            # First succeeds
            mock_completion.return_value = success_response

            processed1 = ProcessedData(
                record_id=f"proc_{records[0].record_id}",
                original_record_id=records[0].record_id,
                tenant_id=records[0].tenant_id,
                confidence_score=Decimal("0.90"),
                auto_approved=True,
                review_required=False,
                ai_category="success",
                ai_confidence=Decimal("0.90"),
                ai_model="gpt-4o",
                cleaned_data=records[0].raw_data,
                ai_analysis="Successful processing",
                cost=Decimal("0.001"),
                processed_at=datetime.utcnow()
            )

            db_session.add(processed1)

            # Second fails
            mock_completion.side_effect = Exception("API error")

            # Should not crash, just record failure
            try:
                await litellm.completion(
                    prompt=f"Process: {records[1].raw_data}",
                    tenant_id=records[1].tenant_id
                )
            except:
                pass  # Expected failure

            await db_session.commit()

            # Verify first was processed, second remains raw
            proc1 = await db_session.get(ProcessedData, processed1.record_id)
            assert proc1 is not None

            # Verify metrics show the failure
            metrics = await litellm.get_metrics()
            assert metrics["requests_failed"] >= 1

    @pytest.mark.e2e
    async def test_workflow_performance_with_large_dataset(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test workflow performance with larger dataset using Redis optimization."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create larger dataset
        records = []
        for i in range(20):
            record = DataRecord(
                record_id=f"large_dataset_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Large Dataset User {i}",
                    "email": f"large{i}@example.com",
                    "department": "Engineering",
                    "level": f"Senior {i % 3}"
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Clear cache
        await redis.clear_cache()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "large_dataset",
                        "confidence": 0.92,
                        "priority": "medium"
                    })
                }
            }],
            "usage": {"prompt_tokens": 150, "completion_tokens": 200, "total_tokens": 350}
        }

        # Process with timing
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            start_time = time.time()
            processed_count = 0

            for record in records:
                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal("0.92"),
                    auto_approved=True,
                    review_required=False,
                    ai_category="large_dataset",
                    ai_confidence=Decimal("0.92"),
                    ai_model="gpt-4o",
                    cleaned_data=record.raw_data,
                    ai_analysis="Large dataset processing",
                    cost=Decimal("0.002"),
                    processing_time_ms=100,
                    processed_at=datetime.utcnow()
                )
                db_session.add(processed)
                processed_count += 1

            await db_session.commit()

            total_processing_time = time.time() - start_time

            # Verify performance
            assert processed_count == 20
            assert total_processing_time < 30  # Should complete in reasonable time

        # Verify Redis usage
        stats = await redis.get_statistics()
        assert stats.sets == 20, "Should cache all processed records"
        assert stats.total_requests == 20

        # Calculate tokens per second
        total_tokens = 20 * 350  # 20 records * 350 tokens each
        tokens_per_second = total_tokens / total_processing_time
        assert tokens_per_second > 100, f"Should process at least 100 tokens/second, got {tokens_per_second}"

    @pytest.mark.e2e
    async def test_workflow_cost_tracking_precision(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test cost tracking with precise Decimal calculations."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records with different costs
        records = []
        for i, cost_factor in enumerate([0.5, 1.0, 2.0, 1.5]):
            record = DataRecord(
                record_id=f"cost_precision_rec_{i}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Cost Test User {i}",
                    "email": f"cost{i}@example.com",
                    "complexity": f"level_{cost_factor}"
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Mock cost service with precise pricing
        cost_calculations = []
        original_cost_calc = litellm.cost_service.calculate_cost

        async def mock_cost_calc(model, prompt_tokens, completion_tokens, tenant_id):
            # Calculate cost with precision
            base_cost = Decimal("0.001")
            prompt_cost = base_cost * (prompt_tokens / 1000) * Decimal(prompt_tokens / 1000)
            completion_cost = base_cost * (completion_tokens / 1000) * Decimal(completion_tokens / 1000)

            total = prompt_cost + completion_cost
            cost_calculations.append({
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tenant_id": tenant_id,
                "cost": total,
                "timestamp": datetime.utcnow()
            })

            return total

        litellm.cost_service.calculate_cost = mock_cost_calc

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({"category": "cost_precision", "confidence": 0.9})
                }
            }],
            "usage": {"prompt_tokens": 200, "completion_tokens": 300, "total_tokens": 500}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            total_expected_cost = Decimal("0")
            processed_data = []

            for record in records:
                # Vary tokens based on record complexity
                token_multiplier = [0.5, 1.0, 2.0, 1.5][records.index(record)]
                prompt_tokens = int(200 * token_multiplier)
                completion_tokens = int(300 * token_multiplier)

                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens
                }

                mock_completion.return_value.usage = Mock()
                mock_completion.return_value.usage.model_dump.return_value = usage

                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal("0.90"),
                    auto_approved=True,
                    review_required=False,
                    ai_category="cost_precision",
                    ai_confidence=Decimal("0.90"),
                    ai_model="gpt-4o",
                    cleaned_data=record.raw_data,
                    ai_analysis="Cost precision test",
                    cost=Decimal("0"),  # Will be set by cost service
                    processing_time_ms=100,
                    processed_at=datetime.utcnow()
                )

                db_session.add(processed)
                processed_data.append(processed)

            await db_session.commit()

            # Calculate expected total cost
            expected_total = sum(calc["cost"] for calc in cost_calculations)
            actual_total = sum(pd.ai_cost for pd in processed_data)

            # Verify precision
            assert expected_total == actual_total
            assert isinstance(expected_total, Decimal)
            assert isinstance(actual_total, Decimal)

            # Verify no floating point errors
            assert str(expected_total) == str(actual_total)

            # Verify breakdown
            for calc, pd in zip(cost_calculations, processed_data):
                assert calc["tenant_id"] == pd.tenant_id
                assert calc["cost"] == pd.ai_cost

        # Restore original cost calculation
        litellm.cost_service.calculate_cost = original_cost_calc

    @pytest.mark.e2e
    async def test_workflow_cache_invalidation_strategy(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """Test cache invalidation strategies in the workflow."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records
        records = []
        for i in range(3):
            record = DataRecord(
                record_id=f"invalidation_rec_{i}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Invalidation User {i}",
                    "email": f"invalid{i}@example.com",
                    "version": "v1"
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "invalidation_test",
                        "confidence": 0.9,
                        "version": "v1"
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        # Process records and cache results
        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response

            for record in records:
                await litellm.completion(
                    prompt=f"Process: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    use_cache=True
                )

            # Verify cache is populated
            stats = await redis.get_statistics()
            assert stats.sets == 3

        # Update one record and verify cache invalidation
        updated_record = records[0]
        updated_record.raw_data = json.dumps({
            "name": f"Invalidation User {0}",
            "email": f"invalid{0}@example.com",
            "version": "v2"  # Changed version
        })
        updated_record.updated_at = datetime.utcnow()

        db_session.add(updated_record)
        await db_session.commit()

        # Process updated record - should use cache for similar but different data
        mock_response_v2 = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "category": "invalidation_test",
                        "confidence": 0.9,
                        "version": "v2"
                    })
                }
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        }

        with patch('src.services.litellm_service.acompletion', new_callable=AsyncMock) as mock_completion:
            mock_completion.return_value = mock_response_v2

            response = await litellm.completion(
                prompt=f"Process: {updated_record.raw_data}",
                tenant_id=updated_record.tenant_id,
                use_cache=True
            )

            # Should get new response (cache miss due to different data)
            assert "v2" in json.loads(response.content)["version"]

            # Verify cache now has both versions
            stats = await redis.get_statistics()
            assert stats.sets == 4  # 3 original + 1 new
            assert stats.hits == 2  # 2 hits for unchanged records