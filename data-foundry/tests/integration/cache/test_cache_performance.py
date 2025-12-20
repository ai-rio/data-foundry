"""
Performance benchmarks for Redis cache operations.

These tests measure and validate the performance characteristics of
the caching system under various loads and conditions.
"""

import asyncio
import time
import statistics
import pytest
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

from src.core.cache import get_cache
from src.services.redis_service import get_redis_service


@dataclass
class BenchmarkResult:
    """Results from a performance benchmark."""
    operation: str
    total_operations: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    median_time: float
    p95_time: float
    p99_time: float
    ops_per_second: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "operation": self.operation,
            "total_operations": self.total_operations,
            "total_time": self.total_time,
            "avg_time": self.avg_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "median_time": self.median_time,
            "p95_time": self.p95_time,
            "p99_time": self.p99_time,
            "ops_per_second": self.ops_per_second
        }


@pytest.fixture
async def cache_benchmark():
    """Setup cache for benchmarking."""
    cache = get_cache()
    await cache.clear()
    yield cache
    await cache.clear()


@pytest.fixture
async def service_benchmark():
    """Setup Redis service for benchmarking."""
    service = get_redis_service()
    await service.clear_cache()
    await service.reset_statistics()
    if await service.get_performance_metrics():
        await service.reset_metrics()
    yield service
    await service.clear_cache()
    await service.close()


class PerformanceBenchmarks:
    """Performance benchmark utilities."""

    @staticmethod
    async def benchmark_operation(
        operation_func,
        operation_name: str,
        num_operations: int,
        concurrency: int = 1
    ) -> BenchmarkResult:
        """
        Benchmark an operation with specified concurrency.

        Args:
            operation_func: Async function to benchmark (accepts index)
            operation_name: Name of the operation for reporting
            num_operations: Total number of operations to perform
            concurrency: Number of concurrent operations

        Returns:
            BenchmarkResult with performance metrics
        """
        timings: List[float] = []

        async def worker(start_idx: int, end_idx: int):
            """Worker function for concurrent execution."""
            worker_timings = []
            for i in range(start_idx, end_idx):
                start_time = time.time()
                try:
                    await operation_func(i)
                except Exception as e:
                    print(f"Operation {i} failed: {e}")
                end_time = time.time()
                worker_timings.append(end_time - start_time)
            return worker_timings

        # Calculate workload distribution
        operations_per_worker = num_operations // concurrency
        start_time = time.time()

        # Create and run workers
        tasks = []
        for i in range(concurrency):
            start_idx = i * operations_per_worker
            end_idx = start_idx + operations_per_worker
            if i == concurrency - 1:  # Last worker gets remaining operations
                end_idx = num_operations
            tasks.append(worker(start_idx, end_idx))

        # Wait for all workers to complete
        worker_results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Flatten timings from all workers
        for worker_timings in worker_results:
            timings.extend(worker_timings)

        # Calculate statistics
        if not timings:
            raise RuntimeError("No timings collected")

        sorted_timings = sorted(timings)
        return BenchmarkResult(
            operation=operation_name,
            total_operations=len(timings),
            total_time=total_time,
            avg_time=statistics.mean(timings),
            min_time=min(timings),
            max_time=max(timings),
            median_time=statistics.median(timings),
            p95_time=sorted_timings[int(len(timings) * 0.95)],
            p99_time=sorted_timings[int(len(timings) * 0.99)],
            ops_per_second=len(timings) / total_time
        )


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestCachePerformance:
    """Performance benchmarks for cache operations."""

    async def test_single_operations_performance(self, cache_benchmark):
        """Benchmark individual cache operations."""
        benchmarks = PerformanceBenchmarks()
        results: List[BenchmarkResult] = []

        # Benchmark SET operations
        async def set_op(index: int):
            await cache_benchmark.set(f"perf_key_{index}", f"value_{index}")

        set_result = await benchmarks.benchmark_operation(
            set_op, "SET", 1000, concurrency=1
        )
        results.append(set_result)

        # Benchmark GET operations (cache hits)
        async def get_hit_op(index: int):
            await cache_benchmark.get(f"perf_key_{index % 100}")  # Hit rate with 100 unique keys

        get_hit_result = await benchmarks.benchmark_operation(
            get_hit_op, "GET_HIT", 1000, concurrency=1
        )
        results.append(get_hit_result)

        # Benchmark GET operations (cache misses)
        async def get_miss_op(index: int):
            await cache_benchmark.get(f"miss_key_{index}")

        get_miss_result = await benchmarks.benchmark_operation(
            get_miss_op, "GET_MISS", 1000, concurrency=1
        )
        results.append(get_miss_result)

        # Benchmark DELETE operations
        async def delete_op(index: int):
            await cache_benchmark.delete(f"perf_key_{index % 100}")

        delete_result = await benchmarks.benchmark_operation(
            delete_op, "DELETE", 100, concurrency=1
        )
        results.append(delete_result)

        # Print results
        print("\nSingle Operations Performance:")
        for result in results:
            print(f"{result.operation}: {result.ops_per_second:.2f} ops/sec "
                  f"(avg: {result.avg_time*1000:.2f}ms, "
                  f"p95: {result.p95_time*1000:.2f}ms)")

        # Performance assertions (these may need adjustment based on environment)
        assert set_result.ops_per_second > 100  # At least 100 SET ops/sec
        assert get_hit_result.ops_per_second > 500  # At least 500 GET ops/sec
        assert get_miss_result.ops_per_second > 100  # At least 100 GET miss ops/sec

    async def test_concurrent_operations_performance(self, cache_benchmark):
        """Benchmark concurrent cache operations."""
        benchmarks = PerformanceBenchmarks()
        concurrency_levels = [1, 5, 10, 20]
        results: Dict[int, BenchmarkResult] = {}

        for concurrency in concurrency_levels:
            async def mixed_op(index: int):
                # Mix of operations: 60% GET, 30% SET, 10% DELETE
                op_type = index % 10
                if op_type < 6:  # GET
                    await cache_benchmark.get(f"concurrent_key_{index % 50}")
                elif op_type < 9:  # SET
                    await cache_benchmark.set(f"concurrent_key_{index % 50}", f"value_{index}")
                else:  # DELETE
                    await cache_benchmark.delete(f"concurrent_key_{index % 50}")

            result = await benchmarks.benchmark_operation(
                mixed_op, f"MIXED_CONCURRENT_{concurrency}",
                2000, concurrency=concurrency
            )
            results[concurrency] = result

        # Print results
        print("\nConcurrent Operations Performance:")
        for concurrency, result in results.items():
            print(f"Concurrency {concurrency:2d}: {result.ops_per_second:.2f} ops/sec "
                  f"(avg: {result.avg_time*1000:.2f}ms, "
                  f"p95: {result.p95_time*1000:.2f}ms)")

        # Verify performance scales reasonably with concurrency
        # (within reason - too much concurrency can hurt performance)
        assert all(r.ops_per_second > 50 for r in results.values())

    async def test_large_data_performance(self, cache_benchmark):
        """Benchmark operations with large data objects."""
        benchmarks = PerformanceBenchmarks()
        data_sizes = [1, 10, 50, 100]  # KB
        results: List[BenchmarkResult] = []

        for size_kb in data_sizes:
            # Create test data of specified size
            data_str = "x" * (size_kb * 1024)
            test_data = {
                "payload": data_str,
                "metadata": {"size_kb": size_kb, "timestamp": time.time()}
            }

            async def large_data_op(index: int):
                await cache_benchmark.set(f"large_key_{index % 10}", test_data)
                await cache_benchmark.get(f"large_key_{index % 10}")

            result = await benchmarks.benchmark_operation(
                large_data_op, f"LARGE_DATA_{size_kb}KB",
                100, concurrency=1
            )
            results.append(result)

        # Print results
        print("\nLarge Data Performance:")
        for size_kb, result in zip(data_sizes, results):
            print(f"{size_kb:3d}KB: {result.ops_per_second:.2f} ops/sec "
                  f"(avg: {result.avg_time*1000:.2f}ms)")

        # Performance should degrade gracefully with size
        assert all(r.ops_per_second > 10 for r in results)  # At least 10 ops/sec even for large data

    async def test_service_batch_performance(self, service_benchmark):
        """Benchmark Redis service batch operations."""
        benchmarks = PerformanceBenchmarks()
        batch_sizes = [10, 50, 100, 500]
        results: List[BenchmarkResult] = []

        for batch_size in batch_sizes:
            # Prepare test data
            test_data = {
                f"batch_key_{i}": {"index": i, "value": f"batch_value_{i}"}
                for i in range(batch_size)
            }

            async def batch_op(index: int):
                # Batch set
                await service_benchmark.batch_set(test_data, ttl=300)
                # Batch get
                keys = list(test_data.keys())
                await service_benchmark.batch_get(keys)
                # Batch delete
                await service_benchmark.batch_delete(keys)

            result = await benchmarks.benchmark_operation(
                batch_op, f"BATCH_SIZE_{batch_size}",
                50, concurrency=1
            )
            results.append(result)

        # Print results
        print("\nBatch Operations Performance:")
        for batch_size, result in zip(batch_sizes, results):
            print(f"Size {batch_size:3d}: {result.ops_per_second:.2f} ops/sec "
                  f"(avg: {result.avg_time*1000:.2f}ms)")

        # Batch operations should be efficient
        assert all(r.ops_per_second > 5 for r in results)  # At least 5 batch ops/sec

    async def test_service_statistics_overhead(self, service_benchmark):
        """Measure overhead of statistics collection."""
        # Test with statistics enabled (default)
        start_time = time.time()
        for i in range(1000):
            await service_benchmark.set(f"stat_test_{i}", f"value_{i}")
            await service_benchmark.get(f"stat_test_{i}")
        time_with_stats = time.time() - start_time

        # Get statistics
        stats = await service_benchmark.get_statistics()
        metrics = await service_benchmark.get_performance_metrics()

        print(f"\nStatistics Overhead:")
        print(f"Time with stats: {time_with_stats:.3f}s for 2000 operations")
        print(f"Operations per second: {2000 / time_with_stats:.2f}")
        print(f"Hit rate: {stats.hit_rate:.2%}")
        if metrics:
            print(f"Avg operation time: {metrics.total_time / metrics.total_operations * 1000:.2f}ms")

        # Statistics overhead should be minimal
        assert time_with_stats < 5.0  # Should complete in under 5 seconds


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestCacheMemoryUsage:
    """Tests for cache memory usage patterns."""

    async def test_memory_usage_growth(self, cache_benchmark):
        """Test how memory usage grows with cached data."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Cache increasing amounts of data
        data_points = []
        for size in [10, 50, 100, 500, 1000]:
            # Create and cache data
            test_data = {
                "payload": "x" * 1024,  # 1KB payload
                "metadata": {"index": i, "size": size}
            }

            for i in range(size):
                await cache_benchmark.set(f"memory_test_{i}", test_data)

            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - initial_memory
            data_points.append((size, memory_increase))

        print("\nMemory Usage Growth:")
        for size, memory_mb in data_points:
            print(f"Entries: {size:4d}, Memory increase: {memory_mb:6.2f}MB")

        # Memory usage should be reasonable
        # (this is a rough check that may vary by system)
        _, max_memory = max(data_points, key=lambda x: x[1])
        assert max_memory < 500  # Should not exceed 500MB for test data

    async def test_cache_efficiency(self, service_benchmark):
        """Test cache hit/miss efficiency."""
        # Reset statistics
        await service_benchmark.reset_statistics()

        # Create a pattern with 70% hits, 30% misses
        hot_keys = [f"hot_key_{i}" for i in range(100)]
        cold_keys = [f"cold_key_{i}" for i in range(1000)]

        # Populate hot keys
        for key in hot_keys:
            await service_benchmark.set(key, f"hot_value_{key}")

        # Simulate access pattern
        import random
        for i in range(2000):
            if i < 1400:  # 70% hot keys
                key = random.choice(hot_keys)
            else:  # 30% cold keys
                key = random.choice(cold_keys)

            await service_benchmark.get(key)

        # Check statistics
        stats = await service_benchmark.get_statistics()
        hit_rate = stats.hit_rate

        print(f"\nCache Efficiency:")
        print(f"Hit rate: {hit_rate:.2%}")
        print(f"Hits: {stats.hits}, Misses: {stats.misses}")
        print(f"Total requests: {stats.total_requests}")

        # Hit rate should be close to expected 70%
        assert 0.6 <= hit_rate <= 0.8


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestCacheStress:
    """Stress tests for cache performance under load."""

    async def test_sustained_load(self, service_benchmark):
        """Test cache performance under sustained load."""
        duration = 10  # seconds
        target_ops_per_sec = 100

        print(f"\nSustained Load Test ({duration}s @ {target_ops_per_sec} ops/sec):")

        async def sustained_worker(worker_id: int):
            """Worker that maintains steady operations."""
            operations = 0
            start_time = time.time()

            while time.time() - start_time < duration:
                # Mix of operations
                key = f"sustain_{worker_id}_{operations % 50}"
                await service_benchmark.set(key, f"value_{operations}")
                await service_benchmark.get(key)

                if operations % 10 == 0:  # Delete occasionally
                    await service_benchmark.delete(f"sustain_{worker_id}_{operations % 20}")

                operations += 2  # Two operations per iteration

                # Rate limiting to maintain target
                elapsed = time.time() - start_time
                expected_ops = elapsed * target_ops_per_sec
                if operations > expected_ops + 10:  # Too far ahead
                    await asyncio.sleep(0.01)

            return operations

        # Run sustained load
        num_workers = 3
        tasks = [sustained_worker(i) for i in range(num_workers)]
        worker_ops = await asyncio.gather(*tasks)
        total_ops = sum(worker_ops)

        actual_ops_per_sec = total_ops / duration
        print(f"Actual: {actual_ops_per_sec:.1f} ops/sec")
        print(f"Total operations: {total_ops}")

        # Should maintain reasonable performance
        assert actual_ops_per_sec > target_ops_per_sec * 0.8  # Within 80% of target

    async def test_burst_load(self, service_benchmark):
        """Test cache performance under burst load."""
        burst_size = 1000
        num_bursts = 5

        print(f"\nBurst Load Test ({num_bursts} bursts of {burst_size} ops):")

        all_timings = []

        for burst in range(num_bursts):
            burst_start = time.time()

            async def burst_operation(i: int):
                key = f"burst_{burst}_{i}"
                await service_benchmark.set(key, f"burst_value_{i}")
                return await service_benchmark.get(key)

            # Execute burst
            tasks = [burst_operation(i) for i in range(burst_size)]
            await asyncio.gather(*tasks)

            burst_time = time.time() - burst_start
            burst_ops_per_sec = burst_size * 2 / burst_time  # SET + GET per operation
            all_timings.append(burst_ops_per_sec)

            print(f"Burst {burst + 1}: {burst_ops_per_sec:.1f} ops/sec")

            # Small rest between bursts
            if burst < num_bursts - 1:
                await asyncio.sleep(0.5)

        avg_burst_performance = statistics.mean(all_timings)
        print(f"Average burst performance: {avg_burst_performance:.1f} ops/sec")

        # Burst performance should be consistently high
        assert all(t > 50 for t in all_timings)  # At least 50 ops/sec per burst
        assert avg_burst_performance > 100  # Average should be good