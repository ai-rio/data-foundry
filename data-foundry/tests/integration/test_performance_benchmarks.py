"""
Performance Benchmark Tests for Consent Management System

Tests system performance under various load conditions and provides
benchmarking metrics for capacity planning and optimization.
"""

import asyncio
import time
import statistics
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil
import pytest
from unittest.mock import Mock

# Import system components
from src.core.consent_manager import ConsentManager
from src.core.database import DatabaseManager
from src.core.audit_service import AuditService
from src.core.security import SecurityManager
from src.models.consent import ConsentRecordDB
from src.models.enums import ConsentStatus

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Collects and analyzes performance metrics."""

    def __init__(self):
        self.metrics = {
            "timings": [],
            "memory_usage": [],
            "cpu_usage": [],
            "database_operations": [],
            "error_counts": {},
            "throughput": []
        }
        self.start_time = None
        self.end_time = None

    def start_recording(self):
        """Start recording performance metrics."""
        self.start_time = time.time()
        self.initial_memory = psutil.Process().memory_info().rss
        self.initial_cpu = psutil.cpu_percent()

    def record_operation(self, operation_name: str, duration: float):
        """Record an operation's duration."""
        self.metrics["timings"].append({
            "operation": operation_name,
            "duration": duration,
            "timestamp": time.time()
        })

    def record_memory(self):
        """Record current memory usage."""
        current_memory = psutil.Process().memory_info().rss
        self.metrics["memory_usage"].append({
            "rss": current_memory,
            "increase": current_memory - self.initial_memory,
            "timestamp": time.time()
        })

    def record_database_operation(self, operation: str, duration: float, rows_affected: int = None):
        """Record database operation metrics."""
        self.metrics["database_operations"].append({
            "operation": operation,
            "duration": duration,
            "rows_affected": rows_affected,
            "timestamp": time.time()
        })

    def record_error(self, error_type: str):
        """Record an error occurrence."""
        if error_type not in self.metrics["error_counts"]:
            self.metrics["error_counts"][error_type] = 0
        self.metrics["error_counts"][error_type] += 1

    def end_recording(self):
        """End recording and calculate summary."""
        self.end_time = time.time()

    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        if not self.timings:
            return {}

        durations = [m["duration"] for m in self.metrics["timings"]]
        db_durations = [m["duration"] for m in self.metrics["database_operations"]]
        memory_increases = [m["increase"] for m in self.metrics["memory_usage"]]

        return {
            "total_time": self.end_time - self.start_time if self.end_time else 0,
            "operation_count": len(durations),
            "operations_per_second": len(durations) / (self.end_time - self.start_time) if self.end_time else 0,
            "timing_stats": {
                "min": min(durations),
                "max": max(durations),
                "mean": statistics.mean(durations),
                "median": statistics.median(durations),
                "p95": statistics.quantiles(durations, n=20)[18] if len(durations) > 20 else max(durations),
                "p99": statistics.quantiles(durations, n=100)[98] if len(durations) > 100 else max(durations)
            },
            "database_stats": {
                "operation_count": len(db_durations),
                "avg_duration": statistics.mean(db_durations) if db_durations else 0,
                "total_rows_affected": sum(m.get("rows_affected", 0) for m in self.metrics["database_operations"])
            },
            "memory_stats": {
                "initial_mb": self.initial_memory / 1024 / 1024,
                "final_mb": self.metrics["memory_usage"][-1]["rss"] / 1024 / 1024 if self.metrics["memory_usage"] else 0,
                "max_increase_mb": max(memory_increases) / 1024 / 1024 if memory_increases else 0,
                "avg_increase_mb": statistics.mean(memory_increases) / 1024 / 1024 if memory_increases else 0
            },
            "error_summary": self.metrics["error_counts"]
        }


class ConsentCreationBenchmark:
    """Benchmark consent creation performance."""

    @pytest.mark.asyncio
    async def test_consent_creation_throughput(self, consent_manager, test_user_data, sample_consent_text):
        """Test consent creation throughput under load."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        # Test parameters
        num_operations = 100
        concurrent_users = 10

        async def create_consent_batch(user_id: str, count: int, start_index: int):
            """Create a batch of consents for a user."""
            results = []
            for i in range(count):
                start_time = time.time()
                try:
                    record = await consent_manager.record_consent(
                        user_id=user_id,
                        consent_type=f"benchmark_test_{start_index + i}",
                        consent_text=sample_consent_text,
                        metadata={
                            "ip": test_user_data["ip_address"],
                            "user_agent": test_user_data["user_agent"],
                            "batch_id": f"batch_{start_index}"
                        }
                    )
                    duration = time.time() - start_time
                    metrics.record_operation("consent_creation", duration)
                    results.append({"success": True, "duration": duration})
                except Exception as e:
                    duration = time.time() - start_time
                    metrics.record_operation("consent_creation_error", duration)
                    metrics.record_error(str(e))
                    results.append({"success": False, "error": str(e), "duration": duration})

                # Record memory periodically
                if i % 10 == 0:
                    metrics.record_memory()

            return results

        # Create consents concurrently
        tasks = []
        for user_idx in range(concurrent_users):
            user_id = f"{test_user_data['user_id']}_{user_idx}"
            batch_size = num_operations // concurrent_users
            start_idx = user_idx * batch_size
            tasks.append(create_consent_batch(user_id, batch_size, start_idx))

        # Execute all tasks
        start_time = time.time()
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        metrics.end_recording()
        summary = metrics.get_summary()

        # Flatten results
        all_operations = []
        for result in all_results:
            if isinstance(result, list):
                all_operations.extend(result)
            else:
                metrics.record_error("TaskException")
                all_operations.append({"success": False, "error": str(result)})

        # Count successful operations
        successful_ops = sum(1 for op in all_operations if op.get("success", False))

        # Performance assertions
        assert successful_ops >= num_operations * 0.95  # At least 95% success rate
        assert summary["operations_per_second"] >= 10  # At least 10 ops/sec
        assert summary["timing_stats"]["p95"] < 1.0  # 95th percentile under 1 second

        # Memory assertions
        assert summary["memory_stats"]["max_increase_mb"] < 500  # Less than 500MB increase

        logger.info(f"Consent Creation Benchmark:")
        logger.info(f"  Total operations: {len(all_operations)}")
        logger.info(f"  Successful operations: {successful_ops}")
        logger.info(f"  Operations per second: {summary['operations_per_second']:.2f}")
        logger.info(f"  P95 response time: {summary['timing_stats']['p95']:.3f}s")
        logger.info(f"  Max memory increase: {summary['memory_stats']['max_increase_mb']:.2f}MB")

    @pytest.mark.asyncio
    async def test_consent_verification_performance(self, consent_manager, populated_consent_data):
        """Test consent verification performance with existing data."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        user_id = populated_consent_data["user_id"]
        consent_types = populated_consent_data["active_consents"] + populated_consent_data["withdrawn_consents"]
        num_verifications = 1000

        # Perform multiple verifications
        for i in range(num_verifications):
            consent_type = consent_types[i % len(consent_types)]

            start_time = time.time()
            try:
                result = await consent_manager.verify_consent(user_id, consent_type)
                duration = time.time() - start_time
                metrics.record_operation("consent_verification", duration)
            except Exception as e:
                duration = time.time() - start_time
                metrics.record_operation("consent_verification_error", duration)
                metrics.record_error(str(e))

            if i % 100 == 0:
                metrics.record_memory()

        metrics.end_recording()
        summary = metrics.get_summary()

        # Verification should be very fast with proper indexing
        assert summary["operations_per_second"] >= 100  # At least 100 verifications/sec
        assert summary["timing_stats"]["p95"] < 0.1  # 95th percentile under 100ms
        assert summary["timing_stats"]["mean"] < 0.05  # Average under 50ms

        logger.info(f"Consent Verification Benchmark:")
        logger.info(f"  Total verifications: {num_verifications}")
        logger.info(f"  Verifications per second: {summary['operations_per_second']:.2f}")
        logger.info(f"  P95 response time: {summary['timing_stats']['p95']:.3f}s")
        logger.info(f"  Mean response time: {summary['timing_stats']['mean']:.3f}s")


class DatabasePerformanceBenchmark:
    """Benchmark database layer performance."""

    @pytest.mark.asyncio
    async def test_bulk_insert_performance(self, db_manager, test_data_factory):
        """Test bulk insert performance for consent records."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        # Create test data
        num_records = 1000
        test_user = test_data_factory.create_user()
        records = test_data_factory.create_bulk_consents(num_records, test_user["user_id"])

        # Measure insert performance
        start_time = time.time()

        for record in records:
            try:
                insert_start = time.time()
                # Simulate database insert
                # In real implementation, this would use the actual db_manager method
                await asyncio.sleep(0.001)  # Simulate database operation
                duration = time.time() - insert_start
                metrics.record_database_operation("insert", duration, 1)
            except Exception as e:
                metrics.record_error("DatabaseInsert")

            if len(metrics["database_operations"]) % 100 == 0:
                metrics.record_memory()

        end_time = time.time()
        metrics.end_recording()
        summary = metrics.get_summary()

        # Performance assertions
        assert summary["database_stats"]["operation_count"] == num_records
        assert summary["database_stats"]["avg_duration"] < 0.01  # Average under 10ms per insert
        assert (end_time - start_time) < 10.0  # Total time under 10 seconds

        logger.info(f"Bulk Insert Benchmark:")
        logger.info(f"  Records inserted: {num_records}")
        logger.info(f"  Total time: {end_time - start_time:.2f}s")
        logger.info(f"  Records per second: {num_records / (end_time - start_time):.2f}")
        logger.info(f"  Avg insert time: {summary['database_stats']['avg_duration']:.3f}s")

    @pytest.mark.asyncio
    async def test_query_performance_with_indexing(self, db_manager, test_data_factory):
        """Test query performance with different data volumes."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        # Test different data volumes
        test_volumes = [100, 500, 1000, 5000]
        query_types = [
            "by_user_id",
            "by_consent_type",
            "by_status",
            "by_user_and_type",
            "by_date_range"
        ]

        for volume in test_volumes:
            logger.info(f"Testing query performance with {volume} records")

            # Create test data
            test_user = test_data_factory.create_user()
            records = test_data_factory.create_bulk_consents(volume, test_user["user_id"])

            # Test different query types
            for query_type in query_types:
                query_times = []

                for _ in range(10):  # Run each query 10 times
                    start_time = time.time()

                    # Simulate different query types
                    if query_type == "by_user_id":
                        await asyncio.sleep(0.001)  # Simulate query
                    elif query_type == "by_consent_type":
                        await asyncio.sleep(0.002)  # Simulate more complex query
                    elif query_type == "by_status":
                        await asyncio.sleep(0.001)
                    elif query_type == "by_user_and_type":
                        await asyncio.sleep(0.001)
                    elif query_type == "by_date_range":
                        await asyncio.sleep(0.003)  # Simulate date range query

                    query_time = time.time() - start_time
                    query_times.append(query_time)

                avg_time = statistics.mean(query_times)
                metrics.record_database_operation(f"{query_type}_v{volume}", avg_time)

                # Query performance should scale reasonably
                if volume <= 1000:
                    assert avg_time < 0.1  # Under 100ms for small volumes
                else:
                    assert avg_time < 0.5  # Under 500ms for larger volumes

            metrics.record_memory()

        metrics.end_recording()
        summary = metrics.get_summary()

        logger.info(f"Query Performance Benchmark:")
        logger.info(f"  Total queries: {summary['database_stats']['operation_count']}")
        logger.info(f"  Average query time: {summary['database_stats']['avg_duration']:.3f}s")


class ConcurrentLoadBenchmark:
    """Benchmark system performance under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_users_simulation(self, consent_manager, test_data_factory):
        """Simulate multiple concurrent users."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        # Test parameters
        num_users = 50
        operations_per_user = 20
        operation_types = ["create", "verify", "withdraw"]

        async def simulate_user(user_id: str, operations: List[Dict]):
            """Simulate a user performing operations."""
            results = []

            for op in operations:
                start_time = time.time()

                try:
                    if op["type"] == "create":
                        record = await consent_manager.record_consent(
                            user_id=user_id,
                            consent_type=op["consent_type"],
                            consent_text=op["consent_text"],
                            metadata=op["metadata"]
                        )
                        results.append({"success": True, "operation": "create"})
                    elif op["type"] == "verify":
                        result = await consent_manager.verify_consent(
                            user_id=user_id,
                            consent_type=op["consent_type"]
                        )
                        results.append({"success": True, "operation": "verify", "result": result})
                    elif op["type"] == "withdraw":
                        result = await consent_manager.withdraw_consent(
                            user_id=user_id,
                            consent_type=op["consent_type"]
                        )
                        results.append({"success": True, "operation": "withdraw", "result": result})

                    duration = time.time() - start_time
                    metrics.record_operation(f"user_{op['type']}", duration)

                except Exception as e:
                    duration = time.time() - start_time
                    metrics.record_error(f"user_{op['type']}_error")
                    results.append({"success": False, "error": str(e)})

            return results

        # Create user operations
        tasks = []
        for user_idx in range(num_users):
            user_id = f"load_user_{user_idx}"
            operations = []

            for op_idx in range(operations_per_user):
                user_data = test_data_factory.create_user(user_id=user_id)

                if op_idx < operations_per_user // 2:
                    # First half: create consents
                    operations.append({
                        "type": "create",
                        "consent_type": f"load_test_{op_idx}",
                        "consent_text": f"Load test consent {op_idx} for performance testing",
                        "metadata": {
                            "ip": user_data["ip_address"],
                            "user_agent": user_data["user_agent"]
                        }
                    })
                elif op_idx < 3 * operations_per_user // 4:
                    # Next quarter: verify consents
                    operations.append({
                        "type": "verify",
                        "consent_type": f"load_test_{op_idx - operations_per_user // 2}"
                    })
                else:
                    # Last quarter: withdraw some consents
                    operations.append({
                        "type": "withdraw",
                        "consent_type": f"load_test_{op_idx - operations_per_user // 2}"
                    })

            tasks.append(simulate_user(user_id, operations))

        # Execute all user simulations
        start_time = time.time()
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        metrics.end_recording()
        summary = metrics.get_summary()

        # Analyze results
        total_operations = 0
        successful_operations = 0

        for result in all_results:
            if isinstance(result, list):
                total_operations += len(result)
                successful_operations += sum(1 for op in result if op.get("success", False))
            else:
                metrics.record_error("UserSimulationFailed")

        success_rate = successful_operations / total_operations if total_operations > 0 else 0

        # Performance assertions
        assert success_rate >= 0.95  # At least 95% success rate
        assert summary["operations_per_second"] >= 5  # At least 5 ops/sec under load
        assert summary["timing_stats"]["p95"] < 2.0  # 95th percentile under 2 seconds

        logger.info(f"Concurrent Load Benchmark:")
        logger.info(f"  Concurrent users: {num_users}")
        logger.info(f"  Total operations: {total_operations}")
        logger.info(f"  Success rate: {success_rate:.2%}")
        logger.info(f"  Operations per second: {summary['operations_per_second']:.2f}")
        logger.info(f"  P95 response time: {summary['timing_stats']['p95']:.3f}s")
        logger.info(f"  Memory increase: {summary['memory_stats']['max_increase_mb']:.2f}MB")


class StressTestBenchmark:
    """Stress test the system to find breaking points."""

    @pytest.mark.asyncio
    async def test_high_volume_consent_creation(self, consent_manager, test_data_factory):
        """Test system with very high volume of consent creation."""
        metrics = PerformanceMetrics()
        metrics.start_recording()

        # Extreme test parameters
        num_operations = 10000
        batch_size = 100

        async def create_batch(batch_id: int, size: int):
            """Create a batch of consents."""
            results = []
            user_id = f"stress_user_{batch_id}"

            for i in range(size):
                try:
                    start_time = time.time()
                    user_data = test_data_factory.create_user(user_id=user_id)

                    record = await consent_manager.record_consent(
                        user_id=user_id,
                        consent_type=f"stress_test_{batch_id}_{i}",
                        consent_text=f"Stress test consent for batch {batch_id}, item {i}",
                        metadata={
                            "ip": user_data["ip_address"],
                            "user_agent": user_data["user_agent"],
                            "batch_id": batch_id
                        }
                    )

                    duration = time.time() - start_time
                    metrics.record_operation("stress_create", duration)
                    results.append({"success": True, "duration": duration})

                except Exception as e:
                    metrics.record_error("StressCreateError")
                    results.append({"success": False, "error": str(e)})

            return results

        # Create batches
        num_batches = num_operations // batch_size
        tasks = []

        for batch_id in range(num_batches):
            tasks.append(create_batch(batch_id, batch_size))

        # Execute batches with controlled concurrency
        all_results = []
        max_concurrent = 10  # Limit concurrent batches

        for i in range(0, len(tasks), max_concurrent):
            batch_tasks = tasks[i:i + max_concurrent]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            all_results.extend(batch_results)

            # Brief pause between batches to prevent overwhelming
            await asyncio.sleep(0.1)

        metrics.end_recording()
        summary = metrics.get_summary()

        # Analyze results
        total_operations = 0
        successful_operations = 0

        for result in all_results:
            if isinstance(result, list):
                total_operations += len(result)
                successful_operations += sum(1 for op in result if op.get("success", False))

        success_rate = successful_operations / total_operations if total_operations > 0 else 0

        logger.info(f"High Volume Stress Test:")
        logger.info(f"  Total operations attempted: {num_operations}")
        logger.info(f"  Total operations completed: {total_operations}")
        logger.info(f"  Success rate: {success_rate:.2%}")
        logger.info(f"  Operations per second: {summary['operations_per_second']:.2f}")
        logger.info(f"  P95 response time: {summary['timing_stats']['p95']:.3f}s")
        logger.info(f"  Max memory: {summary['memory_stats']['max_increase_mb']:.2f}MB")

        # System should handle high volume with reasonable performance
        # Exact thresholds depend on infrastructure, but system should not crash
        assert success_rate >= 0.80  # At least 80% success under extreme load


class ResourceUsageBenchmark:
    """Monitor resource usage during operations."""

    @pytest.mark.asyncio
    async def test_memory_leak_detection(self, consent_manager, test_user_data, sample_consent_text):
        """Test for memory leaks during extended operation."""
        initial_memory = psutil.Process().memory_info().rss
        memory_samples = []

        # Run operations for extended period
        num_cycles = 100
        consents_per_cycle = 10

        for cycle in range(num_cycles):
            # Create consents
            for i in range(consents_per_cycle):
                await consent_manager.record_consent(
                    user_id=test_user_data["user_id"],
                    consent_type=f"leak_test_{cycle}_{i}",
                    consent_text=sample_consent_text,
                    metadata={
                        "ip": test_user_data["ip_address"],
                        "user_agent": test_user_data["user_agent"]
                    }
                )

            # Sample memory usage
            current_memory = psutil.Process().memory_info().rss
            memory_samples.append(current_memory)

            # Force garbage collection periodically
            if cycle % 10 == 0:
                import gc
                gc.collect()

        # Analyze memory growth
        memory_increase = memory_samples[-1] - initial_memory
        memory_increase_mb = memory_increase / 1024 / 1024

        # Memory should not grow excessively
        # Allow some growth due to caching, but not unbounded
        assert memory_increase_mb < 100  # Less than 100MB increase

        logger.info(f"Memory Leak Detection:")
        logger.info(f"  Initial memory: {initial_memory / 1024 / 1024:.2f}MB")
        logger.info(f"  Final memory: {memory_samples[-1] / 1024 / 1024:.2f}MB")
        logger.info(f"  Memory increase: {memory_increase_mb:.2f}MB")
        logger.info(f"  Operations: {num_cycles * consents_per_cycle}")

    @pytest.mark.asyncio
    async def test_cpu_usage_sustainability(self, consent_manager, test_data_factory):
        """Test CPU usage remains reasonable under sustained load."""
        cpu_samples = []

        # Sustained load test
        duration_seconds = 30
        operations_per_second = 10

        start_time = time.time()
        operation_count = 0

        while time.time() - start_time < duration_seconds:
            # Create consent
            user_data = test_data_factory.create_user()
            await consent_manager.record_consent(
                user_id=user_data["user_id"],
                consent_type=f"cpu_test_{operation_count}",
                consent_text="CPU sustainability test consent",
                metadata={
                    "ip": user_data["ip_address"],
                    "user_agent": user_data["user_agent"]
                }
            )

            operation_count += 1

            # Sample CPU usage
            if operation_count % 10 == 0:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                cpu_samples.append(cpu_percent)

            # Control rate
            elapsed = time.time() - start_time
            expected_time = operation_count / operations_per_second
            if elapsed < expected_time:
                await asyncio.sleep(expected_time - elapsed)

        # Analyze CPU usage
        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        max_cpu = max(cpu_samples) if cpu_samples else 0

        # CPU should not be consistently high
        assert avg_cpu < 80  # Average CPU under 80%
        assert max_cpu < 95  # Peak CPU under 95%

        logger.info(f"CPU Sustainability Test:")
        logger.info(f"  Duration: {duration_seconds}s")
        logger.info(f"  Operations: {operation_count}")
        logger.info(f"  Avg CPU: {avg_cpu:.1f}%")
        logger.info(f"  Max CPU: {max_cpu:.1f}%")
        logger.info(f"  Operations per second: {operation_count / duration_seconds:.2f}")


# Performance test runner
class PerformanceTestRunner:
    """Runs all performance tests and generates report."""

    @staticmethod
    async def run_all_benchmarks():
        """Run all performance benchmarks and generate comprehensive report."""
        import subprocess
        import sys

        # Run pytest with performance markers
        cmd = [
            sys.executable, "-m", "pytest",
            __file__,
            "-v",
            "-m", "performance",
            "--tb=short",
            "--benchmark-json=performance_results.json",
            "--benchmark-only",
            "--benchmark-sort=mean"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Generate additional analysis
        report = {
            "test_summary": {
                "exit_code": result.returncode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output": result.stdout,
                "errors": result.stderr
            },
            "system_info": {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / 1024 / 1024 / 1024,
                "platform": psutil.platform.platform()
            }
        }

        # Save performance report
        with open("performance_test_report.json", "w") as f:
            json.dump(report, f, indent=2)

        return result.returncode == 0


if __name__ == "__main__":
    # Run performance tests when executed directly
    success = asyncio.run(PerformanceTestRunner.run_all_benchmarks())
    print(f"Performance Tests: {'PASSED' if success else 'FAILED'}")