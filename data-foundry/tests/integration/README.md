# Integration Tests for Consent Management System

This directory contains comprehensive integration tests for the GDPR-compliant consent management system. The test suite validates end-to-end functionality, GDPR compliance, security measures, and performance characteristics.

## Overview

The integration tests ensure all components of the consent management system work together correctly:

- **Consent Lifecycle Management**: Grant, verify, update, and withdraw consents
- **GDPR Compliance**: Articles 17 (right to erasure), 20 (data portability), and 21 (right to object)
- **API Endpoint Testing**: All REST endpoints with authentication and authorization
- **Database Integration**: Transaction integrity, data consistency, and performance
- **Audit Trail Completeness**: Verify all operations create immutable audit logs
- **Security Testing**: Input validation, XSS/SQL injection prevention, authentication bypass
- **Performance Testing**: Throughput, response times, and resource usage under load
- **Error Handling**: Recovery scenarios and graceful failure modes

## Test Structure

```
tests/integration/
├── README.md                           # This file
├── conftest.py                         # Test fixtures and configuration
├── test_config.yaml                    # Test configuration file
├── test_runner.py                      # Test runner utility
├── execute_integration_tests.sh        # Shell script to run tests
├── test_consent_management_complete.py # Main integration test suite
├── test_consent_api_endpoints.py       # API endpoint tests
└── test_performance_benchmarks.py      # Performance and load tests
```

## Prerequisites

### System Requirements

- Python 3.8 or higher
- PostgreSQL 13+ (for production-like testing)
- Redis 6+ (optional, for caching tests)
- At least 2GB RAM for performance tests

### Python Dependencies

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-html pytest-json-report pytest-timeout
pip install pytest-xdist  # For parallel test execution
pip install httpx  # For API testing
pip install psutil  # For performance monitoring
pip install pyyaml  # For configuration
pip install sqlmodel asyncpg redis  # Database dependencies
```

### Database Setup

For development testing with SQLite:
```bash
# No setup required - uses in-memory database
```

For production-like testing with PostgreSQL:
```bash
# Create test database
createdb test_consent_db

# Set environment variable
export DATABASE_URL="postgresql://user:password@localhost:5432/test_consent_db"
```

## Running Tests

### Quick Start

Run all integration tests with default settings:
```bash
./execute_integration_tests.sh
```

### Test Options

```bash
# Run specific test suite
./execute_integration_tests.sh -s integration
./execute_integration_tests.sh -s api
./execute_integration_tests.sh -s performance
./execute_integration_tests.sh -s security
./execute_integration_tests.sh -s gdpr

# Run in specific environment
./execute_integration_tests.sh -e staging
./execute_integration_tests.sh -e production

# Run tests in parallel
./execute_integration_tests.sh -p

# Generate coverage report
./execute_integration_tests.sh -c

# Verbose output
./execute_integration_tests.sh -v

# Dry run (show commands without executing)
./execute_integration_tests.sh -n
```

### Running Tests Directly with Pytest

```bash
# Run all integration tests
pytest tests/integration/ -v

# Run specific test file
pytest tests/integration/test_consent_api_endpoints.py -v

# Run with coverage
pytest tests/integration/ --cov=src --cov-report=html

# Run specific test class
pytest tests/integration/test_consent_management_complete.py::TestGDPRComplianceIntegration -v

# Run performance tests
pytest tests/integration/test_performance_benchmarks.py -m performance -v
```

## Test Configuration

Tests are configured via `test_config.yaml`. Key settings include:

- **Test Environments**: development, staging, production
- **Database Connections**: SQLite for development, PostgreSQL for staging/production
- **Test Timeouts**: Per-suite timeout configurations
- **Coverage Thresholds**: Minimum code coverage requirements
- **Performance Thresholds**: Response time and throughput limits

## Test Suites

### 1. Consent Lifecycle Tests (`test_consent_management_complete.py`)

Tests complete consent workflows:
- Grant consent with GDPR-compliant text validation
- Verify active consent status
- Withdraw consent with proper audit trail
- File objections under GDPR Article 21

Example:
```python
async def test_complete_consent_lifecycle(self, test_setup):
    # 1. Grant consent
    record = await consent_manager.record_consent(...)

    # 2. Verify consent
    is_active = await consent_manager.verify_consent(...)

    # 3. Withdraw consent
    withdrawn = await consent_manager.withdraw_consent(...)
```

### 2. GDPR Compliance Tests

Validates GDPR Articles:
- **Article 17**: Right to erasure with complete data deletion
- **Article 20**: Data portability with machine-readable exports
- **Article 21**: Right to object to processing

### 3. API Endpoint Tests (`test_consent_api_endpoints.py`)

Tests all REST endpoints:
- Authentication and authorization
- Request/response validation
- Error handling and HTTP status codes
- Rate limiting
- CORS headers

Example:
```python
def test_grant_consent_success(self, client, auth_headers):
    response = client.post("/consent/grant", json=request_data, headers=auth_headers)
    assert response.status_code == 200
```

### 4. Security Tests (`test_consent_management_complete.py::TestSecurityIntegration`)

Validates security measures:
- SQL injection prevention
- XSS prevention
- Input sanitization
- Authentication bypass attempts
- Authorization checks

### 5. Performance Tests (`test_performance_benchmarks.py`)

Benchmarks system performance:
- Consent creation throughput
- Database query performance with indexing
- Concurrent user handling
- Memory usage under load
- CPU usage sustainability

Example thresholds:
- P95 response time < 1 second
- At least 10 operations/second
- Memory increase < 500MB under load

### 6. Database Integration Tests

Validates database layer:
- Transaction integrity
- Data consistency after concurrent operations
- Index performance
- Backup and recovery procedures

## Test Reports

After running tests, reports are generated in `test_artifacts/`:

- **HTML Report**: `test_report.html` - Human-readable test results
- **Coverage Report**: `coverage/html/index.html` - Code coverage details
- **JSON Report**: `test_report.json` - Machine-readable results
- **JUnit XML**: `junit.xml` - CI/CD integration
- **Performance Metrics**: Performance benchmark results

## CI/CD Integration

### GitHub Actions

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov pytest-html
    - name: Run integration tests
      run: |
        export DATABASE_URL=postgresql://postgres:postgres@localhost:5433/test
        ./tests/integration/execute_integration_tests.sh -e staging
    - name: Upload test reports
      uses: actions/upload-artifact@v3
      if: always()
      with:
        name: test-reports
        path: test_artifacts/
```

### Jenkins Pipeline

```groovy
pipeline {
    agent any
    stages {
        stage('Setup') {
            steps {
                sh 'pip install -r requirements.txt'
                sh 'pip install pytest pytest-cov'
            }
        }
        stage('Integration Tests') {
            steps {
                sh '''
                    export DATABASE_URL=postgresql://test:test@localhost:5433/test_db
                    ./tests/integration/execute_integration_tests.sh -s all -c
                '''
            }
            post {
                always {
                    publishHTML([
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'test_artifacts',
                        reportFiles: 'index.html',
                        reportName: 'Integration Test Report'
                    ])
                }
            }
        }
    }
}
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Check PostgreSQL is running
   pg_isready -h localhost -p 5432

   # Create test database
   createdb test_consent_db
   ```

2. **Permission Errors**
   ```bash
   # Make test script executable
   chmod +x tests/integration/execute_integration_tests.sh
   ```

3. **Missing Dependencies**
   ```bash
   # Install all test dependencies
   pip install -r requirements-test.txt
   ```

4. **Test Timeouts**
   - Increase timeout in test_config.yaml
   - Check system resources (CPU, memory)
   - Run tests with fewer parallel workers

5. **Coverage Failures**
   - Check coverage threshold in config
   - Add tests for uncovered code paths
   - Exclude test files from coverage calculation

### Debug Mode

Run tests with extra debugging:
```bash
./execute_integration_tests.sh -v
export PYTEST_DEBUG=1
pytest tests/integration/ -s -vv --tb=long
```

## Contributing

When adding new integration tests:

1. Follow existing test patterns and naming conventions
2. Include proper setup and teardown in fixtures
3. Add documentation for test scenarios
4. Update test configuration if needed
5. Verify tests pass in all environments

Test naming convention:
```python
class TestFeatureName:
    async def test_specific_scenario(self, test_setup):
        # Arrange
        # Act
        # Assert
```

## Best Practices

1. **Use Fixtures**: Leverage fixtures for setup/teardown
2. **Isolate Tests**: Each test should be independent
3. **Mock External Services**: Avoid dependencies on external systems
4. **Clean Test Data**: Always cleanup created test data
5. **Test Edge Cases**: Validate error conditions and boundaries
6. **Document Tests**: Explain complex test scenarios
7. **Use Type Hints**: Improve test code readability

## Performance Benchmarks

Current performance targets (can be adjusted in test_config.yaml):

| Metric | Target |
|--------|--------|
| Consent Creation | > 10 ops/sec |
| Consent Verification | > 100 ops/sec |
| P95 Response Time | < 1 second |
| Memory Increase | < 500MB under load |
| CPU Usage | < 80% average under load |
| Test Coverage | > 80% |

## GDPR Compliance Checklist

The integration tests verify GDPR compliance:

- [ ] Consent is specific, informed, and unambiguous
- [ ] Consent can be withdrawn at any time
- [ ] Right to erasure (Article 17) is supported
- [ ] Data portability (Article 20) is implemented
- [ ] Right to object (Article 21) is available
- [ ] All operations create audit trails
- [ ] IP addresses are properly hashed/anonymized
- [ ] Data retention policies are enforced
- [ ] Cross-border data transfer rules are followed

## Support

For questions or issues with integration tests:

1. Check this README and test documentation
2. Review test logs in `test_artifacts/logs/`
3. Check GitHub issues for known problems
4. Create new issue with detailed error information

## License

These tests are part of the Data Foundry project and subject to the same license terms.