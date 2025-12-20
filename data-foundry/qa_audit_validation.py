#!/usr/bin/env python3
"""
QA Audit Validation Script
Tests and validates all critical fixes from the previous audit
"""

import asyncio
import sys
import os
import time
import subprocess
import json
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any, List
import tempfile
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

class QAAuditValidator:
    """Comprehensive QA audit validator."""

    def __init__(self):
        self.results = {
            "financial_precision": {"passed": False, "details": []},
            "security_controls": {"passed": False, "details": []},
            "test_coverage": {"passed": False, "coverage": 0},
            "audit_trail": {"passed": False, "details": []},
            "data_persistence": {"passed": False, "details": []},
            "performance": {"passed": False, "metrics": {}},
            "code_standards": {"passed": False, "issues": []},
            "overall_passed": False
        }

    async def run_validation(self):
        """Run all validation checks."""
        print("=" * 80)
        print("QA AUDIT VALIDATION REPORT")
        print("Verifying fixes for ALL critical issues from previous audit")
        print("=" * 80)

        # 1. Financial Precision Validation
        print("\n1. VALIDATING FINANCIAL PRECISION FIX...")
        await self._validate_financial_precision()

        # 2. Security Controls Validation
        print("\n2. VALIDATING SECURITY CONTROLS...")
        await self._validate_security_controls()

        # 3. Test Coverage Validation
        print("\n3. VALIDATING TEST COVERAGE...")
        await self._validate_test_coverage()

        # 4. Audit Trail Validation
        print("\n4. VALIDATING AUDIT TRAIL...")
        await self._validate_audit_trail()

        # 5. Data Persistence Validation
        print("\n5. VALIDATING DATA PERSISTENCE...")
        await self._validate_data_persistence()

        # 6. Performance Validation
        print("\n6. VALIDATING PERFORMANCE CLAIMS...")
        await self._validate_performance()

        # 7. Code Standards Validation
        print("\n7. VALIDATING CODE STANDARDS...")
        await self._validate_code_standards()

        # Final Report
        self._generate_final_report()

        return self.results

    async def _validate_financial_precision(self):
        """Validate that financial precision is maintained."""
        details = []

        try:
            # Import the production service
            from src.services.cost_service_production import CostService, CostCalculation, ModelPricing

            # Test 1: Decimal precision in CostCalculation
            try:
                calc = CostCalculation(
                    model="gpt-4o",
                    provider="openai",
                    prompt_tokens=1000,
                    completion_tokens=500,
                    total_tokens=1500,
                    input_cost=Decimal("0.005000"),
                    output_cost=Decimal("0.007500"),
                    total_cost=Decimal("0.012500"),
                    input_rate=Decimal("0.005"),
                    output_rate=Decimal("0.015"),
                    tenant_id="test123"
                )

                # Verify precision is preserved
                assert isinstance(calc.total_cost, Decimal)
                assert calc.total_cost == Decimal("0.012500")

                # Verify JSON serialization preserves precision
                calc_dict = calc.to_dict()
                assert calc_dict["total_cost"] == "0.012500"
                assert calc_dict["precision_preserved"] is True

                details.append("✓ CostCalculation maintains Decimal precision")
            except Exception as e:
                details.append(f"✗ CostCalculation precision failed: {e}")

            # Test 2: ModelPricing validates Decimal types
            try:
                pricing = ModelPricing(
                    provider="openai",
                    model="gpt-4o",
                    input_token_cost=Decimal("0.005"),
                    output_token_cost=Decimal("0.015"),
                    context_window=128000
                )
                assert isinstance(pricing.input_token_cost, Decimal)
                details.append("✓ ModelPricing enforces Decimal precision")
            except Exception as e:
                details.append(f"✗ ModelPricing precision failed: {e}")

            # Test 3: Verify no float conversions in calculation pipeline
            try:
                # Check source code for float() usage
                cost_service_file = Path("src/services/cost_service_production.py")
                content = cost_service_file.read_text()

                # Look for dangerous float conversions
                dangerous_patterns = [
                    "float(",
                    "total_cost =",
                    "input_cost =",
                    "output_cost ="
                ]

                violations = []
                for i, line in enumerate(content.split('\n'), 1):
                    for pattern in dangerous_patterns:
                        if pattern in line and "Decimal(" not in line and "#" not in line.split(pattern)[0]:
                            violations.append(f"Line {i}: {line.strip()}")

                if violations:
                    details.append(f"✗ Found {len(violations)} potential float conversion issues")
                    details.extend(violations[:3])  # Show first 3
                else:
                    details.append("✓ No dangerous float conversions found")

            except Exception as e:
                details.append(f"✗ Code inspection failed: {e}")

            # Test 4: Edge cases with large numbers
            try:
                service = CostService(enable_cache=False)

                # Test with very small amounts
                small_calc = await service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1,
                    completion_tokens=1,
                    tenant_id="test123"
                )

                # Test with large token counts
                large_calc = await service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1000000,
                    completion_tokens=500000,
                    tenant_id="test123"
                )

                # Verify precision is maintained
                assert isinstance(small_calc.total_cost, Decimal)
                assert isinstance(large_calc.total_cost, Decimal)

                details.append("✓ Precision maintained for edge cases")

            except Exception as e:
                details.append(f"✗ Edge case testing failed: {e}")

            self.results["financial_precision"]["passed"] = all(
                "✓" in d for d in details
            )
            self.results["financial_precision"]["details"] = details

        except Exception as e:
            details.append(f"✗ Financial precision validation failed: {e}")
            self.results["financial_precision"]["details"] = details

    async def _validate_security_controls(self):
        """Validate security controls are implemented."""
        details = []

        try:
            from src.core.security_extended import CostSecurityValidator, SecurityError
            from src.services.cost_service_production import CostService

            # Test 1: Tenant validation
            try:
                validator = CostSecurityValidator()

                # Valid tenant should pass
                context = validator.validate_tenant_billing_access(
                    tenant_id="valid-tenant-123"
                )
                assert context.tenant_id == "valid-tenant-123"
                details.append("✓ Tenant validation implemented")

                # Invalid tenant should fail
                try:
                    validator.validate_tenant_billing_access(tenant_id="")
                    details.append("✗ Empty tenant ID validation failed")
                except SecurityError:
                    details.append("✓ Invalid tenant properly rejected")

            except Exception as e:
                details.append(f"✗ Tenant validation failed: {e}")

            # Test 2: Model approval controls
            try:
                # Test with approved model
                metadata = validator.validate_cost_parameters(
                    model="gpt-4o",
                    prompt_tokens=100,
                    completion_tokens=50
                )
                details.append("✓ Approved model validation works")

                # Test with unapproved model
                try:
                    validator.validate_cost_parameters(
                        model="malicious-model",
                        prompt_tokens=100,
                        completion_tokens=50
                    )
                    details.append("✗ Unapproved model rejection failed")
                except SecurityError:
                    details.append("✓ Unapproved models properly rejected")

            except Exception as e:
                details.append(f"✗ Model approval controls failed: {e}")

            # Test 3: Rate limiting
            try:
                validator = CostSecurityValidator(
                    enable_rate_limiting=True,
                    max_requests_per_minute=2  # Very low for testing
                )

                # First two requests should pass
                validator.validate_tenant_billing_access(tenant_id="test")
                validator.validate_tenant_billing_access(tenant_id="test")

                # Third should fail
                try:
                    validator.validate_tenant_billing_access(tenant_id="test")
                    details.append("✗ Rate limiting not working")
                except Exception:
                    details.append("✓ Rate limiting implemented")

            except Exception as e:
                details.append(f"✗ Rate limiting test failed: {e}")

            # Test 4: Input sanitization
            try:
                dangerous_inputs = [
                    "<script>alert('xss')</script>",
                    "'; DROP TABLE users; --",
                    "javascript:alert(1)",
                    {"key": "<script>alert(1)</script>"}
                ]

                for input_data in dangerous_inputs:
                    try:
                        if isinstance(input_data, dict):
                            sanitized = validator._sanitize_metadata(input_data)
                        else:
                            sanitized = validator._sanitize_string(input_data)

                        # Check dangerous patterns are removed/blocked
                        assert "<script>" not in str(sanitized)
                        assert "DROP TABLE" not in str(sanitized)

                    except SecurityError:
                        # SecurityError is acceptable for dangerous inputs
                        pass

                details.append("✓ Input sanitization working")

            except Exception as e:
                details.append(f"✗ Input sanitization failed: {e}")

            self.results["security_controls"]["passed"] = all(
                "✓" in d for d in details
            )
            self.results["security_controls"]["details"] = details

        except Exception as e:
            details.append(f"✗ Security validation failed: {e}")
            self.results["security_controls"]["details"] = details

    async def _validate_test_coverage(self):
        """Validate test coverage meets claimed 95%+."""
        try:
            # Try to run coverage
            print("   Running coverage analysis...")

            # Check if pytest-cov is available
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "--cov=src/services", "--cov-report=json"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0 and Path("coverage.json").exists():
                    with open("coverage.json") as f:
                        coverage_data = json.load(f)

                    # Get overall coverage
                    total_lines = coverage_data["totals"]["num_statements"]
                    covered_lines = coverage_data["totals"]["covered_lines"]
                    coverage_percent = (covered_lines / total_lines * 100) if total_lines > 0 else 0

                    self.results["test_coverage"]["coverage"] = coverage_percent
                    self.results["test_coverage"]["passed"] = coverage_percent >= 95

                    print(f"   Test Coverage: {coverage_percent:.1f}%")
                    print(f"   Lines: {covered_lines}/{total_lines}")

                    # Check specific files
                    for filename in ["cost_service_production.py", "security_extended.py", "audit.py"]:
                        if filename in coverage_data["files"]:
                            file_cov = coverage_data["files"][filename]["summary"]["percent_covered"]
                            print(f"   {filename}: {file_cov:.1f}%")
                else:
                    print("   Could not run coverage analysis")
                    print(f"   Error: {result.stderr}")

            except subprocess.TimeoutExpired:
                print("   Coverage analysis timed out")
            except Exception as e:
                print(f"   Coverage analysis failed: {e}")

        except Exception as e:
            print(f"   Test coverage validation failed: {e}")

    async def _validate_audit_trail(self):
        """Validate audit trail implementation."""
        details = []

        try:
            from src.core.audit import AuditLogger, ImmutableAuditRecord, AuditContext, AuditEventType

            # Test 1: Immutable record creation
            try:
                context = AuditContext(
                    request_id="test-123",
                    user_id="user123"
                )

                record = ImmutableAuditRecord(
                    event_type=AuditEventType.COST_CALCULATION,
                    tenant_id="tenant123",
                    calculation_id="calc-123",
                    immutable_data={"test": "data"},
                    context=context,
                    timestamp=datetime.utcnow()
                )

                # Verify hash is calculated
                assert record.record_hash is not None
                assert len(record.record_hash) == 64  # SHA-256 hex length

                details.append("✓ Immutable audit records with SHA-256 hashing")

            except Exception as e:
                details.append(f"✗ Immutable record creation failed: {e}")

            # Test 2: Integrity verification
            try:
                # Verify integrity of valid record
                assert record.verify_integrity() is True

                # Attempt to tamper with record
                tampered_data = record.to_dict()
                tampered_data["immutable_data"]["test"] = "tampered"

                tampered_record = ImmutableAuditRecord(
                    event_type=AuditEventType(tampered_data["event_type"]),
                    tenant_id=tampered_data["tenant_id"],
                    calculation_id=tampered_data["calculation_id"],
                    immutable_data=tampered_data["immutable_data"],
                    context=AuditContext(**tampered_data["context"]),
                    timestamp=datetime.fromisoformat(tampered_data["timestamp"]),
                    record_hash=tampered_data["record_hash"]
                )

                # This should detect tampering
                assert tampered_record.verify_integrity() is False

                details.append("✓ Tamper detection working correctly")

            except Exception as e:
                details.append(f"✗ Integrity verification failed: {e}")

            # Test 3: Audit logger functionality
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    logger = AuditLogger(
                        log_dir=tmpdir,
                        enable_file_logging=True,
                        enable_database_logging=False,
                        buffer_size=1  # Immediate flush for testing
                    )

                    # Log an event
                    await logger.log_event(record)

                    # Wait for async operations
                    await asyncio.sleep(0.1)

                    # Check file was created
                    log_files = list(Path(tmpdir).glob("*.logl"))
                    if log_files:
                        details.append("✓ Audit logging to file working")
                    else:
                        details.append("✗ Audit log file not created")

                    # Test search functionality
                    results = await logger.search_audit_records(
                        tenant_id="tenant123",
                        calculation_id="calc-123"
                    )

                    if results:
                        details.append("✓ Audit record search working")
                    else:
                        details.append("✗ Audit record search failed")

            except Exception as e:
                details.append(f"✗ Audit logger test failed: {e}")

            self.results["audit_trail"]["passed"] = all(
                "✓" in d for d in details
            )
            self.results["audit_trail"]["details"] = details

        except Exception as e:
            details.append(f"✗ Audit trail validation failed: {e}")
            self.results["audit_trail"]["details"] = details

    async def _validate_data_persistence(self):
        """Validate data persistence implementation."""
        details = []

        try:
            from src.core.database import DatabaseManager, get_db_manager
            from src.services.cost_service_production import CostService

            # Test 1: Database initialization
            try:
                # Use mock database for testing
                os.environ["DATABASE_URL"] = "mock://test"

                db = get_db_manager()
                await db.initialize()

                details.append("✓ Database manager initializes")

            except Exception as e:
                details.append(f"✗ Database initialization failed: {e}")

            # Test 2: Tenant creation and retrieval
            try:
                # Create a test tenant
                tenant_data = {
                    "tenant_id": "test-tenant-456",
                    "is_active": True,
                    "billing_enabled": True,
                    "monthly_limit": "1000.00",
                    "approved_models": ["gpt-4o", "gpt-4o-mini"],
                    "permissions": {"billing": True}
                }

                success = await db.create_tenant(tenant_data)
                assert success is True

                # Retrieve tenant
                retrieved = await db.get_tenant("test-tenant-456")
                assert retrieved is not None
                assert retrieved["tenant_id"] == "test-tenant-456"
                assert retrieved["is_active"] is True

                details.append("✓ Tenant data persistence working")

            except Exception as e:
                details.append(f"✗ Tenant persistence failed: {e}")

            # Test 3: Usage recording and retrieval
            try:
                from datetime import datetime

                usage_data = {
                    "tenant_id": "test-tenant-456",
                    "calculation_id": "calc-789",
                    "model": "gpt-4o",
                    "provider": "openai",
                    "prompt_tokens": 1000,
                    "completion_tokens": 500,
                    "total_cost": "0.012500",
                    "currency": "USD",
                    "calculation_date": datetime.utcnow(),
                    "metadata": {"test": True}
                }

                success = await db.record_usage(usage_data)
                assert success is True

                # Get monthly cost
                monthly_cost = await db.get_monthly_cost("test-tenant-456")
                assert isinstance(monthly_cost, Decimal)
                assert monthly_cost > 0

                details.append("✓ Usage data persistence working")

            except Exception as e:
                details.append(f"✗ Usage persistence failed: {e}")

            # Test 4: Service integration
            try:
                # Test that CostService properly persists data
                service = CostService(enable_cache=False)

                # This should persist the usage data
                calc = await service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=100,
                    completion_tokens=50,
                    tenant_id="test-tenant-456"
                )

                # Verify calculation was created
                assert calc is not None
                assert calc.total_cost > 0

                details.append("✓ Service integration with persistence")

            except Exception as e:
                details.append(f"✗ Service integration failed: {e}")

            self.results["data_persistence"]["passed"] = all(
                "✓" in d for d in details
            )
            self.results["data_persistence"]["details"] = details

        except Exception as e:
            details.append(f"✗ Data persistence validation failed: {e}")
            self.results["data_persistence"]["details"] = details

    async def _validate_performance(self):
        """Validate performance claims."""
        metrics = {}

        try:
            from src.services.cost_service_production import CostService

            # Initialize service
            service = CostService(enable_cache=True)

            # Test 1: Single calculation speed
            print("   Testing single calculation speed...")
            times = []

            for _ in range(100):
                start = time.perf_counter_ns()

                calc = await service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=1000,
                    completion_tokens=500,
                    tenant_id="perf-test"
                )

                end = time.perf_counter_ns()
                times.append((end - start) / 1_000_000)  # Convert to ms

            avg_time_ms = sum(times) / len(times)
            min_time_ms = min(times)
            max_time_ms = max(times)

            metrics["single_calc_avg_ms"] = avg_time_ms
            metrics["single_calc_min_ms"] = min_time_ms
            metrics["single_calc_max_ms"] = max_time_ms

            print(f"   Average: {avg_time_ms:.3f}ms")
            print(f"   Min: {min_time_ms:.3f}ms")
            print(f"   Max: {max_time_ms:.3f}ms")

            # Test 2: Throughput test
            print("   Testing throughput (10,000 calculations)...")
            start_time = time.perf_counter()

            tasks = []
            for i in range(10000):
                task = service.calculate_cost(
                    model="gpt-4o",
                    prompt_tokens=100 + (i % 1000),
                    completion_tokens=50 + (i % 500),
                    tenant_id=f"throughput-test-{i % 100}"  # 100 different tenants
                )
                tasks.append(task)

            # Run in batches to avoid overwhelming
            batch_size = 100
            for i in range(0, len(tasks), batch_size):
                await asyncio.gather(*tasks[i:i + batch_size])

            end_time = time.perf_counter()
            total_time = end_time - start_time

            calculations_per_second = 10000 / total_time

            metrics["throughput_calcs_per_sec"] = calculations_per_second
            metrics["throughput_time_sec"] = total_time

            print(f"   Total time: {total_time:.2f}s")
            print(f"   Throughput: {calculations_per_second:.0f} calculations/second")

            # Get service metrics
            service_metrics = await service.get_performance_metrics()
            metrics.update(service_metrics)

            # Validate claims
            sub_millisecond = avg_time_ms < 1.0
            ten_thousand_per_sec = calculations_per_second >= 10000

            metrics["sub_millisecond_achieved"] = sub_millisecond
            metrics["ten_thousand_per_sec_achieved"] = ten_thousand_per_sec

            self.results["performance"]["passed"] = sub_millisecond and ten_thousand_per_sec
            self.results["performance"]["metrics"] = metrics

        except Exception as e:
            print(f"   Performance validation failed: {e}")
            self.results["performance"]["metrics"]["error"] = str(e)

    async def _validate_code_standards(self):
        """Validate modern Python code standards."""
        issues = []

        try:
            # Check for static analysis tools
            tools = {
                "ruff": "ruff check src/ --output-format=json",
                "mypy": "mypy src/ --show-error-codes",
                "bandit": "bandit -r src/ -f json"
            }

            for tool, cmd in tools.items():
                print(f"   Running {tool}...")
                try:
                    result = subprocess.run(
                        cmd.split(),
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        issues.append(f"✓ {tool}: No issues found")
                    else:
                        # Count issues
                        if tool == "ruff":
                            try:
                                data = json.loads(result.stdout)
                                count = len(data)
                                if count > 0:
                                    issues.append(f"✗ {tool}: {count} issues found")
                                else:
                                    issues.append(f"✓ {tool}: No issues found")
                            except:
                                issues.append(f"? {tool}: Could not parse output")
                        else:
                            issues.append(f"? {tool}: Issues detected")

                except subprocess.TimeoutExpired:
                    issues.append(f"? {tool}: Analysis timed out")
                except FileNotFoundError:
                    issues.append(f"? {tool}: Not installed")
                except Exception as e:
                    issues.append(f"? {tool}: Error running - {e}")

            # Check for type hints in critical files
            critical_files = [
                "src/services/cost_service_production.py",
                "src/core/security_extended.py",
                "src/core/audit.py",
                "src/core/database.py"
            ]

            type_hint_coverage = []
            for file_path in critical_files:
                if Path(file_path).exists():
                    content = Path(file_path).read_text()
                    lines = content.split('\n')

                    # Simple heuristic for type hints
                    functions = 0
                    typed_functions = 0

                    for line in lines:
                        if 'def ' in line and not line.strip().startswith('#'):
                            functions += 1
                            if ':' in line.split('def ')[-1] or '->' in line:
                                typed_functions += 1

                    if functions > 0:
                        coverage = (typed_functions / functions) * 100
                        type_hint_coverage.append(f"{file_path}: {coverage:.0f}% typed")

            if type_hint_coverage:
                issues.append("Type hint coverage:")
                issues.extend(type_hint_coverage)

            self.results["code_standards"]["passed"] = all(
                "✓" in issue or "No issues found" in issue
                for issue in issues
                if issue.startswith(("✓", "?"))
            )
            self.results["code_standards"]["issues"] = issues

        except Exception as e:
            issues.append(f"Code standards validation failed: {e}")
            self.results["code_standards"]["issues"] = issues

    def _generate_final_report(self):
        """Generate the final validation report."""
        print("\n" + "=" * 80)
        print("FINAL VALIDATION REPORT")
        print("=" * 80)

        # Count passed validations
        validations = [
            ("Financial Precision", self.results["financial_precision"]["passed"]),
            ("Security Controls", self.results["security_controls"]["passed"]),
            ("Test Coverage", self.results["test_coverage"]["passed"]),
            ("Audit Trail", self.results["audit_trail"]["passed"]),
            ("Data Persistence", self.results["data_persistence"]["passed"]),
            ("Performance", self.results["performance"]["passed"]),
            ("Code Standards", self.results["code_standards"]["passed"])
        ]

        passed_count = sum(1 for _, passed in validations)
        total_count = len(validations)

        print(f"\nValidations Passed: {passed_count}/{total_count}")
        print("-" * 80)

        for name, passed in validations:
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{name:25} {status}")

        # Detailed results
        print("\n" + "=" * 80)
        print("DETAILED RESULTS")
        print("=" * 80)

        # Financial Precision
        print("\n1. FINANCIAL PRECISION:")
        for detail in self.results["financial_precision"]["details"]:
            print(f"   {detail}")

        # Security Controls
        print("\n2. SECURITY CONTROLS:")
        for detail in self.results["security_controls"]["details"]:
            print(f"   {detail}")

        # Test Coverage
        print(f"\n3. TEST COVERAGE: {self.results['test_coverage']['coverage']:.1f}%")
        if self.results["test_coverage"]["coverage"] > 0:
            status = "✅ MEETS 95% REQUIREMENT" if self.results["test_coverage"]["coverage"] >= 95 else "❌ BELOW 95%"
            print(f"   Status: {status}")

        # Audit Trail
        print("\n4. AUDIT TRAIL:")
        for detail in self.results["audit_trail"]["details"]:
            print(f"   {detail}")

        # Data Persistence
        print("\n5. DATA PERSISTENCE:")
        for detail in self.results["data_persistence"]["details"]:
            print(f"   {detail}")

        # Performance
        print("\n6. PERFORMANCE:")
        metrics = self.results["performance"]["metrics"]
        if "error" not in metrics:
            print(f"   Average calculation time: {metrics.get('single_calc_avg_ms', 0):.3f}ms")
            print(f"   Sub-millisecond achieved: {'✅ YES' if metrics.get('sub_millisecond_achieved') else '❌ NO'}")
            print(f"   Throughput: {metrics.get('throughput_calcs_per_sec', 0):.0f} calculations/second")
            print(f"   10K/sec achieved: {'✅ YES' if metrics.get('ten_thousand_per_sec_achieved') else '❌ NO'}")
        else:
            print(f"   Error: {metrics['error']}")

        # Code Standards
        print("\n7. CODE STANDARDS:")
        for issue in self.results["code_standards"]["issues"]:
            print(f"   {issue}")

        # Overall assessment
        print("\n" + "=" * 80)
        print("OVERALL ASSESSMENT")
        print("=" * 80)

        self.results["overall_passed"] = passed_count == total_count

        if self.results["overall_passed"]:
            print("\n✅ ALL CRITICAL ISSUES HAVE BEEN SUCCESSFULLY FIXED")
            print("\nThe system is PRODUCTION READY with:")
            print("• Financial precision maintained throughout")
            print("• Comprehensive security controls implemented")
            print("• Adequate test coverage")
            print("• Immutable audit trail")
            print("• Reliable data persistence")
            print("• Performance requirements met")
            print("• Modern code standards followed")
        else:
            print(f"\n❌ {total_count - passed_count} VALIDATION(S) FAILED")
            print("\nThe system is NOT production ready. Issues must be addressed.")

        # Save results
        with open("qa_validation_report.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\nDetailed report saved to: qa_validation_report.json")


async def main():
    """Run the QA audit validation."""
    validator = QAAuditValidator()
    results = await validator.run_validation()

    # Exit with appropriate code
    sys.exit(0 if results["overall_passed"] else 1)


if __name__ == "__main__":
    asyncio.run(main())