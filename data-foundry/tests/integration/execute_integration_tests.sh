#!/bin/bash
# Integration Test Execution Script
# Executes comprehensive integration tests for the consent management system

set -e  # Exit on error
set -o pipefail  # Exit if any command in pipeline fails

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_CONFIG="$SCRIPT_DIR/test_config.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="development"
TEST_SUITE="all"
PARALLEL=false
COVERAGE=true
GENERATE_REPORTS=true
VERBOSE=false
DRY_RUN=false

# Test artifacts directory
ARTIFACTS_DIR="$PROJECT_ROOT/test_artifacts"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="$ARTIFACTS_DIR/integration_test_$TIMESTAMP"

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] ${message}${NC}"
}

# Function to show usage
show_usage() {
    cat << EOF
Integration Test Execution Script

Usage: $0 [OPTIONS]

OPTIONS:
    -e, --environment ENV    Test environment (development|staging|production) [default: development]
    -s, --suite SUITE        Test suite to run (unit|integration|api|performance|security|gdpr|all) [default: all]
    -p, --parallel          Run tests in parallel
    -c, --coverage          Generate coverage report [default: true]
    -r, --reports           Generate test reports [default: true]
    -v, --verbose           Verbose output
    -n, --dry-run           Show commands without executing
    -h, --help              Show this help message

EXAMPLES:
    # Run all integration tests
    $0

    # Run only API tests in staging environment
    $0 -e staging -s api

    # Run performance tests with coverage and parallel execution
    $0 -s performance -p -c

    # Dry run to see what would be executed
    $0 -n
EOF
}

# Function to parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -s|--suite)
                TEST_SUITE="$2"
                shift 2
                ;;
            -p|--parallel)
                PARALLEL=true
                shift
                ;;
            -c|--coverage)
                COVERAGE=true
                shift
                ;;
            --no-coverage)
                COVERAGE=false
                shift
                ;;
            -r|--reports)
                GENERATE_REPORTS=true
                shift
                ;;
            --no-reports)
                GENERATE_REPORTS=false
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                print_status $RED "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Function to validate environment
validate_environment() {
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_status $RED "Python 3 is required but not installed"
        exit 1
    fi

    # Check if pytest is available
    if ! python3 -m pytest --version &> /dev/null; then
        print_status $RED "pytest is required but not installed"
        print_status $YELLOW "Install with: pip install pytest pytest-asyncio pytest-cov pytest-html pytest-json-report pytest-timeout"
        exit 1
    fi

    # Check if test config exists
    if [[ ! -f "$TEST_CONFIG" ]]; then
        print_status $RED "Test configuration file not found: $TEST_CONFIG"
        exit 1
    fi

    # Validate environment parameter
    if [[ ! "$ENVIRONMENT" =~ ^(development|staging|production)$ ]]; then
        print_status $RED "Invalid environment: $ENVIRONMENT"
        print_status $YELLOW "Valid environments: development, staging, production"
        exit 1
    fi

    print_status $GREEN "Environment validation passed"
}

# Function to setup test environment
setup_environment() {
    print_status $BLUE "Setting up test environment..."

    # Create artifacts directory
    mkdir -p "$REPORT_DIR"
    mkdir -p "$REPORT_DIR/logs"
    mkdir -p "$REPORT_DIR/coverage"
    mkdir -p "$REPORT_DIR/reports"

    # Export environment variables
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    export TEST_ENVIRONMENT="$ENVIRONMENT"
    export TEST_ARTIFACTS_DIR="$REPORT_DIR"
    export IP_HASH_SALT="test_salt_for_integration_tests_32_characters_minimum"
    export JWT_SECRET="test_jwt_secret_for_integration_32_characters_minimum"

    # Set database URL based on environment
    case $ENVIRONMENT in
        development)
            export DATABASE_URL="sqlite:///$REPORT_DIR/test.db"
            export REDIS_URL="redis://localhost:6379/0"
            ;;
        staging)
            export DATABASE_URL="postgresql://postgres:postgres@localhost:5433/test_staging"
            export REDIS_URL="redis://localhost:6380/1"
            ;;
        production)
            # Use environment variables for production
            export DATABASE_URL="${DATABASE_URL:-$PROD_DB_URL}"
            export REDIS_URL="${REDIS_URL:-$PROD_REDIS_URL}"
            ;;
    esac

    print_status $GREEN "Test environment setup complete"
}

# Function to run tests
run_tests() {
    local test_path=""
    local test_markers=""
    local timeout="1800"
    local extra_args=""

    # Determine test path and markers based on suite
    case $TEST_SUITE in
        unit)
            test_path="tests/unit"
            test_markers="unit"
            timeout="300"
            ;;
        integration)
            test_path="tests/integration/test_consent_management_complete.py"
            test_markers="integration"
            timeout="1800"
            ;;
        api)
            test_path="tests/integration/test_consent_api_endpoints.py"
            test_markers="api"
            timeout="900"
            ;;
        performance)
            test_path="tests/integration/test_performance_benchmarks.py"
            test_markers="performance or slow"
            timeout="3600"
            ;;
        security)
            test_path="tests/integration/test_consent_management_complete.py::TestSecurityIntegration"
            test_markers="security"
            timeout="900"
            ;;
        gdpr)
            test_path="tests/integration/test_consent_management_complete.py::TestGDPRComplianceIntegration"
            test_markers="gdpr or compliance"
            timeout="600"
            ;;
        all)
            test_path="tests/integration"
            test_markers="integration or api or security or gdpr"
            timeout="3600"
            ;;
        *)
            print_status $RED "Unknown test suite: $TEST_SUITE"
            exit 1
            ;;
    esac

    # Build pytest command
    local cmd=("python3" "-m" "pytest")
    cmd+=("$test_path")
    cmd+=("-v")
    cmd+=("--tb=short")
    cmd+=("--timeout=$timeout")

    # Add markers
    if [[ -n "$test_markers" ]]; then
        cmd+=("-m" "$test_markers")
    fi

    # Add parallel execution if requested
    if [[ "$PARALLEL" == "true" ]]; then
        cmd+=("-n" "auto")
    fi

    # Add coverage if requested
    if [[ "$COVERAGE" == "true" ]]; then
        cmd+=("--cov=src")
        cmd+=("--cov-report=html:$REPORT_DIR/coverage/html")
        cmd+=("--cov-report=xml:$REPORT_DIR/coverage/coverage.xml")
        cmd+=("--cov-report=term-missing")
        cmd+=("--cov-fail-under=80")
    fi

    # Add HTML report if requested
    if [[ "$GENERATE_REPORTS" == "true" ]]; then
        cmd+=("--html=$REPORT_DIR/reports/test_report.html")
        cmd+=("--self-contained-html")
        cmd+=("--json-report-file=$REPORT_DIR/reports/test_report.json")
        cmd+=("--junitxml=$REPORT_DIR/reports/junit.xml")
    fi

    # Add verbose flag
    if [[ "$VERBOSE" == "true" ]]; then
        cmd+=("-vv")
        cmd+=("--showlocals")
    fi

    # Add logging
    cmd+=("--log-level=INFO")
    cmd+=("--log-cli-level=INFO")
    cmd+=("--log-file=$REPORT_DIR/logs/test.log")

    # Print command if dry run
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status $YELLOW "Dry run - command that would be executed:"
        echo "${cmd[*]}"
        exit 0
    fi

    # Execute tests
    print_status $BLUE "Running tests..."
    print_status $BLUE "Command: ${cmd[*]}"

    local start_time=$(date +%s)
    local test_log="$REPORT_DIR/logs/test_execution.log"

    # Run tests and capture output
    if "${cmd[@]}" 2>&1 | tee "$test_log"; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_status $GREEN "Tests completed successfully in ${duration}s"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        print_status $RED "Tests failed after ${duration}s"
        return 1
    fi
}

# Function to post-process results
post_process_results() {
    print_status $BLUE "Post-processing test results..."

    # Generate summary report
    python3 "$SCRIPT_DIR/test_runner.py" \
        --environment "$ENVIRONMENT" \
        --suite "$TEST_SUITE" \
        2>&1 | tee "$REPORT_DIR/test_summary.log"

    # Check for any failed tests and create failure summary
    local failed_tests=0
    if [[ -f "$REPORT_DIR/reports/junit.xml" ]]; then
        failed_tests=$(grep -o 'failures="[0-9]*"' "$REPORT_DIR/reports/junit.xml" | grep -o '[0-9]*' || echo "0")
    fi

    # Create test badge if passed
    if [[ $failed_tests -eq 0 ]]; then
        # Create simple success badge
        cat > "$REPORT_DIR/test_badge.svg" << EOF
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20">
    <rect width="100" height="20" fill="#4c1"/>
    <text x="50" y="14" text-anchor="middle" fill="white" font-family="Arial" font-size="12">Tests Pass</text>
</svg>
EOF
    fi

    # Create results index
    cat > "$REPORT_DIR/index.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>Integration Test Results</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #f5f5f5; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; }
        .link { display: inline-block; margin: 5px; padding: 10px; background-color: #e9ecef; text-decoration: none; border-radius: 3px; }
        .status { font-weight: bold; padding: 5px; border-radius: 3px; }
        .pass { background-color: #d4edda; color: #155724; }
        .fail { background-color: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Integration Test Results</h1>
        <p>Environment: $ENVIRONMENT</p>
        <p>Suite: $TEST_SUITE</p>
        <p>Timestamp: $TIMESTAMP</p>
        <p class="status $([ $failed_tests -eq 0 ] && echo pass || echo fail)">
            Status: $([ $failed_tests -eq 0 ] && echo PASSED || echo FAILED) ($failed_tests failures)
        </p>
    </div>

    <div class="section">
        <h2>Reports</h2>
        <a class="link" href="reports/test_report.html">HTML Report</a>
        <a class="link" href="reports/test_report.json">JSON Report</a>
        <a class="link" href="reports/junit.xml">JUnit XML</a>
    </div>

    <div class="section">
        <h2>Coverage</h2>
        <a class="link" href="coverage/html/index.html">Coverage Report</a>
    </div>

    <div class="section">
        <h2>Logs</h2>
        <a class="link" href="logs/test.log">Test Log</a>
        <a class="link" href="logs/test_execution.log">Execution Log</a>
    </div>
</body>
</html>
EOF

    print_status $GREEN "Post-processing complete"
}

# Function to cleanup
cleanup() {
    if [[ $? -eq 0 ]]; then
        print_status $GREEN "All tests completed successfully!"
        print_status $BLUE "Results available at: $REPORT_DIR/index.html"
    else
        print_status $RED "Some tests failed!"
        print_status $BLUE "Check logs at: $REPORT_DIR/logs/"
    fi

    # Cleanup old test artifacts (keep last 5)
    find "$ARTIFACTS_DIR" -maxdepth 1 -type d -name "integration_test_*" \
        | sort -r \
        | tail -n +6 \
        | xargs -r rm -rf
}

# Main execution
main() {
    # Print banner
    print_status $BLUE "=========================================="
    print_status $BLUE "  Integration Test Execution Script"
    print_status $BLUE "=========================================="
    print_status $BLUE "Environment: $ENVIRONMENT"
    print_status $BLUE "Test Suite: $TEST_SUITE"
    print_status $BLUE "Parallel: $PARALLEL"
    print_status $BLUE "Coverage: $COVERAGE"
    print_status $BLUE "Reports: $GENERATE_REPORTS"
    print_status $BLUE "=========================================="

    # Parse command line arguments
    parse_args "$@"

    # Validate environment
    validate_environment

    # Setup test environment
    setup_environment

    # Run tests
    if run_tests; then
        TEST_SUCCESS=true
    else
        TEST_SUCCESS=false
    fi

    # Post-process results
    if [[ "$GENERATE_REPORTS" == "true" ]]; then
        post_process_results
    fi

    # Cleanup and exit
    if [[ "$TEST_SUCCESS" == "true" ]]; then
        cleanup 0
    else
        cleanup 1
    fi
}

# Trap to ensure cleanup runs
trap cleanup EXIT

# Run main function
main "$@"