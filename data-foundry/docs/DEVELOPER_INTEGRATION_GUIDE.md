# Developer Integration Guide
## Building Privacy-First Applications with Data Foundry

**Version**: 1.0.0
**Date**: December 22, 2024
**SDK Version**: 1.0.0
**API Version**: v1.0.0

---

## Quick Start

### Installation

```bash
# Python
pip install datafoundry-sdk

# Node.js
npm install @datafoundry/api

# Java
mvn install:install-file -Dfile=datafoundry-sdk-1.0.0.jar

# .NET
dotnet add package DataFoundry.SDK
```

### Basic Setup

```python
# Python example
from datafoundry_sdk import DataFoundryClient, Config

# Initialize client
config = Config(
    client_id="your_client_id",
    client_secret="your_client_secret",
    base_url="https://api.datafoundry.com/v1"
)

client = DataFoundryClient(config)

# Test connection
health = await client.health.check()
print(f"API Status: {health.status}")
```

---

## Consent Management Integration

### Recording Consent

```python
# Recording new consent
from datafoundry_sdk.models import ConsentRequest

consent_request = ConsentRequest(
    user_id="user_123",
    consent_type="analytics_processing",
    consent_text=(
        "I consent to Data Foundry processing my usage data for analytics purposes, "
        "including page views, feature usage, and performance metrics. This data will "
        "be used to improve our services and will be stored for 365 days in encrypted form."
    ),
    metadata={
        "ip": "203.0.113.1",
        "user_agent": "Mozilla/5.0...",
        "timestamp": "2024-01-01T10:00:00Z",
        "data_categories": ["usage_metrics", "performance_data"],
        "retention_period": "365_days",
        "third_party_sharing": False
    }
)

# Record consent
consent = await client.consent.record(consent_request)
print(f"Consent recorded with ID: {consent.id}")
```

### Verifying Consent Before Processing

```python
# Consent verification middleware
from datafoundry_sdk.middleware import ConsentMiddleware

class DataProcessor:
    def __init__(self, consent_client):
        self.consent_client = consent_client
        self.middleware = ConsentMiddleware(consent_client)

    @middleware.require_consent("data_processing")
    async def process_user_data(self, user_id: str, data: dict):
        """Process user data with automatic consent verification"""
        # This code only executes if consent is valid
        result = await self.analyze_data(data)
        return result

    # Usage
    processor = DataProcessor(client.consent)
    result = await processor.process_user_data("user_123", user_data)
```

### Consent Withdrawal Handling

```python
# Automated consent withdrawal handler
class ConsentWithdrawalHandler:
    def __init__(self, client):
        self.client = client
        self.subscribers = []  # Systems to notify

    def subscribe(self, system_callback):
        """Subscribe to withdrawal notifications"""
        self.subscribers.append(system_callback)

    async def handle_withdrawal(self, user_id: str, consent_type: str):
        """Handle consent withdrawal"""
        # Notify all subscribers
        for callback in self.subscribers:
            await callback(user_id, consent_type)

        # Initiate data deletion
        await self.initiate_data_deletion(user_id, consent_type)

# Example subscriber
async def analytics_system_handler(user_id: str, consent_type: str):
    """Handle withdrawal in analytics system"""
    if consent_type == "analytics_processing":
        # Remove user from analytics
        await analytics.delete_user_data(user_id)
        # Add to suppression list
        await analytics.add_to_suppression(user_id)
```

---

## Data Subject Rights Implementation

### Right to Access

```python
# Data access implementation
class DataAccessService:
    def __init__(self, client):
        self.client = client
        self.data_collectors = {
            "profile": ProfileDataCollector(),
            "usage": UsageDataCollector(),
            "consents": ConsentDataCollector(),
            "communications": CommunicationDataCollector()
        }

    async def prepare_user_data_export(
        self,
        user_id: str,
        format: str = "json",
        include_inactive: bool = False
    ) -> DataExport:
        """Prepare complete data export for user"""
        export = DataExport(
            user_id=user_id,
            format=format,
            requested_at=datetime.now(timezone.utc)
        )

        # Collect all data categories
        for category, collector in self.data_collectors.items():
            data = await collector.collect(
                user_id,
                include_inactive=include_inactive
            )
            export.add_category_data(category, data)

        # Add processing logs
        processing_logs = await self.get_processing_history(user_id)
        export.add_processing_logs(processing_logs)

        # Generate download link
        download_url = await self.generate_secure_download(export)

        return DataExportResponse(
            export_id=export.id,
            download_url=download_url,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            data_summary=export.get_summary()
        )
```

### Right to Erasure

```python
# GDPR right to erasure implementation
class DataErasureService:
    def __init__(self, client):
        self.client = client
        self.legal_hold_checker = LegalHoldChecker()
        self.deletion_coordinator = DeletionCoordinator()

    async def process_deletion_request(
        self,
        user_id: str,
        retention_reasons: List[str] = None
    ) -> DeletionResult:
        """Process GDPR deletion request"""
        # Check for legal holds
        legal_holds = await self.legal_hold_checker.check_holds(
            user_id, retention_reasons
        )

        # Create deletion plan
        deletion_plan = await self.create_deletion_plan(
            user_id, legal_holds
        )

        # Execute deletion
        results = []
        for task in deletion_plan.tasks:
            result = await self.execute_deletion_task(task)
            results.append(result)

            if not result.success and task.is_critical:
                # Stop on critical failures
                break

        # Verify deletion
        verification = await self.verify_deletion(user_id, deletion_plan)

        return DeletionResult(
            user_id=user_id,
            tasks_executed=len(results),
            successful_tasks=len([r for r in results if r.success]),
            verification_passed=verification.success,
            retained_data=verification.retained_data,
            completion_time=datetime.now(timezone.utc)
        )
```

### Data Portability

```python
# Data portability implementation
class DataPortabilityService:
    def __init__(self, client):
        self.client = client
        self.formatters = {
            "json": JSONFormatter(),
            "csv": CSVFormatter(),
            "xml": XMLFormatter(),
            "pdf": PDFFormatter()
        }

    async def create_portable_export(
        self,
        user_id: str,
        format: str = "json",
        destination: TransferDestination = None
    ) -> PortableExport:
        """Create portable data export"""
        # Collect all user data
        user_data = await self.collect_all_user_data(user_id)

        # Format data
        formatter = self.formatters.get(format)
        if not formatter:
            raise ValueError(f"Unsupported format: {format}")

        formatted_data = await formatter.format(user_data)

        if destination and destination.type == "direct_transfer":
            # Direct transfer to another controller
            await self.execute_direct_transfer(
                data=formatted_data,
                destination=destination
            )
            return PortableExport(
                user_id=user_id,
                transfer_completed=True,
                destination=destination
            )
        else:
            # Create secure download
            download_info = await self.create_secure_download(
                data=formatted_data,
                expires_in=timedelta(hours=24)
            )
            return PortableExport(
                user_id=user_id,
                download_url=download_info.url,
                download_token=download_info.token,
                expires_at=download_info.expires_at
            )
```

---

## Security Integration

### Secure API Client

```python
# Secure client with automatic security features
from datafoundry_sdk.security import SecureAPIClient
from datafoundry_sdk.security.middleware import (
    RetryMiddleware,
    CircuitBreakerMiddleware,
    RateLimitMiddleware
)

# Create secure client with middleware
client = SecureAPIClient(
    client_id="your_client_id",
    client_secret="your_client_secret",
    middleware=[
        RateLimitMiddleware(),  # Automatic rate limiting
        RetryMiddleware(max_retries=3),  # Automatic retries
        CircuitBreakerMiddleware()  # Circuit breaker pattern
    ]
)

# Automatic token management
client.auth.enable_auto_refresh()
client.auth.enable_secure_storage()  # Stores tokens securely
```

### Encryption at Rest Integration

```python
# Client-side encryption for sensitive data
from datafoundry_sdk.security.encryption import ClientEncryption

class SecureDataProcessor:
    def __init__(self):
        self.encryption = ClientEncryption()

    async def process_sensitive_data(self, data: dict) -> dict:
        """Process data with client-side encryption"""
        # Encrypt sensitive fields before sending
        encrypted_data = {
            "public_info": data["public_info"],
            "private_info": await self.encryption.encrypt_field(
                data["private_info"]
            )
        }

        # Send to API
        response = await client.process_data(encrypted_data)
        return response
```

### Audit Logging Integration

```python
# Automatic audit logging
from datafoundry_sdk.audit import AuditLogger

class AuditedService:
    def __init__(self):
        self.audit = AuditLogger("my_service")

    @audit.log_action("data_access", include_request=True)
    async def access_user_data(self, user_id: str, purpose: str):
        """Access user data with automatic audit logging"""
        # Business logic
        data = await self.database.get_user_data(user_id)
        return data

    @audit.log_action("data_modification")
    async def update_user_data(
        self,
        user_id: str,
        updates: dict,
        updated_by: str
    ):
        """Update data with audit trail"""
        # Log before state
        before = await self.database.get_user_data(user_id)

        # Apply updates
        await self.database.update_user_data(user_id, updates)

        # Log after state
        after = await self.database.get_user_data(user_id)

        # Audit entry created automatically
        return {"before": before, "after": after}
```

---

## Error Handling and Best Practices

### Comprehensive Error Handling

```python
# Robust error handling
from datafoundry_sdk.errors import (
    APIError,
    ConsentError,
    RateLimitError,
    AuthenticationError
)

class ResilientDataProcessor:
    def __init__(self):
        self.client = DataFoundryClient(config)
        self.retry_config = RetryConfig(
            max_attempts=3,
            backoff_factor=2,
            retry_on=[RateLimitError, APIError]
        )

    async def process_with_retry(self, user_id: str, data: dict):
        """Process with automatic retry and error handling"""
        for attempt in range(self.retry_config.max_attempts):
            try:
                # Check consent first
                has_consent = await self.client.consent.verify(
                    user_id, "data_processing"
                )
                if not has_consent:
                    raise ConsentError("No valid consent found")

                # Process data
                result = await self.client.data.process(data)
                return result

            except RateLimitError as e:
                if attempt < self.retry_config.max_attempts - 1:
                    wait_time = self.retry_config.backoff_factor ** attempt
                    await asyncio.sleep(wait_time)
                    continue
                raise

            except ConsentError as e:
                # Don't retry consent errors
                self.logger.error(f"Consent error for {user_id}: {e}")
                raise

            except APIError as e:
                self.logger.warning(f"API error (attempt {attempt + 1}): {e}")
                if attempt == self.retry_config.max_attempts - 1:
                    raise
```

### GDPR Compliance Monitoring

```python
# Compliance monitoring
from datafoundry_sdk.compliance import ComplianceMonitor

class ComplianceAwareService:
    def __init__(self):
        self.monitor = ComplianceMonitor()
        self.compliance_metrics = ComplianceMetrics()

    async def monitor_data_processing(self, user_id: str, processing_type: str):
        """Monitor for compliance violations"""
        # Check processing against policies
        compliance_check = await self.monitor.check_processing(
            user_id=user_id,
            processing_type=processing_type,
            timestamp=datetime.now(timezone.utc)
        )

        if not compliance_check.compliant:
            # Log violation
            await self.monitor.log_violation(compliance_check.violation)

            # Take corrective action
            await self.handle_compliance_violation(compliance_check)

        # Update metrics
        self.compliance_metrics.record_processing(
            user_id=user_id,
            type=processing_type,
            compliant=compliance_check.compliant
        )
```

---

## Testing Your Integration

### Test Environment Setup

```python
# Test client configuration
from datafoundry_sdk.testing import TestClient

# Initialize test client
test_client = TestClient(
    base_url="https://api-test.datafoundry.com/v1",
    test_credentials="test_api_key"
)

# Mock responses for unit tests
@pytest.fixture
async def mock_consent_service():
    service = ConsentService(test_client)
    service.mock_responses({
        "verify_consent": {"has_consent": True},
        "record_consent": {"consent_id": "test_123"}
    })
    return service

# Integration test example
async def test_consent_flow():
    # Test consent recording
    consent = await test_client.consent.record({
        "user_id": "test_user",
        "consent_type": "test_processing",
        "consent_text": "Test consent text..."
    })
    assert consent.id is not None

    # Test consent verification
    verification = await test_client.consent.verify(
        "test_user", "test_processing"
    )
    assert verification.has_consent is True

    # Test consent withdrawal
    withdrawal = await test_client.consent.withdraw(
        "test_user", "test_processing"
    )
    assert withdrawal.success is True
```

### Performance Testing

```python
# Performance testing utilities
from datafoundry_sdk.testing import PerformanceTestRunner

async def benchmark_consent_verification():
    """Benchmark consent verification performance"""
    runner = PerformanceTestRunner()

    # Warm up
    await runner.warm_up(test_client.consent.verify)

    # Run benchmark
    results = await runner.run_benchmark(
        func=test_client.consent.verify,
        args=("user_123", "data_processing"),
        iterations=1000,
        concurrency=10
    )

    print(f"Average response time: {results.avg_response_time}ms")
    print(f"95th percentile: {results.p95_response_time}ms")
    print(f"Requests per second: {results.rps}")
```

### Security Testing

```python
# Security testing utilities
from datafoundry_sdk.testing import SecurityTests

async def run_security_tests():
    """Run API security tests"""
    security = SecurityTests(test_client)

    # Test for injection vulnerabilities
    injection_results = await security.test_sql_injection([
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "<script>alert('XSS')</script>"
    ])

    # Test for authentication bypass
    auth_results = await security.test_authentication_bypass()

    # Test rate limiting
    rate_limit_results = await security.test_rate_limits()

    return {
        "injection_tests": injection_results,
        "auth_tests": auth_results,
        "rate_limit_tests": rate_limit_results
    }
```

---

## Deployment and Operations

### Production Deployment Checklist

```python
# Production deployment validation
class ProductionValidator:
    def __init__(self, client):
        self.client = client
        self.checks = [
            self.check_api_connectivity,
            self.check_authentication,
            self.check_rate_limits,
            self.check_encryption,
            self.check_audit_logging
        ]

    async def validate_deployment(self) -> DeploymentReport:
        """Validate production deployment"""
        report = DeploymentReport()

        for check in self.checks:
            try:
                result = await check()
                report.add_check(check.__name__, result)
            except Exception as e:
                report.add_failure(check.__name__, str(e))

        return report

    async def check_api_connectivity(self):
        """Check API connectivity"""
        health = await self.client.health.check()
        return health.status == "healthy"

    async def check_authentication(self):
        """Check authentication flow"""
        token = await self.client.auth.get_token()
        return token is not None and not token.expired
```

### Monitoring and Alerting

```python
# Integration with monitoring systems
from datafoundry_sdk.monitoring import MetricsCollector, AlertManager

class ProductionMonitor:
    def __init__(self):
        self.metrics = MetricsCollector("datafoundry_integration")
        self.alerts = AlertManager()

    async def track_api_usage(self):
        """Track API usage metrics"""
        self.metrics.increment("api.requests")

        with self.metrics.timer("api.response_time"):
            response = await self.client.some_endpoint()

        if response.status_code != 200:
            self.metrics.increment("api.errors")
            await self.alerts.send_alert(
                level="warning",
                message=f"API error: {response.status_code}"
            )

    async def monitor_consent_health(self):
        """Monitor consent system health"""
        try:
            # Test consent verification
            result = await self.client.consent.verify("health_check_user", "test")
            self.metrics.gauge("consent.system_health", 1)
        except Exception as e:
            self.metrics.gauge("consent.system_health", 0)
            await self.alerts.send_alert(
                level="critical",
                message=f"Consent system error: {str(e)}"
            )
```

---

## SDK Reference

### Python SDK

```python
# Core classes
from datafoundry_sdk import (
    DataFoundryClient,      # Main client
    Config,                # Configuration
    ConsentRequest,        # Consent data model
    DataExportRequest,     # Data export request
    IncidentReport,        # Incident report
    SecurityConfig         # Security configuration
)

# Services
from datafoundry_sdk.services import (
    ConsentService,        # Consent management
    DataSubjectService,    # Data subject rights
    IncidentService,       # Incident management
    AuditService,         # Audit logging
    SecurityService       # Security features
)

# Utilities
from datafoundry_sdk.utils import (
    TokenManager,         # JWT token management
    RateLimiter,         # Rate limiting
    RetryHandler,        # Retry logic
    SecureStorage        # Secure credential storage
)
```

### Configuration Options

```python
config = Config(
    # Required
    client_id="your_client_id",
    client_secret="your_client_secret",

    # Optional
    base_url="https://api.datafoundry.com/v1",
    timeout=30,  # seconds
    max_retries=3,
    retry_backoff=2,  # seconds

    # Security
    enable_tls=True,
    verify_ssl=True,
    token_encryption_key="your_encryption_key",

    # Performance
    connection_pool_size=10,
    max_concurrent_requests=100,

    # Monitoring
    enable_metrics=True,
    metrics_endpoint="https://metrics.datafoundry.com",

    # Compliance
    auto_consent_check=True,
    audit_logging=True,
    data_minimization=True
)
```

---

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   ```python
   # Debug authentication
   try:
       token = await client.auth.get_token()
       print(f"Token expires: {token.expires_at}")
   except AuthenticationError as e:
       print(f"Auth failed: {e.details}")
   ```

2. **Consent Verification Issues**
   ```python
   # Debug consent
   consent_status = await client.consent.get_status("user_123")
   print(f"Active consents: {consent_status.active}")
   print(f"Expired consents: {consent_status.expired}")
   ```

3. **Rate Limit Handling**
   ```python
   # Handle rate limits gracefully
   try:
       response = await client.make_request()
   except RateLimitError as e:
       print(f"Rate limited. Retry after: {e.retry_after} seconds")
   ```

### Debug Mode

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable SDK debug mode
client = DataFoundryClient(config)
client.set_debug_mode(True)

# View request/response details
client.add_request_logger(lambda req: print(f"Request: {req}"))
client.add_response_logger(lambda resp: print(f"Response: {resp}"))
```

### Support Resources

- **Documentation**: https://docs.datafoundry.com/sdk
- **API Reference**: https://api.datafoundry.com/docs
- **Examples**: https://github.com/datafoundry/sdk-examples
- **Community**: https://community.datafoundry.com
- **Support**: sdk-support@datafoundry.com

---

**Document Version**: 1.0.0
**SDK Version**: 1.0.0
**Last Updated**: December 22, 2024

This guide is maintained in accordance with our developer documentation standards and is updated regularly to reflect new features and best practices.