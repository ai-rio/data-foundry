"""
Validation utilities for tenant IDs and other identifiers.

This module provides validation functions for tenant IDs, customer IDs,
subscription IDs, and other identifiers used throughout the application.
"""

import re
import uuid
from typing import Optional, List


# Validation patterns
TENANT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

# Stripe ID patterns
STRIPE_CUSTOMER_ID_PREFIX = 'cus_'
STRIPE_SUBSCRIPTION_ID_PREFIX = 'sub_'
STRIPE_PRICE_ID_PREFIX = 'price_'


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, field: str, value: Optional[str] = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)


def validate_tenant_id(tenant_id: str) -> str:
    """
    Validate tenant ID format.

    Tenant IDs must be alphanumeric with underscores or hyphens.
    Common formats:
    - tenant_abc123
    - org_company_name
    - 12345678-1234-1234-1234-123456789012 (UUID format)

    Args:
        tenant_id: Tenant ID to validate

    Returns:
        The validated tenant ID

    Raises:
        ValidationError: If tenant_id format is invalid

    Examples:
        >>> validate_tenant_id("tenant_abc123")
        'tenant_abc123'
        >>> validate_tenant_id("invalid@tenant")
        ValidationError: Invalid tenant_id format
    """
    if not tenant_id:
        raise ValidationError(
            "Tenant ID cannot be empty",
            field="tenant_id"
        )

    if not isinstance(tenant_id, str):
        raise ValidationError(
            f"Tenant ID must be a string, got {type(tenant_id).__name__}",
            field="tenant_id",
            value=str(tenant_id)
        )

    # Check for UUID format
    if UUID_PATTERN.match(tenant_id):
        return tenant_id

    # Check for alphanumeric with underscore/hyphen format
    if not TENANT_ID_PATTERN.match(tenant_id):
        raise ValidationError(
            f"Invalid tenant_id format: '{tenant_id}'. "
            "Must be alphanumeric with underscores/hyphens or a valid UUID",
            field="tenant_id",
            value=tenant_id
        )

    # Check length limits (1-255 chars)
    if len(tenant_id) < 1 or len(tenant_id) > 255:
        raise ValidationError(
            f"Tenant ID length must be between 1 and 255 characters, got {len(tenant_id)}",
            field="tenant_id",
            value=tenant_id
        )

    return tenant_id


def validate_stripe_customer_id(customer_id: str) -> str:
    """
    Validate Stripe customer ID format.

    Stripe customer IDs must start with 'cus_' prefix.

    Args:
        customer_id: Stripe customer ID to validate

    Returns:
        The validated customer ID

    Raises:
        ValidationError: If customer_id format is invalid

    Examples:
        >>> validate_stripe_customer_id("cus_abc123")
        'cus_abc123'
    """
    if not customer_id:
        raise ValidationError(
            "Customer ID cannot be empty",
            field="stripe_customer_id"
        )

    if not isinstance(customer_id, str):
        raise ValidationError(
            f"Customer ID must be a string, got {type(customer_id).__name__}",
            field="stripe_customer_id",
            value=str(customer_id)
        )

    if not customer_id.startswith(STRIPE_CUSTOMER_ID_PREFIX):
        raise ValidationError(
            f"Invalid Stripe customer ID format: '{customer_id}'. "
            f"Must start with '{STRIPE_CUSTOMER_ID_PREFIX}'",
            field="stripe_customer_id",
            value=customer_id
        )

    # Stripe customer IDs are typically cus_<random> with total length around 20 chars
    if len(customer_id) < 5 or len(customer_id) > 255:
        raise ValidationError(
            f"Invalid Stripe customer ID length: {len(customer_id)}",
            field="stripe_customer_id",
            value=customer_id
        )

    return customer_id


def validate_stripe_subscription_id(subscription_id: str) -> str:
    """
    Validate Stripe subscription ID format.

    Stripe subscription IDs must start with 'sub_' prefix.

    Args:
        subscription_id: Stripe subscription ID to validate

    Returns:
        The validated subscription ID

    Raises:
        ValidationError: If subscription_id format is invalid
    """
    if not subscription_id:
        raise ValidationError(
            "Subscription ID cannot be empty",
            field="stripe_subscription_id"
        )

    if not isinstance(subscription_id, str):
        raise ValidationError(
            f"Subscription ID must be a string, got {type(subscription_id).__name__}",
            field="stripe_subscription_id",
            value=str(subscription_id)
        )

    if not subscription_id.startswith(STRIPE_SUBSCRIPTION_ID_PREFIX):
        raise ValidationError(
            f"Invalid Stripe subscription ID format: '{subscription_id}'. "
            f"Must start with '{STRIPE_SUBSCRIPTION_ID_PREFIX}'",
            field="stripe_subscription_id",
            value=subscription_id
        )

    if len(subscription_id) < 5 or len(subscription_id) > 255:
        raise ValidationError(
            f"Invalid Stripe subscription ID length: {len(subscription_id)}",
            field="stripe_subscription_id",
            value=subscription_id
        )

    return subscription_id


def validate_stripe_price_id(price_id: str) -> str:
    """
    Validate Stripe price ID format.

    Stripe price IDs must start with 'price_' prefix.

    Args:
        price_id: Stripe price ID to validate

    Returns:
        The validated price ID

    Raises:
        ValidationError: If price_id format is invalid
    """
    if not price_id:
        raise ValidationError(
            "Price ID cannot be empty",
            field="price_id"
        )

    if not isinstance(price_id, str):
        raise ValidationError(
            f"Price ID must be a string, got {type(price_id).__name__}",
            field="price_id",
            value=str(price_id)
        )

    if not price_id.startswith(STRIPE_PRICE_ID_PREFIX):
        raise ValidationError(
            f"Invalid Stripe price ID format: '{price_id}'. "
            f"Must start with '{STRIPE_PRICE_ID_PREFIX}'",
            field="price_id",
            value=price_id
        )

    if len(price_id) < 7 or len(price_id) > 255:
        raise ValidationError(
            f"Invalid Stripe price ID length: {len(price_id)}",
            field="price_id",
            value=price_id
        )

    return price_id


def is_valid_uuid(value: str) -> bool:
    """
    Check if a string is a valid UUID.

    Args:
        value: String to check

    Returns:
        True if valid UUID, False otherwise
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False
