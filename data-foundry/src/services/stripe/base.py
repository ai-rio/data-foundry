"""
Base initialization logic for Stripe service modules.

This module provides the base class with initialization logic that will be
used by the facade module to maintain backward compatibility with the original
StripeService class.

Key responsibilities:
- Stripe client initialization with API key from SecretManager
- Configuration loading via StripeConfig
- Lazy-loading of service dependencies (initialized on first use)
- Service lifecycle management (initialize, is_initialized)

Task: P02-541 (Integration Layer - Base Module)
Created: 2025-12-25
Target LOC: ~100
"""

import logging
from typing import Optional
from threading import Lock

from src.core.secret_manager import SecretManager

from .config import StripeConfig
from .exceptions import StripeInitializationError


logger = logging.getLogger(__name__)


# ============================================================================
# Base Service Class
# ============================================================================

class StripeServiceBase:
    """
    Base class for Stripe service initialization and lifecycle management.

    Provides common initialization logic that will be inherited by the facade
    class to maintain backward compatibility with the original StripeService.

    The base class handles:
    - Stripe API client initialization
    - Configuration management
    - Lazy-loading of service dependencies
    - Thread-safe initialization state

    Attributes:
        config: StripeConfig instance with all configuration
        api_key: Stripe API key (loaded from SecretManager)
        _initialized: Whether the service has been initialized
        _lock: Thread lock for safe initialization

    Example:
        >>> service = StripeServiceBase()
        >>> await service.initialize()
        >>> service.is_initialized()
        True
    """

    # Class-level lock for thread-safe singleton pattern
    _lock: Lock = Lock()

    def __init__(self, config: Optional[StripeConfig] = None):
        """
        Initialize base service with configuration.

        Services are lazy-loaded and will be initialized on first access.
        The service must be initialized by calling initialize() before use.

        Args:
            config: Optional StripeConfig instance. If not provided, loads from environment.

        Example:
            >>> service = StripeServiceBase()
            >>> await service.initialize()
        """
        # Configuration
        self.config = config or StripeConfig.from_environment()

        # API key (will be loaded during initialization)
        self.api_key: Optional[str] = None
        self.secret_manager: Optional[SecretManager] = None

        # Initialization state
        self._initialized: bool = False
        self._init_lock: Lock = Lock()

        # Service placeholders (lazy-loaded)
        self._customer_service = None
        self._meter_service = None
        self._idempotency_service = None
        self._retry_service = None
        self._validator = None
        self._batch_processor = None

    async def initialize(self) -> None:
        """
        Initialize Stripe service with API key from SecretManager.

        Retrieves the Stripe secret key from SecretManager and configures
        the Stripe API client. This method must be called before using
        any service methods.

        Thread-safe: Multiple calls are safe, only the first call initializes.

        Raises:
            StripeInitializationError: If API key is not found or initialization fails

        Example:
            >>> service = StripeServiceBase()
            >>> await service.initialize()
            >>> service.is_initialized()
            True
        """
        # Fast path: already initialized
        if self._initialized:
            logger.warning("StripeService already initialized")
            return

        # Thread-safe initialization
        with self._init_lock:
            # Double-check after acquiring lock
            if self._initialized:
                return

            try:
                # Initialize SecretManager and load API key
                self.secret_manager = SecretManager()
                self.api_key = self.secret_manager.get_secret("STRIPE_SECRET_KEY")

                if not self.api_key:
                    raise StripeInitializationError(
                        "Stripe API key not found in SecretManager. "
                        "Please set STRIPE_SECRET_KEY in your environment."
                    )

                # Configure Stripe API client
                import stripe
                stripe.api_key = self.api_key

                # Validate configuration
                validation_errors = self.config.validate()
                if validation_errors:
                    error_msg = "Configuration validation failed: " + "; ".join(validation_errors)
                    raise StripeInitializationError(error_msg)

                # Mark as initialized
                self._initialized = True
                logger.info("StripeService initialized successfully")

            except StripeInitializationError:
                # Re-raise our custom exceptions
                raise
            except Exception as e:
                logger.error(f"Failed to initialize StripeService: {e}")
                raise StripeInitializationError(f"Failed to initialize StripeService: {e}") from e

    def is_initialized(self) -> bool:
        """
        Check if the service has been initialized.

        Returns:
            True if the service has been initialized, False otherwise

        Example:
            >>> service = StripeServiceBase()
            >>> service.is_initialized()
            False
            >>> await service.initialize()
            >>> service.is_initialized()
            True
        """
        return self._initialized

    def _ensure_initialized(self) -> None:
        """
        Ensure service is initialized before use.

        Raises:
            StripeInitializationError: If service is not initialized

        Example:
            >>> service = StripeServiceBase()
            >>> service._ensure_initialized()
            StripeInitializationError: Service not initialized. Call initialize() first.
        """
        if not self._initialized:
            raise StripeInitializationError(
                "StripeService not initialized. Call initialize() before using the service."
            )

    # ========================================================================
    # Lazy-loading Service Accessors
    # ========================================================================

    @property
    def customer_service(self):
        """
        Get customer service instance (lazy-loaded).

        Returns:
            CustomerService instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._customer_service is None:
            from .customer_service import CustomerService
            self._customer_service = CustomerService()
            # Initialize the service with the API key
            # Note: CustomerService.initialize is async, so we call it synchronously here
            # The api_key is already set in the base class
            self._customer_service._initialized = True
            self._customer_service.api_key = self.api_key
        return self._customer_service

    @property
    def meter_service(self):
        """
        Get meter event service instance (lazy-loaded).

        Returns:
            MeterEventService instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._meter_service is None:
            from .meter_event_service import MeterEventService
            # Import stripe module to create a client wrapper
            import stripe
            self._meter_service = MeterEventService(
                config=self.config,
                validation_service=self.validator,
                idempotency_service=self.idempotency_service,
                retry_service=self.retry_service,
                stripe_client=stripe
            )
        return self._meter_service

    @property
    def idempotency_service(self):
        """
        Get idempotency service instance (lazy-loaded).

        Returns:
            IdempotencyService instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._idempotency_service is None:
            from .idempotency_service import IdempotencyService
            self._idempotency_service = IdempotencyService(
                config=self.config
            )
        return self._idempotency_service

    @property
    def retry_service(self):
        """
        Get retry service instance (lazy-loaded).

        Returns:
            RetryService instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._retry_service is None:
            from .retry_service import RetryService
            self._retry_service = RetryService(
                config=self.config
            )
        return self._retry_service

    @property
    def validator(self):
        """
        Get validator instance (lazy-loaded).

        Returns:
            ValidationService instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._validator is None:
            from .validation import ValidationService
            self._validator = ValidationService(
                config=self.config
            )
        return self._validator

    @property
    def batch_processor(self):
        """
        Get batch processor instance (lazy-loaded).

        Returns:
            BatchProcessor instance

        Raises:
            StripeInitializationError: If service not initialized
        """
        self._ensure_initialized()
        if self._batch_processor is None:
            from .batch_processor import BatchProcessor
            self._batch_processor = BatchProcessor(
                config=self.config,
                meter_event_service=self.meter_service
            )
        return self._batch_processor
