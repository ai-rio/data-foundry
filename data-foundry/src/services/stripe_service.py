"""
StripeService - Stripe billing operations for Data Foundry.

This service provides Stripe customer management operations including:
- Customer CRUD operations (create, read, update, delete)
- Metadata mapping between tenant_id and Stripe customer
- Stripe API integration with proper error handling
- Database persistence for Stripe customer records

P1-002: StripeService base with Customer CRUD operations

Security Features:
- API key management via SecretManager
- Custom exception classes for error handling
- Proper masking of sensitive data in logs
- Tenant isolation through metadata

Meter Types:
- METER_AI_LABELS: AI-powered data labeling usage
- METER_HUMAN_AUDITS: Human review workflow usage
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import col

from src.core.secret_manager import SecretManager
from src.models.tenant import Tenant
from src.models.stripe_billing import StripeCustomer


logger = logging.getLogger(__name__)


# ============================================================================
# Exception Classes
# ============================================================================

class StripeServiceError(Exception):
    """
    Base exception for Stripe service errors.

    All StripeService exceptions inherit from this class for proper
    error handling and exception hierarchy.
    """

    def __init__(self, message: str, stripe_error: Optional[Exception] = None):
        """
        Initialize StripeServiceError.

        Args:
            message: Error message describing what went wrong
            stripe_error: Optional underlying Stripe API error
        """
        self.message = message
        self.stripe_error = stripe_error
        super().__init__(self.message)


class StripeCustomerNotFoundError(StripeServiceError):
    """
    Raised when Stripe customer is not found.

    This exception is raised when:
    - get_customer_by_tenant() returns None
    - update_customer() is called with non-existent customer
    - delete_customer() is called with non-existent customer
    """

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        stripe_customer_id: Optional[str] = None
    ):
        """
        Initialize StripeCustomerNotFoundError.

        Args:
            message: Error message
            tenant_id: Optional tenant_id for context
            stripe_customer_id: Optional Stripe customer ID for context
        """
        self.tenant_id = tenant_id
        self.stripe_customer_id = stripe_customer_id
        super().__init__(message)


class StripeAPIError(StripeServiceError):
    """
    Raised when Stripe API call fails.

    This exception wraps Stripe API errors and provides
    additional context for debugging and logging.
    """

    def __init__(
        self,
        message: str,
        stripe_error_type: Optional[str] = None,
        stripe_code: Optional[str] = None
    ):
        """
        Initialize StripeAPIError.

        Args:
            message: Error message
            stripe_error_type: Type of Stripe error (e.g., "StripeError")
            stripe_code: Stripe error code (e.g., "api_key_invalid")
        """
        self.stripe_error_type = stripe_error_type
        self.stripe_code = stripe_code
        super().__init__(message)


# ============================================================================
# StripeService
# ============================================================================

class StripeService:
    """
    Service for Stripe billing operations.

    Provides customer CRUD operations with:
    - Stripe API integration
    - Database persistence
    - Metadata synchronization
    - Proper error handling and logging

    Meter Types:
        METER_AI_LABELS: AI-powered data labeling usage meter
        METER_HUMAN_AUDITS: Human review workflow usage meter
    """

    # Meter type constants for Stripe metered billing
    METER_AI_LABELS = "ai_labels"
    METER_HUMAN_AUDITS = "human_audits"

    def __init__(self):
        """
        Initialize StripeService.

        The service must be initialized by calling initialize() before use.
        """
        self.api_key: Optional[str] = None
        self.secret_manager: Optional[SecretManager] = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        Initialize Stripe client with API key from SecretManager.

        Retrieves the Stripe secret key from SecretManager and configures
        the Stripe API client.

        Raises:
            StripeServiceError: If API key is not found in SecretManager

        Example:
            >>> service = StripeService()
            >>> await service.initialize()
        """
        if self._initialized:
            logger.warning("StripeService already initialized")
            return

        try:
            self.secret_manager = SecretManager()
            self.api_key = self.secret_manager.get_secret("STRIPE_SECRET_KEY")

            if not self.api_key:
                raise StripeServiceError(
                    "Stripe API key not found in SecretManager. "
                    "Please set STRIPE_SECRET_KEY in your environment."
                )

            # Configure Stripe API key
            stripe.api_key = self.api_key

            self._initialized = True
            logger.info("StripeService initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize StripeService: {e}")
            raise StripeServiceError(f"Failed to initialize StripeService: {e}") from e

    def _ensure_initialized(self) -> None:
        """
        Ensure service is initialized before use.

        Raises:
            StripeServiceError: If service is not initialized
        """
        if not self._initialized:
            raise StripeServiceError(
                "StripeService not initialized. Call initialize() before using the service."
            )

    async def create_customer(
        self,
        tenant: Tenant,
        email: str,
        name: Optional[str] = None,
        db_session: Optional[AsyncSession] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Create Stripe customer for tenant.

        Creates a new Stripe customer with tenant metadata and persists
        the mapping to the database.

        Args:
            tenant: Tenant object
            email: Customer email address
            name: Optional customer name
            db_session: Database session for persistence
            created_by: Optional user who created the record

        Returns:
            Stripe customer ID (cus_*)

        Raises:
            StripeServiceError: If service not initialized
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer_id = await service.create_customer(
            ...     tenant=tenant,
            ...     email="billing@example.com",
            ...     name="Example Corp",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare customer data with tenant metadata
            customer_data = {
                "email": email,
                "name": name or tenant.name,
                "metadata": {
                    "tenant_id": tenant.tenant_id,
                    "tenant_name": tenant.name,
                    "created_at": datetime.utcnow().isoformat()
                }
            }

            # Create customer in Stripe
            stripe_customer = stripe.Customer.create(**customer_data)
            logger.info(
                f"Created Stripe customer {stripe_customer.id} for tenant {tenant.tenant_id}"
            )

            # Persist to database if session provided
            if db_session:
                db_customer = StripeCustomer(
                    tenant_id=tenant.tenant_id,
                    stripe_customer_id=stripe_customer.id,
                    email=email,
                    name=name or tenant.name,
                    created_by=created_by
                )
                db_session.add(db_customer)
                await db_session.commit()
                await db_session.refresh(db_customer)
                logger.info(f"Persisted Stripe customer mapping to database")

            return stripe_customer.id

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating customer: {e}")
            raise StripeAPIError(
                f"Failed to create Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error creating customer: {e}")
            raise StripeServiceError(f"Failed to create customer: {e}") from e

    async def get_customer_by_tenant(
        self,
        tenant_id: str,
        db_session: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve Stripe customer by tenant_id from database.

        Queries the database for the Stripe customer associated with
        the given tenant_id.

        Args:
            tenant_id: Tenant identifier
            db_session: Database session for query

        Returns:
            Dictionary with customer data or None if not found

        Example:
            >>> customer = await service.get_customer_by_tenant(
            ...     tenant_id="tenant_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Query database for customer
            statement = select(StripeCustomer).where(
                col(StripeCustomer.tenant_id) == tenant_id
            )
            result = await db_session.execute(statement)
            db_customer = result.scalar_one_or_none()

            if not db_customer:
                logger.info(f"No Stripe customer found for tenant {tenant_id}")
                return None

            # Return customer data as dictionary
            return {
                "tenant_id": db_customer.tenant_id,
                "stripe_customer_id": db_customer.stripe_customer_id,
                "email": db_customer.email,
                "name": db_customer.name,
                "created_at": db_customer.created_at.isoformat() if db_customer.created_at else None,
                "updated_at": db_customer.updated_at.isoformat() if db_customer.updated_at else None
            }

        except Exception as e:
            logger.error(f"Error retrieving customer for tenant {tenant_id}: {e}")
            raise StripeServiceError(f"Failed to retrieve customer: {e}") from e

    async def update_customer(
        self,
        stripe_customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Update Stripe customer.

        Updates customer details in Stripe and optionally syncs to database.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            email: Optional new email address
            name: Optional new name
            metadata: Optional metadata updates
            db_session: Optional database session for sync

        Returns:
            Updated customer data dictionary

        Raises:
            StripeCustomerNotFoundError: If customer doesn't exist
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer = await service.update_customer(
            ...     stripe_customer_id="cus_123",
            ...     email="newemail@example.com"
            ... )
        """
        self._ensure_initialized()

        try:
            # Prepare update data (only include non-None values)
            update_data = {}
            if email is not None:
                update_data["email"] = email
            if name is not None:
                update_data["name"] = name
            if metadata is not None:
                update_data["metadata"] = metadata

            # Return early if no updates
            if not update_data:
                logger.info(f"No updates provided for customer {stripe_customer_id}")
                # Fetch and return current customer
                stripe_customer = stripe.Customer.retrieve(stripe_customer_id)
                return self._stripe_customer_to_dict(stripe_customer)

            # Update in Stripe
            stripe_customer = stripe.Customer.modify(stripe_customer_id, **update_data)
            logger.info(f"Updated Stripe customer {stripe_customer_id}")

            # Sync to database if session provided
            if db_session and (email or name):
                statement = select(StripeCustomer).where(
                    col(StripeCustomer.stripe_customer_id) == stripe_customer_id
                )
                result = await db_session.execute(statement)
                db_customer = result.scalar_one_or_none()

                if db_customer:
                    if email:
                        db_customer.email = email
                    if name:
                        db_customer.name = name
                    db_customer.updated_at = datetime.utcnow()
                    await db_session.commit()
                    logger.info(f"Synced customer update to database")

            return self._stripe_customer_to_dict(stripe_customer)

        except stripe.error.InvalidRequestError as e:
            if "No such customer" in str(e):
                logger.error(f"Customer not found: {stripe_customer_id}")
                raise StripeCustomerNotFoundError(
                    f"Stripe customer not found: {stripe_customer_id}",
                    stripe_customer_id=stripe_customer_id
                ) from e
            raise

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error updating customer: {e}")
            raise StripeAPIError(
                f"Failed to update Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

    async def delete_customer(
        self,
        stripe_customer_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> bool:
        """
        Delete Stripe customer.

        Deletes customer from Stripe and removes database record.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            db_session: Optional database session for cleanup

        Returns:
            True if deletion was successful

        Raises:
            StripeAPIError: If Stripe API call fails

        Example:
            >>> success = await service.delete_customer(
            ...     stripe_customer_id="cus_123",
            ...     db_session=session
            ... )
        """
        self._ensure_initialized()

        try:
            # Delete from Stripe
            stripe.Customer.delete(stripe_customer_id)
            logger.info(f"Deleted Stripe customer {stripe_customer_id}")

            # Remove from database if session provided
            if db_session:
                statement = select(StripeCustomer).where(
                    col(StripeCustomer.stripe_customer_id) == stripe_customer_id
                )
                result = await db_session.execute(statement)
                db_customer = result.scalar_one_or_none()

                if db_customer:
                    await db_session.delete(db_customer)
                    await db_session.commit()
                    logger.info(f"Removed customer record from database")

            return True

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error deleting customer: {e}")
            raise StripeAPIError(
                f"Failed to delete Stripe customer: {str(e)}",
                stripe_error_type=type(e).__name__,
                stripe_code=getattr(e, 'code', None)
            ) from e

        except Exception as e:
            logger.error(f"Unexpected error deleting customer: {e}")
            raise StripeServiceError(f"Failed to delete customer: {e}") from e

    def _stripe_customer_to_dict(self, stripe_customer) -> Dict[str, Any]:
        """
        Convert Stripe customer object to dictionary.

        Args:
            stripe_customer: Stripe API customer object

        Returns:
            Dictionary with customer data
        """
        return {
            "stripe_customer_id": stripe_customer.id,
            "email": stripe_customer.get("email"),
            "name": stripe_customer.get("name"),
            "metadata": dict(stripe_customer.get("metadata", {})),
            "created": stripe_customer.get("created")
        }
