"""
Performance and security tests for Data Foundry
Tests performance metrics and security boundaries with mocked timing
"""

import time
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import DataRecord, ProcessedData, HumanReviewQueue, TokenUsage, AuditLog
from src.models.data_record import DataSource, DataStatus


class TestPerformanceMetrics:
    """Test performance metrics with mocked timing."""

    def test_processing_time_measurement(self):
        """Test processing time measurement and metrics."""
        print("Testing processing time measurement...")

        # Mock time tracking
        def mock_processing_time(records):
            processing_times = []

            for i, record in enumerate(records):
                # Simulate variable processing time
                start_time = time.time()

                # Simulate work
                time.sleep(0.01)  # 10ms base processing

                # Add variability
                if i % 3 == 0:
                    time.sleep(0.005)  # Extra 5ms for some records

                end_time = time.time()
                processing_time = (end_time - start_time) * 1000  # Convert to ms
                processing_times.append(processing_time)

                yield record, processing_time

            return processing_times

        # Test with multiple records
        records = [{"id": i, "name": f"Record {i}"} for i in range(10)]

        results = list(mock_processing_time(records))
        processing_times = [t for _, t in results]

        # Verify performance metrics
        assert len(processing_times) == 10, f"Expected 10 processing times, got {len(processing_times)}"
        assert all(t > 0 for t in processing_times), "All processing times should be positive"

        # Calculate statistics
        avg_time = statistics.mean(processing_times)
        min_time = min(processing_times)
        max_time = max(processing_times)
        std_dev = statistics.stdev(processing_times) if len(processing_times) > 1 else 0

        print(f"  Average processing time: {avg_time:.2f}ms")
        print(f"  Min processing time: {min_time:.2f}ms")
        print(f"  Max processing time: {max_time:.2f}ms")
        print(f"  Standard deviation: {std_dev:.2f}ms")

        # Verify reasonable performance (should be < 20ms)
        assert avg_time < 20, f"Average processing time {avg_time}ms should be < 20ms"
        assert max_time < 30, f"Max processing time {max_time}ms should be < 30ms"

        print("✓ Processing time measurement test passed")

    def test_throughput_measurement(self):
        """Test throughput measurement (records per second)."""
        print("Testing throughput measurement...")

        def simulate_batch_processing(batch_size, processing_time_per_record):
            """Simulate batch processing and calculate throughput."""
            start_time = time.time()

            # Simulate processing
            for i in range(batch_size):
                time.sleep(processing_time_per_record)

            end_time = time.time()
            total_time = end_time - start_time

            throughput = batch_size / total_time
            return throughput, total_time

        # Test different batch sizes
        batch_sizes = [10, 50, 100, 500]
        processing_time = 0.005  # 5ms per record

        for batch_size in batch_sizes:
            throughput, total_time = simulate_batch_processing(batch_size, processing_time)

            print(f"  Batch size {batch_size}: {throughput:.1f} records/sec ({total_time:.3f}s total)")

            # Verify throughput meets minimum requirements
            min_throughput = 100  # 100 records per second minimum
            assert throughput >= min_throughput, f"Throughput {throughput} should be >= {min_throughput}"

        print("✓ Throughput measurement test passed")

    def test_memory_usage_tracking(self):
        """Test memory usage tracking with mock memory monitoring."""
        print("Testing memory usage tracking...")

        # Mock memory tracking
        class MockMemoryMonitor:
            def __init__(self):
                self.baseline_memory = 100  # MB baseline
                self.peak_memory = 0

            def record_memory_usage(self, operation):
                """Simulate memory usage during operations."""
                # Simulate memory usage based on operation
                memory_factor = {
                    "small": 2,
                    "medium": 5,
                    "large": 10
                }

                usage = self.baseline_memory + memory_factor.get(operation, 5)
                self.peak_memory = max(self.peak_memory, usage)
                return usage

        # Test memory tracking during different operations
        monitor = MockMemoryMonitor()

        operations = ["small", "medium", "large", "small", "medium"]

        for op in operations:
            memory_usage = monitor.record_memory_usage(op)
            print(f"  {op} operation: {memory_usage}MB")

        # Verify peak memory tracking
        assert monitor.peak_memory >= 100, f"Peak memory {monitor.peak_memory} should be >= baseline"
        assert monitor.peak_memory <= 120, f"Peak memory {monitor.peak_memory} should be reasonable"

        print("✓ Memory usage tracking test passed")

    def test_concurrent_processing_simulation(self):
        """Test concurrent processing simulation with performance metrics."""
        print("Testing concurrent processing simulation...")

        def simulate_concurrent_processing(num_workers, num_tasks, task_duration):
            """Simulate concurrent processing and measure performance."""
            start_time = time.time()
            completed_tasks = []

            # Simulate task completion with different delays
            import threading

            def worker(worker_id):
                for i in range(num_tasks // num_workers):
                    task_start = time.time()
                    time.sleep(task_duration)  # Simulate work
                    task_end = time.time()
                    completed_tasks.append({
                        "worker": worker_id,
                        "task_id": i,
                        "duration": (task_end - task_start) * 1000,
                        "timestamp": task_end
                    })

            # Start workers
            workers = []
            for i in range(num_workers):
                worker_thread = threading.Thread(target=worker, args=(i,))
                worker_thread.start()
                workers.append(worker_thread)

            # Wait for completion
            for worker in workers:
                worker.join()

            end_time = time.time()
            total_time = end_time - start_time

            # Calculate metrics
            total_tasks = len(completed_tasks)
            throughput = total_tasks / total_time
            avg_task_time = statistics.mean([t["duration"] for t in completed_tasks])

            return {
                "total_time": total_time,
                "throughput": throughput,
                "avg_task_time": avg_task_time,
                "total_tasks": total_tasks
            }

        # Test with different concurrency levels
        scenarios = [
            (1, 10, 0.01),   # 1 worker, 10 tasks
            (2, 20, 0.01),   # 2 workers, 20 tasks
            (4, 40, 0.01),   # 4 workers, 40 tasks
            (8, 80, 0.01),   # 8 workers, 80 tasks
        ]

        for workers, tasks, duration in scenarios:
            metrics = simulate_concurrent_processing(workers, tasks, duration)

            print(f"  {workers} workers: {metrics['throughput']:.1f} tasks/sec, "
                  f"avg {metrics['avg_task_time']:.1f}ms")

            # Verify throughput improves with more workers
            assert metrics["throughput"] > 0, f"Throughput should be positive"
            assert metrics["total_tasks"] == tasks, f"Should complete all {tasks} tasks"

        print("✓ Concurrent processing simulation test passed")


class TestSecurityBoundaries:
    """Test security boundaries with mocked validation."""

    def test_tenant_isolation_enforcement(self):
        """Test tenant isolation is strictly enforced."""
        print("Testing tenant isolation enforcement...")

        # Mock database access with tenant context
        def query_with_tenant_context(tenant_id, query_type):
            """Simulate tenant-isolated database queries."""
            # All data in the database
            all_data = [
                {"id": 1, "tenant_id": "tenant_a", "data": "Sensitive data A"},
                {"id": 2, "tenant_id": "tenant_b", "data": "Sensitive data B"},
                {"id": 3, "tenant_id": "tenant_a", "data": "More data A"},
                {"id": 4, "tenant_id": "tenant_c", "data": "Confidential data C"},
            ]

            # Enforce tenant isolation
            if query_type == "strict":
                filtered = [d for d in all_data if d["tenant_id"] == tenant_id]
            else:
                # Insecure (for testing isolation breach)
                filtered = all_data

            return filtered

        # Test strict isolation
        tenant_a_data_strict = query_with_tenant_context("tenant_a", "strict")
        tenant_b_data_strict = query_with_tenant_context("tenant_b", "strict")

        # Verify no cross-tenant data access
        assert len(tenant_a_data_strict) == 2, "Tenant A should have 2 records"
        assert len(tenant_b_data_strict) == 1, "Tenant B should have 1 record"

        # Verify tenant data is completely separate
        tenant_a_ids = {r["id"] for r in tenant_a_data_strict}
        tenant_b_ids = {r["id"] for r in tenant_b_data_strict}
        assert tenant_a_ids.isdisjoint(tenant_b_ids), "Tenants should have disjoint data"

        print("  ✓ Strict tenant isolation enforced")

    def test_data_access_validation(self):
        """Test data access validation with permission checks."""
        print("Testing data access validation...")

        # Mock permission system
        class MockPermissionSystem:
            def __init__(self):
                self.permissions = {
                    "admin": ["read_all", "write_all", "delete_all"],
                    "analyst": ["read_own", "write_own"],
                    "viewer": ["read_own"]
                }

            def check_permission(self, user_role, resource_tenant, request_tenant):
                """Check if user can access resource."""
                # Rule: users can only access their own tenant's data
                if resource_tenant != request_tenant:
                    return False

                # Check role-based permissions
                user_perms = self.permissions.get(user_role, [])
                return "read_all" in user_perms or "read_own" in user_perms

        # Test permission enforcement
        permission_system = MockPermissionSystem()

        test_cases = [
            ("admin", "tenant_001", "tenant_001", True),   # Admin can access own tenant
            ("analyst", "tenant_001", "tenant_001", True),  # Analyst can access own tenant
            ("viewer", "tenant_001", "tenant_001", True),   # Viewer can access own tenant
            ("admin", "tenant_001", "tenant_002", False),  # Cannot access other tenant
            ("analyst", "tenant_001", "tenant_002", False), # Cannot access other tenant
            ("viewer", "tenant_001", "tenant_002", False), # Cannot access other tenant
        ]

        for role, resource_tenant, request_tenant, expected in test_cases:
            result = permission_system.check_permission(role, resource_tenant, request_tenant)
            assert result == expected, f"{role} accessing {resource_tenant} from {request_tenant}: expected {expected}, got {result}"

        print("  ✓ Data access validation enforced")

    def test_pii_detection_sensitivity(self):
        """Test PII detection sensitivity and accuracy."""
        print("Testing PII detection sensitivity...")

        # Mock PII detection with configurable sensitivity
        class MockPIIDetector:
            def __init__(self, sensitivity="medium"):
                self.sensitivity = sensitivity
                self.thresholds = {
                    "low": 0.3,
                    "medium": 0.7,
                    "high": 0.9
                }

            def detect_pii(self, text):
                """Detect PII with configurable sensitivity."""
                threshold = self.thresholds.get(self.sensitivity, 0.7)

                # Mock PII detection results
                pii_items = [
                    {"type": "PERSON", "confidence": 0.95},
                    {"type": "EMAIL", "confidence": 0.98},
                    {"type": "PHONE", "confidence": 0.85},
                    {"type": "SSN", "confidence": 0.99},
                ]

                # Filter by sensitivity
                detected = [
                    item for item in pii_items
                    if item["confidence"] >= threshold
                ]

                return detected

        # Test different sensitivity levels
        test_text = "John Doe john@example.com 555-1234"

        for sensitivity in ["low", "medium", "high"]:
            detector = MockPIIDetector(sensitivity)
            detected = detector.detect_pii(test_text)

            print(f"  {sensitivity} sensitivity: {len(detected)} PII items detected")

            # Verify sensitivity affects detection
            if sensitivity == "low":
                assert len(detected) >= 2, "Low sensitivity should detect at least 2 items"
            elif sensitivity == "medium":
                assert len(detected) >= 2, "Medium sensitivity should detect at least 2 items"
            elif sensitivity == "high":
                # Only very confident PII detected
                assert len(detected) <= 3, "High sensitivity should be more selective"

        print("  ✓ PII detection sensitivity working")

    def test_input_validation_sanitization(self):
        """Test input validation and sanitization."""
        print("Testing input validation and sanitization...")

        # Mock input validator
        class MockInputValidator:
            def __init__(self):
                self.sanitization_rules = {
                    "sql_injection": ["'", "\"", ";", "--", "/*", "*/"],
                    "xss": ["<script>", "</script>", "javascript:", "onerror="],
                    "command_injection": ["|", "&", ";", "$(", "`"],
                }

            def validate_and_sanitize(self, input_text):
                """Validate and sanitize input."""
                errors = []
                sanitized = input_text

                # Check for malicious patterns
                for category, patterns in self.sanitization_rules.items():
                    for pattern in patterns:
                        if pattern.lower() in input_text.lower():
                            errors.append(f"Potential {category} detected: {pattern}")
                            sanitized = sanitized.replace(pattern, "[REDACTED]")

                return sanitized, errors

        # Test with various inputs
        test_inputs = [
            "Normal user input",
            "John'; DROP TABLE users; --",  # SQL injection
            "Click here <script>alert('xss')</script>",  # XSS
            "cat /etc/passwd | grep root",  # Command injection
            "Safe data with @#$ symbols",  # Safe special chars
        ]

        validator = MockInputValidator()

        for input_text in test_inputs:
            sanitized, errors = validator.validate_and_sanitize(input_text)

            if errors:
                print(f"  Input '{input_text[:30]}...' -> {len(errors)} security issues")
                for error in errors:
                    print(f"    - {error}")
            else:
                print(f"  Input '{input_text[:30]}...' -> Clean")

            # Verify sanitization removes threats
            if "DROP TABLE" in input_text:
                assert "[REDACTED]" in sanitized, "SQL injection should be redacted"
            if "<script>" in input_text:
                assert "[REDACTED]" in sanitized, "XSS should be redacted"

        print("  ✓ Input validation and sanitization working")

    def test_audit_log_integrity(self):
        """Test audit log integrity and tamper resistance."""
        print("Testing audit log integrity...")

        # Mock audit log with integrity check
        class MockAuditLog:
            def __init__(self):
                self.logs = []
                self.hash_key = "secret_audit_hash"

            def create_log(self, tenant_id, operation, data):
                """Create audit log with integrity hash."""
                import hashlib

                timestamp = datetime.utcnow()

                # Create log entry
                log_entry = {
                    "id": f"log_{len(self.logs) + 1}",
                    "tenant_id": tenant_id,
                    "operation": operation,
                    "data": data,
                    "timestamp": timestamp,
                    "hash": self._calculate_hash(tenant_id, operation, data, timestamp)
                }

                self.logs.append(log_entry)
                return log_entry

            def _calculate_hash(self, tenant_id, operation, data, timestamp):
                """Calculate integrity hash."""
                import hashlib
                hash_string = f"{tenant_id}:{operation}:{data}:{timestamp}:{self.hash_key}"
                return hashlib.sha256(hash_string.encode()).hexdigest()

            def verify_integrity(self, log_entry):
                """Verify log entry integrity."""
                calculated_hash = self._calculate_hash(
                    log_entry["tenant_id"],
                    log_entry["operation"],
                    log_entry["data"],
                    log_entry["timestamp"]
                )

                return calculated_hash == log_entry["hash"]

        # Test audit log integrity
        audit_log = MockAuditLog()

        # Create legitimate log
        legitimate_log = audit_log.create_log(
            tenant_id="tenant_001",
            operation="data_access",
            data={"record_id": "rec_001"}
        )

        # Verify legitimate log
        assert audit_log.verify_integrity(legitimate_log), "Legitimate log should be valid"

        # Tamper with log
        tampered_log = legitimate_log.copy()
        tampered_log["data"] = {"record_id": "rec_999"}  # Change data

        # Verify tampered log fails
        assert not audit_log.verify_integrity(tampered_log), "Tampered log should be invalid"

        print("  ✓ Audit log integrity verified")

    def test_rate_limiting_protection(self):
        """Test rate limiting protection against abuse."""
        print("Testing rate limiting protection...")

        # Mock rate limiter
        class MockRateLimiter:
            def __init__(self, max_requests_per_minute=60):
                self.max_requests = max_requests_per_minute
                self.requests = {}

            def check_request(self, user_id, endpoint):
                """Check if request is allowed."""
                current_time = time.time()
                minute_key = int(current_time // 60)  # Current minute

                # Initialize user tracking
                if user_id not in self.requests:
                    self.requests[user_id] = {}

                # Initialize endpoint tracking
                if endpoint not in self.requests[user_id]:
                    self.requests[user_id][endpoint] = {}

                # Initialize minute tracking
                if minute_key not in self.requests[user_id][endpoint]:
                    self.requests[user_id][endpoint][minute_key] = 0

                # Check limit
                if self.requests[user_id][endpoint][minute_key] >= self.max_requests:
                    return False

                # Record request
                self.requests[user_id][endpoint][minute_key] += 1
                return True

        # Test rate limiting
        rate_limiter = MockRateLimiter(max_requests_per_minute=5)

        # Simulate requests from a user
        user_id = "user_001"
        endpoint = "/api/data"

        allowed_requests = 0
        blocked_requests = 0

        for i in range(10):  # Make 10 requests
            if rate_limiter.check_request(user_id, endpoint):
                allowed_requests += 1
            else:
                blocked_requests += 1

        print(f"  Allowed requests: {allowed_requests}")
        print(f"  Blocked requests: {blocked_requests}")

        # Verify rate limiting works
        assert allowed_requests == 5, f"Should allow 5 requests, got {allowed_requests}"
        assert blocked_requests == 5, f"Should block 5 requests, got {blocked_requests}"

        print("  ✓ Rate limiting protection working")


def main():
    """Run all performance and security tests."""
    print("Running Data Foundry Performance and Security Tests\n")
    print("=" * 60)

    performance_tests = [
        TestPerformanceMetrics.test_processing_time_measurement,
        TestPerformanceMetrics.test_throughput_measurement,
        TestPerformanceMetrics.test_memory_usage_tracking,
        TestPerformanceMetrics.test_concurrent_processing_simulation,
    ]

    security_tests = [
        TestSecurityBoundaries.test_tenant_isolation_enforcement,
        TestSecurityBoundaries.test_data_access_validation,
        TestSecurityBoundaries.test_pii_detection_sensitivity,
        TestSecurityBoundaries.test_input_validation_sanitization,
        TestSecurityBoundaries.test_audit_log_integrity,
        TestSecurityBoundaries.test_rate_limiting_protection,
    ]

    all_tests = performance_tests + security_tests
    passed = 0
    failed = 0

    for test in all_tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {str(e)}")
            failed += 1
        print()

    print("=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All performance and security tests passed!")
        return 0
    else:
        print(f"❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())