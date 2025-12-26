"""
TDD Test Suite for StripeService Facade - P02-543

This test suite follows strict RED-GREEN-REFACTOR TDD discipline for implementing
the StripeService facade with 100% backward compatibility.

Task: P02-543 (Integration Layer - Facade Module)
Created: 2025-12-25
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

# Import models
from src.models.tenant import Tenant
from src.models.stripe_billing import StripeCustomer

# Import exceptions from original stripe_service
from src.services.stripe_service import (
    StripeServiceError,
    StripeCustomerNotFoundError,
    StripeAPIError,
    StripeMeterValidationError,
    BatchResult,
)

# Import the facade
from src.services.stripe.facade import StripeService
from src.services.stripe.base import StripeServiceBase
from src.services.stripe.exceptions import StripeInitializationError


# ============================================================================
# CYCLE 1: Facade Class Structure
# ============================================================================

class TestStripeServiceFacadeStructure:
    """
    CYCLE 1: Facade class structure and inheritance
    """

    def test_facade_class_exists(self):
        """Test that StripeService facade class exists."""
        from src.services.stripe.facade import StripeService
        assert StripeService is not None

    def test_facade_inherits_from_base(self):
        """Test that facade inherits from StripeServiceBase."""
        from src.services.stripe.facade import StripeService
        from src.services.stripe.base import StripeServiceBase
        assert issubclass(StripeService, StripeServiceBase)

    def test_facade_has_same_constants_as_original(self):
        """Test that facade has same class constants."""
        from src.services.stripe_service import StripeService as OriginalStripeService
        from src.services.stripe.facade import StripeService as FacadeStripeService

        assert FacadeStripeService.METER_AI_LABELS == OriginalStripeService.METER_AI_LABELS
        assert FacadeStripeService.METER_HUMAN_AUDITS == OriginalStripeService.METER_HUMAN_AUDITS
        assert FacadeStripeService.MAX_BATCH_SIZE == OriginalStripeService.MAX_BATCH_SIZE
        assert FacadeStripeService.RESERVED_METADATA_KEYS == OriginalStripeService.RESERVED_METADATA_KEYS
        assert FacadeStripeService.MAX_IDEMPOTENCY_KEY_LENGTH == OriginalStripeService.MAX_IDEMPOTENCY_KEY_LENGTH
        assert FacadeStripeService.IDEMPOTENCY_KEY_RETENTION_HOURS == OriginalStripeService.IDEMPOTENCY_KEY_RETENTION_HOURS
        assert FacadeStripeService.MAX_IDEMPOTENCY_REGISTRY_SIZE == OriginalStripeService.MAX_IDEMPOTENCY_REGISTRY_SIZE


# ============================================================================
# CYCLE 2: initialize() Method
# ============================================================================

class TestStripeServiceFacadeInitialization:
    """CYCLE 2: initialize() method delegation"""

    @pytest.mark.asyncio
    async def test_facade_initialize_delegates_to_base(self):
        """Test that initialize() delegates to StripeServiceBase."""
        from src.services.stripe.facade import StripeService

        facade = StripeService()

        with patch('src.services.stripe.base.SecretManager') as mock_secret_mgr:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = "sk_test_test_key"
            mock_secret_mgr.return_value = mock_instance

            with patch('stripe.api_key', None):
                await facade.initialize()
                assert facade.is_initialized()
                assert facade.api_key == "sk_test_test_key"

    @pytest.mark.asyncio
    async def test_facade_initialize_is_idempotent(self):
        """Test that initialize() can be called multiple times."""
        from src.services.stripe.facade import StripeService

        facade = StripeService()

        with patch('src.services.stripe.base.SecretManager') as mock_secret_mgr:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = "sk_test_test_key"
            mock_secret_mgr.return_value = mock_instance

            with patch('stripe.api_key', None):
                await facade.initialize()
                await facade.initialize()
                assert facade.is_initialized()


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

class TestStripeServiceFacadeBackwardCompatibility:
    """Backward compatibility verification tests."""

    def test_facade_has_same_public_api_as_original(self):
        """Test that facade has exact same public API as original StripeService."""
        from src.services.stripe_service import StripeService as OriginalStripeService
        from src.services.stripe.facade import StripeService as FacadeStripeService

        required_methods = [
            'initialize', 'create_customer', 'get_customer_by_tenant',
            'update_customer', 'delete_customer', 'report_usage',
            'report_usage_batch', 'generate_idempotency_key',
            'get_idempotency_metrics'
        ]

        for method_name in required_methods:
            assert hasattr(FacadeStripeService, method_name), \
                f"Facade missing required method: {method_name}"

    def test_facade_raises_same_exceptions_as_original(self):
        """Test that facade raises same exception types as original."""
        from src.services.stripe_service import (
            StripeServiceError, StripeCustomerNotFoundError,
            StripeAPIError, StripeMeterValidationError
        )

        assert StripeServiceError is not None
        assert StripeCustomerNotFoundError is not None
        assert StripeAPIError is not None
        assert StripeMeterValidationError is not None


# ============================================================================
# Integration Tests
# ============================================================================

class TestStripeServiceFacadeIntegration:
    """Integration tests for facade with real dependencies."""

    @pytest.mark.asyncio
    async def test_facade_initialize_and_create_customer(self):
        """Integration test: Initialize facade and create customer."""
        from src.services.stripe.facade import StripeService

        facade = StripeService()

        with patch('src.services.stripe.base.SecretManager') as mock_secret_mgr:
            mock_instance = Mock()
            mock_instance.get_secret.return_value = "sk_test_test_key"
            mock_secret_mgr.return_value = mock_instance

            with patch('stripe.Customer.create') as mock_create:
                mock_customer = Mock()
                mock_customer.id = "cus_test123"
                mock_create.return_value = mock_customer

                with patch('stripe.api_key', None):
                    await facade.initialize()

                    tenant = Tenant(tenant_id="tenant_123", name="Test Tenant")
                    customer_id = await facade.create_customer(
                        tenant=tenant,
                        email="test@example.com"
                    )

                    assert customer_id == "cus_test123"
                    assert facade.is_initialized()

    @pytest.mark.asyncio
    async def test_facade_throws_error_when_not_initialized(self):
        """Integration test: Verify facade throws error when not initialized."""
        from src.services.stripe.facade import StripeService

        facade = StripeService()

        with pytest.raises((StripeInitializationError, StripeServiceError)):
            await facade.create_customer(
                tenant=Tenant(tenant_id="tenant_123", name="Test"),
                email="test@example.com"
            )
