#!/usr/bin/env python3
"""
LiteLLM Integration Test Runner

This script runs all tests for the LiteLLM integration:
1. Unit tests (mocked)
2. Integration tests (real APIs)
3. Performance tests (load testing)

Usage:
    python run_litellm_tests.py --type unit      # Run unit tests only
    python run_litellm_tests.py --type integration  # Run integration tests
    python run_litellm_tests.py --type performance  # Run performance tests
    python run_litellm_tests.py --type all       # Run all tests (default)
"""

import asyncio
import os
import sys
import subprocess
import argparse
from typing import List, Dict, Any
from datetime import datetime

def get_test_args(test_type: str) -> List[str]:
    """Get pytest arguments for test type."""
    base_args = [
        "pytest",
        "-v",
        "--tb=short",
        "--no-header",
        "-p", "no:warnings"
    ]

    if test_type == "unit":
        return base_args + [
            "-m", "unit",
            "tests/unit/services/test_litellm_service.py",
            "tests/unit/services/test_ai_service.py"
        ]
    elif test_type == "integration":
        return base_args + [
            "-m", "integration",
            "tests/integration/test_litellm_integration.py",
            "-s"  # Show print statements
        ]
    elif test_type == "performance":
        return base_args + [
            "-m", "performance",
            "tests/performance/test_litellm_performance.py",
            "-s",  # Show print statements
            "--durations=10"  # Show 10 slowest tests
        ]
    else:  # all
        return base_args + [
            "tests/unit/services/test_litellm_service.py",
            "tests/unit/services/test_ai_service.py",
            "tests/integration/test_litellm_integration.py",
            "tests/performance/test_litellm_performance.py"
        ]

def check_environment(test_type: str) -> bool:
    """Check if environment is set up for tests."""
    required_vars = []

    if test_type in ["integration", "all", "performance"]:
        # For integration tests, need at least one provider key
        if not any([
            os.getenv("OPENAI_API_KEY"),
            os.getenv("ANTHROPIC_API_KEY"),
            os.getenv("AZURE_API_KEY"),
            os.getenv("GOOGLE_API_KEY")
        ]):
            print("\n⚠️  WARNING: No AI provider API keys found!")
            print("   Integration tests will be skipped.")
            print("   Set one of the following:")
            print("   - OPENAI_API_KEY")
            print("   - ANTHROPIC_API_KEY")
            print("   - AZURE_API_KEY")
            print("   - GOOGLE_API_KEY")
            print()

            # Prompt to continue
            response = input("Continue anyway? (y/N): ")
            if response.lower() != "y":
                return False

    # Check Redis for caching tests
    if not os.getenv("REDIS_URL"):
        print("\n⚠️  WARNING: REDIS_URL not set!")
        print("   Redis-dependent tests will be skipped.")
        print()

    return True

def run_tests(test_args: List[str]) -> Dict[str, Any]:
    """Run pytest with given arguments and return results."""
    # Run pytest
    result = subprocess.run(
        test_args,
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )

    # Parse results
    output = result.stdout
    error_output = result.stderr

    # Extract test statistics
    stats = {
        "exit_code": result.returncode,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration": 0
    }

    # Parse pytest summary (last few lines)
    for line in output.split('\n')[-10:]:
        if " passed in " in line:
            parts = line.split()
            if parts[0].isdigit():
                stats["passed"] = int(parts[0])
        if " failed, " in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "failed," and i > 0 and parts[i-1].isdigit():
                    stats["failed"] = int(parts[i-1])
        if " skipped in " in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "skipped" and i > 0 and parts[i-1].isdigit():
                    stats["skipped"] = int(parts[i-1])
        if " errors in " in line:
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "errors" and i > 0 and parts[i-1].isdigit():
                    stats["errors"] = int(parts[i-1])
        if " passed in " in line and "seconds" in line:
            # Extract duration
            import re
            match = re.search(r'(\d+\.?\d*) seconds', line)
            if match:
                stats["duration"] = float(match.group(1))

    stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"] + stats["errors"]
    stats["output"] = output
    stats["error_output"] = error_output

    return stats

def print_results(test_type: str, stats: Dict[str, Any]):
    """Print formatted test results."""
    print(f"\n{'='*60}")
    print(f"LiteLLM {test_type.title()} Test Results")
    print(f"{'='*60}")
    print(f"Total:   {stats['total']}")
    print(f"Passed:  {stats['passed']}")
    print(f"Failed:  {stats['failed']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Errors:  {stats['errors']}")
    print(f"Duration: {stats['duration']:.2f} seconds")

    if stats['failed'] > 0 or stats['errors'] > 0:
        print(f"\n❌ {test_type.title()} tests completed with failures/errors")

        # Show failures
        if stats['error_output']:
            print("\nErrors:")
            print("-" * 40)
            print(stats['error_output'])
    else:
        print(f"\n✅ All {test_type} tests passed!")

    print("="*60)

def run_health_check():
    """Run a quick health check on the LiteLLM service."""
    print("\n" + "="*60)
    print("LiteLLM Service Health Check")
    print("="*60)

    try:
        # Create test script
        test_script = """
import asyncio
import os
from src.services.litellm_service import LiteLLMService

async def health_check():
    service = LiteLLMService()
    await service.initialize()

    health = await service.health_check()
    print(f"Service Health: {'✅ Healthy' if health['healthy'] else '❌ Unhealthy'}")

    for model, status in health['models'].items():
        print(f"  {model}: {'✅' if status['status'] == 'healthy' else '❌'} "
              f"({status['provider']})")

asyncio.run(health_check())
"""

        # Write and run
        with open("health_check.py", "w") as f:
            f.write(test_script)

        result = subprocess.run(
            [sys.executable, "health_check.py"],
            capture_output=True,
            text=True
        )

        print(result.stdout)

        if result.stderr:
            print("Errors:")
            print(result.stderr)

        # Cleanup
        os.remove("health_check.py")

    except Exception as e:
        print(f"Health check failed: {str(e)}")

    print("="*60)

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="LiteLLM Integration Test Runner"
    )
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "performance", "all"],
        default="all",
        help="Type of tests to run (default: all)"
    )
    parser.add_argument(
        "--no-health-check",
        action="store_true",
        help="Skip health check before running tests"
    )
    parser.add_argument(
        "--env-file",
        help="Path to .env file with test configuration"
    )

    args = parser.parse_args()

    # Load environment file if provided
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
        print(f"✅ Loaded environment from {args.env_file}")

    # Print header
    print("\n" + "="*60)
    print("LiteLLM Integration Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Check environment
    if not check_environment(args.type):
        print("Environment check failed. Exiting.")
        sys.exit(1)

    # Run health check
    if not args.no_health_check and args.type in ["integration", "performance", "all"]:
        run_health_check()

    # Get test arguments
    test_args = get_test_args(args.type)

    # Run tests
    print(f"\n🧪 Running {args.type} tests...")
    stats = run_tests(test_args)

    # Print results
    print_results(args.type, stats)

    # Exit with appropriate code
    if stats['exit_code'] != 0:
        sys.exit(1)

    # Print recommendations
    if args.type == "all":
        print("\n📊 Recommendations:")

        if stats['skipped'] > 0:
            print("  - Some tests were skipped. Check API key configuration.")

        if stats['duration'] > 60:
            print("  - Tests took longer than expected. Check network connectivity.")

        print("  - For production deployment:")
        print("    1. Set up Redis for caching")
        print("    2. Configure rate limiting")
        print("    3. Set up monitoring and alerts")
        print("    4. Test with real workloads")

if __name__ == "__main__":
    main()