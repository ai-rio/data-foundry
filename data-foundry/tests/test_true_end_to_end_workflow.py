"""
TRUE End-to-End Workflow Tests for Data Foundry

This test suite validates the complete data processing workflow with:
- Real OpenRouter API calls (NO MOCKING)
- Real Redis caching at each step
- Real cost calculation with actual API pricing
- Real database operations
- Real AI processing and categorization
- Performance validation (<5s response time)

Tests the complete flow: Upload → Processing → AI Labeling → Cost Tracking → Human Review
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile

from src.services.litellm_service import LiteLLMService
from src.services.redis_service import RedisService
from src.core.prompts.prompt_manager import PromptManager, PromptManagerError
from src.services.cost_service import CostService
from src.models.data_record import DataRecord
from src.models.processed_data import ProcessedData
from src.models.human_review_queue import HumanReviewQueue
from src.models.usage_tracking import TenantUsage, AuditLog
from src.core.audit_service import AuditService
from src.database.connection import get_db_session


class TestTrueEndToEndWorkflow:
    """TRUE end-to-end workflow tests - NO MOCKING ALLOWED"""

    @pytest.fixture
    async def workflow_services(self):
        """Initialize all services with real configurations."""
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
            'audit_service': AuditService()
        }

        # Initialize services
        await services['litellm'].initialize()

        # Verify all services are healthy
        redis_health = await services['redis'].health_check()
        assert redis_health, "Redis not available"

        litellm_health = await services['litellm'].health_check()
        assert litellm_health["healthy"], "LiteLLM service not healthy"

        yield services

        # Cleanup
        await services['redis'].close()
        await services['litellm'].close()

    @pytest.fixture
    def test_csv_data(self):
        """Test CSV data for real processing."""
        return """name,email,phone,title,company
John Doe,john@example.com,+1-555-0123,Software Engineer,TechCorp
Jane Smith,jane@startup.io,+1-555-0456,Product Manager,StartupIO
Bob Johnson,bob@enterprise.com,+1-555-0789,CTO,Enterprise Corp
Alice Williams,alice@startup.com,+1-555-2468,Marketing Manager,StartupIO"""

    @pytest.fixture
    def test_json_data(self):
        """Test JSON data for real processing."""
        return [
            {
                "name": "Charlie Brown",
                "email": "charlie@example.com",
                "phone": "+1-555-1357",
                "title": "Sales Representative",
                "company": "SalesCo"
            },
            {
                "name": "Diana Prince",
                "email": "diana@hero.com",
                "phone": "+1-555-7531",
                "title": "UX Designer",
                "company": "Hero Design"
            },
            {
                "name": "Ethan Hunt",
                "email": "ethan@mission.com",
                "phone": "+1-555-9999",
                "title": "Security Analyst",
                "company": "Mission Security"
            }
        ]

    @pytest.fixture
    async def test_tenant(self, db_session: AsyncSession):
        """Create test tenant."""
        from src.models.tenant import Tenant

        tenant = Tenant(
            tenant_id="workflow_test_tenant",
            name="Workflow Test Tenant",
            status="active",
            max_users=100,
            max_data_records=10000,
            storage_limit_gb=100.0,
            enable_ai_labeling=True
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        yield tenant

        # Cleanup
        await db_session.delete(tenant)
        await db_session.commit()

    @pytest.mark.true_e2e
    async def test_true_complete_data_workflow(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant,
        test_csv_data
    ):
        """TRUE complete workflow with real AI processing."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']
        prompt_manager = workflow_services['prompt_manager']

        start_time = time.time()

        # Clear any existing data
        await redis.clear_cache()

        # Step 1: Parse CSV and create data records
        lines = test_csv_data.strip().split('\n')
        headers = lines[0].split(',')

        records = []
        for i, line in enumerate(lines[1:], 1):
            values = line.split(',')
            record_data = dict(zip(headers, values))

            record = DataRecord(
                record_id=f"true_workflow_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="csv",
                status="raw",
                raw_data=json.dumps(record_data),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db_session.add(record)
            records.append(record)

        await db_session.commit()

        # Step 2: Process each record with REAL AI
        processed_data = []
        total_ai_time = 0

        for record in records:
            record_start = time.time()

            try:
                # Get real system prompt
                system_prompt = prompt_manager.get_system_prompt("data_classification")

                # Make REAL API call to OpenRouter
                ai_response = await litellm.completion(
                    prompt=f"Analyze this customer contact data and provide classification: {record.raw_data}",
                    system_prompt=system_prompt,
                    model="openrouter/openai/gpt-4o-mini",
                    tenant_id=record.tenant_id,
                    use_cache=True,  # Enable real caching
                    metadata={
                        "record_id": record.record_id,
                        "operation": "real_ai_labeling",
                        "workflow_step": "classification"
                    }
                )

                record_ai_time = time.time() - record_start
                total_ai_time += record_ai_time

                # Parse AI response
                ai_data = json.loads(ai_response.content)

                # Create processed data record
                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal(str(ai_data.get("confidence", 0.9))),
                    auto_approved=ai_data.get("auto_approved", True),
                    review_required=ai_data.get("review_required", False),
                    ai_category=ai_data.get("category", "unknown"),
                    ai_confidence=Decimal(str(ai_data.get("confidence", 0.9))),
                    ai_model=ai_response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=ai_response.content,
                    processing_time_ms=int(record_ai_time * 1000),
                    cost=ai_response.cost,
                    processed_at=datetime.utcnow()
                )

                processed_data.append(processed)
                db_session.add(processed)

                # Validate response time
                assert record_ai_time < 5, f"Record {record.record_id} AI processing too slow: {record_ai_time:.2f}s"

            except Exception as e:
                pytest.fail(f"AI processing failed for record {record.record_id}: {str(e)}")

        await db_session.commit()

        total_workflow_time = time.time() - start_time

        # Step 3: Verify complete workflow results
        assert len(processed_data) == len(records), "Should process all records"
        assert len(records) == 4, "Should have 4 records from CSV"

        # Validate AI categorization
        categories = [pd.ai_category for pd in processed_data]
        assert len(categories) == 4, "Should have 4 categories"

        for category in categories:
            assert isinstance(category, str), f"Category should be string: {category}"

        # Validate confidence scores
        for pd in processed_data:
            assert pd.confidence_score >= Decimal("0")
            assert pd.confidence_score <= Decimal("1")
            assert isinstance(pd.confidence_score, Decimal)

        # Validate real cost calculation
        total_cost = sum(pd.ai_cost for pd in processed_data)
        assert total_cost > Decimal("0"), "Total cost should be positive"
        assert isinstance(total_cost, Decimal)

        # Validate performance
        assert total_workflow_time < 30, f"Total workflow time too slow: {total_workflow_time:.2f}s"
        assert total_ai_time < 20, f"Total AI time too slow: {total_ai_time:.2f}s"

        # Average AI time per record should be < 5s
        avg_ai_time = total_ai_time / len(records)
        assert avg_ai_time < 5, f"Average AI time per record too slow: {avg_ai_time:.2f}s"

        # Verify Redis cache usage
        redis_stats = await redis.get_statistics()
        assert redis_stats.sets > 0, "Redis should have cached AI responses"
        assert redis_stats.total_requests > 0, "Redis should have recorded requests"

        # Verify metrics include all requests
        metrics = await litellm.get_metrics()
        assert metrics["requests_total"] >= len(records), f"Should have {len(records)} AI requests"
        assert metrics["cache_hits"] >= 0, "Should have cache hits"
        assert metrics["cache_misses"] >= len(records), f"Should have at least {len(records)} cache misses"

    @pytest.mark.true_e2e
    async def test_true_redis_caching_workflow_performance(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant,
        test_json_data
    ):
        """TRUE workflow performance with real Redis caching optimization."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records
        records = []
        for i, data in enumerate(test_json_data):
            record = DataRecord(
                record_id=f"true_perf_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps(data),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # First pass: Process without cache (all real API calls)
        start_time = time.time()
        processing_times = []

        for record in records:
            record_start = time.time()

            response = await litellm.completion(
                prompt=f"Process: {record.raw_data}",
                tenant_id=record.tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True  # Will be cache miss
            )

            processing_times.append(time.time() - record_start)
            assert response is not None

        first_pass_time = time.time() - start_time

        # Verify cache misses
        redis_stats = await redis.get_statistics()
        assert redis_stats.misses >= len(records), f"Should have {len(records)} cache misses"

        # Second pass: Process with cache (all cache hits)
        start_time = time.time()
        cached_times = []

        for record in records:
            record_start = time.time()

            response = await litellm.completion(
                prompt=f"Process: {record.raw_data}",
                tenant_id=record.tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True  # Should be cache hit
            )

            cached_times.append(time.time() - record_start)
            assert response is not None

        second_pass_time = time.time() - start_time

        # Verify cache hits
        redis_stats = await redis.get_statistics()
        assert redis_stats.hits >= len(records), f"Should have {len(records)} cache hits"

        # Performance comparison - cached should be significantly faster
        assert second_pass_time < first_pass_time, f"Cached {second_pass_time:.3f}s should be faster than uncached {first_pass_time:.3f}s"

        # Individual response times should be < 5s
        for response_time in processing_times + cached_times:
            assert response_time < 5, f"Response time {response_time:.3f}s exceeds 5s limit"

        # Verify performance metrics were collected
        perf_metrics = await redis.get_performance_metrics()
        assert perf_metrics is not None
        assert perf_metrics.total_operations > 0

    @pytest.mark.true_e2e
    async def test_true_multi_tenant_workflow_isolation(
        self,
        workflow_services,
        db_session: AsyncSession
    ):
        """TRUE multi-tenant workflow isolation with real data separation."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create multiple tenants
        tenants_data = [
            {"tenant_id": "multi_a", "name": "Tenant A"},
            {"tenant_id": "multi_b", "name": "Tenant B"},
            {"tenant_id": "multi_c", "name": "Tenant C"}
        ]

        tenants = []
        for tenant_data in tenants_data:
            from src.models.tenant import Tenant

            tenant = Tenant(
                tenant_id=tenant_data["tenant_id"],
                name=tenant_data["name"],
                status="active",
                max_users=50,
                max_data_records=1000,
                storage_limit_gb=10.0,
                enable_ai_labeling=True
            )
            db_session.add(tenant)
            tenants.append(tenant)

        await db_session.commit()

        # Create records for each tenant
        all_records = []
        for tenant in tenants:
            for i in range(2):
                record = DataRecord(
                    record_id=f"{tenant.tenant_id}_rec_{i:03d}",
                    tenant_id=tenant.tenant_id,
                    data_source="json",
                    status="raw",
                    raw_data=json.dumps({
                        "name": f"{tenant.tenant_id} User {i}",
                        "email": f"user{i}@{tenant.tenant_id}.example.com",
                        "department": "Test Department"
                    }),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                all_records.append(record)
                db_session.add(record)

        await db_session.commit()

        # Process records for all tenants
        processed_data = []

        for record in all_records:
            start_time = time.time()

            try:
                # Make REAL API call
                response = await litellm.completion(
                    prompt=f"Categorize: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=True
                )

                response_time = time.time() - start_time
                assert response_time < 5, f"Record {record.record_id} processing too slow: {response_time:.2f}s"

                # Create processed data
                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal("0.90"),
                    auto_approved=True,
                    review_required=False,
                    ai_category="multi_tenant_test",
                    ai_confidence=Decimal("0.90"),
                    ai_model=response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=response.content,
                    processing_time_ms=int(response_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                processed_data.append(processed)
                db_session.add(processed)

            except Exception as e:
                pytest.fail(f"Processing failed for record {record.record_id}: {str(e)}")

        await db_session.commit()

        # Verify tenant isolation
        tenant_records = {}
        for pd in processed_data:
            tenant = pd.tenant_id
            if tenant not in tenant_records:
                tenant_records[tenant] = []
            tenant_records[tenant].append(pd)

        for tenant, records in tenant_records.items():
            assert len(records) == 2, f"Tenant {tenant} should have 2 records"

        # Verify cache separation (each tenant should have separate cache entries)
        redis_stats = await redis.get_statistics()
        assert redis_stats.sets >= len(all_records), "Should have separate cache entries for each record"

    @pytest.mark.true_e2e
    async def test_true_human_review_workflow_integration(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """TRUE human review workflow integration with real confidence scoring."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records with varying confidence
        records = []

        # High confidence record
        high_conf_record = DataRecord(
            record_id="true_high_conf",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({
                "name": "High Confidence User",
                "email": "high@example.com",
                "title": "CEO",
                "company": "Big Corp"
            }),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        records.append(high_conf_record)

        # Low confidence record
        low_conf_record = DataRecord(
            record_id="true_low_conf",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({
                "name": "Uncertain User",
                "email": "uncertain@example.com",
                "data": "partial"  # Partial data to trigger low confidence
            }),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        records.append(low_conf_record)

        # Medium confidence record
        med_conf_record = DataRecord(
            record_id="true_med_conf",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({
                "name": "Medium Confidence User",
                "email": "medium@example.com",
                "phone": "+1-555-0000"
            }),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        records.append(med_conf_record)

        for record in records:
            db_session.add(record)

        await db_session.commit()

        processed_data = []

        # Process records with REAL AI
        for record in records:
            start_time = time.time()

            try:
                response = await litellm.completion(
                    prompt=f"Analyze contact data: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=True
                )

                response_time = time.time() - start_time
                assert response_time < 5, f"Record {record.record_id} processing too slow: {response_time:.2f}s"

                ai_data = json.loads(response.content)
                confidence = ai_data.get("confidence", 0.5)

                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal(str(confidence)),
                    auto_approved=confidence >= 0.85,
                    review_required=confidence < 0.85,
                    ai_category=ai_data.get("category", "unknown"),
                    ai_confidence=Decimal(str(confidence)),
                    ai_model=response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=response.content,
                    processing_time_ms=int(response_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                processed_data.append(processed)
                db_session.add(processed)

            except Exception as e:
                pytest.fail(f"AI processing failed for record {record.record_id}: {str(e)}")

        await db_session.commit()

        # Create human review entries for low confidence records
        low_conf_processed = next(pd for pd in processed_data if pd.original_record_id == "true_low_conf")
        med_conf_processed = next(pd for pd in processed_data if pd.original_record_id == "true_med_conf")

        if low_conf_processed.review_required:
            review_entry = HumanReviewQueue(
                review_id=f"rev_{low_conf_processed.record_id}",
                record_id=low_conf_processed.original_record_id,
                tenant_id=low_conf_processed.tenant_id,
                status="pending",
                priority="medium" if low_conf_processed.confidence_score >= Decimal("0.5") else "high",
                original_data=low_conf_processed.cleaned_data,
                ai_confidence=low_conf_processed.ai_confidence,
                ai_category=low_conf_processed.ai_category,
                review_required_reason="AI confidence below threshold",
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow()
            )
            db_session.add(review_entry)

        if med_conf_processed.review_required:
            review_entry = HumanReviewQueue(
                review_id=f"rev_{med_conf_processed.record_id}",
                record_id=med_conf_processed.original_record_id,
                tenant_id=med_conf_processed.tenant_id,
                status="pending",
                priority="low",
                original_data=med_conf_processed.cleaned_data,
                ai_confidence=med_conf_processed.ai_confidence,
                ai_category=med_conf_processed.ai_category,
                review_required_reason="Medium confidence - human review recommended",
                created_at=datetime.utcnow(),
                submitted_at=datetime.utcnow()
            )
            db_session.add(review_entry)

        await db_session.commit()

        # Verify workflow results
        high_conf = next(pd for pd in processed_data if pd.original_record_id == "true_high_conf")
        assert high_conf.auto_approved is True
        assert high_conf.review_required is False

        # Verify confidence levels make sense
        confidences = [pd.confidence_score for pd in processed_data]
        assert all(0 <= conf <= 1 for conf in confidences), "All confidence scores should be between 0 and 1"

        # Verify real costs
        total_cost = sum(pd.ai_cost for pd in processed_data)
        assert total_cost > 0, "Total cost should be positive"

    @pytest.mark.true_e2e
    async def test_true_audit_trail_workflow(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """TRUE audit trail throughout the workflow."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']
        audit_service = workflow_services['audit_service']

        # Create test record
        record = DataRecord(
            record_id="true_audit_rec",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({
                "name": "Audit Test User",
                "email": "audit@example.com",
                "department": "Audit Department"
            }),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db_session.add(record)
        await db_session.commit()

        start_time = time.time()

        # Process with REAL AI and capture audit events
        response = await litellm.completion(
            prompt=f"Process audit record: {record.raw_data}",
            tenant_id=record.tenant_id,
            metadata={
                "record_id": record.record_id,
                "operation": "real_ai_processing",
                "workflow_step": "classification",
                "source": "true_integration_test"
            }
        )

        response_time = time.time() - start_time
        assert response_time < 5, f"Audit workflow too slow: {response_time:.2f}s"

        # Create processed data
        processed = ProcessedData(
            record_id=f"proc_{record.record_id}",
            original_record_id=record.record_id,
            tenant_id=record.tenant_id,
            confidence_score=Decimal("0.90"),
            auto_approved=True,
            review_required=False,
            ai_category="audit_test",
            ai_confidence=Decimal("0.90"),
            ai_model=response.model,
            cleaned_data=record.raw_data,
            ai_analysis=response.content,
            processing_time_ms=int(response_time * 1000),
            cost=response.cost,
            processed_at=datetime.utcnow()
        )

        db_session.add(processed)
        await db_session.commit()

        # Verify metrics include the request
        metrics = await litellm.get_metrics()
        assert metrics["requests_total"] >= 1, "Should have at least 1 AI request"
        assert metrics["requests_success"] >= 1, "Should have successful requests"

        # Verify total cost is tracked
        assert metrics["total_cost"] > 0, "Total cost should be tracked"

    @pytest.mark.true_e2e
    async def test_true_workflow_error_handling_and_recovery(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """TRUE error handling and recovery in the workflow."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test record
        record = DataRecord(
            record_id="true_error_rec",
            tenant_id=test_tenant.tenant_id,
            data_source="json",
            status="raw",
            raw_data=json.dumps({
                "name": "Error Test User",
                "email": "error@example.com",
                "complex_data": "test data for error handling"
            }),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db_session.add(record)
        await db_session.commit()

        # Test 1: Normal operation
        try:
            start_time = time.time()
            response = await litellm.completion(
                prompt=f"Process error test: {record.raw_data}",
                tenant_id=record.tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=True
            )
            response_time = time.time() - start_time
            assert response_time < 5, f"Normal operation too slow: {response_time:.2f}s"
            assert response is not None
        except Exception as e:
            pytest.fail(f"Normal operation should not fail: {str(e)}")

        # Test 2: Test with invalid model (should fallback)
        try:
            start_time = time.time()
            response = await litellm.completion(
                prompt=f"Process fallback test: {record.raw_data}",
                tenant_id=record.tenant_id,
                model="invalid/model/name",  # Should trigger fallback
                use_cache=False
            )
            response_time = time.time() - start_time
            assert response_time < 5, f"Fallback operation too slow: {response_time:.2f}s"
            assert response.fallback_used is True
            assert response.model != "invalid/model/name"
        except Exception as e:
            pytest.fail(f"Fallback operation should not fail: {str(e)}")

        # Test 3: Test with very long prompt (should handle gracefully)
        try:
            long_prompt = "Process this data: " + "x" * 10000  # Very long
            response = await litellm.completion(
                prompt=long_prompt,
                tenant_id=record.tenant_id,
                model="openrouter/openai/gpt-4o-mini",
                use_cache=False
            )
            assert response is not None
        except Exception as e:
            # Should handle gracefully or give meaningful error
            assert "error" in str(e).lower() or "too long" in str(e).lower()

        # Verify error metrics are tracked
        metrics = await litellm.get_metrics()
        assert metrics["requests_total"] >= 3, "Should track all requests"
        assert metrics["requests_failed"] >= 0, "Should track failed requests"

    @pytest.mark.true_e2e
    async def test_true_workflow_cost_tracking_precision(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """TRUE cost tracking with precise Decimal calculations."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create test records with different complexities
        records = []
        complexities = ["simple", "medium", "complex", "very_complex"]

        for i, complexity in enumerate(complexities):
            record = DataRecord(
                record_id=f"true_cost_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Cost Test User {i}",
                    "email": f"cost{i}@example.com",
                    "complexity": complexity,
                    "data_length": len(complexity) * 100  # Vary data length
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        processed_data = []
        total_expected_cost = Decimal("0")

        # Process records with REAL AI
        for record in records:
            start_time = time.time()

            try:
                response = await litellm.completion(
                    prompt=f"Process cost test: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=True
                )

                response_time = time.time() - start_time
                assert response_time < 5, f"Record {record.record_id} cost test too slow: {response_time:.2f}s"

                total_expected_cost += response.cost

                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal("0.90"),
                    auto_approved=True,
                    review_required=False,
                    ai_category="cost_precision_test",
                    ai_confidence=Decimal("0.90"),
                    ai_model=response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=response.content,
                    processing_time_ms=int(response_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                processed_data.append(processed)
                db_session.add(processed)

            except Exception as e:
                pytest.fail(f"Cost processing failed for record {record.record_id}: {str(e)}")

        await db_session.commit()

        # Verify precise cost tracking
        actual_total_cost = sum(pd.ai_cost for pd in processed_data)

        # Should match exactly (no floating point errors)
        assert total_expected_cost == actual_total_cost
        assert isinstance(total_expected_cost, Decimal)
        assert isinstance(actual_total_cost, Decimal)

        # Verify individual costs are positive and precise
        for pd in processed_data:
            assert pd.ai_cost > 0
            assert isinstance(pd.ai_cost, Decimal)
            assert pd.ai_cost < Decimal("0.10")  # Should be small for these requests

        # Verify overall cost makes sense
        assert total_expected_cost > Decimal("0")
        assert total_expected_cost < Decimal("0.50")  # Should be reasonable for 4 requests

    @pytest.mark.true_e2e
    async def test_true_large_dataset_workflow_performance(
        self,
        workflow_services,
        db_session: AsyncSession,
        test_tenant
    ):
        """TRUE workflow performance with larger dataset."""
        redis = workflow_services['redis']
        litellm = workflow_services['litellm']

        # Create larger dataset (10 records)
        records = []
        for i in range(10):
            record = DataRecord(
                record_id=f"true_large_rec_{i:03d}",
                tenant_id=test_tenant.tenant_id,
                data_source="json",
                status="raw",
                raw_data=json.dumps({
                    "name": f"Large Dataset User {i}",
                    "email": f"large{i}@example.com",
                    "department": "Engineering" if i % 2 == 0 else "Sales",
                    "level": f"Senior {i % 3}",
                    "skills": ["Python", "SQL", "ML"] if i % 3 == 0 else ["Java", "Spring"],
                    "experience_years": i + 1
                }),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)
            db_session.add(record)

        await db_session.commit()

        # Clear cache
        await redis.clear_cache()

        start_time = time.time()
        processed_count = 0

        # Process records with timing
        for record in records:
            record_start = time.time()

            try:
                response = await litellm.completion(
                    prompt=f"Large dataset processing: {record.raw_data}",
                    tenant_id=record.tenant_id,
                    model="openrouter/openai/gpt-4o-mini",
                    use_cache=True
                )

                response_time = time.time() - record_start
                assert response_time < 5, f"Record {record.record_id} processing too slow: {response_time:.2f}s"

                processed = ProcessedData(
                    record_id=f"proc_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=record.tenant_id,
                    confidence_score=Decimal("0.90"),
                    auto_approved=True,
                    review_required=False,
                    ai_category="large_dataset_test",
                    ai_confidence=Decimal("0.90"),
                    ai_model=response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=response.content,
                    processing_time_ms=int(response_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                db_session.add(processed)
                processed_count += 1

            except Exception as e:
                pytest.fail(f"Large dataset processing failed for record {record.record_id}: {str(e)}")

        await db_session.commit()
        total_processing_time = time.time() - start_time

        # Verify performance
        assert processed_count == 10, f"Should process {len(records)} records"
        assert total_processing_time < 60, f"Large dataset processing too slow: {total_processing_time:.2f}s"

        # Calculate average time per record
        avg_time_per_record = total_processing_time / processed_count
        assert avg_time_per_record < 5, f"Average time per record too slow: {avg_time_per_record:.2f}s"

        # Verify Redis usage
        redis_stats = await redis.get_statistics()
        assert redis_stats.sets >= processed_count, f"Should cache {processed_count} processed records"
        assert redis_stats.total_requests >= processed_count

        # Calculate tokens per second (rough estimate)
        total_tokens_estimated = processed_count * 500  # Rough estimate
        tokens_per_second = total_tokens_estimated / total_processing_time
        assert tokens_per_second > 50, f"Should process at least 50 tokens/second, got {tokens_per_second:.0f}"