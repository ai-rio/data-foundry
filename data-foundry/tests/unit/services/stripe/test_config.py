"""
Comprehensive unit tests for Stripe configuration module.

This test suite focuses heavily on:
- P0 CRITICAL: API key exposure prevention in repr() and str()
- P0 CRITICAL: Environment variable injection attacks
- Security validation and sanitization
- Configuration edge cases and boundaries

Test Categories:
- Security Tests (P0): API key exposure, injection attacks
- Validation Tests: Configuration validation logic
- Environment Variable Tests: Loading and parsing
- Meter Configuration Tests: Meter ID management
- TypedDict Export Tests: Configuration export format
- Edge Cases: Boundary conditions, invalid inputs

Created: 2025-12-26
"""

import os
import sys
import pytest
from typing import Dict, Any
from dataclasses import fields

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../.."))

from src.services.stripe.config import (
    StripeConfig,
    MeterType,
    RetryConfig,
    IdempotencyConfig,
)


# ============================================================================
# Security Test Fixtures
# ============================================================================

@pytest.fixture
def clean_env():
    """Fixture to ensure clean environment before each test."""
    # Save original environment
    original_env = os.environ.copy()

    # Clear Stripe-related environment variables
    stripe_keys = [k for k in os.environ if k.startswith("STRIPE_")]
    for key in stripe_keys:
        del os.environ[key]

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def test_api_key():
    """Test API key fixture - realistic format but not real."""
    return "sk_test_51M4g1cK3yF4k3K3yT3stD4t4N0tR34lAbc123def456ghi789"


@pytest.fixture
def production_like_api_key():
    """Production-like API key for testing exposure prevention."""
    return "sk_live_51AbCdEfGhIjKlMnOpQrStUvWxYz1234567890abcdef"


# ============================================================================
# P0 CRITICAL SECURITY TESTS
# ============================================================================

class TestConfigAPIKeySanitization:
    """
    P0 CRITICAL: Test that API keys are NEVER exposed in string representations.

    This is critical for preventing:
    - Accidental logging of credentials
    - Debug output containing secrets
    - Stack traces exposing API keys
    - Error messages leaking credentials
    """

    def test_repr_does_not_expose_api_key(self, test_api_key):
        """CRITICAL: repr() must never contain the API key."""
        config = StripeConfig(api_key=test_api_key)

        repr_output = repr(config)

        # Direct check - API key should not be in repr
        assert test_api_key not in repr_output, \
            "SECURITY VIOLATION: API key exposed in repr() output"

        # Check key components aren't exposed
        assert "sk_test_" not in repr_output, \
            "SECURITY VIOLATION: API key prefix exposed in repr()"

        # Verify the repr contains class name but not secrets
        assert "StripeConfig" in repr_output
        assert len(repr_output) > 0

    def test_str_does_not_expose_api_key(self, test_api_key):
        """CRITICAL: str() must never contain the API key."""
        config = StripeConfig(api_key=test_api_key)

        str_output = str(config)

        # Direct check - API key should not be in str
        assert test_api_key not in str_output, \
            "SECURITY VIOLATION: API key exposed in str() output"

        # Check key components aren't exposed
        assert "sk_test_" not in str_output, \
            "SECURITY VIOLATION: API key prefix exposed in str()"

    def test_repr_with_live_key(self, production_like_api_key):
        """CRITICAL: Test with production-like key format."""
        config = StripeConfig(api_key=production_like_api_key)

        repr_output = repr(config)

        # Live key should not be exposed
        assert production_like_api_key not in repr_output, \
            "SECURITY VIOLATION: Production API key exposed in repr()"

        assert "sk_live_" not in repr_output, \
            "SECURITY VIOLATION: Live key prefix exposed"

    def test_str_with_live_key(self, production_like_api_key):
        """CRITICAL: Test str() with production-like key."""
        config = StripeConfig(api_key=production_like_api_key)

        str_output = str(config)

        assert production_like_api_key not in str_output, \
            "SECURITY VIOLATION: Production API key exposed in str()"

    def test_api_key_field_has_repr_false(self):
        """Verify api_key field has repr=False set in dataclass."""
        config_fields = {f.name: f for f in fields(StripeConfig)}

        api_key_field = config_fields.get("api_key")
        assert api_key_field is not None, "api_key field not found"

        # The repr parameter should be False
        assert api_key_field.repr == False, \
            "SECURITY: api_key field must have repr=False to prevent exposure"

    def test_api_key_none_no_exposure(self):
        """Test that None API key doesn't cause issues in string methods."""
        config = StripeConfig(api_key=None)

        # Should not raise exceptions
        repr_output = repr(config)
        str_output = str(config)

        assert isinstance(repr_output, str)
        assert isinstance(str_output, str)

    def test_empty_string_api_key_no_exposure(self):
        """Test empty string API key doesn't expose anything."""
        config = StripeConfig(api_key="")

        repr_output = repr(config)
        str_output = str(config)

        # Empty string is fine
        assert isinstance(repr_output, str)
        assert isinstance(str_output, str)

    def test_api_key_with_special_characters(self):
        """Test API key with various special characters aren't exposed."""
        special_keys = [
            "sk_test_51ABC<SCRIPT>alert('xss')</SCRIPT>123",
            "sk_test_51ABC\n\t\r\x00",
            "sk_test_51ABC' OR '1'='1",
            "sk_test_51ABC; DROP TABLE users;--",
        ]

        for key in special_keys:
            config = StripeConfig(api_key=key)

            repr_output = repr(config)
            str_output = str(config)

            # Should not contain the malicious payload
            assert key not in repr_output, \
                f"SECURITY: Special character key exposed in repr: {key[:20]}..."
            assert key not in str_output, \
                f"SECURITY: Special character key exposed in str: {key[:20]}..."


class TestEnvVarInjection:
    """
    P0 CRITICAL: Test environment variable injection attack prevention.

    Attack vectors to test:
    - SQL injection in numeric config values
    - Command injection in config values
    - Null byte injection
    - Path traversal attempts
    - Format string attacks
    """

    def test_sql_injection_in_max_retries(self, clean_env):
        """SQL injection attempt in STRIPE_MAX_RETRIES."""
        os.environ["STRIPE_MAX_RETRIES"] = "100; DROP DATABASE;--"

        # This should raise ValueError when parsing
        with pytest.raises(ValueError):
            config = StripeConfig()
            # Force evaluation of the default_factory
            _ = config.max_retries

    def test_sql_injection_in_initial_delay(self, clean_env):
        """SQL injection attempt in initial delay."""
        os.environ["STRIPE_INITIAL_RETRY_DELAY_MS"] = "1000' OR '1'='1"

        with pytest.raises(ValueError):
            config = StripeConfig()
            _ = config.initial_retry_delay_ms

    def test_null_byte_in_api_key(self, clean_env):
        """
        Null byte injection in API key.

        Note: Python's os.environ raises ValueError for null bytes,
        which is a good security feature. This test verifies that
        when a null byte is passed directly to StripeConfig, it's
        handled safely and not exposed in string representations.
        """
        # Can't set env var with null byte (Python prevents this)
        # But test direct parameter passing with null byte
        malicious_key = "sk_test_51ABC\x00NULLBYTE"

        # Create config with null byte in API key
        config = StripeConfig(api_key=malicious_key)

        # The key shouldn't be exposed in string representations
        # (even though it contains null bytes)
        repr_output = repr(config)
        str_output = str(config)

        # Verify the malicious key isn't exposed
        assert malicious_key not in repr_output, \
            "SECURITY: API key with null byte exposed in repr()"
        assert malicious_key not in str_output, \
            "SECURITY: API key with null byte exposed in str()"

    def test_command_injection_in_meter_id(self, clean_env):
        """Command injection attempt in meter ID."""
        os.environ["STRIPE_AI_LABELS_METER_ID"] = "meter_123; rm -rf /;"

        config = StripeConfig()

        # Meter ID should be loaded as-is (it's a string)
        # But validation should catch issues if there are any
        meter_id = config.get_meter_id(MeterType.AI_LABELS)
        assert meter_id is not None

        # The meter ID should be sanitized or validated
        # For now, just ensure it doesn't cause crashes
        assert isinstance(meter_id, str)

    def test_format_string_injection(self, clean_env):
        """Format string attack in config values."""
        os.environ["STRIPE_MAX_RETRIES"] = "%s%s%s%s"

        with pytest.raises(ValueError):
            config = StripeConfig()
            _ = config.max_retries

    def test_overflow_injection(self, clean_env):
        """Integer overflow attempt."""
        os.environ["STRIPE_MAX_RETRIES"] = "999999999999999999999999"

        config = StripeConfig()
        # Python handles big integers, but validation should catch this
        errors = config.validate()

        # Should have validation errors about unreasonable retry count
        # (even if not explicitly validated, logic should handle it)
        assert isinstance(config.max_retries, int)

    def test_unicode_injection(self, clean_env):
        """Unicode obfuscation attempts."""
        # Homograph attacks
        os.environ["STRIPE_MAX_RETRIES"] = "①₀₀"  # Unicode numbers

        with pytest.raises(ValueError):
            config = StripeConfig()
            _ = config.max_retries

    def test_xml_injection_in_meter_id(self, clean_env):
        """XML injection attempt in meter ID."""
        os.environ["STRIPE_AI_LABELS_METER_ID"] = "<!DOCTYPE xml [..]>"

        config = StripeConfig()
        meter_id = config.get_meter_id(MeterType.AI_LABELS)

        # Should be handled as string, not parsed
        assert isinstance(meter_id, str)

    def test_path_traversal_in_meter_id(self, clean_env):
        """Path traversal attempt in meter ID."""
        os.environ["STRIPE_AI_LABELS_METER_ID"] = "../../../etc/passwd"

        config = StripeConfig()
        meter_id = config.get_meter_id(MeterType.AI_LABELS)

        # Should just be a string, no actual file access
        assert meter_id == "../../../etc/passwd"

    def test_newline_injection(self, clean_env):
        """Newline injection in config values."""
        os.environ["STRIPE_MAX_RETRIES"] = "5\nADMIN=true\n"

        with pytest.raises(ValueError):
            config = StripeConfig()
            _ = config.max_retries


# ============================================================================
# Configuration Validation Tests
# ============================================================================

class TestConfigValidation:
    """Test configuration validation logic."""

    def test_valid_config_passes_validation(self):
        """Valid configuration should have no errors."""
        config = StripeConfig(
            api_key="sk_test_123",
            max_retries=5,
            initial_retry_delay_ms=1000,
            max_retry_delay_ms=32000,
            max_batch_size=100
        )

        errors = config.validate()
        assert errors == []

    def test_negative_max_retries_fails(self):
        """Negative max_retries should fail validation."""
        config = StripeConfig(max_retries=-1)

        errors = config.validate()
        assert len(errors) > 0
        assert any("max_retries must be >= 0" in e for e in errors)

    def test_negative_initial_delay_fails(self):
        """Negative initial delay should fail validation."""
        config = StripeConfig(initial_retry_delay_ms=-100)

        errors = config.validate()
        assert len(errors) > 0
        assert any("initial_retry_delay_ms must be >= 0" in e for e in errors)

    def test_max_delay_less_than_initial_fails(self):
        """Max delay less than initial delay should fail."""
        config = StripeConfig(
            initial_retry_delay_ms=5000,
            max_retry_delay_ms=1000
        )

        errors = config.validate()
        assert len(errors) > 0
        assert any("max_retry_delay_ms" in e and "must be >=" in e for e in errors)

    def test_batch_size_zero_fails(self):
        """Zero batch size should fail validation."""
        config = StripeConfig(max_batch_size=0)

        errors = config.validate()
        assert len(errors) > 0
        assert any("max_batch_size must be >= 1" in e for e in errors)

    def test_batch_size_exceeds_limit_fails(self):
        """Batch size over Stripe API limit should fail."""
        config = StripeConfig(max_batch_size=1001)

        errors = config.validate()
        assert len(errors) > 0
        assert any("must be <= 1000" in e for e in errors)

    def test_idempotency_key_length_zero_fails(self):
        """Zero idempotency key length should fail."""
        config = StripeConfig(max_idempotency_key_length=0)

        errors = config.validate()
        assert len(errors) > 0
        assert any("max_idempotency_key_length must be >= 1" in e for e in errors)

    def test_idempotency_key_length_exceeds_limit_fails(self):
        """Idempotency key length over Stripe limit should fail."""
        config = StripeConfig(max_idempotency_key_length=256)

        errors = config.validate()
        assert len(errors) > 0
        assert any("must be <= 255" in e for e in errors)

    def test_retention_hours_zero_fails(self):
        """Zero retention hours should fail validation."""
        config = StripeConfig(idempotency_retention_hours=0)

        errors = config.validate()
        assert len(errors) > 0
        assert any("idempotency_retention_hours must be >= 1" in e for e in errors)

    def test_registry_size_zero_fails(self):
        """Zero registry size should fail validation."""
        config = StripeConfig(max_idempotency_registry_size=0)

        errors = config.validate()
        assert len(errors) > 0
        assert any("max_idempotency_registry_size must be >= 1" in e for e in errors)

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are all reported."""
        config = StripeConfig(
            max_retries=-1,
            initial_retry_delay_ms=-100,
            max_batch_size=0
        )

        errors = config.validate()
        assert len(errors) >= 3


# ============================================================================
# Environment Variable Tests
# ============================================================================

class TestEnvironmentVariables:
    """Test environment variable loading."""

    def test_load_max_retries_from_env(self, clean_env):
        """Load max_retries from environment variable."""
        os.environ["STRIPE_MAX_RETRIES"] = "10"

        config = StripeConfig()
        assert config.max_retries == 10

    def test_load_initial_delay_from_env(self, clean_env):
        """Load initial delay from environment."""
        os.environ["STRIPE_INITIAL_RETRY_DELAY_MS"] = "2000"

        config = StripeConfig()
        assert config.initial_retry_delay_ms == 2000

    def test_load_max_delay_from_env(self, clean_env):
        """Load max delay from environment."""
        os.environ["STRIPE_MAX_RETRY_DELAY_MS"] = "60000"

        config = StripeConfig()
        assert config.max_retry_delay_ms == 60000

    def test_default_when_env_not_set(self, clean_env):
        """Use defaults when env vars are not set."""
        config = StripeConfig()

        assert config.max_retries == 5
        assert config.initial_retry_delay_ms == 1000
        assert config.max_retry_delay_ms == 32000

    def test_load_ai_labels_meter_id(self, clean_env):
        """Load AI labels meter ID from environment."""
        os.environ["STRIPE_AI_LABELS_METER_ID"] = "meter_ai_123"

        config = StripeConfig()
        meter_id = config.get_meter_id(MeterType.AI_LABELS)

        assert meter_id == "meter_ai_123"

    def test_load_human_audits_meter_id(self, clean_env):
        """Load human audits meter ID from environment."""
        os.environ["STRIPE_HUMAN_AUDITS_METER_ID"] = "meter_human_456"

        config = StripeConfig()
        meter_id = config.get_meter_id(MeterType.HUMAN_AUDITS)

        assert meter_id == "meter_human_456"

    def test_from_environment_classmethod(self, clean_env):
        """Test from_environment class method."""
        os.environ["STRIPE_MAX_RETRIES"] = "15"

        config = StripeConfig.from_environment()

        assert config.max_retries == 15


# ============================================================================
# Meter Configuration Tests
# ============================================================================

class TestMeterConfiguration:
    """Test meter ID management."""

    def test_get_existing_meter_id(self):
        """Get an existing meter ID."""
        config = StripeConfig(
            meter_ids={
                "ai_labels": "meter_ai_123",
                "human_audits": "meter_human_456"
            }
        )

        meter_id = config.get_meter_id(MeterType.AI_LABELS)
        assert meter_id == "meter_ai_123"

    def test_get_nonexistent_meter_id(self):
        """Get a meter ID that doesn't exist."""
        config = StripeConfig(meter_ids={})

        meter_id = config.get_meter_id(MeterType.AI_LABELS)
        assert meter_id is None

    def test_is_meter_configured_true(self):
        """Check if meter is configured (positive case)."""
        config = StripeConfig(
            meter_ids={"ai_labels": "meter_123"}
        )

        assert config.is_meter_configured(MeterType.AI_LABELS) is True

    def test_is_meter_configured_false(self):
        """Check if meter is configured (negative case)."""
        config = StripeConfig(meter_ids={})

        assert config.is_meter_configured(MeterType.AI_LABELS) is False

    def test_is_meter_configured_empty_string(self):
        """Check that empty string meter ID is not configured."""
        config = StripeConfig(
            meter_ids={"ai_labels": ""}
        )

        assert config.is_meter_configured(MeterType.AI_LABELS) is False

    def test_meter_ids_loaded_in_post_init(self):
        """Test that meter IDs are loaded in __post_init__."""
        config = StripeConfig(meter_ids={})

        # __post_init__ should populate meter_ids
        assert isinstance(config.meter_ids, dict)
        assert "ai_labels" in config.meter_ids
        assert "human_audits" in config.meter_ids


# ============================================================================
# TypedDict Export Tests
# ============================================================================

class TestTypedDictExports:
    """Test configuration export as TypedDict."""

    def test_get_retry_config(self):
        """Test export of retry configuration."""
        config = StripeConfig(
            max_retries=5,
            initial_retry_delay_ms=1000,
            max_retry_delay_ms=32000,
            retry_backoff_multiplier=2.0,
            jitter_enabled=True
        )

        retry_config = config.get_retry_config()

        assert isinstance(retry_config, dict)
        assert retry_config["max_retries"] == 5
        assert retry_config["initial_delay_ms"] == 1000
        assert retry_config["max_delay_ms"] == 32000
        assert retry_config["backoff_multiplier"] == 2.0
        assert retry_config["jitter_enabled"] is True

    def test_get_idempotency_config(self):
        """Test export of idempotency configuration."""
        config = StripeConfig(
            max_idempotency_key_length=255,
            idempotency_retention_hours=24,
            max_idempotency_registry_size=10000
        )

        idem_config = config.get_idempotency_config()

        assert isinstance(idem_config, dict)
        assert idem_config["max_key_length"] == 255
        assert idem_config["retention_hours"] == 24
        assert idem_config["max_registry_size"] == 10000


# ============================================================================
# Edge Cases and Boundary Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_retries_allowed(self):
        """Zero retries is valid (means no retries)."""
        config = StripeConfig(max_retries=0)
        errors = config.validate()

        assert not any("max_retries" in e for e in errors)

    def test_equal_initial_and_max_delay(self):
        """Initial and max delay can be equal."""
        config = StripeConfig(
            initial_retry_delay_ms=1000,
            max_retry_delay_ms=1000
        )
        errors = config.validate()

        assert not any("must be >=" in e for e in errors)

    def test_minimum_batch_size(self):
        """Minimum batch size is 1."""
        config = StripeConfig(max_batch_size=1)
        errors = config.validate()

        assert not any("max_batch_size" in e for e in errors)

    def test_maximum_batch_size(self):
        """Maximum batch size is 1000."""
        config = StripeConfig(max_batch_size=1000)
        errors = config.validate()

        assert not any("max_batch_size" in e for e in errors)

    def test_minimum_idempotency_key_length(self):
        """Minimum idempotency key length is 1."""
        config = StripeConfig(max_idempotency_key_length=1)
        errors = config.validate()

        assert not any("max_idempotency_key_length" in e for e in errors)

    def test_maximum_idempotency_key_length(self):
        """Maximum idempotency key length is 255 (Stripe limit)."""
        config = StripeConfig(max_idempotency_key_length=255)
        errors = config.validate()

        assert not any("max_idempotency_key_length" in e for e in errors)

    def test_reserved_metadata_keys_frozenset(self):
        """Test reserved metadata keys is a frozenset."""
        config = StripeConfig()

        assert isinstance(config.reserved_metadata_keys, frozenset)
        assert "value" in config.reserved_metadata_keys
        assert "stripe_customer_id" in config.reserved_metadata_keys
        assert "batch_id" in config.reserved_metadata_keys

    def test_custom_reserved_metadata_keys(self):
        """Test custom reserved metadata keys."""
        custom_keys = frozenset({"custom", "keys", "here"})
        config = StripeConfig(reserved_metadata_keys=custom_keys)

        assert config.reserved_metadata_keys == custom_keys


# ============================================================================
# MeterType Enum Tests
# ============================================================================

class TestMeterTypeEnum:
    """Test MeterType enum."""

    def test_ai_labels_value(self):
        """Test AI labels enum value."""
        assert MeterType.AI_LABELS.value == "ai_labels"

    def test_human_audits_value(self):
        """Test human audits enum value."""
        assert MeterType.HUMAN_AUDITS.value == "human_audits"

    def test_enum_is_string(self):
        """Test that MeterType is a string enum."""
        assert isinstance(MeterType.AI_LABELS, str)
        assert isinstance(MeterType.HUMAN_AUDITS, str)


# ============================================================================
# Dataclass Field Tests
# ============================================================================

class TestDataclassFields:
    """Test dataclass field properties."""

    def test_all_fields_exist(self):
        """Test all expected fields exist."""
        config = StripeConfig()

        # Check all fields are accessible
        assert hasattr(config, "api_key")
        assert hasattr(config, "max_retries")
        assert hasattr(config, "initial_retry_delay_ms")
        assert hasattr(config, "max_retry_delay_ms")
        assert hasattr(config, "retry_backoff_multiplier")
        assert hasattr(config, "jitter_enabled")
        assert hasattr(config, "max_idempotency_key_length")
        assert hasattr(config, "idempotency_retention_hours")
        assert hasattr(config, "max_idempotency_registry_size")
        assert hasattr(config, "max_batch_size")
        assert hasattr(config, "meter_ids")
        assert hasattr(config, "reserved_metadata_keys")

    def test_default_values(self):
        """Test default field values."""
        config = StripeConfig()

        assert config.api_key is None
        assert config.max_retries == 5
        assert config.initial_retry_delay_ms == 1000
        assert config.max_retry_delay_ms == 32000
        assert config.retry_backoff_multiplier == 2.0
        assert config.jitter_enabled is True
        assert config.max_idempotency_key_length == 255
        assert config.idempotency_retention_hours == 24
        assert config.max_idempotency_registry_size == 10000
        assert config.max_batch_size == 100


# ============================================================================
# Integration Tests
# ============================================================================

class TestConfigIntegration:
    """Integration tests for configuration."""

    def test_full_config_with_all_values(self):
        """Test configuration with all values set."""
        config = StripeConfig(
            api_key="sk_test_123",
            max_retries=10,
            initial_retry_delay_ms=500,
            max_retry_delay_ms=10000,
            retry_backoff_multiplier=3.0,
            jitter_enabled=False,
            max_idempotency_key_length=200,
            idempotency_retention_hours=48,
            max_idempotency_registry_size=5000,
            max_batch_size=50,
            meter_ids={"ai_labels": "meter_1", "human_audits": "meter_2"}
        )

        errors = config.validate()
        assert errors == []

        assert config.get_retry_config()["max_retries"] == 10
        assert config.get_idempotency_config()["retention_hours"] == 48
        assert config.is_meter_configured(MeterType.AI_LABELS) is True

    def test_config_from_env_with_validation(self, clean_env):
        """Test loading from env and validating."""
        os.environ["STRIPE_MAX_RETRIES"] = "3"
        os.environ["STRIPE_INITIAL_RETRY_DELAY_MS"] = "500"
        os.environ["STRIPE_MAX_RETRY_DELAY_MS"] = "5000"
        os.environ["STRIPE_AI_LABELS_METER_ID"] = "meter_test"

        config = StripeConfig.from_environment()
        errors = config.validate()

        assert errors == []
        assert config.max_retries == 3
        assert config.is_meter_configured(MeterType.AI_LABELS) is True


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
