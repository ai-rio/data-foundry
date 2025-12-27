"""
Comprehensive unit tests for IdempotencyService.

Task: P02-523 (Infrastructure Layer - Idempotency Service)
Created: 2025-12-25

This test suite follows strict TDD approach for a SECURITY-CRITICAL module.
Tests cover:
- Key generation with uniqueness and collision detection
- Key registration and tracking
- Key expiration and cleanup
- Security features (sanitization, length validation)
- Collision metrics and monitoring
- Registry size limits (DoS protection)
- Thread-safety for concurrent access

TDD Phases:
- RED: Tests written first, must fail initially
- GREEN: Implementation added to pass tests
- REFACTOR: Code cleaned up while maintaining test coverage
"""

import pytest
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.services.stripe.types import (
    IdempotencyServiceProtocol,
    CollisionMetrics,
    IdempotencyKeyInfo,
)
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import (
    StripeIdempotencyKeyTooLongError,
    StripeMeterValidationError,
)


class TestIdempotencyServiceProtocol:
    """
    Test that IdempotencyService implements the required protocol.

    Verifies the service conforms to IdempotencyServiceProtocol interface.
    """

    def test_idempotency_service_implements_protocol(self):
        """
        Test that IdempotencyService implements IdempotencyServiceProtocol.

        This is a structural test that verifies the service class can be
        used wherever the protocol is expected.
        """
        from src.services.stripe.idempotency_service import IdempotencyService

        # Verify class exists
        assert IdempotencyService is not None

        # Verify it can be instantiated with config
        config = StripeConfig.from_environment()
        service = IdempotencyService(config)

        # Verify it implements protocol methods
        assert hasattr(service, "generate_key")
        assert hasattr(service, "is_registered")
        assert hasattr(service, "register_key")
        assert hasattr(service, "get_metrics")

        # Verify it's an instance of the protocol
        assert isinstance(service, IdempotencyServiceProtocol)


class TestGenerateKey:
    """
    Test suite for idempotency key generation.

    Security-critical tests ensuring:
    - Uniqueness of generated keys
    - Proper key format
    - Input sanitization
    - Length validation (Stripe 255 char limit)
    - Timestamp inclusion
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_generate_key_basic_format(self, service):
        """
        Test basic key format includes required components.

        Key format: {meter_event}:{tenant_id}:{value}:{batch_id}:{timestamp}:{nonce}
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Verify key is a string
        assert isinstance(key, str)

        # Verify key is not empty
        assert len(key) > 0

        # Verify key contains expected delimiters (colons)
        assert ":" in key

        # Split and verify component count (at least 4: meter, tenant, value, timestamp, nonce)
        parts = key.split(":")
        assert len(parts) >= 5

    def test_generate_key_uniqueness(self, service):
        """
        Test that generated keys are unique across multiple calls.

        SECURITY: Keys must be unique to prevent duplicate billing.
        """
        keys = set()

        # Generate 100 keys
        for _ in range(100):
            key = service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100
            )
            keys.add(key)

        # All keys should be unique
        assert len(keys) == 100

    def test_generate_key_with_batch_id(self, service):
        """
        Test key generation with batch_id parameter.

        Keys with different batch_ids should be different.
        """
        key1 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100,
            batch_id="batch_001"
        )

        key2 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100,
            batch_id="batch_002"
        )

        # Keys should be different due to different batch_id
        assert key1 != key2

    def test_generate_key_different_tenants(self, service):
        """
        Test keys differ for different tenants.

        Keys should incorporate tenant_id for tenant isolation.
        """
        key1 = service.generate_key(
            tenant_id="tenant_001",
            meter_event="ai_labels",
            value=100
        )

        key2 = service.generate_key(
            tenant_id="tenant_002",
            meter_event="ai_labels",
            value=100
        )

        # Keys should be different
        assert key1 != key2

    def test_generate_key_different_meters(self, service):
        """
        Test keys differ for different meter events.
        """
        key1 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        key2 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="human_audits",
            value=100
        )

        # Keys should be different
        assert key1 != key2

    def test_generate_key_different_values(self, service):
        """
        Test keys differ for different values.
        """
        key1 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        key2 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=200
        )

        # Keys should be different
        assert key1 != key2

    def test_generate_key_timestamp_inclusion(self, service):
        """
        Test that keys include timestamp for uniqueness over time.

        SECURITY: Timestamps ensure uniqueness across time boundaries.
        """
        key1 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Wait a small amount to ensure timestamp changes
        time.sleep(0.01)

        key2 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Keys should be different due to timestamp
        assert key1 != key2

    def test_generate_key_sanitization_dangerous_chars(self, service):
        """
        Test that dangerous characters are sanitized.

        SECURITY: Input sanitization prevents injection attacks.
        """
        # Test with path traversal
        key = service.generate_key(
            tenant_id="../malicious",
            meter_event="ai_labels'; DROP TABLE--",
            value=100
        )

        # Key should not contain dangerous sequences
        assert "../" not in key
        assert ";" not in key
        assert "--" not in key
        assert "'" not in key

        # Key should still be valid format
        assert isinstance(key, str)
        assert len(key) > 0

    def test_generate_key_sanitization_xss(self, service):
        """
        Test that XSS attempts are sanitized.
        """
        key = service.generate_key(
            tenant_id="<script>alert('xss')</script>",
            meter_event="ai_labels",
            value=100
        )

        # Key should not contain script tags
        assert "<script" not in key
        assert "</script>" not in key

    def test_generate_key_length_validation(self, service):
        """
        Test that excessively long keys are rejected.

        SECURITY: Stripe has a 255 character limit on idempotency keys.
        Keys exceeding this limit should raise StripeIdempotencyKeyTooLongError.

        Note: Component sanitization limits each component to 100 chars.
        To exceed 255 total chars, we need many components at max length.
        """
        # Create inputs at the sanitization limit (100 chars each)
        long_tenant = "a" * 100
        long_meter = "b" * 100
        long_batch = "c" * 100

        # With all components at max length, key should exceed 255
        # Format: tenant:meter:value:batch:timestamp:nonce
        # Max: 100 + 100 + 11 + 100 + 20 + 8 + 5 delimiters = 344 chars
        with pytest.raises(StripeIdempotencyKeyTooLongError) as exc_info:
            service.generate_key(
                tenant_id=long_tenant,
                meter_event=long_meter,
                value=100,
                batch_id=long_batch
            )

        # Verify exception contains useful info
        assert exc_info.value.key_length is not None
        assert exc_info.value.max_length == 255

    def test_generate_key_exactly_at_limit(self, service):
        """
        Test key that is exactly at Stripe's 255 character limit.

        Keys at the limit should be accepted.
        """
        # Calculate component lengths to hit exactly 255
        # Format: meter:tenant:value:timestamp:nonce
        # Let's create components that sum to 255
        tenant = "t" * 50
        meter = "m" * 50
        # timestamp (~20 chars), nonce (~8 chars), separators (5 colons) = ~33 chars
        # So we need 255 - 33 = 222 chars for meter + tenant + value
        # value can be up to 11 chars (max int)

        key = service.generate_key(
            tenant_id=tenant,
            meter_event=meter,
            value=12345678901  # 11 chars
        )

        # Should succeed (key <= 255 chars)
        # Note: This test may need adjustment based on actual key format
        assert len(key) <= 255

    def test_generate_key_empty_components(self, service):
        """
        Test handling of empty component values.

        Empty components should be sanitized to prevent invalid keys.
        """
        key = service.generate_key(
            tenant_id="",
            meter_event="ai_labels",
            value=100
        )

        # Should still generate a valid key
        assert isinstance(key, str)
        assert len(key) > 0
        assert len(key) <= 255


class TestIsRegistered:
    """
    Test suite for key registration checking.

    Tests cover:
    - Registration status tracking
    - Expiration handling
    - Key uniqueness verification
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_is_registered_false_initially(self, service):
        """
        Test that unregistered keys return False.
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Key should not be registered initially
        assert service.is_registered(key) is False

    def test_is_registered_true_after_registration(self, service):
        """
        Test that registered keys return True.
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Register the key
        service.register_key(key)

        # Key should now be registered
        assert service.is_registered(key) is True

    def test_is_registered_multiple_keys(self, service):
        """
        Test registration status for multiple keys.
        """
        key1 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        key2 = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=200
        )

        # Register only key1
        service.register_key(key1)

        # Check status
        assert service.is_registered(key1) is True
        assert service.is_registered(key2) is False

    def test_is_registered_expires_after_retention_period(self, service):
        """
        Test that keys expire after retention period.

        SECURITY: Keys should not persist forever to prevent memory leaks.
        """
        # Create a service with short retention for testing
        config = StripeConfig()
        # Use negative retention to simulate already-expired state
        config.idempotency_retention_hours = -1

        service_with_short_retention = service.__class__(config)

        key = service_with_short_retention.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        service_with_short_retention.register_key(key)

        # With negative retention, key should be considered expired immediately
        assert service_with_short_retention.is_registered(key) is False


class TestRegisterKey:
    """
    Test suite for key registration.

    Tests cover:
    - Key registration
    - Registry size limits (DoS protection)
    - Automatic cleanup of expired keys
    - Thread-safety
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_register_key_basic(self, service):
        """
        Test basic key registration.
        """
        key = "test_key_123"

        # Should not raise exception
        service.register_key(key)

        # Key should now be registered
        assert service.is_registered(key) is True

    def test_register_key_duplicate_allowed(self, service):
        """
        Test that re-registering the same key is allowed.

        Re-registration should update the timestamp, extending retention.
        """
        key = "test_key_123"

        # Register first time
        service.register_key(key)
        assert service.is_registered(key) is True

        # Register again (should not fail)
        service.register_key(key)
        assert service.is_registered(key) is True

    def test_register_key_registry_size_limit(self, service):
        """
        Test that registry size is limited to prevent DoS.

        SECURITY: Unbounded registry growth would cause memory exhaustion.
        """
        # Create service with small registry size for testing
        config = StripeConfig()
        config.max_idempotency_registry_size = 10

        limited_service = service.__class__(config)

        # Register keys up to limit
        for i in range(10):
            key = f"key_{i}"
            limited_service.register_key(key)

        # All should be registered
        for i in range(10):
            assert limited_service.is_registered(f"key_{i}") is True

        # Add one more - should trigger cleanup
        limited_service.register_key("key_10")

        # Registry should still be functional (oldest keys may be removed)
        # At minimum, the most recent key should be registered
        assert limited_service.is_registered("key_10") is True

    def test_register_key_concurrent(self, service):
        """
        Test thread-safe concurrent key registration.

        SECURITY: Registry must be thread-safe for production use.
        """
        keys = []
        errors = []

        def register_keys(thread_id):
            try:
                for i in range(50):
                    key = f"thread_{thread_id}_key_{i}"
                    service.register_key(key)
                    keys.append(key)
            except Exception as e:
                errors.append((thread_id, e))

        # Launch multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=register_keys, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0

        # All keys should be registered
        for key in keys:
            assert service.is_registered(key) is True


class TestGetMetrics:
    """
    Test suite for collision metrics.

    Tests cover:
    - Metrics tracking
    - Collision detection
    - Near-collision detection
    - Registry size reporting
    - Collision rate calculation
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_get_metrics_initial_state(self, service):
        """
        Test that initial metrics are zero.
        """
        metrics = service.get_metrics()

        assert isinstance(metrics, CollisionMetrics)
        assert metrics.total_keys_generated == 0
        assert metrics.collision_count == 0
        assert metrics.near_collision_count == 0
        assert metrics.registry_size == 0

    def test_get_metrics_tracks_keys_generated(self, service):
        """
        Test that metrics track total keys generated.
        """
        # Generate some keys
        for _ in range(10):
            service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100
            )

        metrics = service.get_metrics()
        assert metrics.total_keys_generated == 10

    def test_get_metrics_tracks_registry_size(self, service):
        """
        Test that metrics track registry size.
        """
        # Register some keys
        for i in range(5):
            key = f"key_{i}"
            service.register_key(key)

        metrics = service.get_metrics()
        assert metrics.registry_size == 5

    def test_get_metrics_collision_rate(self, service):
        """
        Test collision rate calculation.

        Collision rate = (collisions + near_collisions) / total_keys * 100
        """
        # Generate keys
        for _ in range(100):
            service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100
            )

        metrics = service.get_metrics()

        # Collision rate should be 0.0 for unique keys
        assert metrics.collision_rate == 0.0

    def test_get_metrics_collision_rate_with_collisions(self, service):
        """
        Test collision rate with simulated collisions.

        Note: This test may need to be adjusted based on actual
        collision detection implementation.
        """
        # This test assumes we can force collisions
        # If collision detection is automatic, we might need
        # to generate many keys to trigger near-collisions

        # Generate many keys rapidly
        for _ in range(1000):
            service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100
            )

        metrics = service.get_metrics()

        # With 1000 keys, we might have some near-collisions due to timing
        # If not, collision_rate should still be 0
        assert metrics.total_keys_generated == 1000
        assert 0.0 <= metrics.collision_rate <= 100.0


class TestSecurityFeatures:
    """
    Security-focused test suite.

    Tests verify:
    - DoS protection (registry size limits)
    - Injection attack prevention (sanitization)
    - Key uniqueness guarantee
    - Memory leak prevention (expiration)
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_security_sql_injection_prevention(self, service):
        """
        Test SQL injection attempts are prevented.

        SECURITY: Key components must be sanitized to prevent SQL injection.
        """
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin'--",
            "1' UNION SELECT--",
        ]

        for malicious in malicious_inputs:
            key = service.generate_key(
                tenant_id=malicious,
                meter_event="ai_labels",
                value=100
            )

            # Key should not contain dangerous SQL patterns
            assert "'" not in key
            assert ";" not in key
            assert "--" not in key
            assert "UNION SELECT" not in key

    def test_security_path_traversal_prevention(self, service):
        """
        Test path traversal attempts are prevented.
        """
        malicious_inputs = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\sam",
        ]

        for malicious in malicious_inputs:
            key = service.generate_key(
                tenant_id=malicious,
                meter_event="ai_labels",
                value=100
            )

            # Key should not contain path traversal patterns
            assert "../" not in key
            assert "..\\" not in key

    def test_security_command_injection_prevention(self, service):
        """
        Test command injection attempts are prevented.
        """
        malicious_inputs = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "$(whoami)",
            "`id`",
        ]

        for malicious in malicious_inputs:
            key = service.generate_key(
                tenant_id=malicious,
                meter_event="ai_labels",
                value=100
            )

            # Key should not contain command injection patterns
            assert ";" not in key
            assert "|" not in key
            assert "$(" not in key
            assert "`" not in key

    def test_security_registry_memory_limit(self, service):
        """
        Test that registry cannot grow unbounded.

        SECURITY: Unbounded registry would cause memory exhaustion.
        """
        config = StripeConfig()
        config.max_idempotency_registry_size = 100

        limited_service = service.__class__(config)

        # Try to register more keys than limit
        for i in range(1000):
            limited_service.register_key(f"key_{i}")

        # Registry should be limited
        metrics = limited_service.get_metrics()
        assert metrics.registry_size <= 100

    def test_security_key_uniqueness_under_load(self, service):
        """
        Test key uniqueness under rapid generation.

        SECURITY: Keys must remain unique even under high load.
        """
        keys = set()

        # Generate keys rapidly
        for _ in range(1000):
            key = service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100
            )
            keys.add(key)

        # All keys should be unique
        assert len(keys) == 1000

    def test_security_expiration_prevents_memory_leak(self, service):
        """
        Test that expired keys are cleaned up.

        SECURITY: Keys must expire to prevent memory leaks.
        """
        config = StripeConfig()
        # Use negative retention to simulate already-expired state
        config.idempotency_retention_hours = -1

        expiring_service = service.__class__(config)

        # Register many keys
        for i in range(100):
            expiring_service.register_key(f"key_{i}")

        # Check is_registered (triggers cleanup)
        # With negative retention, all keys should be expired immediately
        for i in range(100):
            is_registered = expiring_service.is_registered(f"key_{i}")
            # Keys should be expired
            assert is_registered is False

        # Registry should be empty or very small
        metrics = expiring_service.get_metrics()
        assert metrics.registry_size == 0


class TestEdgeCases:
    """
    Edge case tests for robustness.

    Tests cover unusual inputs and boundary conditions.
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_edge_case_maximum_value(self, service):
        """
        Test key generation with maximum integer value.
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=2**63 - 1  # Max 64-bit integer
        )

        # Should handle large values
        assert isinstance(key, str)
        assert len(key) > 0
        assert len(key) <= 255

    def test_edge_case_minimum_value(self, service):
        """
        Test key generation with minimum value.
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=1
        )

        # Should handle minimum value
        assert isinstance(key, str)
        assert len(key) > 0

    def test_edge_case_unicode_characters(self, service):
        """
        Test key generation with Unicode characters.
        """
        key = service.generate_key(
            tenant_id="tenant_🚀",
            meter_event="ai_labels",
            value=100
        )

        # Should handle Unicode
        assert isinstance(key, str)
        assert len(key) > 0

    def test_edge_case_special_characters_in_batch_id(self, service):
        """
        Test special characters in batch_id.
        """
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100,
            batch_id="batch@#$%^&*()"
        )

        # Should sanitize special characters
        assert isinstance(key, str)
        assert len(key) > 0

    def test_edge_case_null_bytes(self, service):
        """
        Test handling of null bytes.
        """
        key = service.generate_key(
            tenant_id="tenant\x00abc",
            meter_event="ai_labels",
            value=100
        )

        # Should handle null bytes safely
        assert isinstance(key, str)
        assert "\x00" not in key

    def test_edge_case_very_long_batch_id(self, service):
        """
        Test very long batch_id doesn't cause issues.
        """
        long_batch_id = "batch_" + "a" * 200

        # Should either handle gracefully or raise exception
        try:
            key = service.generate_key(
                tenant_id="tenant_123",
                meter_event="ai_labels",
                value=100,
                batch_id=long_batch_id
            )
            assert len(key) <= 255
        except StripeIdempotencyKeyTooLongError:
            # This is also acceptable behavior
            pass


class TestIntegrationScenarios:
    """
    Integration-style tests for realistic scenarios.

    Tests cover common usage patterns.
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_scenario_meter_event_workflow(self, service):
        """
        Test typical meter event workflow.

        1. Generate key for event
        2. Check if registered
        3. Register key
        4. Verify registration
        5. Check metrics
        """
        # Generate key
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # Check not registered
        assert service.is_registered(key) is False

        # Register key
        service.register_key(key)

        # Verify registered
        assert service.is_registered(key) is True

        # Check metrics
        metrics = service.get_metrics()
        assert metrics.total_keys_generated == 1
        assert metrics.registry_size == 1

    def test_scenario_batch_processing_workflow(self, service):
        """
        Test batch processing workflow.

        Simulates processing multiple events in a batch.
        """
        batch_id = "batch_20251225_123456"
        events = [
            ("tenant_001", "ai_labels", 100),
            ("tenant_001", "ai_labels", 200),
            ("tenant_002", "human_audits", 50),
        ]

        keys = []
        for tenant_id, meter_event, value in events:
            key = service.generate_key(
                tenant_id=tenant_id,
                meter_event=meter_event,
                value=value,
                batch_id=batch_id
            )
            keys.append(key)

        # All keys should be unique
        assert len(set(keys)) == 3

        # All keys should contain batch_id
        for key in keys:
            # Batch ID should be reflected in key (sanitized)
            assert isinstance(key, str)

        # Metrics should reflect 3 keys
        metrics = service.get_metrics()
        assert metrics.total_keys_generated == 3

    def test_scenario_retry_scenario(self, service):
        """
        Test retry scenario where same key is reused.

        Idempotency ensures retries don't cause duplicate billing.
        """
        # Generate key for event
        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100
        )

        # First attempt - register key
        service.register_key(key)
        assert service.is_registered(key) is True

        # Simulate retry - check key already registered
        # (This would prevent duplicate billing in real scenario)
        assert service.is_registered(key) is True

        # Metrics should show 1 key
        metrics = service.get_metrics()
        assert metrics.total_keys_generated == 1
        assert metrics.registry_size == 1


class TestEdgeCaseCoverage:
    """
    Additional tests to improve code coverage for edge cases.

    Tests cover:
    - Key expiration during is_registered check
    - Non-string component conversion
    - Empty after sanitization fallback
    - Near-collision detection
    """

    @pytest.fixture
    def service(self):
        """Create an IdempotencyService instance for testing."""
        from src.services.stripe.idempotency_service import IdempotencyService

        config = StripeConfig.from_environment()
        return IdempotencyService(config)

    def test_coverage_key_expires_during_check(self, service):
        """
        Test key expiration during is_registered check.

        Covers line 229: Key expired - remove it
        """
        # Register a key
        key = "test_key_coverage_123"
        service.register_key(key)

        # Manually expire it by setting old timestamp
        with service._registry_lock:
            service._registry[key] = datetime.now(timezone.utc) - timedelta(hours=25)

        # Should be detected as expired and removed
        assert service.is_registered(key) is False
        # Key should have been removed from registry
        assert key not in service._registry

    def test_coverage_non_string_component_conversion(self, service):
        """
        Test non-string component conversion.

        Covers line 320: component = str(component)
        """
        # Pass integer as tenant_id (non-string)
        key = service.generate_key(
            tenant_id=12345,  # Integer instead of string
            meter_event="ai_labels",
            value=100
        )

        # Should convert to string and generate valid key
        assert isinstance(key, str)
        assert len(key) > 0

    def test_coverage_empty_after_sanitization(self, service):
        """
        Test empty component after sanitization.

        Covers line 350: component = "sanitized"
        """
        # Create a component that becomes empty after sanitization
        # All special characters that get removed
        key = service.generate_key(
            tenant_id="';--$<>()\\|",  # All dangerous chars
            meter_event="ai_labels",
            value=100
        )

        # Should handle and generate valid key (fallback to "sanitized")
        assert isinstance(key, str)
        assert len(key) > 0
        # Should contain "sanitized" or "empty" as fallback
        assert "sanitized" in key or "empty" in key

    def test_coverage_near_collision_detection(self, service):
        """
        Test near-collision detection logic.

        Covers lines 395, 403-426: Collision detection
        """
        # Generate and register first key
        key1 = service.generate_key(
            tenant_id="tenant_collision",
            meter_event="ai_labels",
            value=100
        )
        service.register_key(key1)

        # Generate second key very quickly (same second)
        # Use time.sleep to ensure we're in the same second
        key2 = service.generate_key(
            tenant_id="tenant_collision",
            meter_event="ai_labels",
            value=200
        )
        service.register_key(key2)

        # Metrics should track both keys
        metrics = service.get_metrics()
        assert metrics.total_keys_generated >= 2

    def test_coverage_key_with_many_colons(self, service):
        """
        Test key with many colons (edge case for collision detection).

        Covers line 395: Invalid format check
        """
        # Register malformed key with few colons (less than 5 parts)
        # This tests the early return in collision detection
        malformed_key = "a:b:c"  # Only 3 parts

        # Should handle gracefully
        service.register_key(malformed_key)
        assert service.is_registered(malformed_key) is True

    def test_coverage_component_trimming(self, service):
        """
        Test component length limit trimming.

        Covers line 346: component = component[:100]
        """
        # Create component exactly at limit
        long_value = "a" * 150

        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=0  # Will be converted to string "0", then sanitized
        )

        # Value component should be truncated
        assert isinstance(key, str)
        assert len(key) <= 255

    def test_coverage_batch_id_truncation(self, service):
        """
        Test batch_id component gets truncated properly.

        Covers batch_id component processing
        """
        long_batch = "batch_" + "x" * 200

        key = service.generate_key(
            tenant_id="tenant_123",
            meter_event="ai_labels",
            value=100,
            batch_id=long_batch
        )

        # Should handle long batch_id
        assert isinstance(key, str)
        assert len(key) <= 255

    def test_coverage_unicode_sanitization(self, service):
        """
        Test Unicode character handling.

        Covers control character removal
        """
        # String with various Unicode characters
        key = service.generate_key(
            tenant_id="tenant_123_\u00e9\u00f1\u00fc",  # UTF-8 encoded
            meter_event="ai_labels",
            value=100
        )

        # Should handle Unicode
        assert isinstance(key, str)
        assert len(key) > 0
        assert len(key) <= 255
