"""
Idempotency Service for Stripe meter event operations.

This module provides idempotency key generation and tracking to ensure
exactly-once semantics for meter events, preventing duplicate billing.

Task: P02-523 (Infrastructure Layer - Idempotency Service)
Created: 2025-12-25

Security Features:
- Key collision detection and metrics
- Near-collision detection (similar keys within 1 second)
- Key length validation (255 char Stripe limit)
- Registry size limits (DoS protection)
- Component sanitization (injection attack prevention)
- Automatic key expiration (memory leak prevention)
- Thread-safe operations for concurrent access

Key Format:
    {tenant_id}:{meter_event}:{value}:{batch_id}:{timestamp}:{nonce}

Example:
    tenant_123:ai_labels:100:batch_001:20241225T143000Z:a1b2c3d4
"""

import re
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional


# Import types and protocols
from .types import (
    IdempotencyServiceProtocol,
    CollisionMetrics,
    IdempotencyKeyInfo,
)
from .config import StripeConfig
from .exceptions import (
    StripeIdempotencyKeyTooLongError,
    StripeMeterValidationError,
)


class IdempotencyService(IdempotencyServiceProtocol):
    """
    Service for generating and tracking idempotency keys.

    This service implements the IdempotencyServiceProtocol and provides:
    - Unique key generation with collision detection
    - Key registration and tracking
    - Automatic expiration and cleanup
    - Thread-safe operations
    - Security-focused input sanitization

    Attributes:
        config: StripeConfig instance with idempotency settings
        max_key_length: Maximum idempotency key length (default: 255)
        retention_hours: Hours to retain keys in registry (default: 24)
        max_registry_size: Maximum number of keys to track (default: 10000)

    Example:
        >>> config = StripeConfig.from_environment()
        >>> service = IdempotencyService(config)
        >>> key = service.generate_key("tenant_123", "ai_labels", 100)
        >>> service.register_key(key)
        >>> assert service.is_registered(key) is True
    """

    # Component sanitization patterns
    _DANGEROUS_PATTERNS = [
        r'\.\./',       # Path traversal
        r'\.\.\\',      # Windows path traversal
        r';',           # SQL injection separator
        r'--',          # SQL comment
        r"'",           # SQL quote
        r'"',           # Quote
        r'<script',     # XSS
        r'</script>',   # XSS close
        r'=',           # Could be used in injection
        r'\|',          # Command injection
        r'\$',          # Command substitution
        r'\`',          # Command substitution
        r'\(',          # Command substitution
        r'\)',          # Command substitution
    ]

    def __init__(self, config: StripeConfig):
        """
        Initialize IdempotencyService.

        Args:
            config: StripeConfig instance with idempotency settings
        """
        self.config = config

        # Idempotency configuration
        self.max_key_length = config.max_idempotency_key_length
        self.retention_hours = config.idempotency_retention_hours
        self.max_registry_size = config.max_idempotency_registry_size

        # Idempotency key registry (thread-safe)
        # Dictionary: {key: registration_timestamp}
        self._registry: Dict[str, datetime] = {}
        self._registry_lock = threading.Lock()

        # Collision detection metrics (thread-safe)
        self._metrics = CollisionMetrics(
            total_keys_generated=0,
            collision_count=0,
            near_collision_count=0,
            registry_size=0
        )
        self._metrics_lock = threading.Lock()

    def generate_key(
        self,
        tenant_id: str,
        meter_event: str,
        value: int,
        batch_id: Optional[str] = None
    ) -> str:
        """
        Generate a unique idempotency key.

        Key format: {tenant_id}:{meter_event}:{value}:{batch_id}:{timestamp}:{nonce}

        Components are sanitized to prevent injection attacks. Timestamp and nonce
        ensure uniqueness across time boundaries and concurrent requests.

        Args:
            tenant_id: Tenant identifier
            meter_event: Meter event name (e.g., "ai_labels", "human_audits")
            value: Event value/quantity
            batch_id: Optional batch identifier for batch operations

        Returns:
            Unique idempotency key string

        Raises:
            StripeIdempotencyKeyTooLongError: If key exceeds 255 characters

        Example:
            >>> key = service.generate_key("tenant_123", "ai_labels", 100)
            >>> print(key)
            'tenant_123:ai_labels:100:20241225T143000Z:a1b2c3d4'
        """
        # Update metrics
        with self._metrics_lock:
            self._metrics.total_keys_generated += 1

        # Sanitize all input components (security critical)
        safe_tenant_id = self._sanitize_component(tenant_id)
        safe_meter_event = self._sanitize_component(meter_event)
        safe_value = self._sanitize_component(str(value))
        safe_batch_id = self._sanitize_component(batch_id) if batch_id else None

        # Generate timestamp in ISO format (UTC)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # Generate nonce (8 chars for uniqueness)
        nonce = uuid.uuid4().hex[:8]

        # Build key with colon delimiter
        parts = [
            safe_tenant_id,
            safe_meter_event,
            safe_value,
        ]

        if safe_batch_id:
            parts.append(safe_batch_id)

        parts.extend([timestamp, nonce])

        key = ":".join(parts)

        # Validate length (Stripe limit: 255 chars)
        if len(key) > self.max_key_length:
            raise StripeIdempotencyKeyTooLongError(
                f"Idempotency key length {len(key)} exceeds maximum of "
                f"{self.max_key_length} characters",
                idempotency_key=key,
                key_length=len(key),
                max_length=self.max_key_length
            )

        # Check for collisions with recent keys
        self._check_collision(key)

        return key

    def is_registered(self, key: str) -> bool:
        """
        Check if a key is already registered.

        Automatically cleans up expired keys before checking.

        Args:
            key: Idempotency key to check

        Returns:
            True if key is registered and not expired, False otherwise

        Example:
            >>> key = service.generate_key("tenant_123", "ai_labels", 100)
            >>> service.is_registered(key)
            False
            >>> service.register_key(key)
            >>> service.is_registered(key)
            True
        """
        with self._registry_lock:
            # Cleanup expired keys first
            self._cleanup_expired_keys()

            # Check if key exists and is not expired
            if key in self._registry:
                registration_time = self._registry[key]
                age_hours = (datetime.now(timezone.utc) - registration_time).total_seconds() / 3600

                # Key exists and is within retention period
                if age_hours <= self.retention_hours:
                    return True
                else:
                    # Key expired - remove it
                    del self._registry[key]

        return False

    def register_key(self, key: str) -> None:
        """
        Register an idempotency key.

        Thread-safe registration with automatic cleanup of expired keys
        and registry size limits to prevent DoS via memory exhaustion.

        Args:
            key: Idempotency key to register

        Example:
            >>> key = service.generate_key("tenant_123", "ai_labels", 100)
            >>> service.register_key(key)
            >>> service.is_registered(key)
            True
        """
        with self._registry_lock:
            # Cleanup expired keys before adding new one
            self._cleanup_expired_keys()

            # Prevent unbounded registry growth (DoS protection)
            if len(self._registry) >= self.max_registry_size:
                # Registry full - remove oldest entries
                # Remove oldest 10% of entries
                sorted_items = sorted(
                    self._registry.items(),
                    key=lambda x: x[1]
                )
                num_to_remove = max(1, len(sorted_items) // 10)
                for old_key, _ in sorted_items[:num_to_remove]:
                    del self._registry[old_key]

            # Register the key with current timestamp
            self._registry[key] = datetime.now(timezone.utc)

    def get_metrics(self) -> CollisionMetrics:
        """
        Get collision detection metrics.

        Returns:
            CollisionMetrics with current statistics

        Example:
            >>> metrics = service.get_metrics()
            >>> print(f"Total keys: {metrics.total_keys_generated}")
            >>> print(f"Collision rate: {metrics.collision_rate:.2f}%")
        """
        with self._metrics_lock:
            metrics_copy = CollisionMetrics(
                total_keys_generated=self._metrics.total_keys_generated,
                collision_count=self._metrics.collision_count,
                near_collision_count=self._metrics.near_collision_count,
            )

        # Add registry size
        with self._registry_lock:
            metrics_copy.registry_size = len(self._registry)

        return metrics_copy

    def _sanitize_component(self, component: str) -> str:
        """
        Sanitize a component for use in idempotency key.

        Removes dangerous characters to prevent injection attacks
        and key collisions.

        Sanitization rules:
        - Remove path traversal sequences (../, ..\\)
        - Remove SQL injection attempts (;, --, ')
        - Remove XSS attempts (<script>, etc.)
        - Remove command injection attempts (|, $, `, ())
        - Remove control characters
        - Replace remaining special chars with underscore
        - Limit component length to prevent DoS

        Args:
            component: Raw component string to sanitize

        Returns:
            Sanitized component string safe for idempotency keys
        """
        if not component:
            return "empty"

        # Convert to string if not already
        if not isinstance(component, str):
            component = str(component)

        # Remove null bytes
        component = component.replace('\x00', '')

        # Remove control characters (except common safe ones)
        component = ''.join(
            char for char in component
            if ord(char) >= 32 or char in '\t\n\r'
        )

        # Remove dangerous sequences
        for pattern in self._DANGEROUS_PATTERNS:
            component = re.sub(pattern, '', component, flags=re.IGNORECASE)

        # Replace remaining non-alphanumeric chars (except underscore, hyphen) with underscore
        component = re.sub(r'[^a-zA-Z0-9_-]', '_', component)

        # Collapse multiple underscores
        component = re.sub(r'_+', '_', component)

        # Remove leading/trailing underscores
        component = component.strip('_')

        # Limit length to prevent DoS (max 100 chars per component)
        if len(component) > 100:
            component = component[:100]

        # Fallback if empty after sanitization
        if not component:
            component = "sanitized"

        return component

    def _cleanup_expired_keys(self) -> None:
        """
        Remove expired keys from the registry.

        Must be called with registry_lock held.
        """
        current_time = datetime.now(timezone.utc)
        retention_delta = timedelta(hours=self.retention_hours)

        # Find expired keys
        expired_keys = [
            key for key, reg_time in self._registry.items()
            if current_time - reg_time > retention_delta
        ]

        # Remove expired keys
        for key in expired_keys:
            del self._registry[key]

    def _check_collision(self, new_key: str) -> None:
        """
        Check for potential idempotency key collisions.

        Analyzes new key against recent keys to detect patterns
        that might indicate key generation issues.

        Detects:
        - Exact matches (true collisions)
        - Near collisions (same tenant/event/timestamp within 1 second)

        Args:
            new_key: New idempotency key to check
        """
        with self._registry_lock:
            recent_keys = list(self._registry.keys())

        # Extract components from new key
        # Format: tenant:meter:value[:batch]:timestamp:nonce
        parts = new_key.split(':')

        if len(parts) < 5:
            return  # Invalid format, skip collision check

        new_tenant = parts[0]
        new_meter = parts[1]
        new_timestamp = parts[-2]  # Second to last is timestamp

        # Check for near-collisions with recent keys
        for existing_key in recent_keys[-100:]:  # Check last 100 keys
            existing_parts = existing_key.split(':')

            if len(existing_parts) < 5:
                continue

            existing_tenant = existing_parts[0]
            existing_meter = existing_parts[1]
            existing_timestamp = existing_parts[-2]

            # Check if same tenant and meter event
            if new_tenant == existing_tenant and new_meter == existing_meter:
                # Parse timestamps to check if very close (within 1 second)
                try:
                    new_dt = datetime.strptime(new_timestamp, "%Y%m%dT%H%M%SZ")
                    existing_dt = datetime.strptime(existing_timestamp, "%Y%m%dT%H%M%SZ")
                    time_diff = abs((new_dt - existing_dt).total_seconds())

                    if time_diff < 1.0:
                        # Near collision detected
                        with self._metrics_lock:
                            self._metrics.near_collision_count += 1
                except (ValueError, IndexError):
                    # Timestamp parsing failed, skip
                    pass
