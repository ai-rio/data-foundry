"""
Simple REAL API Integration Tests - No Database Dependencies

These tests validate the core OpenRouter API integration without database setup.
They focus on the essential functionality: real AI calls, caching, and cost tracking.
"""

import asyncio
import json
import pytest
import time
from datetime import datetime
from decimal import Decimal
import os

# Load environment for real API integration
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.local", override=True)

# Verify OpenRouter API key is available
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    pytest.skip("OPENROUTER_API_KEY not found - cannot run real API tests")

from src.services.litellm_service import LiteLLMService
from src.services.redis_service import RedisService
from src.services.cost_service_production import CostService


@pytest.mark.asyncio
class TestRealAPISimple:
    """Simple real API tests without database dependencies."""

    @pytest.fixture
    async def services(self):
        """Initialize core services for real API testing."""
        # Redis service
        redis = RedisService(
            url="redis://localhost:6379/0",
            max_connections=5,
            retry_attempts=2,
            retry_delay=0.1,
            default_ttl=3600,
            enable_metrics=True
        )

        # Verify Redis is available
        redis_health = await redis.health_check()
        if not redis_health:
            pytest.fail("Redis is not available")

        # LiteLLM service with real OpenRouter API
        litellm = LiteLLMService()
        os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY

        try:
            await litellm.initialize()
        except Exception as e:
            pytest.fail(f"Failed to initialize LiteLLM: {str(e)}")

        # Cost service
        cost_service = CostService(enable_cache=True, cache_ttl=3600)

        yield {
            'redis': redis,
            'litellm': litellm,
            'cost_service': cost_service
        }

        # Cleanup
        await redis.close()
        await litellm.close()

    async def test_real_openrouter_api_call(self, services):
        """Test direct real OpenRouter API call."""
        litellm = services['litellm']

        start_time = time.time()

        response = await litellm.completion(
            prompt="Categorize this contact: John Doe, CEO at Tech Corp",
            system_prompt="You are a data categorization assistant. Return category and confidence score.",
            model="openrouter/openai/gpt-4o-mini",
            tenant_id="test_tenant",
            use_cache=False,  # Force real API call
            metadata={"test": "real_api_call"}
        )

        response_time = time.time() - start_time

        # Validate real response
        assert response is not None
        assert response.content is not None
        assert response.cost > 0
        assert response.model is not None
        assert response_time < 5.0
        assert response.cached is False
        assert len(response.content.strip()) > 0

        print(f"✅ Real API call successful:")
        print(f"   Model: {response.model}")
        print(f"   Cost: ${response.cost}")
        print(f"   Time: {response_time:.2f}s")
        print(f"   Response: {response.content[:100]}...")

    async def test_real_caching_behavior(self, services):
        """Test real Redis caching with API responses."""
        litellm = services['litellm']
        redis = services['redis']

        # Clear cache
        await redis.clear_cache()

        test_prompt = "Categorize: jane@example.com, Sales Manager"

        # First call (cache miss)
        start_time = time.time()
        response1 = await litellm.completion(
            prompt=test_prompt,
            model="openrouter/openai/gpt-4o-mini",
            tenant_id="test_tenant",
            use_cache=True,
            metadata={"test": "cache_miss"}
        )
        first_time = time.time() - start_time

        assert response1.cached is False
        assert first_time > 0.5  # Real API call takes time

        # Second call (cache hit)
        start_time = time.time()
        response2 = await litellm.completion(
            prompt=test_prompt,
            model="openrouter/openai/gpt-4o-mini",
            tenant_id="test_tenant",
            use_cache=True,
            metadata={"test": "cache_hit"}
        )
        second_time = time.time() - start_time

        assert response2.cached is True
        assert second_time < first_time / 2
        assert response2.content == response1.content

        # Check Redis stats
        stats = await redis.get_statistics()
        assert stats.hits > 0
        assert stats.sets >= 1

        print(f"✅ Caching behavior validated:")
        print(f"   First call: {first_time:.3f}s (API)")
        print(f"   Second call: {second_time:.3f}s (Cache)")
        print(f"   Speedup: {first_time/second_time:.1f}x")

    async def test_real_cost_tracking(self, services):
        """Test real cost calculation from API responses."""
        litellm = services['litellm']

        responses = []

        # Make multiple API calls with different lengths
        prompts = [
            "Short: john@example.com",
            "Medium: John Smith is a Senior Software Engineer with 10 years of experience at Tech Corp",
            "Long: Dr. Elizabeth Johnson, MD, PhD is a renowned cardiologist specializing in cardiovascular diseases and minimally invasive procedures"
        ]

        for i, prompt in enumerate(prompts):
            response = await litellm.completion(
                prompt=f"Categorize: {prompt}",
                model="openrouter/openai/gpt-4o-mini",
                tenant_id="test_tenant",
                use_cache=False,
                metadata={"test": "cost_tracking", "prompt_index": i}
            )
            responses.append(response)

        # Validate costs
        total_cost = sum(r.cost for r in responses)
        assert total_cost > 0
        assert all(r.cost > 0 for r in responses)

        print(f"✅ Cost tracking validated:")
        print(f"   Calls made: {len(responses)}")
        print(f"   Total cost: ${total_cost}")
        print(f"   Cost per call: ${total_cost/len(responses)}")
        print(f"   Costs: {[f'${r.cost}' for r in responses]}")

    async def test_real_performance_requirements(self, services):
        """Test performance with real API calls."""
        litellm = services['litellm']

        num_calls = 3
        response_times = []

        for i in range(num_calls):
            start_time = time.time()
            response = await litellm.completion(
                prompt=f"Categorize contact {i}: user{i}@example.com",
                model="openrouter/openai/gpt-4o-mini",
                tenant_id="test_tenant",
                use_cache=False,  # Test real API performance
                metadata={"test": "performance", "call_index": i}
            )
            response_time = time.time() - start_time
            response_times.append(response_time)

            assert response_time < 5.0, f"Call {i} too slow: {response_time}s"
            assert response.cost > 0
            assert len(response.content.strip()) > 0

        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)

        assert avg_time < 3.0, f"Average too slow: {avg_time}s"

        print(f"✅ Performance requirements met:")
        print(f"   Calls: {num_calls}")
        print(f"   Avg time: {avg_time:.2f}s")
        print(f"   Max time: {max_time:.2f}s")
        print(f"   Times: {[f'{t:.2f}s' for t in response_times]}")

    async def test_real_model_response_quality(self, services):
        """Test quality of real AI responses."""
        litellm = services['litellm']

        test_contacts = [
            {"name": "Dr. Sarah Johnson", "email": "sarah@mayo.edu", "title": "Cardiologist"},
            {"name": "Mike Chen", "email": "mike@techstartup.io", "title": "CTO"},
            {"name": "Maria Garcia", "email": "maria@gmail.com", "phone": "555-0123"}
        ]

        results = []

        for i, contact in enumerate(test_contacts):
            response = await litellm.completion(
                prompt=f"Analyze and categorize: {json.dumps(contact)}",
                system_prompt="You are a data analysis expert. Provide insights about this contact.",
                model="openrouter/openai/gpt-4o-mini",
                tenant_id="test_tenant",
                use_cache=True,
                metadata={"test": "response_quality", "contact_index": i}
            )

            results.append({
                "contact": contact,
                "response": response,
                "content_length": len(response.content),
                "has_insights": len(response.content) > 100
            })

        # Validate response quality
        assert len(results) == len(test_contacts)
        assert all(r["content_length"] > 50 for r in results)  # Substantial responses
        assert all(r["has_insights"] for r in results)  # Meaningful content

        print(f"✅ Response quality validated:")
        print(f"   Contacts analyzed: {len(results)}")
        print(f"   Avg response length: {sum(r['content_length'] for r in results)/len(results):.0f} chars")
        print(f"   All responses have insights: {all(r['has_insights'] for r in results)}")

        # Show sample responses
        for i, result in enumerate(results):
            print(f"   Contact {i+1}: {result['contact']['name']}")
            print(f"   Response preview: {result['response'].content[:150]}...")
            print()