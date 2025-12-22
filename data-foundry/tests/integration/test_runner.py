"""
Integration Test Runner

Comprehensive test runner for consent management system integration tests.
Provides CI/CD integration, reporting, and test orchestration.
"""

import asyncio
import json
import logging
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


class TestConfiguration:
    """Configuration for integration tests."""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "tests/integration/test_config.yaml"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load test configuration from file."""
        default_config = {
            "test_environments": {
                "development": {
                    "database_url": "sqlite:///./test_dev.db",
                    "redis_url": "redis://localhost:6379/0",
                    "log_level": "DEBUG"
                },
                "staging": {
                    "database_url": os.getenv("STAGING_DB_URL", "postgresql://localhost/test_staging"),
                    "redis_url": os.getenv("STAGING_REDIS_URL", "redis://localhost:6379/1"),
                    "log_level": "INFO"
                },
                "production": {
                    "database_url": os.getenv("PROD_DB_URL"),
                    "redis_url": os.getenv("PROD_REDIS_URL"),
                    "log_level": "WARNING"
                }
            },
            "test_suites": {
                "unit": {
                    "path": "tests/unit",
                    "timeout": 300,
                    "parallel": True
                },
                "integration": {
                    "path": "tests/integration",
                    "timeout": 1800,
                    "parallel": False
                },
                "performance": {
                    "path": "tests/integration/test_performance_benchmarks.py",
                    "timeout": 3600,
                    "parallel": False
                },
                "security": {
                    "path": "tests/integration/test_consent_management_complete.py",
                    "timeout": 900,
                    "parallel": False
                }
            },
            "reporting": {
                "formats": ["html", "json", "junit"],
                "coverage": {
                    "enabled": True,
                    "threshold": 80,
                    "fail_below_threshold": True
                },
                "artifacts": {
                    "directory": "test_artifacts",
                    "retention_days": 30
                }
            },
            "notifications": {
                "email": {
                    "enabled": False,
                    "recipients": []
                },
                "slack": {
                    "enabled": False,
                    "webhook_url": ""
                }
            }
        }

        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                user_config = yaml.safe_load(f)
                # Merge with defaults
                default_config.update(user_config)

        return default_config

    def get_environment_config(self, environment: str) -> Dict[str, Any]:
        """Get configuration for specific environment."""
        return self.config["test_environments"].get(environment, {})

    def get_test_suite_config(self, suite: str) -> Dict[str, Any]:
        """Get configuration for specific test suite."""
        return self.config["test_suites"].get(suite, {})


class TestRunner:
    """Main test runner orchestrator."""

    def __init__(self, config_file: Optional[str] = None):
        self.config = TestConfiguration(config_file)
        self.test_results = {}
        self.start_time = None
        self.end_time = None

    async def run_all_tests(self, environment: str = "development") -> Dict[str, Any]:
        """Run all test suites for the specified environment."""
        logger.info(f"Starting integration test suite for environment: {environment}")
        self.start_time = datetime.now(timezone.utc)

        # Setup test environment
        await self._setup_environment(environment)

        # Run test suites
        suite_results = {}
        test_suites = self.config.config["test_suites"]

        for suite_name, suite_config in test_suites.items():
            logger.info(f"Running test suite: {suite_name}")
            result = await self._run_test_suite(suite_name, suite_config, environment)
            suite_results[suite_name] = result

            # Fail fast if critical suite fails
            if not result["success"] and suite_name in ["integration", "security"]:
                logger.error(f"Critical test suite {suite_name} failed, stopping execution")
                break

        self.end_time = datetime.now(timezone.utc)
        self.test_results = {
            "environment": environment,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "suites": suite_results,
            "overall_success": all(r["success"] for r in suite_results.values())
        }

        # Generate reports
        await self._generate_reports()

        # Cleanup
        await self._cleanup()

        return self.test_results

    async def run_suite(self, suite_name: str, environment: str = "development") -> Dict[str, Any]:
        """Run a specific test suite."""
        logger.info(f"Running test suite: {suite_name}")
        self.start_time = datetime.now(timezone.utc)

        await self._setup_environment(environment)

        suite_config = self.config.get_test_suite_config(suite_name)
        if not suite_config:
            raise ValueError(f"Unknown test suite: {suite_name}")

        result = await self._run_test_suite(suite_name, suite_config, environment)

        self.end_time = datetime.now(timezone.utc)
        self.test_results = {
            "environment": environment,
            "suite": suite_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "result": result
        }

        await self._generate_reports()
        await self._cleanup()

        return self.test_results

    async def _setup_environment(self, environment: str):
        """Setup test environment."""
        env_config = self.config.get_environment_config(environment)

        # Set environment variables
        for key, value in env_config.items():
            if value:
                os.environ[key.upper()] = str(value)

        # Create artifacts directory
        artifacts_dir = Path(self.config.config["reporting"]["artifacts"]["directory"])
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Test environment setup complete for: {environment}")

    async def _cleanup(self):
        """Cleanup after tests."""
        logger.info("Cleaning up test environment")

        # Cleanup environment variables
        env_vars = ["DATABASE_URL", "REDIS_URL", "LOG_LEVEL"]
        for var in env_vars:
            os.environ.pop(var, None)

        # Additional cleanup logic here
        # e.g., cleanup test databases, containers, etc.

    async def _run_test_suite(
        self,
        suite_name: str,
        suite_config: Dict[str, Any],
        environment: str
    ) -> Dict[str, Any]:
        """Run a specific test suite."""
        test_path = suite_config["path"]
        timeout = suite_config.get("timeout", 600)
        parallel = suite_config.get("parallel", False)

        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "-v",
            f"--timeout={timeout}",
            "--tb=short"
        ]

        # Add parallel execution if enabled
        if parallel:
            cmd.extend(["-n", "auto"])

        # Add coverage if enabled
        if self.config.config["reporting"]["coverage"]["enabled"]:
            cmd.extend([
                "--cov=src",
                "--cov-fail-under=" + str(self.config.config["reporting"]["coverage"]["threshold"]),
                "--cov-report=html",
                "--cov-report=xml",
                "--cov-report=term-missing"
            ])

        # Add reporting formats
        for fmt in self.config.config["reporting"]["formats"]:
            if fmt == "html":
                cmd.extend([
                    f"--html={self._get_report_path(suite_name, 'html')}",
                    "--self-contained-html"
                ])
            elif fmt == "json":
                cmd.extend([f"--json-report-file={self._get_report_path(suite_name, 'json')}"])
            elif fmt == "junit":
                cmd.extend([f"--junitxml={self._get_report_path(suite_name, 'junit')}"])

        # Execute tests
        logger.info(f"Executing: {' '.join(cmd)}")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            duration = time.time() - start_time

            # Parse results
            success = result.returncode == 0
            output = result.stdout
            error_output = result.stderr

            # Extract test count if available
            test_count = self._extract_test_count(output)

            return {
                "success": success,
                "duration_seconds": duration,
                "exit_code": result.returncode,
                "test_count": test_count,
                "stdout": output,
                "stderr": error_output,
                "command": " ".join(cmd)
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "duration_seconds": timeout,
                "exit_code": -1,
                "error": f"Test suite timed out after {timeout} seconds",
                "command": " ".join(cmd)
            }

    def _extract_test_count(self, output: str) -> Optional[int]:
        """Extract test count from pytest output."""
        import re

        # Look for patterns like "X passed" or "X tests selected"
        patterns = [
            r"(\d+) passed",
            r"(\d+) failed",
            r"(\d+) tests? (?:deselected|selected)"
        ]

        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return int(match.group(1))

        return None

    def _get_report_path(self, suite_name: str, format: str) -> str:
        """Get path for test report file."""
        artifacts_dir = self.config.config["reporting"]["artifacts"]["directory"]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{artifacts_dir}/{suite_name}_report_{timestamp}.{format}"

    async def _generate_reports(self):
        """Generate comprehensive test reports."""
        logger.info("Generating test reports")

        # Save main results
        results_file = Path(self.config.config["reporting"]["artifacts"]["directory"]) / "test_results.json"
        with open(results_file, 'w') as f:
            json.dump(self.test_results, f, indent=2)

        # Generate summary report
        await self._generate_summary_report()

        # Generate JUnit report for CI/CD
        if "junit" in self.config.config["reporting"]["formats"]:
            await self._generate_junit_report()

        # Send notifications if configured
        await self._send_notifications()

    async def _generate_summary_report(self):
        """Generate a human-readable summary report."""
        summary_path = Path(self.config.config["reporting"]["artifacts"]["directory"]) / "test_summary.md"

        with open(summary_path, 'w') as f:
            f.write("# Integration Test Summary\n\n")
            f.write(f"**Environment:** {self.test_results.get('environment', 'unknown')}\n")
            f.write(f"**Duration:** {self.test_results.get('duration_seconds', 0):.2f} seconds\n")
            f.write(f"**Timestamp:** {self.test_results.get('start_time', 'unknown')}\n\n")

            f.write("## Test Suites\n\n")

            if "suites" in self.test_results:
                for suite_name, suite_result in self.test_results["suites"].items():
                    status = "✅ PASSED" if suite_result.get("success", False) else "❌ FAILED"
                    f.write(f"### {suite_name.title()}: {status}\n")
                    f.write(f"- Duration: {suite_result.get('duration_seconds', 0):.2f}s\n")
                    f.write(f"- Tests: {suite_result.get('test_count', 'unknown')}\n")
                    if suite_result.get("error"):
                        f.write(f"- Error: {suite_result['error']}\n")
                    f.write("\n")

            f.write("## Coverage Report\n\n")
            if self.config.config["reporting"]["coverage"]["enabled"]:
                f.write(f"Coverage threshold: {self.config.config['reporting']['coverage']['threshold']}%\n")
                f.write("Detailed coverage report available in `htmlcov/index.html`\n\n")

            f.write("## Artifacts\n\n")
            artifacts_dir = self.config.config["reporting"]["artifacts"]["directory"]
            f.write(f"All test artifacts saved to: `{artifacts_dir}/`\n\n")

        logger.info(f"Summary report generated: {summary_path}")

    async def _generate_junit_report(self):
        """Generate JUnit XML report for CI/CD systems."""
        # This would convert the test results to JUnit format
        # Implementation depends on specific CI/CD system requirements
        pass

    async def _send_notifications(self):
        """Send test result notifications."""
        if not self.test_results.get("overall_success", True):
            # Only notify on failure
            pass

        # Email notification
        if self.config.config["notifications"]["email"]["enabled"]:
            # Send email with results
            pass

        # Slack notification
        if self.config.config["notifications"]["slack"]["enabled"]:
            # Send Slack message with results
            pass


class CIIntegration:
    """CI/CD integration utilities."""

    @staticmethod
    def github_actions_output(variable_name: str, value: str):
        """Output to GitHub Actions."""
        print(f"::set-output name={variable_name}::{value}")

    @staticmethod
    def github_actions_step_summary(message: str):
        """Add message to GitHub Actions step summary."""
        with open(os.environ.get("GITHUB_STEP_SUMMARY", ""), "a") as f:
            f.write(f"{message}\n")

    @staticmethod
    def azure_devops_task_log_issue(message: str):
        """Log issue in Azure DevOps."""
        print(f"##vso[task.logissue type=error]{message}")

    @staticmethod
    def jenkins_set_description(description: str):
        """Set build description in Jenkins."""
        print(f"<JENKINS_BUILD_DESCRIPTION>{description}</JENKINS_BUILD_DESCRIPTION>")

    @staticmethod
    def gitlab_ci_artifact_report(file_path: str):
        """Report artifact in GitLab CI."""
        print(f"Artifact created at: {file_path}")


async def main():
    """Main entry point for test runner."""
    import argparse

    parser = argparse.ArgumentParser(description="Integration Test Runner")
    parser.add_argument(
        "--environment",
        choices=["development", "staging", "production"],
        default="development",
        help="Test environment"
    )
    parser.add_argument(
        "--suite",
        help="Specific test suite to run (default: all)"
    )
    parser.add_argument(
        "--config",
        help="Path to test configuration file"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Running in CI/CD environment"
    )

    args = parser.parse_args()

    # Create test runner
    runner = TestRunner(args.config)

    # Run tests
    if args.suite:
        results = await runner.run_suite(args.suite, args.environment)
    else:
        results = await runner.run_all_tests(args.environment)

    # CI/CD integration
    if args.ci:
        overall_success = results.get("overall_success", True)

        if "GITHUB_ACTIONS" in os.environ:
            CIIntegration.github_actions_output("tests_passed", str(overall_success))
            CIIntegration.github_actions_step_summary(
                f"Tests {'PASSED' if overall_success else 'FAILED'}"
            )
        elif "AZURE_PIPELINES" in os.environ:
            if not overall_success:
                CIIntegration.azure_devops_task_log_issue("Integration tests failed")

    # Exit with appropriate code
    sys.exit(0 if results.get("overall_success", True) else 1)


if __name__ == "__main__":
    asyncio.run(main())