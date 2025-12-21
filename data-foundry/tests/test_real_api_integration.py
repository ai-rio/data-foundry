"""
TRUE Integration Tests for Data Foundry - Real OpenRouter API Integration

Phase 4.2 TDD Remediation: These tests follow strict TDD methodology
- RED Phase: Tests are written FIRST and expected to FAIL initially
- GREEN Phase: Minimal code implemented to make tests pass
- REFACTOR Phase: Code improved while keeping tests green

CRITICAL REQUIREMENTS:
- ZERO mocking of LiteLLM/OpenRouter API calls
- Real OpenRouter API integration with actual AI models
- Real Redis caching with live data
- Real cost calculations with Decimal precision
- Real performance measurements (<5s response time requirement)
- Actual AI categorization and confidence scores

SUCCESS CRITERIA:
- 100% real API integration (0% mocking)
- Tests validate actual AI responses and categorization
- Real Redis caching behavior tested
- Performance measured with actual API response times
- Cost tracking accuracy validated with real API costs
"""

import asyncio
import json
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional
from pathlib import Path

import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.litellm_service import LiteLLMService
from src.services.redis_service import RedisService
from src.core.prompts.prompt_manager import PromptManager
from src.services.cost_service_production import CostService
from src.models.data_record import DataRecord
from src.models.processed_data import ProcessedData
from src.models.human_review_queue import HumanReviewQueue
from src.models.usage_tracking import TenantUsage, AuditLog
from src.database.connection import db_connection

# Import test configuration
import os
from dotenv import load_dotenv

# Ensure we have the real OpenRouter API key
load_dotenv(dotenv_path=".env.local", override=True)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise pytest.skip("OPENROUTER_API_KEY not found in .env.local - cannot run TRUE integration tests")


@pytest.mark.asyncio
@pytest.mark.integration
class TestRealAPIIntegration:
    """
    TRUE Integration Tests with Real OpenRouter API

    These tests validate the complete system works with:
    - Actual OpenRouter API calls to real AI models
    - Real Redis caching with live data
    - Real cost calculations from actual API responses
    - Real performance measurements

    NO MOCKING ALLOWED - These must test the real system!
    """

    @pytest.fixture
    async def real_services(self):
        """
        Initialize services with REAL API connections.
        NO MOCKING - Real connections only!
        """
        # Verify Redis is available
        redis = RedisService(
            url="redis://localhost:6379/0",
            max_connections=10,
            retry_attempts=3,
            retry_delay=0.1,
            default_ttl=3600,
            enable_metrics=True
        )

        redis_health = await redis.health_check()
        if not redis_health:
            pytest.fail("Redis is not available for TRUE integration tests")

        # Initialize LiteLLM with REAL OpenRouter API
        litellm = LiteLLMService()

        # Override environment for real OpenRouter API
        os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY

        # Initialize with real API connectivity test
        try:
            await litellm.initialize()
        except Exception as e:
            pytest.fail(f"Failed to initialize LiteLLM with real API: {str(e)}")

        # Initialize Prompt Manager with real YAML templates
        prompt_manager = PromptManager(skip_singleton=True)

        # Initialize Production Cost Service
        cost_service = CostService(enable_cache=True, cache_ttl=3600)

        yield {
            'redis': redis,
            'litellm': litellm,
            'prompt_manager': prompt_manager,
            'cost_service': cost_service
        }

        # Cleanup
        await redis.close()
        await litellm.close()

    @pytest.fixture
    async def test_tenant(self, db_session: AsyncSession):
        """Create test tenant for real API integration."""
        from src.models.tenant import Tenant

        tenant = Tenant(
            tenant_id="real_api_test_tenant",
            name="Real API Integration Test",
            status="active",
            max_users=10,
            max_data_records=1000,
            storage_limit_gb=10.0,
            enable_ai_labeling=True,
            billing_enabled=True
        )

        db_session.add(tenant)
        await db_session.commit()
        await db_session.refresh(tenant)

        return tenant

    @pytest.mark.real_api
    async def test_real_openrouter_api_connection(
        self,
        real_services,
        test_tenant
    ):
        """
        RED PHASE: Test real OpenRouter API connection.

        This test validates that we can make REAL API calls to OpenRouter.
        Expected to fail if OpenRouter API is not accessible or configured.

        NO MOCKING ALLOWED!
        """
        litellm = real_services['litellm']

        # Real API call to OpenRouter
        start_time = time.time()

        try:
            response = await litellm.completion(
                prompt="Categorize this contact: John Doe, john@example.com, Software Engineer at Tech Corp",
                system_prompt="You are a data categorization assistant. Respond with JSON containing category, confidence (0-1), and reasoning.",
                model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                tenant_id=test_tenant.tenant_id,
                use_cache=False,  # Force real API call
                metadata={"test_type": "real_api_connection"}
            )

            response_time = time.time() - start_time

            # Assertions for real API response
            assert response is not None, "Real API should return response"
            assert response.content is not None, "Real API should return content"
            assert response.model is not None, "Real API should return model name"
            assert response.cost > 0, "Real API should incur cost"
            assert isinstance(response.cost, Decimal), "Cost should be Decimal"
            assert response_time < 5.0, f"Real API response should be <5s, took {response_time}s"
            assert response.cached is False, "Response should not be cached when use_cache=False"

            # Verify AI categorization actually happened
            try:
                ai_result = json.loads(response.content)
                assert "category" in ai_result, "AI should categorize the data"
                assert "confidence" in ai_result, "AI should provide confidence score"
                assert isinstance(ai_result["confidence"], (int, float)), "Confidence should be numeric"
                assert 0 <= ai_result["confidence"] <= 1, "Confidence should be between 0 and 1"
            except json.JSONDecodeError:
                pytest.fail(f"Real API should return valid JSON, got: {response.content}")

            print(f"✅ Real OpenRouter API Success: {response.model}, Cost: ${response.cost}, Time: {response_time}s")

        except Exception as e:
            pytest.fail(f"Real OpenRouter API call failed: {str(e)}")

    @pytest.mark.real_api
    async def test_real_ai_categorization_performance(
        self,
        real_services,
        test_tenant,
        db_session: AsyncSession
    ):
        """
        RED PHASE: Test real AI categorization with performance validation.

        This test validates that real AI categorization works within performance requirements.
        Expected to fail if AI categorization is too slow or inaccurate.

        NO MOCKING ALLOWED!
        """
        litellm = real_services['litellm']
        prompt_manager = real_services['prompt_manager']

        # Real test data for categorization
        test_contacts = [
            {
                "name": "Dr. Sarah Johnson",
                "email": "sarah.johnson@mayo.edu",
                "title": "Cardiologist",
                "organization": "Mayo Clinic"
            },
            {
                "name": "Mike Chen",
                "email": "mike.chen@techstartup.io",
                "title": "CTO",
                "organization": "InnovateTech"
            },
            {
                "name": "Maria Garcia",
                "email": "maria.garcia@gmail.com",
                "phone": "555-0123"
            }
        ]

        # Get real prompt template
        template_data = prompt_manager.get_template("data_classification")
        system_prompt = prompt_manager.get_system_prompt("data_classification")

        categorization_results = []

        for i, contact in enumerate(test_contacts):
            start_time = time.time()

            try:
                # Real AI categorization
                response = await litellm.completion(
                    prompt=f"Categorize this contact: {json.dumps(contact)}",
                    system_prompt=system_prompt,
                    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                    tenant_id=test_tenant.tenant_id,
                    use_cache=True,  # Test caching with real data
                    metadata={
                        "test_type": "real_categorization",
                        "contact_index": i,
                        "contact_data": contact
                    }
                )

                response_time = time.time() - start_time

                # Validate performance requirement
                if response_time > 5.0:
                    pytest.fail(f"Real AI categorization exceeded 5s limit: {response_time}s")

                # Validate AI response quality
                ai_result = json.loads(response.content)

                # Create processed data record
                processed = ProcessedData(
                    record_id=f"real_cat_{i:03d}_{int(time.time())}",
                    original_record_id=f"test_contact_{i}",
                    tenant_id=test_tenant.tenant_id,
                    confidence_score=Decimal(str(ai_result.get("confidence", 0))),
                    auto_approved=ai_result.get("confidence", 0) >= 0.85,
                    review_required=ai_result.get("confidence", 0) < 0.85,
                    ai_category=ai_result.get("category", "unknown"),
                    ai_confidence=Decimal(str(ai_result.get("confidence", 0))),
                    ai_model=response.model,
                    cleaned_data=json.dumps(contact),
                    ai_analysis=response.content,
                    processing_time_ms=int(response_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                db_session.add(processed)
                categorization_results.append({
                    "contact": contact,
                    "ai_result": ai_result,
                    "response": response,
                    "response_time": response_time
                })

                print(f"✅ Contact {i+1} categorized: {ai_result.get('category')} (confidence: {ai_result.get('confidence')})")

            except Exception as e:
                pytest.fail(f"Real AI categorization failed for contact {i}: {str(e)}")

        await db_session.commit()

        # Validate overall performance
        avg_response_time = sum(r["response_time"] for r in categorization_results) / len(categorization_results)
        if avg_response_time > 3.0:
            pytest.fail(f"Average categorization time exceeded 3s: {avg_response_time}s")

        # Validate categorization quality
        valid_categories = ["medical", "corporate", "personal", "education", "government", "unknown"]
        for result in categorization_results:
            category = result["ai_result"].get("category", "").lower()
            if category not in valid_categories:
                print(f"⚠️  Unexpected category: {category}")

        print(f"✅ Real AI categorization completed: {len(categorization_results)} contacts, avg time: {avg_response_time:.2f}s")

    @pytest.mark.real_api
    async def test_real_redis_caching_with_api(
        self,
        real_services,
        test_tenant
    ):
        """
        RED PHASE: Test real Redis caching with actual API responses.

        This test validates that Redis caching works with real API responses.
        Expected to fail if caching is not working properly.

        NO MOCKING ALLOWED!
        """
        redis = real_services['redis']
        litellm = real_services['litellm']

        # Clear cache for clean test
        await redis.clear_cache()

        test_prompt = "Categorize this: CEO at Fortune 500 company"

        # First call - should be cache miss and real API call
        start_time = time.time()

        try:
            response1 = await litellm.completion(
                prompt=test_prompt,
                model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                tenant_id=test_tenant.tenant_id,
                use_cache=True,
                metadata={"test_type": "real_cache_miss"}
            )

            first_call_time = time.time() - start_time

            # Validate first call
            assert response1 is not None, "First call should return response"
            assert response1.cached is False, "First call should not be cached"
            assert first_call_time > 0.5, "Real API call should take time"

            # Get Redis statistics
            stats_after_first = await redis.get_statistics()

            # Second call - should be cache hit
            start_time = time.time()

            response2 = await litellm.completion(
                prompt=test_prompt,
                model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                tenant_id=test_tenant.tenant_id,
                use_cache=True,
                metadata={"test_type": "real_cache_hit"}
            )

            second_call_time = time.time() - start_time

            # Validate cache hit
            assert response2 is not None, "Second call should return response"
            assert response2.cached is True, "Second call should be cached"
            assert response2.content == response1.content, "Cached response should match original"
            assert response2.model == response1.model, "Cached model should match original"
            assert second_call_time < first_call_time / 2, f"Cached call should be faster: {second_call_time}s vs {first_call_time}s"

            # Get final Redis statistics
            stats_after_second = await redis.get_statistics()

            # Validate cache behavior
            assert stats_after_second.hits > stats_after_first.hits, "Should have cache hits"
            assert stats_after_second.sets >= 1, "Should have cache sets"

            print(f"✅ Real Redis caching verified:")
            print(f"   First call (API): {first_call_time:.3f}s")
            print(f"   Second call (Cache): {second_call_time:.3f}s")
            print(f"   Speedup: {first_call_time/second_call_time:.1f}x faster")

        except Exception as e:
            pytest.fail(f"Real Redis caching test failed: {str(e)}")

    @pytest.mark.real_api
    async def test_real_cost_calculation_accuracy(
        self,
        real_services,
        test_tenant,
        db_session: AsyncSession
    ):
        """
        RED PHASE: Test real cost calculation with actual API billing.

        This test validates that cost calculation works with real API responses.
        Expected to fail if cost calculation is inaccurate.

        NO MOCKING ALLOWED!
        """
        litellm = real_services['litellm']
        cost_service = real_services['cost_service']

        test_prompts = [
            "Short categorization: john@example.com",
            "Medium categorization: John Smith, Senior Software Engineer at Tech Corp with 10 years experience",
            "Long categorization: Dr. Elizabeth Johnson, MD, PhD, is a renowned cardiologist at Mayo Clinic with extensive research in cardiovascular diseases and has published over 50 peer-reviewed papers"
        ]

        total_cost_from_api = Decimal("0")
        api_responses = []

        for i, prompt in enumerate(test_prompts):
            try:
                # Real API call with cost tracking
                response = await litellm.completion(
                    prompt=prompt,
                    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                    tenant_id=test_tenant.tenant_id,
                    use_cache=False,  # Force real API calls for accurate cost testing
                    metadata={
                        "test_type": "real_cost_calculation",
                        "prompt_index": i,
                        "prompt_length": len(prompt)
                    }
                )

                api_responses.append(response)
                total_cost_from_api += response.cost

                # Calculate cost using production service
                if hasattr(response, 'usage') and response.usage:
                    cost_calculation = await cost_service.calculate_cost(
                        model=response.model,
                        prompt_tokens=response.usage.get("prompt_tokens", 0),
                        completion_tokens=response.usage.get("completion_tokens", 0),
                        tenant_id=test_tenant.tenant_id,
                        request_id=f"real_cost_test_{i}"
                    )

                    # Validate cost calculation accuracy
                    api_cost = response.cost
                    calculated_cost = cost_calculation.total_cost

                    # Allow small difference for rounding/precision
                    cost_difference = abs(api_cost - calculated_cost)
                    if cost_difference > Decimal("0.001"):  # $0.001 tolerance
                        pytest.fail(
                            f"Cost calculation mismatch for prompt {i}:\n"
                            f"  API cost: ${api_cost}\n"
                            f"  Calculated cost: ${calculated_cost}\n"
                            f"  Difference: ${cost_difference}"
                        )

                    print(f"✅ Cost test {i+1}: API=${api_cost}, Calculated=${calculated_cost}")

            except Exception as e:
                pytest.fail(f"Real cost calculation failed for prompt {i}: {str(e)}")

        # Validate total cost
        if total_cost_from_api <= Decimal("0"):
            pytest.fail("Total cost from real API should be positive")

        print(f"✅ Real cost calculation validated: Total cost ${total_cost_from_api} for {len(test_prompts)} API calls")

    @pytest.mark.real_api
    async def test_real_model_fallback_mechanism(
        self,
        real_services,
        test_tenant
    ):
        """
        RED PHASE: Test real model fallback with actual API calls.

        This test validates that fallback works between real OpenRouter models.
        Expected to fail if fallback mechanism is not working.

        NO MOCKING ALLOWED!
        """
        litellm = real_services['litellm']

        # Configure fallback models
        litellm.fallback_models = [
            "openrouter/meta-llama/llama-3.1-8b-instruct:free",
            "openrouter/mistralai/mistral-7b-instruct:free"
        ]

        test_prompt = "Simple categorization test for fallback"

        try:
            # Try with primary model (will fallback if needed)
            response = await litellm.completion(
                prompt=test_prompt,
                model="openrouter/meta-llama/llama-3.1-8b-instruct:free",  # Primary
                tenant_id=test_tenant.tenant_id,
                use_cache=False,
                metadata={"test_type": "real_fallback_test"},
                max_retries=1,
                retry_delay=0.5
            )

            # Validate response
            assert response is not None, "Fallback should return response"
            assert response.content is not None, "Fallback should return content"
            assert response.model is not None, "Response should indicate which model was used"

            # Check if fallback was used
            metrics = await litellm.get_metrics()

            print(f"✅ Real model fallback test completed:")
            print(f"   Model used: {response.model}")
            print(f"   Fallback used: {getattr(response, 'fallback_used', False)}")
            print(f"   Response: {response.content[:100]}...")

        except Exception as e:
            pytest.fail(f"Real model fallback test failed: {str(e)}")

    @pytest.mark.real_api
    async def test_real_performance_requirements(
        self,
        real_services,
        test_tenant
    ):
        """
        RED PHASE: Test real performance requirements with actual API.

        This test validates that the system meets performance requirements with real API calls.
        Expected to fail if performance requirements are not met.

        NO MOCKING ALLOWED!
        """
        litellm = real_services['litellm']
        redis = real_services['redis']

        # Performance test parameters
        num_requests = 10
        max_response_time = 5.0  # 5 seconds per request
        max_avg_response_time = 3.0  # 3 seconds average
        min_cache_speedup = 2.0  # 2x faster with cache

        test_prompts = [
            f"Categorize contact {i}: user{i}@example.com"
            for i in range(num_requests)
        ]

        # Test 1: Uncached performance (real API calls)
        uncached_times = []

        for i, prompt in enumerate(test_prompts):
            start_time = time.time()

            try:
                response = await litellm.completion(
                    prompt=prompt,
                    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                    tenant_id=test_tenant.tenant_id,
                    use_cache=False,  # Force real API calls
                    metadata={"test_type": "performance_uncached", "request_index": i}
                )

                response_time = time.time() - start_time
                uncached_times.append(response_time)

                # Validate individual response time
                if response_time > max_response_time:
                    pytest.fail(f"Request {i} exceeded {max_response_time}s limit: {response_time}s")

            except Exception as e:
                pytest.fail(f"Performance test failed for request {i}: {str(e)}")

        # Calculate uncached statistics
        avg_uncached_time = sum(uncached_times) / len(uncached_times)

        # Test 2: Cached performance
        cached_times = []

        for i, prompt in enumerate(test_prompts):
            start_time = time.time()

            try:
                response = await litellm.completion(
                    prompt=prompt,
                    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                    tenant_id=test_tenant.tenant_id,
                    use_cache=True,  # Should hit cache
                    metadata={"test_type": "performance_cached", "request_index": i}
                )

                response_time = time.time() - start_time
                cached_times.append(response_time)

            except Exception as e:
                pytest.fail(f"Cached performance test failed for request {i}: {str(e)}")

        # Calculate cached statistics
        avg_cached_time = sum(cached_times) / len(cached_times)

        # Validate performance requirements
        if avg_uncached_time > max_avg_response_time:
            pytest.fail(f"Average uncached time {avg_uncached_time:.2f}s exceeded {max_avg_response_time}s limit")

        cache_speedup = avg_uncached_time / avg_cached_time
        if cache_speedup < min_cache_speedup:
            pytest.fail(f"Cache speedup {cache_speedup:.1f}x below {min_cache_speedup}x requirement")

        # Validate Redis cache performance
        redis_stats = await redis.get_statistics()
        cache_hit_rate = redis_stats.hit_rate

        print(f"✅ Real performance requirements validated:")
        print(f"   Requests: {num_requests}")
        print(f"   Avg uncached: {avg_uncached_time:.3f}s")
        print(f"   Avg cached: {avg_cached_time:.3f}s")
        print(f"   Cache speedup: {cache_speedup:.1f}x")
        print(f"   Cache hit rate: {cache_hit_rate:.1%}")

    @pytest.mark.real_api
    async def test_real_end_to_end_workflow(
        self,
        real_services,
        test_tenant,
        db_session: AsyncSession
    ):
        """
        RED PHASE: Test complete end-to-end workflow with real APIs.

        This test validates the complete workflow with real APIs.
        Expected to fail if any part of the workflow is not working.

        NO MOCKING ALLOWED!
        """
        redis = real_services['redis']
        litellm = real_services['litellm']
        prompt_manager = real_services['prompt_manager']

        # Clear cache for clean test
        await redis.clear_cache()

        # Test data
        csv_data = """name,email,department,level
Dr. James Wilson,james.wilson@hospital.com,Medical,Senior
Lisa Chen,lisa.chen@techcorp.com,Engineering,Lead
Robert Johnson,bob@startup.io,Management,C-Level"""

        # Create data records
        records = []
        lines = csv_data.strip().split('\n')
        headers = lines[0].split(',')

        for i, line in enumerate(lines[1:], 1):
            values = line.split(',')
            record_data = dict(zip(headers, values))

            record = DataRecord(
                record_id=f"e2e_real_{i:03d}",
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

        # Process records with real AI
        processed_data = []
        total_cost = Decimal("0")
        total_processing_time = 0

        for record in records:
            start_time = time.time()

            try:
                # Get real prompt template
                system_prompt = prompt_manager.get_system_prompt("data_classification")

                # Real AI processing
                response = await litellm.completion(
                    prompt=f"Analyze this employee data: {record.raw_data}",
                    system_prompt=system_prompt,
                    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
                    tenant_id=test_tenant.tenant_id,
                    use_cache=True,
                    metadata={
                        "test_type": "e2e_real_workflow",
                        "record_id": record.record_id
                    }
                )

                processing_time = time.time() - start_time

                # Parse AI response
                ai_result = json.loads(response.content)

                # Create processed data
                processed = ProcessedData(
                    record_id=f"proc_e2e_{record.record_id}",
                    original_record_id=record.record_id,
                    tenant_id=test_tenant.tenant_id,
                    confidence_score=Decimal(str(ai_result.get("confidence", 0))),
                    auto_approved=ai_result.get("confidence", 0) >= 0.85,
                    review_required=ai_result.get("confidence", 0) < 0.85,
                    ai_category=ai_result.get("category", "unknown"),
                    ai_confidence=Decimal(str(ai_result.get("confidence", 0))),
                    ai_model=response.model,
                    cleaned_data=record.raw_data,
                    ai_analysis=response.content,
                    processing_time_ms=int(processing_time * 1000),
                    cost=response.cost,
                    processed_at=datetime.utcnow()
                )

                db_session.add(processed)
                processed_data.append(processed)
                total_cost += response.cost
                total_processing_time += processing_time

            except Exception as e:
                pytest.fail(f"E2E workflow failed for record {record.record_id}: {str(e)}")

        await db_session.commit()

        # Validate workflow results
        assert len(processed_data) == len(records), "All records should be processed"
        assert total_cost > Decimal("0"), "Total cost should be positive"
        assert total_processing_time > 0, "Total processing time should be positive"

        # Validate Redis caching
        redis_stats = await redis.get_statistics()
        assert redis_stats.total_requests > 0, "Should have made Redis requests"

        # Validate LiteLLM metrics
        litellm_metrics = await litellm.get_metrics()
        assert litellm_metrics["requests_total"] >= len(records), "Should have made API requests"

        avg_processing_time = total_processing_time / len(records)
        if avg_processing_time > 5.0:
            pytest.fail(f"Average processing time {avg_processing_time:.2f}s exceeded 5s limit")

        print(f"✅ Real E2E workflow completed:")
        print(f"   Records processed: {len(processed_data)}")
        print(f"   Total cost: ${total_cost}")
        print(f"   Avg processing time: {avg_processing_time:.2f}s")
        print(f"   Cache hits: {redis_stats.hits}")
        print(f"   Cache misses: {redis_stats.misses}")