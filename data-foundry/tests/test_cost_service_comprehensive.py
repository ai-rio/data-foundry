"""
Comprehensive test suite for Cost Calculation Service using TDD approach.

These tests cover all aspects of cost calculation including:
- Multi-provider pricing models
- Token usage tracking and aggregation
- Volume tier and discount calculations
- Currency conversion and precision handling
- Stripe billing integration
- Cost alerts and threshold validation
- Edge cases and error conditions
- Performance and concurrency tests

All tests are written to FAIL initially, then implementation will be added.
"""

import pytest
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import json
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from src.services.cost_service import (
    CostService,
    ModelPricing,
    CostCalculation,
    AIProvider
)
from src.models.usage_tracking import (
    TokenUsage,
    TenantUsage,
    BillingEvent,
    CostAlert,
    UsagePeriod,
    BillingStatus
)
from src.models.tenant import Tenant, TenantStatus
from src.core.config import settings


class TestModelPricing:
    """Test ModelPricing class functionality."""

    def test_model_pricing_initialization(self):
        """FAIL: Test ModelPricing initialization with all parameters."""
        pricing = ModelPricing(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            input_token_cost=Decimal("0.005"),
            output_token_cost=Decimal("0.015"),
            context_window=128000,
            volume_tiers={
                "small": {"input": Decimal("0.0045"), "output": Decimal("0.0135")},
                "enterprise": {"input": Decimal("0.004"), "output": Decimal("0.012")}
            },
            currency="USD"
        )

        assert pricing.provider == AIProvider.OPENAI
        assert pricing.model == "gpt-4o"
        assert pricing.input_token_cost == Decimal("0.005")
        assert pricing.output_token_cost == Decimal("0.015")
        assert pricing.context_window == 128000
        assert pricing.currency == "USD"
        assert len(pricing.volume_tiers) == 2
        assert pricing.updated_at is not None

    def test_get_rate_default_tier(self):
        """FAIL: Test getting default rate when no volume tier specified."""
        pricing = ModelPricing(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            input_token_cost=Decimal("0.005"),
            output_token_cost=Decimal("0.015"),
            context_window=128000
        )

        input_rate = pricing.get_rate("input", "default")
        output_rate = pricing.get_rate("output", "default")

        assert input_rate == Decimal("0.005")
        assert output_rate == Decimal("0.015")

    def test_get_rate_volume_tier(self):
        """FAIL: Test getting volume tier rates."""
        pricing = ModelPricing(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            input_token_cost=Decimal("0.005"),
            output_token_cost=Decimal("0.015"),
            context_window=128000,
            volume_tiers={
                "enterprise": {"input": Decimal("0.004"), "output": Decimal("0.012")}
            }
        )

        input_rate = pricing.get_rate("input", "enterprise")
        output_rate = pricing.get_rate("output", "enterprise")

        assert input_rate == Decimal("0.004")
        assert output_rate == Decimal("0.012")

    def test_get_rate_nonexistent_tier_fallback(self):
        """FAIL: Test fallback to default when volume tier doesn't exist."""
        pricing = ModelPricing(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            input_token_cost=Decimal("0.005"),
            output_token_cost=Decimal("0.015"),
            context_window=128000
        )

        input_rate = pricing.get_rate("input", "nonexistent")

        assert input_rate == Decimal("0.005")


class TestCostCalculation:
    """Test CostCalculation class functionality."""

    def test_cost_calculation_initialization(self):
        """FAIL: Test CostCalculation initialization."""
        calc = CostCalculation(
            model="gpt-4o",
            provider=AIProvider.OPENAI,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            input_cost=Decimal("5.00"),
            output_cost=Decimal("7.50"),
            total_cost=Decimal("12.50"),
            input_rate=Decimal("0.005"),
            output_rate=Decimal("0.015"),
            tenant_id="tenant_123",
            volume_tier="enterprise",
            currency="USD"
        )

        assert calc.model == "gpt-4o"
        assert calc.provider == AIProvider.OPENAI
        assert calc.prompt_tokens == 1000
        assert calc.completion_tokens == 500
        assert calc.total_tokens == 1500
        assert calc.input_cost == Decimal("5.00")
        assert calc.output_cost == Decimal("7.50")
        assert calc.total_cost == Decimal("12.50")
        assert calc.input_rate == Decimal("0.005")
        assert calc.output_rate == Decimal("0.015")
        assert calc.tenant_id == "tenant_123"
        assert calc.volume_tier == "enterprise"
        assert calc.currency == "USD"
        assert calc.calculation_date is not None


class TestCostServiceBasics:
    """Test basic CostService functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_cost_service_initialization(self):
        """FAIL: Test CostService initialization with proper data structures."""
        assert hasattr(self.cost_service, '_model_pricing')
        assert hasattr(self.cost_service, '_exchange_rates')
        assert hasattr(self.cost_service, '_tenant_usage')
        assert isinstance(self.cost_service._model_pricing, dict)
        assert isinstance(self.cost_service._exchange_rates, dict)
        assert isinstance(self.cost_service._tenant_usage, dict)
        assert "USD" in self.cost_service._exchange_rates
        assert self.cost_service._exchange_rates["USD"] == Decimal("1.0")

    def test_get_model_pricing_existing(self):
        """FAIL: Test getting pricing for existing model."""
        pricing = self.cost_service.get_model_pricing("gpt-4o")

        assert isinstance(pricing, ModelPricing)
        assert pricing.model == "gpt-4o"
        assert pricing.provider == AIProvider.OPENAI

    def test_get_model_pricing_nonexistent(self):
        """FAIL: Test getting pricing for nonexistent model raises error."""
        with pytest.raises(ValueError, match="No pricing information available"):
            self.cost_service.get_model_pricing("nonexistent-model")

    @pytest.mark.asyncio
    async def test_calculate_cost_basic(self):
        """FAIL: Test basic cost calculation without tenant or volume tier."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500
        )

        # Expected: (1000/1000) * 0.005 + (500/1000) * 0.015 = 0.005 + 0.0075 = 0.0125
        assert isinstance(cost, Decimal)
        assert cost == Decimal("0.012500")

    @pytest.mark.asyncio
    async def test_calculate_cost_with_tenant(self):
        """FAIL: Test cost calculation with tenant for volume pricing."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            tenant_id="tenant_123"
        )

        assert isinstance(cost, Decimal)
        # Should track usage for tenant
        assert "tenant_123" in self.cost_service._tenant_usage

    @pytest.mark.asyncio
    async def test_calculate_cost_currency_conversion(self):
        """FAIL: Test cost calculation with currency conversion."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            currency="EUR"
        )

        assert isinstance(cost, Decimal)
        # Should be converted from USD to EUR
        assert cost < Decimal("0.012500")  # EUR rate < USD rate

    def test_estimate_cost(self):
        """FAIL: Test cost estimation before completion."""
        estimate = self.cost_service.estimate_cost(
            model="gpt-4o",
            estimated_input_tokens=1000,
            estimated_output_tokens=500
        )

        assert isinstance(estimate, Decimal)
        assert estimate == Decimal("0.012500")

    def test_calculate_total_cost_multiple_calculations(self):
        """FAIL: Test calculating total cost from multiple calculations."""
        calc1 = CostCalculation(
            model="gpt-4o",
            provider=AIProvider.OPENAI,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            input_cost=Decimal("5.00"),
            output_cost=Decimal("7.50"),
            total_cost=Decimal("12.50"),
            input_rate=Decimal("0.005"),
            output_rate=Decimal("0.015"),
            tenant_id="tenant_123"
        )

        calc2 = CostCalculation(
            model="claude-3-5-sonnet",
            provider=AIProvider.ANTHROPIC,
            prompt_tokens=2000,
            completion_tokens=1000,
            total_tokens=3000,
            input_cost=Decimal("6.00"),
            output_cost=Decimal("15.00"),
            total_cost=Decimal("21.00"),
            input_rate=Decimal("0.003"),
            output_rate=Decimal("0.015"),
            tenant_id="tenant_123"
        )

        total = self.cost_service.calculate_total_cost([calc1, calc2])
        assert total == Decimal("33.50")


class TestCurrencyConversion:
    """Test currency conversion functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_convert_currency_same_currency(self):
        """FAIL: Test converting to same currency returns same amount."""
        amount = Decimal("100.00")
        converted = self.cost_service.convert_currency(amount, "USD", "USD")
        assert converted == amount

    def test_convert_currency_supported(self):
        """FAIL: Test converting between supported currencies."""
        amount = Decimal("100.00")

        # USD to EUR
        eur = self.cost_service.convert_currency(amount, "USD", "EUR")
        assert isinstance(eur, Decimal)
        assert eur == Decimal("92.00")  # 100 * 0.92

        # EUR to GBP
        gbp = self.cost_service.convert_currency(eur, "EUR", "GBP")
        assert isinstance(gbp, Decimal)
        # EUR -> USD -> GBP: 92 / 0.92 * 0.79 = 79.00

    def test_convert_currency_unsupported(self):
        """FAIL: Test converting with unsupported currency raises error."""
        with pytest.raises(ValueError, match="Unsupported currency"):
            self.cost_service.convert_currency(
                Decimal("100.00"), "USD", "UNSUPPORTED"
            )

        with pytest.raises(ValueError, match="Unsupported currency"):
            self.cost_service.convert_currency(
                Decimal("100.00"), "UNSUPPORTED", "USD"
            )

    def test_convert_currency_precision(self):
        """FAIL: Test currency conversion maintains proper precision."""
        amount = Decimal("0.012345")
        converted = self.cost_service.convert_currency(amount, "USD", "EUR")

        # Should maintain configured billing precision
        assert converted.as_tuple().exponent <= -settings.BILLING_PRECISION


class TestVolumeTierCalculations:
    """Test volume tier and discount calculations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_get_volume_tier_default(self):
        """FAIL: Test getting default volume tier for new tenant."""
        tier = self.cost_service._get_volume_tier("new_tenant")
        assert tier == "default"

    @pytest.mark.asyncio
    async def test_calculate_cost_with_volume_tier(self):
        """FAIL: Test cost calculation with specific volume tier."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            volume_tier="enterprise"
        )

        # Should use enterprise rates: 0.004 input, 0.012 output
        # Expected: (1000/1000) * 0.004 + (500/1000) * 0.012 = 0.004 + 0.006 = 0.010
        assert cost == Decimal("0.010000")

    @pytest.mark.asyncio
    async def test_volume_tier_discount_application(self):
        """FAIL: Test that volume tier discounts are properly applied."""
        # Default tier cost
        default_cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=10000,
            completion_tokens=5000,
            volume_tier="default"
        )

        # Enterprise tier cost (should be lower)
        enterprise_cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=10000,
            completion_tokens=5000,
            volume_tier="enterprise"
        )

        assert enterprise_cost < default_cost
        # Enterprise should be 20% discount: 0.010 vs 0.0125
        assert enterprise_cost / default_cost == Decimal("0.80")


class TestCostThresholdsAndAlerts:
    """Test cost threshold checking and alert generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_check_cost_thresholds_none(self):
        """FAIL: Test threshold check with no thresholds set."""
        cost_data = {
            "daily_cost": Decimal("50.00"),
            "daily_threshold": Decimal("0.00"),
            "monthly_cost": Decimal("500.00"),
            "monthly_threshold": Decimal("0.00")
        }

        alerts = self.cost_service.check_cost_thresholds(cost_data)
        assert len(alerts) == 0

    def test_check_cost_thresholds_daily_warning(self):
        """FAIL: Test daily cost threshold warning generation."""
        cost_data = {
            "daily_cost": Decimal("90.00"),
            "daily_threshold": Decimal("100.00"),
            "monthly_cost": Decimal("500.00"),
            "monthly_threshold": Decimal("1000.00")
        }

        alerts = self.cost_service.check_cost_thresholds(cost_data)
        assert len(alerts) == 1
        assert alerts[0]["type"] == "daily_limit_warning"
        assert alerts[0]["severity"] == "warning"
        assert "90.0%" in alerts[0]["message"]

    def test_check_cost_thresholds_daily_exceeded(self):
        """FAIL: Test daily cost limit exceeded alert."""
        cost_data = {
            "daily_cost": Decimal("110.00"),
            "daily_threshold": Decimal("100.00"),
            "monthly_cost": Decimal("500.00"),
            "monthly_threshold": Decimal("1000.00")
        }

        alerts = self.cost_service.check_cost_thresholds(cost_data)
        assert len(alerts) == 2  # Warning + Critical
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) == 1
        assert critical_alerts[0]["type"] == "daily_limit_exceeded"

    def test_check_cost_thresholds_monthly_warning(self):
        """FAIL: Test monthly cost threshold warning."""
        cost_data = {
            "daily_cost": Decimal("50.00"),
            "daily_threshold": Decimal("100.00"),
            "monthly_cost": Decimal("900.00"),
            "monthly_threshold": Decimal("1000.00")
        }

        alerts = self.cost_service.check_cost_thresholds(cost_data)
        assert len(alerts) == 2  # Daily info + Monthly warning
        monthly_warning = next(a for a in alerts if a["type"] == "monthly_limit_warning")
        assert monthly_warning["severity"] == "warning"
        assert "90.0%" in monthly_warning["message"]

    def test_would_exceed_monthly_limit(self):
        """FAIL: Test monthly limit exceedance check."""
        tenant_usage = {
            "current_month_cost": Decimal("900.00"),
            "monthly_limit": Decimal("1000.00")
        }

        # Should not exceed
        assert not self.cost_service.would_exceed_monthly_limit(
            tenant_usage, Decimal("50.00")
        )

        # Should exceed
        assert self.cost_service.would_exceed_monthly_limit(
            tenant_usage, Decimal("150.00")
        )


class TestStripeBillingIntegration:
    """Test Stripe billing integration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    @patch('src.services.cost_service.stripe')
    @pytest.mark.asyncio
    async def test_record_billing_event_success(self, mock_stripe):
        """FAIL: Test successful billing event recording in Stripe."""
        # Mock Stripe response
        mock_event = Mock()
        mock_event.id = "evt_123456"
        mock_stripe.billing.meter_event.create.return_value = mock_event

        with patch.object(settings, 'STRIPE_SECRET_KEY', 'sk_test_123'):
            with patch.object(settings, 'STRIPE_AI_LABEL_METER_ID', 'meter_123'):
                await self.cost_service.record_billing_event(
                    tenant_id="tenant_123",
                    amount=Decimal("12.50"),
                    usage_data={"tokens": 1500, "model": "gpt-4o"}
                )

                mock_stripe.billing.meter_event.create.assert_called_once()
                call_args = mock_stripe.billing.meter_event.create.call_args[1]
                assert call_args["event_name"] == "ai_label_usage"
                assert call_args["payload"]["stripe_customer_id"] == "tenant_123"
                assert call_args["payload"]["value"] == "1500"
                assert call_args["meter"] == "meter_123"

    @patch('src.services.cost_service.stripe')
    @pytest.mark.asyncio
    async def test_record_billing_event_no_meter_id(self, mock_stripe):
        """FAIL: Test billing event recording with no meter ID configured."""
        with patch.object(settings, 'STRIPE_SECRET_KEY', 'sk_test_123'):
            with patch.object(settings, 'STRIPE_AI_LABEL_METER_ID', None):
                await self.cost_service.record_billing_event(
                    tenant_id="tenant_123",
                    amount=Decimal("12.50"),
                    usage_data={"tokens": 1500}
                )

                mock_stripe.billing.meter_event.create.assert_not_called()

    @patch('src.services.cost_service.stripe')
    @patch('src.services.cost_service.logger')
    @pytest.mark.asyncio
    async def test_record_billing_event_failure(self, mock_logger, mock_stripe):
        """FAIL: Test billing event recording failure handling."""
        mock_stripe.billing.meter_event.create.side_effect = Exception("Stripe error")

        with patch.object(settings, 'STRIPE_SECRET_KEY', 'sk_test_123'):
            with patch.object(settings, 'STRIPE_AI_LABEL_METER_ID', 'meter_123'):
                await self.cost_service.record_billing_event(
                    tenant_id="tenant_123",
                    amount=Decimal("12.50"),
                    usage_data={"tokens": 1500}
                )

                mock_logger.error.assert_called_once()
                assert "Failed to record billing event" in mock_logger.error.call_args[0][0]


class TestUsageTracking:
    """Test usage tracking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    @pytest.mark.asyncio
    async def test_track_usage_new_tenant(self):
        """FAIL: Test usage tracking for new tenant."""
        await self.cost_service._track_usage(
            tenant_id="new_tenant",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            cost=Decimal("12.50")
        )

        usage = self.cost_service._tenant_usage["new_tenant"]
        assert usage["monthly_tokens"] == 1500
        assert usage["monthly_cost"] == Decimal("12.50")
        assert usage["model_usage"]["gpt-4o"] == 1

    @pytest.mark.asyncio
    async def test_track_usage_existing_tenant(self):
        """FAIL: Test usage tracking for existing tenant."""
        # Set up existing usage
        self.cost_service._tenant_usage["existing_tenant"] = {
            "monthly_tokens": 5000,
            "monthly_cost": Decimal("50.00"),
            "model_usage": {"gpt-4o": 3, "claude-3-5-sonnet": 2}
        }

        await self.cost_service._track_usage(
            tenant_id="existing_tenant",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            cost=Decimal("12.50")
        )

        usage = self.cost_service._tenant_usage["existing_tenant"]
        assert usage["monthly_tokens"] == 6500  # 5000 + 1500
        assert usage["monthly_cost"] == Decimal("62.50")  # 50.00 + 12.50
        assert usage["model_usage"]["gpt-4o"] == 4  # 3 + 1

    def test_get_usage_report_existing_tenant(self):
        """FAIL: Test getting usage report for existing tenant."""
        # Set up existing usage
        self.cost_service._tenant_usage["tenant_123"] = {
            "monthly_tokens": 15000,
            "monthly_cost": Decimal("150.00"),
            "model_usage": {"gpt-4o": 10, "claude-3-5-sonnet": 5}
        }

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        report = self.cost_service.get_usage_report(
            tenant_id="tenant_123",
            start_date=start_date,
            end_date=end_date
        )

        assert report["tenant_id"] == "tenant_123"
        assert report["usage"]["monthly_tokens"] == 15000
        assert report["usage"]["monthly_cost"] == Decimal("150.00")
        assert report["usage"]["model_usage"]["gpt-4o"] == 10

    def test_get_usage_report_nonexistent_tenant(self):
        """FAIL: Test getting usage report for nonexistent tenant."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 31)

        report = self.cost_service.get_usage_report(
            tenant_id="nonexistent_tenant",
            start_date=start_date,
            end_date=end_date
        )

        assert report["tenant_id"] == "nonexistent_tenant"
        assert report["usage"]["monthly_tokens"] == 0
        assert report["usage"]["monthly_cost"] == Decimal("0")
        assert report["usage"]["model_usage"] == {}


class TestPricingUpdates:
    """Test pricing update functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_update_model_pricing_success(self):
        """FAIL: Test successful model pricing update."""
        original_input_cost = self.cost_service._model_pricing["gpt-4o"].input_token_cost

        self.cost_service.update_model_pricing(
            model="gpt-4o",
            input_cost=Decimal("0.0045"),
            output_cost=Decimal("0.014"),
            valid_until=datetime.utcnow() + timedelta(days=30)
        )

        pricing = self.cost_service._model_pricing["gpt-4o"]
        assert pricing.input_token_cost == Decimal("0.0045")
        assert pricing.output_token_cost == Decimal("0.014")
        assert pricing.valid_until is not None
        assert pricing.updated_at > datetime.utcnow() - timedelta(seconds=1)
        assert pricing.input_token_cost != original_input_cost

    def test_update_model_pricing_nonexistent_model(self):
        """FAIL: Test updating pricing for nonexistent model raises error."""
        with pytest.raises(ValueError, match="Model not found"):
            self.cost_service.update_model_pricing(
                model="nonexistent-model",
                input_cost=Decimal("0.005"),
                output_cost=Decimal("0.015")
            )

    @patch('src.services.cost_service.logger')
    def test_refresh_pricing(self, mock_logger):
        """FAIL: Test pricing refresh functionality."""
        self.cost_service._refresh_pricing("gpt-4o")
        mock_logger.info.assert_called_once_with("Refreshing pricing for model: gpt-4o")


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    @pytest.mark.asyncio
    async def test_calculate_cost_zero_tokens(self):
        """FAIL: Test cost calculation with zero tokens."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=0,
            completion_tokens=0
        )

        assert cost == Decimal("0.000000")

    @pytest.mark.asyncio
    async def test_calculate_cost_negative_tokens(self):
        """FAIL: Test cost calculation with negative tokens raises error."""
        with pytest.raises(ValueError):
            await self.cost_service.calculate_cost(
                model="gpt-4o",
                prompt_tokens=-100,
                completion_tokens=0
            )

    @pytest.mark.asyncio
    async def test_calculate_cost_very_large_numbers(self):
        """FAIL: Test cost calculation with very large token numbers."""
        large_tokens = 10_000_000  # 10M tokens

        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=large_tokens,
            completion_tokens=large_tokens
        )

        # Should handle large numbers without overflow
        assert isinstance(cost, Decimal)
        assert cost > Decimal("0")

        # Verify precision is maintained
        assert cost.as_tuple().exponent <= -settings.BILLING_PRECISION

    @pytest.mark.asyncio
    async def test_calculate_cost_maximum_precision(self):
        """FAIL: Test cost calculation maintains maximum precision."""
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=1,
            completion_tokens=1
        )

        # Should maintain configured precision even for small amounts
        expected_precision = -settings.BILLING_PRECISION
        assert cost.as_tuple().exponent <= expected_precision

    def test_convert_currency_zero_amount(self):
        """FAIL: Test currency conversion with zero amount."""
        converted = self.cost_service.convert_currency(
            Decimal("0"), "USD", "EUR"
        )
        assert converted == Decimal("0")

    def test_convert_currency_negative_amount(self):
        """FAIL: Test currency conversion with negative amount."""
        converted = self.cost_service.convert_currency(
            Decimal("-100.00"), "USD", "EUR"
        )
        assert converted < Decimal("0")
        assert converted == Decimal("-92.00")


class TestPerformanceAndConcurrency:
    """Test performance and concurrency handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    @pytest.mark.asyncio
    async def test_concurrent_cost_calculations(self):
        """FAIL: Test concurrent cost calculations don't interfere."""
        async def calculate_and_track(tenant_id: str, tokens: int):
            return await self.cost_service.calculate_cost(
                model="gpt-4o",
                prompt_tokens=tokens,
                completion_tokens=tokens // 2,
                tenant_id=tenant_id
            )

        # Run 100 concurrent calculations
        tasks = [
            calculate_and_track(f"tenant_{i}", 1000 + i * 100)
            for i in range(100)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 100
        assert all(isinstance(r, Decimal) for r in results)

        # Verify tenant usage is tracked correctly
        for i in range(100):
            tenant_id = f"tenant_{i}"
            if tenant_id in self.cost_service._tenant_usage:
                usage = self.cost_service._tenant_usage[tenant_id]
                assert usage["monthly_tokens"] > 0
                assert usage["monthly_cost"] > Decimal("0")

    @pytest.mark.asyncio
    async def test_performance_large_volume_calculations(self):
        """FAIL: Test performance with large volume of calculations."""
        import time

        start_time = time.time()

        # Perform 1000 cost calculations
        for i in range(1000):
            await self.cost_service.calculate_cost(
                model="gpt-4o",
                prompt_tokens=1000,
                completion_tokens=500
            )

        duration = time.time() - start_time

        # Should complete within reasonable time (adjust threshold as needed)
        assert duration < 5.0  # 5 seconds

    def test_memory_usage_with_large_tenant_count(self):
        """FAIL: Test memory usage doesn't grow excessively with many tenants."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Create usage for 1000 tenants
        for i in range(1000):
            self.cost_service._tenant_usage[f"tenant_{i}"] = {
                "monthly_tokens": 10000,
                "monthly_cost": Decimal("100.00"),
                "model_usage": {"gpt-4o": 100}
            }

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (less than 100MB)
        assert memory_increase < 100 * 1024 * 1024  # 100MB


class TestIntegrationWithUsageModels:
    """Test integration with usage tracking models."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()
        self.mock_session = Mock()

    @pytest.mark.asyncio
    async def test_create_token_usage_from_calculation(self):
        """FAIL: Test creating TokenUsage record from cost calculation."""
        calc = CostCalculation(
            model="gpt-4o",
            provider=AIProvider.OPENAI,
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            input_cost=Decimal("5.00"),
            output_cost=Decimal("7.50"),
            total_cost=Decimal("12.50"),
            input_rate=Decimal("0.005"),
            output_rate=Decimal("0.015"),
            tenant_id="tenant_123"
        )

        # Mock the database operations
        self.mock_session.add = Mock()
        self.mock_session.commit = AsyncMock()
        self.mock_session.refresh = AsyncMock()

        # Import and test the function
        from src.models.usage_tracking import create_token_usage

        with patch('src.models.usage_tracking.update_tenant_usage') as mock_update:
            token_usage = await create_token_usage(
                session=self.mock_session,
                tenant_id=calc.tenant_id,
                request_id="req_123",
                model=calc.model,
                provider=calc.provider.value,
                prompt_tokens=calc.prompt_tokens,
                completion_tokens=calc.completion_tokens,
                input_cost=calc.input_cost,
                output_cost=calc.output_cost,
                total_cost=calc.total_cost,
                response_time_ms=1500.0,
                success=True
            )

            assert isinstance(token_usage, TokenUsage)
            assert token_usage.tenant_id == calc.tenant_id
            assert token_usage.model == calc.model
            assert token_usage.provider == calc.provider.value
            assert token_usage.total_cost == calc.total_cost
            self.mock_session.add.assert_called_once()
            self.mock_session.commit.assert_called_once()


# Advanced test scenarios for production readiness

class TestFinancialAccuracy:
    """Test financial accuracy and compliance."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    def test_financial_precision_maintained(self):
        """FAIL: Test financial precision is maintained throughout calculations."""
        # Use values that require high precision
        result = self.cost_service.calculate_total_cost([
            CostCalculation(
                model="gpt-4o",
                provider=AIProvider.OPENAI,
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                input_cost=Decimal("0.000005"),
                output_cost=Decimal("0.000015"),
                total_cost=Decimal("0.000020"),
                input_rate=Decimal("0.005"),
                output_rate=Decimal("0.015"),
                tenant_id="tenant_123"
            )
        ])

        # Should maintain exact precision
        assert result == Decimal("0.000020")
        assert result.as_tuple().exponent <= -6

    def test_rounding_consistency(self):
        """FAIL: Test rounding is consistent and predictable."""
        # Test rounding edge cases
        test_cases = [
            (Decimal("0.000001"), Decimal("0.000001")),
            (Decimal("0.000004"), Decimal("0.000004")),
            (Decimal("0.000005"), Decimal("0.000005")),  # Round up
            (Decimal("0.000009"), Decimal("0.000009")),
        ]

        for input_val, expected in test_cases:
            result = self.cost_service.calculate_total_cost([
                CostCalculation(
                    model="test",
                    provider=AIProvider.OPENAI,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    input_cost=Decimal("0"),
                    output_cost=Decimal("0"),
                    total_cost=input_val,
                    input_rate=Decimal("0"),
                    output_rate=Decimal("0"),
                    tenant_id="tenant_123"
                )
            ])
            assert result == expected

    @pytest.mark.asyncio
    async def test_no_floating_point_errors(self):
        """FAIL: Test no floating point precision errors in calculations."""
        # This should use Decimal throughout, never float
        cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=333,
            completion_tokens=667
        )

        # Verify it's a Decimal with proper precision
        assert isinstance(cost, Decimal)
        # Should not have floating point representation issues
        assert cost * Decimal("1000000") == Decimal("12.50") * Decimal("1000000")


class TestCostOptimization:
    """Test cost optimization recommendations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cost_service = CostService()

    @pytest.mark.asyncio
    async def test_cost_comparison_across_models(self):
        """FAIL: Test cost comparison between different models."""
        # Calculate cost for same input across different models
        prompt_tokens = 1000
        completion_tokens = 500

        gpt4_cost = await self.cost_service.calculate_cost(
            model="gpt-4",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        gpt4o_cost = await self.cost_service.calculate_cost(
            model="gpt-4o",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        claude_cost = await self.cost_service.calculate_cost(
            model="claude-3-5-sonnet",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # GPT-4 should be most expensive
        assert gpt4_cost > gpt4o_cost
        assert gpt4_cost > claude_cost

        # Verify actual costs
        # GPT-4: (1000/1000)*0.03 + (500/1000)*0.06 = 0.03 + 0.03 = 0.06
        # GPT-4o: (1000/1000)*0.005 + (500/1000)*0.015 = 0.005 + 0.0075 = 0.0125
        # Claude: (1000/1000)*0.003 + (500/1000)*0.015 = 0.003 + 0.0075 = 0.0105
        assert gpt4_cost == Decimal("0.060000")
        assert gpt4o_cost == Decimal("0.012500")
        assert claude_cost == Decimal("0.010500")

    def test_recommend_cheaper_model(self):
        """FAIL: Test recommending cheaper models for cost optimization."""
        # This would be a new feature to implement
        # For now, test that we can compare costs
        models = ["gpt-4", "gpt-4o", "gpt-3.5-turbo", "claude-3-5-sonnet", "claude-3-haiku"]

        costs = {}
        for model in models:
            # Estimate cost (simplified)
            pricing = self.cost_service.get_model_pricing(model)
            total_rate = pricing.input_token_cost + pricing.output_token_cost
            costs[model] = total_rate

        # Find cheapest model
        cheapest_model = min(costs.items(), key=lambda x: x[1])

        # Should be claude-3-haiku at $0.0015 per 1K tokens
        assert cheapest_model[0] == "claude-3-haiku"
        assert cheapest_model[1] == Decimal("0.001500")  # 0.00025 + 0.00125


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])