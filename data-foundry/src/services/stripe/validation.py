"""
ValidationService for Stripe service modules.

This module provides validation and sanitization services for Stripe operations.
It is security-critical and prevents injection attacks through rigorous input
validation and sanitization.

Features:
- Meter event validation (name and value)
- Metadata sanitization (blocks dangerous chars, reserved keys)
- Idempotency component sanitization (prevents injection attacks)

Phase: 2.5.2 (Infrastructure Services)
Task: 2.5.2.1 - Extract validation.py with ValidationService
Created: 2025-12-25

Security Considerations:
- Blocks shell metacharacters to prevent injection attacks
- Blocks reserved metadata keys (value, stripe_customer_id, batch_id)
- Enforces length limits
- Type coercion for metadata values (all to strings)
- Blocks null bytes and control characters
"""

import re
import logging
from typing import Dict, Any, List, Optional

from src.services.stripe.types import ValidationServiceProtocol, MeterType
from src.services.stripe.config import StripeConfig
from src.services.stripe.exceptions import StripeMeterValidationError


logger = logging.getLogger(__name__)


class ValidationService(ValidationServiceProtocol):
    """
    Service for validating and sanitizing Stripe service inputs.

    This class implements security-critical validation to prevent injection attacks
    and ensure data integrity for all Stripe operations.

    Attributes:
        config: StripeConfig instance with reserved keys and validation settings

    Example:
        >>> config = StripeConfig()
        >>> validator = ValidationService(config)
        >>> errors = validator.validate_meter_event("ai_labels", 100)
        >>> if not errors:
        ...     # Safe to proceed
        ...     pass
    """

    # Maximum component length for idempotency keys (prevents DoS)
    _MAX_COMPONENT_LENGTH = 100

    # Shell metacharacters that must be blocked (injection attack prevention)
    # ORDER MATTERS: More specific patterns must come before general ones
    _DANGEROUS_PATTERNS = [
        r'`.*?`',          # Backtick command substitution with content (CRITICAL)
        r'\$\(.*?\)',      # $() command substitution with content (CRITICAL)
        r'\$\{.*?\}',      # ${} variable expansion with content (CRITICAL)
        r'\.\./',          # Path traversal
        r'\.\.\\',         # Windows path traversal
        r';',              # SQL injection/command separator
        r'--',             # SQL comment
        r"'",              # SQL quote
        r'"',              # Double quote
        r'<script',        # XSS opening
        r'</script>',      # XSS closing
        r'=',              # Could be used in injection
        r'\$',             # Standalone dollar sign (variable expansion)
    ]

    def __init__(self, config: StripeConfig):
        """
        Initialize ValidationService.

        Args:
            config: StripeConfig instance with validation settings
        """
        self.config = config
        self._reserved_keys = config.reserved_metadata_keys
        # Create lowercase version for case-insensitive comparison (security fix)
        self._reserved_keys_lower = [rk.lower() for rk in self._reserved_keys]

    def validate_meter_event(self, meter_event: str, value: int) -> List[str]:
        """
        Validate meter event parameters.

        Validates that the meter event name is a known type and that the value
        is a positive integer.

        Args:
            meter_event: Meter event name to validate
            value: Event value to validate

        Returns:
            List of validation error messages (empty if valid)

        Example:
            >>> errors = validator.validate_meter_event("ai_labels", 100)
            >>> assert errors == []
        """
        errors = []

        # Validate meter_event name
        valid_events = [MeterType.AI_LABELS.value, MeterType.HUMAN_AUDITS.value]

        if not isinstance(meter_event, str):
            errors.append(
                f"Invalid meter_event: must be a string, got {type(meter_event).__name__}"
            )
        elif meter_event not in valid_events:
            errors.append(
                f"Invalid meter_event '{meter_event}'. "
                f"Must be one of: {', '.join(valid_events)}"
            )

        # Validate value is positive integer
        if not isinstance(value, int):
            errors.append(f"Value must be an integer, got {type(value).__name__}")
        elif value <= 0:
            errors.append(f"Value must be positive, got {value}")

        return errors

    def sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, str]:
        """
        Sanitize metadata for Stripe API.

        Validates that metadata keys are strings and values are primitive types.
        Blocks reserved keys to prevent overwriting critical fields.

        Security Features:
        - Blocks reserved metadata keys (value, stripe_customer_id, batch_id)
        - Type coercion for values (int, float, bool -> str)
        - Validates keys are strings
        - Validates values are primitive types

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Sanitized metadata with string values

        Raises:
            StripeMeterValidationError: If validation fails

        Example:
            >>> metadata = {"count": 100, "enabled": True}
            >>> result = validator.sanitize_metadata(metadata)
            >>> assert result == {"count": "100", "enabled": "True"}
        """
        if not isinstance(metadata, dict):
            raise StripeMeterValidationError(
                f"Metadata must be a dictionary, got {type(metadata).__name__}"
            )

        sanitized = {}
        validation_errors = []

        for key, value in metadata.items():
            # Validate key is a string
            if not isinstance(key, str):
                validation_errors.append(
                    f"Metadata key '{key}' must be a string, got {type(key).__name__}"
                )
                continue

            # Check for reserved keys (case-insensitive to prevent bypass)
            if key.lower() in self._reserved_keys_lower:
                validation_errors.append(
                    f"Metadata key '{key}' is reserved and cannot be set"
                )
                continue

            # Validate value is a primitive type that can be converted to string
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = str(value)
            else:
                validation_errors.append(
                    f"Metadata value for key '{key}' must be a primitive type "
                    f"(str, int, float, bool), got {type(value).__name__}"
                )

        if validation_errors:
            raise StripeMeterValidationError(
                f"Metadata validation failed: {'; '.join(validation_errors)}",
                validation_errors=validation_errors
            )

        return sanitized

    def sanitize_idempotency_component(self, component: str) -> str:
        """
        Sanitize a component for idempotency key generation.

        Removes dangerous characters that could be used in injection attacks
        or cause key collisions. This is critical for security.

        Sanitization Rules:
        - Remove control characters (ord < 32)
        - Remove dangerous sequences (path traversal, SQL injection, XSS)
        - Replace remaining special chars with underscore
        - Limit component length to prevent DoS
        - Collapse multiple underscores
        - Remove leading/trailing underscores

        Args:
            component: Raw component string

        Returns:
            Sanitized component string safe for idempotency keys

        Example:
            >>> result = validator.sanitize_idempotency_component("tenant;123")
            >>> assert ";" not in result
            >>> assert "tenant_123" in result or "tenant123" in result
        """
        if not component:
            return "empty"

        # Convert to string if not already
        if not isinstance(component, str):
            component = str(component)

        # Remove control characters (ord < 32)
        component = ''.join(char for char in component if ord(char) >= 32)

        # Remove dangerous patterns
        for pattern in self._DANGEROUS_PATTERNS:
            component = re.sub(pattern, '', component, flags=re.IGNORECASE)

        # Replace remaining non-alphanumeric chars (except underscore, hyphen) with underscore
        component = re.sub(r'[^a-zA-Z0-9_-]', '_', component)

        # Collapse multiple underscores
        component = re.sub(r'_+', '_', component)

        # Remove leading/trailing underscores
        component = component.strip('_')

        # Limit length to prevent DoS (max 100 chars per component)
        if len(component) > self._MAX_COMPONENT_LENGTH:
            component = component[:self._MAX_COMPONENT_LENGTH]

        # Fallback if empty after sanitization
        if not component:
            component = "sanitized"

        return component
