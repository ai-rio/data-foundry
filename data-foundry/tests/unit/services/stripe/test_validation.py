"""
Unit tests for ValidationService.

This module contains comprehensive tests for the ValidationService class,
which validates and sanitizes inputs to prevent injection attacks and ensure
data integrity.

Test Categories:
1. Meter Event Validation Tests
2. Metadata Sanitization Tests
3. Idempotency Component Sanitization Tests

Security Tests:
- Shell metacharacter blocking
- Reserved metadata key blocking
- Length limit enforcement
- Type coercion
- Null byte blocking

Phase: 2.5.2 (Infrastructure Services)
Task: 2.5.2.1 - Extract validation.py with ValidationService
Created: 2025-12-25
"""

import pytest
from typing import Dict, Any, List

from src.services.stripe.types import MeterType
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import StripeMeterValidationError


class TestMeterEventValidation:
    """
    Test suite for validate_meter_event() method.

    Tests validation of meter event name and value parameters.
    """

    @pytest.fixture
    def validation_service(self):
        """Fixture for ValidationService instance."""
        from src.services.stripe.validation import ValidationService
        config = StripeConfig()
        return ValidationService(config)

    def test_validate_meter_event_valid_ai_labels(self, validation_service):
        """Test validation passes for valid ai_labels meter event."""
        errors = validation_service.validate_meter_event(
            meter_event="ai_labels",
            value=100
        )
        assert errors == []

    def test_validate_meter_event_valid_human_audits(self, validation_service):
        """Test validation passes for valid human_audits meter event."""
        errors = validation_service.validate_meter_event(
            meter_event="human_audits",
            value=50
        )
        assert errors == []

    def test_validate_meter_event_invalid_name(self, validation_service):
        """Test validation fails for invalid meter event name."""
        errors = validation_service.validate_meter_event(
            meter_event="invalid_meter",
            value=100
        )
        assert len(errors) > 0
        assert any("Invalid meter_event" in e for e in errors)

    def test_validate_meter_event_empty_name(self, validation_service):
        """Test validation fails for empty meter event name."""
        errors = validation_service.validate_meter_event(
            meter_event="",
            value=100
        )
        assert len(errors) > 0

    def test_validate_meter_event_none_name(self, validation_service):
        """Test validation fails for None meter event name."""
        errors = validation_service.validate_meter_event(
            meter_event=None,  # type: ignore
            value=100
        )
        assert len(errors) > 0

    def test_validate_meter_event_invalid_value_type_string(self, validation_service):
        """Test validation fails for string value."""
        errors = validation_service.validate_meter_event(
            meter_event="ai_labels",
            value="100"  # type: ignore
        )
        assert len(errors) > 0
        assert any("must be an integer" in e for e in errors)

    def test_validate_meter_event_invalid_value_type_float(self, validation_service):
        """Test validation fails for float value."""
        errors = validation_service.validate_meter_event(
            meter_event="ai_labels",
            value=100.5  # type: ignore
        )
        assert len(errors) > 0
        assert any("must be an integer" in e for e in errors)

    def test_validate_meter_event_negative_value(self, validation_service):
        """Test validation fails for negative value."""
        errors = validation_service.validate_meter_event(
            meter_event="ai_labels",
            value=-10
        )
        assert len(errors) > 0
        assert any("positive" in e.lower() for e in errors)

    def test_validate_meter_event_zero_value(self, validation_service):
        """Test validation fails for zero value."""
        errors = validation_service.validate_meter_event(
            meter_event="ai_labels",
            value=0
        )
        assert len(errors) > 0
        assert any("positive" in e.lower() for e in errors)

    def test_validate_meter_event_multiple_errors(self, validation_service):
        """Test validation returns multiple errors for invalid input."""
        errors = validation_service.validate_meter_event(
            meter_event="invalid_meter",
            value=-10
        )
        assert len(errors) >= 2
        assert any("Invalid meter_event" in e for e in errors)
        assert any("positive" in e.lower() for e in errors)


class TestMetadataSanitization:
    """
    Test suite for sanitize_metadata() method.

    Tests sanitization of metadata dictionaries to prevent injection attacks.
    """

    @pytest.fixture
    def validation_service(self):
        """Fixture for ValidationService instance."""
        from src.services.stripe.validation import ValidationService
        config = StripeConfig()
        return ValidationService(config)

    def test_sanitize_metadata_valid_dict(self, validation_service):
        """Test sanitization passes for valid metadata dict."""
        metadata = {
            "source": "api",
            "count": "100",
            "enabled": "true"
        }
        result = validation_service.sanitize_metadata(metadata)
        assert result == metadata

    def test_sanitize_metadata_type_coercion_int_to_str(self, validation_service):
        """Test sanitization coerces integer values to strings."""
        metadata = {
            "count": 100,
            "total": 500
        }
        result = validation_service.sanitize_metadata(metadata)
        assert result == {
            "count": "100",
            "total": "500"
        }

    def test_sanitize_metadata_type_coercion_float_to_str(self, validation_service):
        """Test sanitization coerces float values to strings."""
        metadata = {
            "rate": 1.5,
            "percentage": 99.9
        }
        result = validation_service.sanitize_metadata(metadata)
        assert result == {
            "rate": "1.5",
            "percentage": "99.9"
        }

    def test_sanitize_metadata_type_coercion_bool_to_str(self, validation_service):
        """Test sanitization coerces boolean values to strings."""
        metadata = {
            "enabled": True,
            "disabled": False
        }
        result = validation_service.sanitize_metadata(metadata)
        assert result == {
            "enabled": "True",
            "disabled": "False"
        }

    def test_sanitize_metadata_reserved_key_value(self, validation_service):
        """Test sanitization blocks reserved metadata key 'value'."""
        metadata = {
            "value": "test"
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "reserved" in str(exc_info.value).lower() or "cannot be set" in str(exc_info.value).lower()

    def test_sanitize_metadata_reserved_key_stripe_customer_id(self, validation_service):
        """Test sanitization blocks reserved metadata key 'stripe_customer_id'."""
        metadata = {
            "stripe_customer_id": "cus_123"
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "reserved" in str(exc_info.value).lower() or "cannot be set" in str(exc_info.value).lower()

    def test_sanitize_metadata_reserved_key_batch_id(self, validation_service):
        """Test sanitization blocks reserved metadata key 'batch_id'."""
        metadata = {
            "batch_id": "batch_123"
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "reserved" in str(exc_info.value).lower() or "cannot be set" in str(exc_info.value).lower()

    def test_sanitize_metadata_multiple_reserved_keys(self, validation_service):
        """Test sanitization blocks multiple reserved keys."""
        metadata = {
            "value": "test",
            "batch_id": "batch_123",
            "stripe_customer_id": "cus_123"
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        # Should list all reserved keys in error
        error_msg = str(exc_info.value).lower()
        assert "reserved" in error_msg or "cannot be set" in error_msg

    def test_sanitize_metadata_non_dict_input(self, validation_service):
        """Test sanitization fails for non-dict input."""
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata("not_a_dict")  # type: ignore
        assert "dictionary" in str(exc_info.value).lower()

    def test_sanitize_metadata_non_string_key(self, validation_service):
        """Test sanitization fails for non-string key."""
        metadata = {
            123: "test"  # type: ignore
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "must be a string" in str(exc_info.value).lower()

    def test_sanitize_metadata_invalid_value_type_dict(self, validation_service):
        """Test sanitization fails for dict value."""
        metadata = {
            "nested": {"key": "value"}
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "primitive type" in str(exc_info.value).lower()

    def test_sanitize_metadata_invalid_value_type_list(self, validation_service):
        """Test sanitization fails for list value."""
        metadata = {
            "items": ["a", "b", "c"]
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "primitive type" in str(exc_info.value).lower()

    def test_sanitize_metadata_invalid_value_type_none(self, validation_service):
        """Test sanitization fails for None value."""
        metadata = {
            "my_key": None
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        assert "primitive type" in str(exc_info.value).lower()

    def test_sanitize_metadata_empty_dict(self, validation_service):
        """Test sanitization passes for empty dict."""
        metadata = {}
        result = validation_service.sanitize_metadata(metadata)
        assert result == {}

    def test_sanitize_metadata_mixed_valid_invalid(self, validation_service):
        """Test sanitization fails with mixed valid and invalid entries."""
        metadata = {
            "valid_key": "valid_value",
            123: "invalid_key",  # type: ignore
            "another_valid": 100,
            "invalid_value": {"nested": "dict"}
        }
        with pytest.raises(StripeMeterValidationError) as exc_info:
            validation_service.sanitize_metadata(metadata)
        # Should mention both invalid key and invalid value
        error_msg = str(exc_info.value).lower()
        assert "123" in error_msg or "nested" in error_msg or "primitive" in error_msg


class TestIdempotencyComponentSanitization:
    """
    Test suite for sanitize_idempotency_component() method.

    Tests sanitization of strings for use in idempotency keys to prevent
    injection attacks and key collisions.
    """

    @pytest.fixture
    def validation_service(self):
        """Fixture for ValidationService instance."""
        from src.services.stripe.validation import ValidationService
        config = StripeConfig()
        return ValidationService(config)

    def test_sanitize_idempotency_component_valid_string(self, validation_service):
        """Test sanitization passes for valid string."""
        result = validation_service.sanitize_idempotency_component("tenant_123")
        assert result == "tenant_123"

    def test_sanitize_idempotency_component_alphanumeric(self, validation_service):
        """Test sanitization preserves alphanumeric characters."""
        result = validation_service.sanitize_idempotency_component("TenantABC123")
        assert result == "TenantABC123"

    def test_sanitize_idempotency_component_with_hyphen(self, validation_service):
        """Test sanitization preserves hyphens."""
        result = validation_service.sanitize_idempotency_component("tenant-123")
        assert result == "tenant-123"

    def test_sanitize_idempotency_component_with_underscore(self, validation_service):
        """Test sanitization preserves underscores."""
        result = validation_service.sanitize_idempotency_component("tenant_123")
        assert result == "tenant_123"

    def test_sanitize_idempotency_component_shell_metacharacters_semicolon(self, validation_service):
        """Test sanitization blocks semicolon (SQL injection)."""
        result = validation_service.sanitize_idempotency_component("tenant;123")
        assert ";" not in result
        assert "_" in result or "tenant123" in result

    def test_sanitize_idempotency_component_shell_metacharacters_pipe(self, validation_service):
        """Test sanitization blocks pipe (command injection)."""
        result = validation_service.sanitize_idempotency_component("tenant|123")
        assert "|" not in result

    def test_sanitize_idempotency_component_shell_metacharacters_ampersand(self, validation_service):
        """Test sanitization blocks ampersand (command chaining)."""
        result = validation_service.sanitize_idempotency_component("tenant&123")
        assert "&" not in result

    def test_sanitize_idempotency_component_shell_metacharacters_dollar(self, validation_service):
        """Test sanitization blocks dollar sign (variable expansion)."""
        result = validation_service.sanitize_idempotency_component("tenant$123")
        assert "$" not in result

    def test_sanitize_idempotency_component_shell_metacharacters_parentheses(self, validation_service):
        """Test sanitization blocks parentheses (command substitution)."""
        result = validation_service.sanitize_idempotency_component("tenant(123)")
        assert "(" not in result
        assert ")" not in result

    def test_sanitize_idempotency_component_newline(self, validation_service):
        """Test sanitization blocks newline (command injection)."""
        result = validation_service.sanitize_idempotency_component("tenant\n123")
        assert "\n" not in result

    def test_sanitize_idempotency_component_carriage_return(self, validation_service):
        """Test sanitization blocks carriage return."""
        result = validation_service.sanitize_idempotency_component("tenant\r123")
        assert "\r" not in result

    def test_sanitize_idempotency_component_tab(self, validation_service):
        """Test sanitization blocks tab."""
        result = validation_service.sanitize_idempotency_component("tenant\t123")
        assert "\t" not in result

    def test_sanitize_idempotency_component_null_byte(self, validation_service):
        """Test sanitization blocks null byte."""
        result = validation_service.sanitize_idempotency_component("tenant\x00123")
        assert "\x00" not in result

    def test_sanitize_idempotency_component_path_traversal_double_dot(self, validation_service):
        """Test sanitization blocks path traversal attempts."""
        result = validation_service.sanitize_idempotency_component("../etc/passwd")
        assert ".." not in result

    def test_sanitize_idempotency_component_sql_injection_single_quote(self, validation_service):
        """Test sanitization blocks SQL injection single quote."""
        result = validation_service.sanitize_idempotency_component("tenant' OR '1'='1")
        assert "'" not in result

    def test_sanitize_idempotency_component_sql_injection_double_quote(self, validation_service):
        """Test sanitization blocks SQL injection double quote."""
        result = validation_service.sanitize_idempotency_component('tenant" OR "1"="1')
        assert '"' not in result

    def test_sanitize_idempotency_component_sql_injection_comment(self, validation_service):
        """Test sanitization blocks SQL comment."""
        result = validation_service.sanitize_idempotency_component("tenant--123")
        assert "--" not in result

    def test_sanitize_idempotency_component_xss_script_tag(self, validation_service):
        """Test sanitization blocks XSS script tag."""
        result = validation_service.sanitize_idempotency_component("<script>alert(1)</script>")
        assert "<script" not in result.lower()
        assert "</script>" not in result.lower()

    def test_sanitize_idempotency_component_special_characters_replaced(self, validation_service):
        """Test sanitization replaces special chars with underscore."""
        result = validation_service.sanitize_idempotency_component("tenant@123#456")
        assert "@" not in result
        assert "#" not in result
        assert "_" in result

    def test_sanitize_idempotency_component_spaces_replaced(self, validation_service):
        """Test sanitization replaces spaces with underscore."""
        result = validation_service.sanitize_idempotency_component("tenant 123")
        assert " " not in result
        assert "_" in result

    def test_sanitize_idempotency_component_multiple_underscores_collapsed(self, validation_service):
        """Test sanitization collapses multiple consecutive underscores."""
        result = validation_service.sanitize_idempotency_component("tenant!!!123")
        assert "__" not in result

    def test_sanitize_idempotency_component_leading_underscore_removed(self, validation_service):
        """Test sanitization removes leading underscores."""
        result = validation_service.sanitize_idempotency_component("_tenant")
        assert not result.startswith("_")

    def test_sanitize_idempotency_component_trailing_underscore_removed(self, validation_service):
        """Test sanitization removes trailing underscores."""
        result = validation_service.sanitize_idempotency_component("tenant_")
        assert not result.endswith("_")

    def test_sanitize_idempotency_component_length_limit(self, validation_service):
        """Test sanitization enforces length limit."""
        long_string = "a" * 200
        result = validation_service.sanitize_idempotency_component(long_string)
        assert len(result) <= 100  # Max 100 chars per component

    def test_sanitize_idempotency_component_empty_string(self, validation_service):
        """Test sanitization handles empty string."""
        result = validation_service.sanitize_idempotency_component("")
        assert result == "empty" or len(result) > 0

    def test_sanitize_idempotency_component_only_special_chars(self, validation_service):
        """Test sanitization handles string with only special characters."""
        result = validation_service.sanitize_idempotency_component("!@#$%^&*()")
        # Should fallback to "sanitized" or similar
        assert len(result) > 0

    def test_sanitize_idempotency_component_mixed_case_preserved(self, validation_service):
        """Test sanitization preserves case."""
        result = validation_service.sanitize_idempotency_component("TenantABC")
        assert "TenantABC" in result

    def test_sanitize_idempotency_component_numbers_preserved(self, validation_service):
        """Test sanitization preserves numbers."""
        result = validation_service.sanitize_idempotency_component("tenant123456")
        assert "123456" in result


class TestSecurityEdgeCases:
    """
    Test suite for security edge cases.

    Tests various edge cases and attack vectors that could be used
    to bypass validation or cause security issues.
    """

    @pytest.fixture
    def validation_service(self):
        """Fixture for ValidationService instance."""
        from src.services.stripe.validation import ValidationService
        config = StripeConfig()
        return ValidationService(config)

    def test_metadata_reserved_key_case_sensitivity(self, validation_service):
        """Test that reserved key checking is case-sensitive or insensitive as designed."""
        # If case-sensitive, "Value" should pass; if case-insensitive, it should fail
        metadata = {"Value": "test"}
        # Current implementation is case-sensitive, so this should pass
        result = validation_service.sanitize_metadata(metadata)
        assert result == {"Value": "test"}

    def test_idempotency_component_unicode_characters(self, validation_service):
        """Test sanitization handles unicode characters."""
        result = validation_service.sanitize_idempotency_component("tenant\xc3\xa9")
        # Should handle without crashing
        assert len(result) > 0

    def test_idempotency_component_control_characters(self, validation_service):
        """Test sanitization removes control characters."""
        result = validation_service.sanitize_idempotency_component("tenant\x01\x02\x03")
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x03" not in result

    def test_metadata_very_long_key(self, validation_service):
        """Test sanitization handles very long keys."""
        metadata = {
            "a" * 1000: "value"
        }
        # Should handle without crashing
        result = validation_service.sanitize_metadata(metadata)
        assert len(result) == 1

    def test_metadata_very_long_value(self, validation_service):
        """Test sanitization handles very long values."""
        metadata = {
            "key": "a" * 10000
        }
        result = validation_service.sanitize_metadata(metadata)
        assert result["key"] == "a" * 10000

    def test_idempotency_component_all_control_chars(self, validation_service):
        """Test sanitization handles string of all control characters."""
        control_string = "".join(chr(i) for i in range(32))
        result = validation_service.sanitize_idempotency_component(control_string)
        # Should return fallback string
        assert len(result) > 0

    def test_combined_attack_vector(self, validation_service):
        """Test combined attack vector in metadata."""
        # Test with reserved key
        metadata1 = {"value": "test"}
        with pytest.raises(StripeMeterValidationError):
            validation_service.sanitize_metadata(metadata1)

        # Test with invalid value type (non-primitive)
        metadata2 = {"valid_key": {"nested": "dict"}}
        with pytest.raises(StripeMeterValidationError):
            validation_service.sanitize_metadata(metadata2)

        # Test with non-string key
        metadata3 = {123: "test"}  # type: ignore
        with pytest.raises(StripeMeterValidationError):
            validation_service.sanitize_metadata(metadata3)
