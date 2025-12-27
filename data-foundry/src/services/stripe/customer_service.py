"""
CustomerService - Domain Layer for Stripe customer operations.

This module provides customer CRUD operations extracted from stripe_service.py
and adapted to the CustomerServiceProtocol interface for dependency injection.

Implements:
- create_customer(): Creates Stripe customer with database persistence
- get_customer_by_tenant(): Retrieves customer by tenant ID
- update_customer(): Updates customer email/name/metadata
- delete_customer(): Deletes Stripe customer

Phase: 2.5.3 (Domain Services)
Task: 2.5.3.1 - Extract customer_service.py with CustomerService

Security Features:
- Proper error handling with custom exception classes
- Database persistence for Stripe customer records
- Tenant isolation through metadata
- Stripe API integration with proper error handling
- Logging for all operations

Testing Approach: HYBRID
- Existing tests in test_stripe_service.py (161 tests)
- Extracted code maintains backward compatibility
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime, timezone

import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import col

from src.services.stripe.types import CustomerServiceProtocol, CustomerData
from src.services.stripe.exceptions import (
    StripeCustomerNotFoundError,
    StripeCustomerExistsError,
    StripeAPIError,
    StripeServiceError
)
from src.models.stripe_billing import StripeCustomer
from src.models.tenant import Tenant


logger = logging.getLogger(__name__)


class CustomerService(CustomerServiceProtocol):
    """
    Domain service for Stripe customer operations.

    Implements CustomerServiceProtocol interface for dependency injection.
    Provides customer CRUD operations with:
    - Stripe API integration
    - Database persistence
    - Metadata synchronization
    - Proper error handling and logging

    This service must be initialized with Stripe API credentials before use.

    Example:
        >>> service = CustomerService()
        >>> await service.initialize(api_key="sk_test_...")
        >>> customer_id = await service.create_customer(
        ...     tenant_id="tenant_123",
        ...     tenant_name="Example Corp",
        ...     email="billing@example.com"
        ...     )
    """

    def __init__(self):
        """Initialize CustomerService.

        The service must be initialized by calling initialize() before use.
        """
        self._initialized: bool = False
        self.api_key: Optional[str] = None

    async def initialize(self, api_key: str) -> None:
        """
        Initialize CustomerService with Stripe API key.

        Args:
            api_key: Stripe secret API key (sk_test_... or sk_live_...)

        Raises:
            StripeServiceError: If api_key is empty or initialization fails

        Example:
            >>> service = CustomerService()
            >>> await service.initialize(api_key="sk_test_...")
        """
        if not api_key:
            raise StripeServiceError(
                "Stripe API key cannot be empty. "
                "Please provide a valid API key."
            )

        try:
            self.api_key = api_key
            stripe.api_key = self.api_key
            self._initialized = True
            logger.info("CustomerService initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize CustomerService: {e}")
            raise StripeServiceError(f"Failed to initialize CustomerService: {e}") from e

    def _ensure_initialized(self) -> None:
        """
        Ensure service is initialized before use.

        Raises:
            StripeServiceError: If service is not initialized
        """
        if not self._initialized:
            raise StripeServiceError(
                "CustomerService not initialized. Call initialize() before using the service."
            )

    async def create_customer(
        self,
        tenant_id: str,
        tenant_name: str,
        email: str,
        name: Optional[str] = None,
        created_by: Optional[str] = None,
        db_session: Optional[AsyncSession] = None
    ) -> str:
        """
        Create a Stripe customer for a tenant.

        Creates a new Stripe customer with tenant metadata and optionally
        persists the mapping to the database.

        Args:
            tenant_id: Tenant identifier
            tenant_name: Tenant name for metadata
            email: Customer email address
            name: Optional customer name (defaults to tenant_name)
            created_by: Optional user identifier for audit trail
            db_session: Optional database session for persistence

        Returns:
            Stripe customer ID (cus_*)

        Raises:
            StripeServiceError: If service not initialized
            StripeCustomerExistsError: If customer already exists for tenant
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer_id = await service.create_customer(
            ...     tenant_id="tenant_123",
            ...     tenant_name="Example Corp",
            ...     email="billing@example.com",
            ...     name="Example Corp",
            ...     db_session=session
            ...     )
        """
        self._ensure_initialized()

        try:
            # Check if customer already exists (if db_session provided)
            if db_session:
                statement = select(StripeCustomer).where(
                    col(StripeCustomer.tenant_id) == tenant_id
                )
                result = await db_session.execute(statement)
                existing = result.scalar_one_or_none()

                if existing:
                    logger.warning(
                        f"Customer already exists for tenant {tenant_id}: "
                        f"{existing.stripe_customer_id}"
                    )
                    raise StripeCustomerExistsError(
                        f"Stripe customer already exists for tenant {tenant_id}",
                        tenant_id=tenant_id,
                        stripe_customer_id=existing.stripe_customer_id
                    )

            # Prepare customer data with tenant metadata
            customer_data = {
                "email": email,
                "name": name or tenant_name,
                "metadata": {
                    "tenant_id": tenant_id,
                    "tenant_name": tenant_name,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }

            # Create customer in Stripe
            stripe_customer = stripe.Customer.create(**customer_data)
            logger.info(
                f"Created Stripe customer {stripe_customer.id} for tenant {tenant_id}"
            )

            # Persist to database if session provided
            if db_session:
                db_customer = StripeCustomer(
                    tenant_id=tenant_id,
                    stripe_customer_id=stripe_customer.id,
                    email=email,
                    name=name or tenant_name,
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

        except StripeCustomerExistsError:
            # Re-raise exists error as-is
            raise

        except Exception as e:
            logger.error(f"Unexpected error creating customer: {e}")
            raise StripeServiceError(f"Failed to create customer: {e}") from e

    async def get_customer_by_tenant(
        self,
        tenant_id: str,
        db_session: AsyncSession
    ) -> Optional[CustomerData]:
        """
        Get customer by tenant ID from database.

        Queries the database for the Stripe customer associated with
        the given tenant_id.

        Args:
            tenant_id: Tenant identifier
            db_session: Database session for query

        Returns:
            CustomerData dictionary if found, None otherwise

        Example:
            >>> customer = await service.get_customer_by_tenant(
            ...     tenant_id="tenant_123",
            ...     db_session=session
            ...     )
            >>> if customer:
            ...     print(f"Customer: {customer['stripe_customer_id']}")
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

            # Return customer data as CustomerData TypedDict
            return CustomerData(
                tenant_id=db_customer.tenant_id,
                stripe_customer_id=db_customer.stripe_customer_id,
                email=db_customer.email,
                name=db_customer.name,
                metadata={
                    "created_at": db_customer.created_at.isoformat() if db_customer.created_at else None,
                    "updated_at": db_customer.updated_at.isoformat() if db_customer.updated_at else None
                },
                created_at=db_customer.created_at.isoformat() if db_customer.created_at else None,
                updated_at=db_customer.updated_at.isoformat() if db_customer.updated_at else None
            )

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
    ) -> CustomerData:
        """
        Update a Stripe customer.

        Updates customer details in Stripe and optionally syncs to database.

        Args:
            stripe_customer_id: Stripe customer ID (cus_*)
            email: Optional new email address
            name: Optional new name
            metadata: Optional metadata updates
            db_session: Optional database session for sync

        Returns:
            Updated CustomerData dictionary

        Raises:
            StripeCustomerNotFoundError: If customer doesn't exist
            StripeAPIError: If Stripe API call fails

        Example:
            >>> customer = await service.update_customer(
            ...     stripe_customer_id="cus_123",
            ...     email="newemail@example.com",
            ...     db_session=session
            ...     )
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
                return self._stripe_customer_to_customer_data(stripe_customer)

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
                    db_customer.updated_at = datetime.now(timezone.utc)
                    await db_session.commit()
                    logger.info(f"Synced customer update to database")

            return self._stripe_customer_to_customer_data(stripe_customer)

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

        except Exception as e:
            logger.error(f"Unexpected error updating customer: {e}")
            raise StripeServiceError(f"Failed to update customer: {e}") from e

    async def delete_customer(
        self,
        stripe_customer_id: str,
        db_session: Optional[AsyncSession] = None
    ) -> bool:
        """
        Delete a Stripe customer.

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
            ...     )
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

    def _stripe_customer_to_customer_data(
        self,
        stripe_customer
    ) -> CustomerData:
        """
        Convert Stripe customer object to CustomerData TypedDict.

        Args:
            stripe_customer: Stripe API customer object

        Returns:
            CustomerData dictionary with customer information
        """
        stripe_metadata = dict(stripe_customer.get("metadata", {}))

        return CustomerData(
            stripe_customer_id=stripe_customer.id,
            email=stripe_customer.get("email"),
            name=stripe_customer.get("name"),
            metadata={
                "tenant_id": stripe_metadata.get("tenant_id", ""),
                "tenant_name": stripe_metadata.get("tenant_name", ""),
                "created_at": stripe_metadata.get("created_at", "")
            },
            created_at=stripe_metadata.get("created_at"),
            updated_at=stripe_metadata.get("updated_at")
        )
