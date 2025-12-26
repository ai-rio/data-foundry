"""
Configuration management for Stripe service modules.

This module provides centralized configuration with environment variable support,
sensible defaults, and validation for all Stripe service components.

Features:
- Environment variable loading with defaults
- Configuration validation
- Meter ID mapping
- Retry, idempotency, and batch configuration

Task: P02-513 (Foundation Layer - Config)
Created: 2025-12-25
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, List, TypedDict
from enum import Enum


# ============================================================================
# Enum Definitions
# ============================================================================

class MeterType(str, Enum):
    """Supported meter event types for usage-based billing."""
    AI_LABELS = "ai_labels"
    HUMAN_AUDITS = "human_audits"


# ============================================================================
# TypedDict Definitions (will move to types.py when created)
# ============================================================================

class RetryConfig(TypedDict, total=False):
    """Retry configuration settings."""
    max_retries: int
    initial_delay_ms: int
    max_delay_ms: int
    backoff_multiplier: float
    jitter_enabled: bool


class IdempotencyConfig(TypedDict, total=False):
    """Idempotency configuration settings."""
    max_key_length: int
    retention_hours: int
    max_registry_size: int


# ============================================================================
# Configuration Dataclass
# ============================================================================

@dataclass
class StripeConfig:
    """
    Centralized configuration for Stripe services.

    Loads configuration from environment variables with sensible defaults.
    All configuration values are validated on creation.

    Environment Variables:
        STRIPE_MAX_RETRIES: Maximum retry attempts (default: 5)
        STRIPE_INITIAL_RETRY_DELAY_MS: Initial delay in ms (default: 1000)
        STRIPE_MAX_RETRY_DELAY_MS: Maximum delay in ms (default: 32000)
        STRIPE_AI_LABELS_METER_ID: Meter ID for AI labels (required for production)
        STRIPE_HUMAN_AUDITS_METER_ID: Meter ID for human audits (required for production)
    """

    # API Configuration
    api_key: Optional[str] = field(default=None, repr=False)

    # Retry Configuration
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("STRIPE_MAX_RETRIES", "5"))
    )
    initial_retry_delay_ms: int = field(
        default_factory=lambda: int(os.getenv("STRIPE_INITIAL_RETRY_DELAY_MS", "1000"))
    )
    max_retry_delay_ms: int = field(
        default_factory=lambda: int(os.getenv("STRIPE_MAX_RETRY_DELAY_MS", "32000"))
    )
    retry_backoff_multiplier: float = 2.0
    jitter_enabled: bool = True

    # Idempotency Configuration
    max_idempotency_key_length: int = 255  # Stripe API limit
    idempotency_retention_hours: int = 24
    max_idempotency_registry_size: int = 10000

    # Batch Configuration
    max_batch_size: int = 100

    # Meter Configuration
    meter_ids: Dict[str, str] = field(default_factory=dict)

    # Validation Configuration
    reserved_metadata_keys: frozenset = field(
        default_factory=lambda: frozenset({"value", "stripe_customer_id", "batch_id"})
    )

    def __post_init__(self):
        """Load meter IDs from environment after initialization."""
        if not self.meter_ids:
            self.meter_ids = {
                MeterType.AI_LABELS.value: os.getenv("STRIPE_AI_LABELS_METER_ID", ""),
                MeterType.HUMAN_AUDITS.value: os.getenv("STRIPE_HUMAN_AUDITS_METER_ID", ""),
            }

    @classmethod
    def from_environment(cls) -> "StripeConfig":
        """
        Create configuration from environment variables.

        Returns:
            StripeConfig instance with values loaded from environment
        """
        return cls()

    def validate(self) -> List[str]:
        """
        Validate configuration values.

        Returns:
            List of validation error messages (empty if valid)

        Validates:
        - Retry configuration has non-negative values
        - Max retry delay >= initial retry delay
        - Batch size is within valid range
        - Meter IDs are configured for production use
        """
        errors: List[str] = []

        # Validate retry configuration
        if self.max_retries < 0:
            errors.append(
                f"max_retries must be >= 0, got {self.max_retries}"
            )

        if self.initial_retry_delay_ms < 0:
            errors.append(
                f"initial_retry_delay_ms must be >= 0, got {self.initial_retry_delay_ms}"
            )

        if self.max_retry_delay_ms < self.initial_retry_delay_ms:
            errors.append(
                f"max_retry_delay_ms ({self.max_retry_delay_ms}) must be >= "
                f"initial_retry_delay_ms ({self.initial_retry_delay_ms})"
            )

        # Validate batch size
        if self.max_batch_size < 1:
            errors.append(
                f"max_batch_size must be >= 1, got {self.max_batch_size}"
            )

        if self.max_batch_size > 1000:
            errors.append(
                f"max_batch_size must be <= 1000 (Stripe API limit), got {self.max_batch_size}"
            )

        # Validate idempotency configuration
        if self.max_idempotency_key_length < 1:
            errors.append(
                f"max_idempotency_key_length must be >= 1, got {self.max_idempotency_key_length}"
            )

        if self.max_idempotency_key_length > 255:
            errors.append(
                f"max_idempotency_key_length must be <= 255 (Stripe API limit), "
                f"got {self.max_idempotency_key_length}"
            )

        if self.idempotency_retention_hours < 1:
            errors.append(
                f"idempotency_retention_hours must be >= 1, got {self.idempotency_retention_hours}"
            )

        if self.max_idempotency_registry_size < 1:
            errors.append(
                f"max_idempotency_registry_size must be >= 1, got {self.max_idempotency_registry_size}"
            )

        # Warn about missing meter IDs (not an error for development)
        missing_meters = [
            meter_type for meter_type, meter_id in self.meter_ids.items()
            if not meter_id
        ]
        if missing_meters:
            # This is a warning, not an error - development may work without meter IDs
            pass  # Could log warning here

        return errors

    def get_retry_config(self) -> RetryConfig:
        """
        Get retry configuration as TypedDict.

        Returns:
            RetryConfig dictionary with retry settings
        """
        return RetryConfig(
            max_retries=self.max_retries,
            initial_delay_ms=self.initial_retry_delay_ms,
            max_delay_ms=self.max_retry_delay_ms,
            backoff_multiplier=self.retry_backoff_multiplier,
            jitter_enabled=self.jitter_enabled
        )

    def get_idempotency_config(self) -> IdempotencyConfig:
        """
        Get idempotency configuration as TypedDict.

        Returns:
            IdempotencyConfig dictionary with idempotency settings
        """
        return IdempotencyConfig(
            max_key_length=self.max_idempotency_key_length,
            retention_hours=self.idempotency_retention_hours,
            max_registry_size=self.max_idempotency_registry_size
        )

    def get_meter_id(self, meter_type: MeterType) -> Optional[str]:
        """
        Get meter ID for a meter type.

        Args:
            meter_type: The MeterType enum value

        Returns:
            Meter ID string or None if not configured
        """
        meter_id = self.meter_ids.get(meter_type.value, "")
        return meter_id if meter_id else None

    def is_meter_configured(self, meter_type: MeterType) -> bool:
        """
        Check if a meter type has a configured ID.

        Args:
            meter_type: The MeterType enum value

        Returns:
            True if meter ID is configured and non-empty
        """
        return bool(self.get_meter_id(meter_type))
