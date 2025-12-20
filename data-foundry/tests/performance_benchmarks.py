"""
Performance Benchmarks for Cost Service

Validates performance claims:
- Sub-millisecond calculations
- 10,000+ calculations per second
- Memory efficiency
- Concurrency performance
"""

import asyncio
import time
import psutil
import statistics
import gc
from typing import List, Dict, Any
from dataclasses import dataclass
from decimal import Decimal
import pytest
import matplotlib.pyplot as plt
import numpy as np

from src.services.cost_service_production import CostService


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""
    name: str
    operations: int
    total_time_ns: int
    avg_time_ns: float
    min_time_ns: float
    max_time_ns: float
    std_dev_ns: float
    ops_per_second: float
    memory_mb: float


class PerformanceBenchmarks:
    """Comprehensive performance benchmarks."""

    def __init__(self):
        self.service = None
        self.results: List[BenchmarkResult] = []

    async def setup(self):
        """Setup cost service for benchmarking."""
        # Mock dependencies for pure performance testing
        import sys
        from unittest.mock import AsyncMock, patch

        # Mock database
        mock_db = AsyncMock()
        mock_db.get_tenant.return_value = {
            "tenant_id": "benchmark",
            "is_active": True,
            "billing_enabled": True,
            "approved_models": ["gpt-4o", "gpt-3.5-turbo"],
            "permissions": {"billing": True}
        }
        mock_db.get_monthly_cost.return_value = Decimal("0")
        mock_db.get_tenant_usage_stats.return_value = {
            "monthly_tokens": 0,
            "monthly_cost": Decimal("0")
        }

        # Mock audit logger
        mock_audit = AsyncMock()

        with patch('src.services.cost_service_production.get_db_manager', return_value=mock_db), \
             patch('src.services.cost_service_production.AuditLogger', return_value=mock_audit):
            self.service = CostService(enable_cache=True)

    async def benchmark_cost_calculation(
        self,
        iterations: int = 10000,
        concurrent: bool = False
    ) -> BenchmarkResult:
        """Benchmark cost calculation performance."""
        if not self.service:
            await self.setup()

        print(f"\nBenchmarking cost calculation ({iterations} iterations, concurrent={concurrent})")

        # Warm up
        for _ in range(100):
            await self.service.calculate_cost(
                model="gpt-4o",
                prompt_tokens=1000,
                completion_tokens=500,
                tenant_id="benchmark"
            )

        # Measure memory before
        gc.collect()
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Collect timing data
        times_ns = []

        if concurrent:
            # Run concurrently
            start_time = time.perf_counter_ns()

            tasks = []
            for _ in range(iterations):
                task = self.service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1000,
                    completion_tokens=500,
                    tenant_id="benchmark"
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

            total_time_ns = time.perf_counter_ns() - start_time
            avg_time_ns = total_time_ns / iterations

        else:
            # Run sequentially
            for _ in range(iterations):
                start = time.perf_counter_ns()
                await self.service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1000,
                    completion_tokens=500,
                    tenant_id="benchmark"
                )
                times_ns.append(time.perf_counter_ns() - start)

            total_time_ns = sum(times_ns)
            avg_time_ns = statistics.mean(times_ns)

        # Measure memory after
        memory_after = process.memory_info().rss / 1024 / 1024  # MB

        # Calculate statistics
        if times_ns:
            min_time_ns = min(times_ns)
            max_time_ns = max(times_ns)
            std_dev_ns = statistics.stdev(times_ns) if len(times_ns) > 1 else 0
        else:
            min_time_ns = max_time_ns = std_dev_ns = 0

        ops_per_second = iterations / (total_time_ns / 1_000_000_000)

        result = BenchmarkResult(
            name=f"Cost Calculation ({'Concurrent' if concurrent else 'Sequential'})",
            operations=iterations,
            total_time_ns=total_time_ns,
            avg_time_ns=avg_time_ns,
            min_time_ns=min_time_ns,
            max_time_ns=max_time_ns,
            std_dev_ns=std_dev_ns,
            ops_per_second=ops_per_second,
            memory_mb=memory_after - memory_before
        )

        self.results.append(result)

        # Print results
        print(f"  Average time: {avg_time_ns / 1_000_000:.4f} ms")
        print(f"  Operations/sec: {ops_per_second:.0f}")
        print(f"  Memory used: {result.memory_mb:.2f} MB")

        # Check performance requirements
        if avg_time_ns / 1_000_000 >= 1.0:
            print(f"  ❌ FAIL: Average time >= 1ms ({avg_time_ns / 1_000_000:.4f}ms)")
        else:
            print(f"  ✅ PASS: Average time < 1ms")

        if ops_per_second < 10000:
            print(f"  ❌ FAIL: Operations/sec < 10,000 ({ops_per_second:.0f})")
        else:
            print(f"  ✅ PASS: Operations/sec >= 10,000")

        return result

    async def benchmark_currency_conversion(self, iterations: int = 100000) -> BenchmarkResult:
        """Benchmark currency conversion performance."""
        if not self.service:
            await self.setup()

        print(f"\nBenchmarking currency conversion ({iterations} iterations)")

        times_ns = []

        for _ in range(iterations):
            start = time.perf_counter_ns()
            await self.service._convert_currency(
                Decimal("100.00"),
                "USD",
                "EUR"
            )
            times_ns.append(time.perf_counter_ns() - start)

        total_time_ns = sum(times_ns)
        avg_time_ns = statistics.mean(times_ns)

        result = BenchmarkResult(
            name="Currency Conversion",
            operations=iterations,
            total_time_ns=total_time_ns,
            avg_time_ns=avg_time_ns,
            min_time_ns=min(times_ns),
            max_time_ns=max(times_ns),
            std_dev_ns=statistics.stdev(times_ns),
            ops_per_second=iterations / (total_time_ns / 1_000_000_000),
            memory_mb=0  # Minimal memory impact
        )

        self.results.append(result)

        print(f"  Average time: {avg_time_ns / 1_000_000:.4f} ms")
        print(f"  Operations/sec: {result.ops_per_second:.0f}")

        return result

    async def benchmark_tenant_validation(self, iterations: int = 50000) -> BenchmarkResult:
        """Benchmark tenant validation performance."""
        if not self.service:
            await self.setup()

        print(f"\nBenchmarking tenant validation ({iterations} iterations)")

        times_ns = []

        for i in range(iterations):
            start = time.perf_counter_ns()
            await self.service._validate_tenant_access(f"tenant_{i % 10}")
            times_ns.append(time.perf_counter_ns() - start)

        total_time_ns = sum(times_ns)
        avg_time_ns = statistics.mean(times_ns)

        result = BenchmarkResult(
            name="Tenant Validation",
            operations=iterations,
            total_time_ns=total_time_ns,
            avg_time_ns=avg_time_ns,
            min_time_ns=min(times_ns),
            max_time_ns=max(times_ns),
            std_dev_ns=statistics.stdev(times_ns),
            ops_per_second=iterations / (total_time_ns / 1_000_000_000),
            memory_mb=0
        )

        self.results.append(result)

        print(f"  Average time: {avg_time_ns / 1_000_000:.4f} ms")
        print(f"  Operations/sec: {result.ops_per_second:.0f}")

        return result

    async def benchmark_memory_usage(self, duration_seconds: int = 60) -> Dict[str, Any]:
        """Benchmark memory usage over time."""
        if not self.service:
            await self.setup()

        print(f"\nBenchmarking memory usage ({duration_seconds} seconds)")

        process = psutil.Process()
        memory_samples = []
        calculation_count = 0

        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            # Perform calculations
            for _ in range(100):
                await self.service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1000,
                    completion_tokens=500,
                    tenant_id="benchmark"
                )
                calculation_count += 1

            # Sample memory
            memory_mb = process.memory_info().rss / 1024 / 1024
            memory_samples.append(memory_mb)

            # Brief pause
            await asyncio.sleep(0.1)

        # Calculate statistics
        avg_memory = statistics.mean(memory_samples)
        min_memory = min(memory_samples)
        max_memory = max(memory_samples)

        # Calculate memory per calculation
        memory_per_calc = (max_memory - min_memory) / calculation_count * 1024 * 1024  # bytes

        result = {
            "duration_seconds": duration_seconds,
            "total_calculations": calculation_count,
            "avg_memory_mb": avg_memory,
            "min_memory_mb": min_memory,
            "max_memory_mb": max_memory,
            "memory_growth_mb": max_memory - min_memory,
            "memory_per_calc_bytes": memory_per_calc,
            "calculations_per_second": calculation_count / duration_seconds
        }

        print(f"  Total calculations: {calculation_count}")
        print(f"  Memory growth: {result['memory_growth_mb']:.2f} MB")
        print(f"  Memory per calc: {memory_per_calc:.0f} bytes")

        return result

    def generate_report(self, save_path: str = "performance_report.html"):
        """Generate performance report with visualizations."""
        if not self.results:
            print("No benchmark results to report")
            return

        # Create figure
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Cost Service Performance Benchmarks', fontsize=16)

        # Plot 1: Average time per operation
        ax1 = axes[0, 0]
        names = [r.name for r in self.results]
        avg_times_ms = [r.avg_time_ns / 1_000_000 for r in self.results]
        bars = ax1.bar(names, avg_times_ms)
        ax1.set_ylabel('Average Time (ms)')
        ax1.set_title('Average Time per Operation')
        ax1.tick_params(axis='x', rotation=45)

        # Add threshold line
        ax1.axhline(y=1.0, color='r', linestyle='--', label='1ms Threshold')
        ax1.legend()

        # Color bars based on performance
        for bar, time_ms in zip(bars, avg_times_ms):
            bar.set_color('green' if time_ms < 1.0 else 'red')

        # Plot 2: Operations per second
        ax2 = axes[0, 1]
        ops_per_sec = [r.ops_per_second for r in self.results]
        bars = ax2.bar(names, ops_per_sec)
        ax2.set_ylabel('Operations per Second')
        ax2.set_title('Throughput')
        ax2.tick_params(axis='x', rotation=45)

        # Add threshold line
        ax2.axhline(y=10000, color='r', linestyle='--', label='10K ops/sec Threshold')
        ax2.legend()

        # Color bars based on performance
        for bar, ops in zip(bars, ops_per_sec):
            bar.set_color('green' if ops >= 10000 else 'red')

        # Plot 3: Time distribution
        ax3 = axes[1, 0]
        for result in self.results:
            if result.std_dev_ns > 0:
                # Create normal distribution
                x = np.linspace(
                    result.avg_time_ns - 3 * result.std_dev_ns,
                    result.avg_time_ns + 3 * result.std_dev_ns,
                    100
                )
                y = np.exp(-0.5 * ((x - result.avg_time_ns) / result.std_dev_ns) ** 2)
                y = y / y.max() * 0.8  # Normalize
                ax3.plot(x / 1_000_000, y, label=result.name)

        ax3.set_xlabel('Time (ms)')
        ax3.set_ylabel('Probability Density')
        ax3.set_title('Response Time Distribution')
        ax3.legend()
        ax3.grid(True, alpha=0.3)

        # Plot 4: Summary table
        ax4 = axes[1, 1]
        ax4.axis('off')

        # Create table data
        table_data = []
        for r in self.results:
            table_data.append([
                r.name,
                f"{r.avg_time_ns / 1_000_000:.4f}",
                f"{r.ops_per_second:.0f}",
                f"{r.memory_mb:.2f}"
            ])

        table = ax4.table(
            cellText=table_data,
            colLabels=['Operation', 'Avg Time (ms)', 'Ops/sec', 'Memory (MB)'],
            cellLoc='center',
            loc='center'
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)

        # Color table cells based on performance
        for i, r in enumerate(self.results):
            time_cell = table[(i + 1, 1)]
            ops_cell = table[(i + 1, 2)]

            if r.avg_time_ns / 1_000_000 >= 1.0:
                time_cell.set_facecolor('#ffcccc')
            else:
                time_cell.set_facecolor('#ccffcc')

            if r.ops_per_second < 10000:
                ops_cell.set_facecolor('#ffcccc')
            else:
                ops_cell.set_facecolor('#ccffcc')

        plt.tight_layout()
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"\nPerformance report saved to: {save_path}")

        # Generate summary
        print("\n" + "="*60)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("="*60)

        all_pass = True
        for result in self.results:
            status = "✅ PASS" if result.avg_time_ns / 1_000_000 < 1.0 and result.ops_per_second >= 10000 else "❌ FAIL"
            print(f"\n{result.name}: {status}")
            print(f"  Average: {result.avg_time_ns / 1_000_000:.4f} ms")
            print(f"  Throughput: {result.ops_per_second:.0f} ops/sec")

            if result.avg_time_ns / 1_000_000 >= 1.0 or result.ops_per_second < 10000:
                all_pass = False

        print("\n" + "="*60)
        print(f"OVERALL: {'✅ ALL REQUIREMENTS MET' if all_pass else '❌ SOME REQUIREMENTS FAILED'}")
        print("="*60)


async def run_all_benchmarks():
    """Run all performance benchmarks."""
    print("Starting Performance Benchmarks for Cost Service")
    print("="*60)

    benchmarks = PerformanceBenchmarks()

    # Run all benchmarks
    await benchmarks.benchmark_cost_calculation(iterations=10000, concurrent=False)
    await benchmarks.benchmark_cost_calculation(iterations=10000, concurrent=True)
    await benchmarks.benchmark_currency_conversion(iterations=100000)
    await benchmarks.benchmark_tenant_validation(iterations=50000)
    await benchmarks.benchmark_memory_usage(duration_seconds=30)

    # Generate report
    benchmarks.generate_report()


if __name__ == "__main__":
    # Run benchmarks
    asyncio.run(run_all_benchmarks())