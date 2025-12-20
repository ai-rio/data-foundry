"""
Performance tests for LiteLLM integration.

These tests validate:
- Load handling under concurrent requests
- Response time SLAs
- Memory usage optimization
- Throughput benchmarks
"""

import asyncio
import gc
import pytest
import pytest_asyncio
import time
import tracemalloc
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.services.ai_service import AIService, AIRequest


@pytest.mark.performance
class TestLiteLLMPerformance:
    """Performance tests for LiteLLM service."""

    @pytest_asyncio.fixture
    async def service(self):
        """Create LiteLLM service instance."""
        service = LiteLLMService()

        # Mock dependencies for performance testing
        service.redis_client = None  # Disable cache for pure performance test
        service.cost_service = None  # Disable cost calculation overhead

        await service.initialize()
        return service

    @pytest_asyncio.fixture
    async def ai_service(self):
        """Create AI service instance."""
        service = AIService()
        await service.initialize()
        return service

    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, service):
        """Test performance under concurrent load."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for performance test")

        # Configuration
        num_requests = 50
        concurrent_limit = 10
        max_response_time = 5.0  # seconds

        # Track performance metrics
        response_times: List[float] = []
        start_time = time.time()
        errors = []

        async def make_request(request_id: int):
            """Make a single request."""
            try:
                request_start = time.time()
                response = await service.completion(
                    prompt=f"Performance test {request_id}",
                    model="gpt-3.5-turbo",
                    max_tokens=5,  # Minimize tokens for speed
                    tenant_id="perf_test"
                )
                response_time = time.time() - request_start
                response_times.append(response_time)

                assert response_time < max_response_time, \
                    f"Response time {response_time}s exceeded SLA {max_response_time}s"

                return response

            except Exception as e:
                errors.append(str(e))
                return None

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def limited_request(request_id: int):
            async with semaphore:
                return await make_request(request_id)

        # Run all requests
        tasks = [limited_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate metrics
        total_time = time.time() - start_time
        successful_requests = [r for r in results if r is not None]
        success_rate = len(successful_requests) / num_requests

        # Performance assertions
        assert success_rate >= 0.95, f"Success rate {success_rate} below threshold"

        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response = max(response_times)
            p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]

            assert avg_response_time < 2.0, \
                f"Average response time {avg_response_time}s exceeded threshold"
            assert p95_response_time < 3.0, \
                f"P95 response time {p95_response_time}s exceeded threshold"

        # Throughput calculation
        throughput = num_requests / total_time
        assert throughput > 5, f"Throughput {throughput} RPS below threshold"

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, ai_service):
        """Test memory usage doesn't grow excessively under load."""
        import psutil
        import os

        process = psutil.Process(os.getpid())

        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for memory test")

        # Start memory tracking
        tracemalloc.start()
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make many requests
        num_requests = 100

        async def make_request(i):
            try:
                request = AIRequest(
                    prompt=f"Memory test {i}",
                    max_tokens=5,
                    tenant_id="memory_test"
                )
                await ai_service.completion(request)
            except:
                pass  # Ignore errors for memory test

        # Run requests in batches
        batch_size = 20
        for i in range(0, num_requests, batch_size):
            tasks = [make_request(j) for j in range(i, min(i + batch_size, num_requests))]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Force garbage collection
            gc.collect()

            # Check memory after each batch
            current_memory = process.memory_info().rss / 1024 / 1024
            memory_increase = current_memory - initial_memory

            # Memory shouldn't increase by more than 100MB total
            assert memory_increase < 100, \
                f"Memory increased by {memory_increase}MB, exceeds limit"

        # Final memory check
        current_memory = process.memory_info().rss / 1024 / 1024
        final_memory_trace = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        total_memory_increase = current_memory - initial_memory
        assert total_memory_increase < 100, \
            f"Total memory increase {total_memory_increase}MB exceeds limit"

    @pytest.mark.asyncio
    async def test_cache_performance(self, service):
        """Test caching improves performance."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for cache test")

        # Mock Redis for caching
        from unittest.mock import AsyncMock
        service.redis_client = AsyncMock()
        service.cost_service = AsyncMock()

        # Test data
        prompt = "Cache performance test prompt"
        num_requests = 20

        # First request - no cache
        service.redis_client.get.return_value = None
        service.cost_service.calculate_cost.return_value = Decimal("0.001")

        with pytest.MonkeyPatch().context() as m:
            # Mock LiteLLM to measure API call time
            async def mock_completion(**kwargs):
                await asyncio.sleep(0.5)  # Simulate API latency
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
                mock_response.usage = MagicMock(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15
                )
                mock_response.model_dump.return_value = {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
                return mock_response

            m.setattr("src.services.litellm_service.acompletion", mock_completion)

            # Time first request
            start_time = time.time()
            await service.completion(
                prompt=prompt,
                model="gpt-3.5-turbo",
                tenant_id="cache_perf_test",
                use_cache=True
            )
            first_request_time = time.time() - start_time

            # Setup cached response
            cached_data = {
                "content": "Cached response",
                "model": "gpt-3.5-turbo",
                "provider": "openai",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "cost": "0.001",
                "response_time_ms": 500,
                "metadata": {},
                "fallback_used": False,
                "retry_count": 0,
                "cached_at": datetime.utcnow().isoformat()
            }
            service.redis_client.get.return_value = json.dumps(cached_data)

            # Time cached requests
            cached_times = []
            for _ in range(num_requests):
                start_time = time.time()
                await service.completion(
                    prompt=prompt,
                    model="gpt-3.5-turbo",
                    tenant_id="cache_perf_test",
                    use_cache=True
                )
                cached_time = time.time() - start_time
                cached_times.append(cached_time)

            avg_cached_time = sum(cached_times) / len(cached_times)

            # Cache should be significantly faster
            assert avg_cached_time < first_request_time * 0.5, \
                f"Cache {avg_cached_time}s not significantly faster than {first_request_time}s"

            # Verify cache was used
            assert service.redis_client.get.call_count == num_requests + 1

    @pytest.mark.asyncio
    async def test_fallback_performance_impact(self, service):
        """Test fallback mechanism doesn't significantly impact performance."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for fallback test")

        # Configure fallback
        service.primary_model = "invalid-model"
        service.fallback_models = ["gpt-3.5-turbo"]

        with pytest.MonkeyPatch().context() as m:
            response_times = []
            num_requests = 10

            async def mock_completion(**kwargs):
                if kwargs.get("model") == "invalid-model":
                    raise Exception("Model not found")

                start_time = time.time()
                # Simulate actual API time
                await asyncio.sleep(0.1)

                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Fallback response"))]
                mock_response.usage = MagicMock(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15
                )
                mock_response.model_dump.return_value = {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
                return mock_response

            m.setattr("src.services.litellm_service.acompletion", mock_completion)

            # Measure fallback response times
            for i in range(num_requests):
                start_time = time.time()

                response = await service.completion(
                    prompt=f"Fallback test {i}",
                    tenant_id="fallback_perf_test",
                    max_retries=1
                )

                response_time = time.time() - start_time
                response_times.append(response_time)

                # Verify fallback was used
                assert response.fallback_used is True
                assert response.model == "gpt-3.5-turbo"

            # Calculate metrics
            avg_fallback_time = sum(response_times) / len(response_times)
            max_fallback_time = max(response_times)

            # Fallback shouldn't add too much overhead
            assert avg_fallback_time < 1.0, \
                f"Average fallback time {avg_fallback_time}s too high"
            assert max_fallback_time < 2.0, \
                f"Max fallback time {max_fallback_time}s too high"

    @pytest.mark.asyncio
    async def test_throughput_scaling(self, ai_service):
        """Test how throughput scales with concurrency."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for scaling test")

        concurrency_levels = [1, 5, 10, 20]
        requests_per_level = 20
        results: Dict[int, Dict[str, float]] = {}

        for concurrency in concurrency_levels:
            start_time = time.time()

            # Create requests
            async def make_request(i):
                try:
                    request = AIRequest(
                        prompt=f"Scaling test {i}",
                        max_tokens=5,
                        tenant_id="scaling_test"
                    )
                    await ai_service.completion(request)
                    return True
                except:
                    return False

            # Run with semaphore
            semaphore = asyncio.Semaphore(concurrency)

            async def limited_request(i):
                async with semaphore:
                    return await make_request(i)

            tasks = [limited_request(i) for i in range(requests_per_level)]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            total_time = time.time() - start_time
            successful = sum(1 for r in task_results if r is True)
            throughput = successful / total_time

            results[concurrency] = {
                "total_time": total_time,
                "successful": successful,
                "throughput": throughput
            }

        # Analyze scaling
        # Throughput should increase with concurrency up to a point
        assert results[5]["throughput"] > results[1]["throughput"], \
            "Throughput didn't increase with concurrency"
        assert results[10]["throughput"] >= results[5]["throughput"] * 0.8, \
            "Throughput degraded significantly at 10x concurrency"

        # Even at high concurrency, should maintain reasonable throughput
        assert results[20]["throughput"] > 1.0, \
            f"Throughput too low at 20x concurrency: {results[20]['throughput']}"

    @pytest.mark.asyncio
    async def test_large_prompt_handling(self, service):
        """Test performance with large prompts."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for large prompt test")

        # Create large prompt (close to context limit)
        large_prompt = "Test prompt. " * 1000  # About 8000 tokens

        with pytest.MonkeyPatch().context() as m:
            async def mock_completion(**kwargs):
                # Simulate processing time proportional to prompt size
                prompt_size = len(kwargs.get("messages", [{}])[0].get("content", ""))
                processing_time = min(prompt_size / 10000, 2.0)  # Cap at 2 seconds
                await asyncio.sleep(processing_time)

                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Large response"))]
                mock_response.usage = MagicMock(
                    prompt_tokens=8000,
                    completion_tokens=100,
                    total_tokens=8100
                )
                mock_response.model_dump.return_value = {
                    "prompt_tokens": 8000,
                    "completion_tokens": 100,
                    "total_tokens": 8100
                }
                return mock_response

            m.setattr("src.services.litellm_service.acompletion", mock_completion)

            # Time the request
            start_time = time.time()
            response = await service.completion(
                prompt=large_prompt,
                model="gpt-3.5-turbo",
                max_tokens=100,
                tenant_id="large_prompt_test"
            )
            response_time = time.time() - start_time

            # Performance assertions
            assert response_time < 5.0, \
                f"Large prompt response time {response_time}s exceeded threshold"
            assert response.usage["prompt_tokens"] == 8000, \
                "Large prompt token count incorrect"
            assert response.usage["total_tokens"] == 8100, \
                "Total token count incorrect"

    @pytest.mark.asyncio
    async def test_streaming_performance(self, service):
        """Test streaming completion performance."""
        # Skip if no API keys
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set for streaming test")

        with pytest.MonkeyPatch().context() as m:
            # Mock streaming response
            async def mock_completion(**kwargs):
                chunks = ["This ", "is ", "a ", "streamed ", "response."]
                for chunk in chunks:
                    mock_chunk = MagicMock()
                    mock_chunk.choices = [
                        MagicMock(delta=MagicMock(content=chunk))
                    ]
                    yield mock_chunk
                    await asyncio.sleep(0.05)  # Simulate network latency

            m.setattr("src.services.litellm_service.acompletion", mock_completion)

            # Time streaming response
            start_time = time.time()
            chunks = []

            async for chunk in service.stream_completion(
                prompt="Stream test",
                model="gpt-3.5-turbo",
                tenant_id="stream_test"
            ):
                chunks.append(chunk)

            response_time = time.time() - start_time

            # Performance assertions
            assert response_time < 2.0, \
                f"Streaming response time {response_time}s exceeded threshold"
            assert len(chunks) == 5, \
                f"Expected 5 chunks, got {len(chunks)}"
            assert "".join(chunks) == "This is a streamed response.", \
                "Streamed content incorrect"