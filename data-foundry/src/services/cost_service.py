"""
Cost Service for AI Operations

This service provides accurate cost calculation for AI operations across
different providers, models, and usage patterns.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from src.core.config import settings


class AIProvider(str, Enum):
    """AI Provider enumeration."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    GOOGLE = "google"
    COHERE = "cohere"


class ModelPricing:
    """Model pricing information."""

    def __init__(
        self,
        provider: AIProvider,
        model: str,
        input_token_cost: Decimal,
        output_token_cost: Decimal,
        context_window: int,
        volume_tiers: Optional[Dict[str, Dict[str, Decimal]]] = None,
        currency: str = "USD"
    ):
        self.provider = provider
        self.model = model
        self.input_token_cost = input_token_cost
        self.output_token_cost = output_token_cost
        self.context_window = context_window
        self.volume_tiers = volume_tiers or {}
        self.currency = currency
        self.updated_at = datetime.utcnow()
        self.valid_until = None

    def get_rate(self, token_type: str, volume_tier: str = "default") -> Decimal:
        """Get pricing rate for token type and volume tier."""
        if volume_tier in self.volume_tiers:
            tier_pricing = self.volume_tiers[volume_tier]
            if token_type in tier_pricing:
                return tier_pricing[token_type]

        return getattr(self, f"{token_type}_token_cost")


class CostCalculation:
    """Cost calculation breakdown."""

    def __init__(
        self,
        model: str,
        provider: AIProvider,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        input_cost: Decimal,
        output_cost: Decimal,
        total_cost: Decimal,
        input_rate: Decimal,
        output_rate: Decimal,
        tenant_id: str,
        volume_tier: Optional[str] = None,
        currency: str = "USD"
    ):
        self.model = model
        self.provider = provider
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.input_cost = input_cost
        self.output_cost = output_cost
        self.total_cost = total_cost
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.tenant_id = tenant_id
        self.volume_tier = volume_tier
        self.currency = currency
        self.calculation_date = datetime.utcnow()


class CostService:
    """Service for calculating and tracking AI costs."""

    def __init__(self):
        # Initialize model pricing database
        self._model_pricing: Dict[str, ModelPricing] = {}
        self._load_pricing_data()

        # Exchange rates (simplified - in production use real API)
        self._exchange_rates = {
            "USD": Decimal("1.0"),
            "EUR": Decimal("0.92"),
            "GBP": Decimal("0.79"),
            "JPY": Decimal("149.50")
        }

        # Cost tracking per tenant
        self._tenant_usage: Dict[str, Dict[str, Any]] = {}

    def _load_pricing_data(self):
        """Load current pricing data for all models."""
        # OpenAI pricing (as of 2024)
        self._model_pricing.update({
            "gpt-4o": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4o",
                input_token_cost=Decimal("0.005"),  # $0.005 per 1K
                output_token_cost=Decimal("0.015"),  # $0.015 per 1K
                context_window=128000,
                volume_tiers={
                    "small": {"input": Decimal("0.005"), "output": Decimal("0.015")},
                    "medium": {"input": Decimal("0.0045"), "output": Decimal("0.0135")},
                    "enterprise": {"input": Decimal("0.004"), "output": Decimal("0.012")}
                }
            ),
            "gpt-4-turbo": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4-turbo",
                input_token_cost=Decimal("0.01"),
                output_token_cost=Decimal("0.03"),
                context_window=128000
            ),
            "gpt-4": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4",
                input_token_cost=Decimal("0.03"),
                output_token_cost=Decimal("0.06"),
                context_window=8192
            ),
            "gpt-3.5-turbo": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-3.5-turbo",
                input_token_cost=Decimal("0.0015"),
                output_token_cost=Decimal("0.002"),
                context_window=16385
            ),
        })

        # Anthropic pricing
        self._model_pricing.update({
            "claude-3-5-sonnet": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-5-sonnet",
                input_token_cost=Decimal("0.003"),
                output_token_cost=Decimal("0.015"),
                context_window=200000
            ),
            "claude-3-opus": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-opus",
                input_token_cost=Decimal("0.015"),
                output_token_cost=Decimal("0.075"),
                context_window=200000
            ),
            "claude-3-haiku": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-haiku",
                input_token_cost=Decimal("0.00025"),
                output_token_cost=Decimal("0.00125"),
                context_window=200000
            ),
        })

    def get_model_pricing(self, model: str) -> ModelPricing:
        """Get pricing information for a model."""
        if model not in self._model_pricing:
            raise ValueError(f"No pricing information available for model: {model}")

        pricing = self._model_pricing[model]

        # Check if pricing is still valid
        if pricing.valid_until and datetime.utcnow() > pricing.valid_until:
            self._refresh_pricing(model)
            pricing = self._model_pricing[model]

        return pricing

    async def calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        tenant_id: Optional[str] = None,
        volume_tier: Optional[str] = None,
        currency: str = "USD"
    ) -> Decimal:
        """
        Calculate cost for AI usage.

        Args:
            model: Model name
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used
            tenant_id: Tenant ID for volume pricing
            volume_tier: Volume pricing tier
            currency: Output currency

        Returns:
            Decimal: Total cost in specified currency
        """
        # Get model pricing
        pricing = self.get_model_pricing(model)

        # Determine volume tier
        if not volume_tier and tenant_id:
            volume_tier = self._get_volume_tier(tenant_id)

        # Get rates
        input_rate = pricing.get_rate("input", volume_tier or "default")
        output_rate = pricing.get_rate("output", volume_tier or "default")

        # Calculate costs
        input_cost = (Decimal(prompt_tokens) / Decimal(1000)) * input_rate
        output_cost = (Decimal(completion_tokens) / Decimal(1000)) * output_rate
        total_cost = input_cost + output_cost

        # Apply precision rounding
        total_cost = total_cost.quantize(
            Decimal(f"0.{'0' * (settings.BILLING_PRECISION - 1)}1"),
            rounding=ROUND_HALF_UP
        )

        # Convert currency if needed
        if currency != pricing.currency:
            total_cost = self.convert_currency(total_cost, pricing.currency, currency)

        # Track usage if tenant provided
        if tenant_id:
            await self._track_usage(
                tenant_id=tenant_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=total_cost
            )

        return total_cost

    def estimate_cost(
        self,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        tenant_id: Optional[str] = None,
        currency: str = "USD"
    ) -> Decimal:
        """
        Estimate cost before completion.

        Args:
            model: Model name
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens
            tenant_id: Tenant ID for volume pricing
            currency: Output currency

        Returns:
            Decimal: Estimated cost
        """
        return self.calculate_cost(
            model=model,
            prompt_tokens=estimated_input_tokens,
            completion_tokens=estimated_output_tokens,
            tenant_id=tenant_id,
            currency=currency
        )

    def calculate_total_cost(
        self,
        calculations: List[CostCalculation]
    ) -> Decimal:
        """Calculate total cost from multiple calculations."""
        total = Decimal("0")
        for calc in calculations:
            total += calc.total_cost
        return total

    def convert_currency(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str
    ) -> Decimal:
        """Convert amount between currencies."""
        if from_currency == to_currency:
            return amount

        if from_currency not in self._exchange_rates:
            raise ValueError(f"Unsupported currency: {from_currency}")

        if to_currency not in self._exchange_rates:
            raise ValueError(f"Unsupported currency: {to_currency}")

        # Convert to USD first, then to target
        usd_amount = amount / self._exchange_rates[from_currency]
        target_amount = usd_amount * self._exchange_rates[to_currency]

        return target_amount.quantize(
            Decimal(f"0.{'0' * (settings.BILLING_PRECISION - 1)}1"),
            rounding=ROUND_HALF_UP
        )

    def update_model_pricing(
        self,
        model: str,
        input_cost: Decimal,
        output_cost: Decimal,
        valid_until: Optional[datetime] = None
    ):
        """Update pricing for a model."""
        if model not in self._model_pricing:
            raise ValueError(f"Model not found: {model}")

        pricing = self._model_pricing[model]
        pricing.input_token_cost = input_cost
        pricing.output_token_cost = output_cost
        pricing.updated_at = datetime.utcnow()
        pricing.valid_until = valid_until

    def _get_volume_tier(self, tenant_id: str) -> str:
        """Determine volume tier for tenant based on usage."""
        # This would typically query the database for tenant usage
        # For now, return default tier
        return "default"

    async def _track_usage(
        self,
        tenant_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: Decimal
    ):
        """Track usage for billing and analytics."""
        if tenant_id not in self._tenant_usage:
            self._tenant_usage[tenant_id] = {
                "monthly_tokens": 0,
                "monthly_cost": Decimal("0"),
                "model_usage": {}
            }

        usage = self._tenant_usage[tenant_id]
        usage["monthly_tokens"] += prompt_tokens + completion_tokens
        usage["monthly_cost"] += cost

        if model not in usage["model_usage"]:
            usage["model_usage"][model] = 0
        usage["model_usage"][model] += 1

    def would_exceed_monthly_limit(
        self,
        tenant_usage: Dict[str, Any],
        additional_cost: Decimal
    ) -> bool:
        """Check if additional cost would exceed monthly limit."""
        current_cost = tenant_usage.get("current_month_cost", Decimal("0"))
        monthly_limit = tenant_usage.get("monthly_limit", Decimal("0"))

        return (current_cost + additional_cost) > monthly_limit

    def check_cost_thresholds(
        self,
        cost_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Check cost thresholds and generate alerts."""
        alerts = []

        # Daily threshold check
        daily_cost = cost_data.get("daily_cost", Decimal("0"))
        daily_threshold = cost_data.get("daily_threshold", Decimal("0"))

        if daily_threshold > 0:
            daily_percentage = (daily_cost / daily_threshold) * 100

            if daily_percentage >= 100:
                alerts.append({
                    "type": "daily_limit_exceeded",
                    "message": f"Daily cost limit exceeded: ${daily_cost} > ${daily_threshold}",
                    "severity": "critical"
                })
            elif daily_percentage >= 90:
                alerts.append({
                    "type": "daily_limit_warning",
                    "message": f"Daily cost at {daily_percentage:.1f}% of limit",
                    "severity": "warning"
                })
            elif daily_percentage >= 50:
                alerts.append({
                    "type": "daily_limit_info",
                    "message": f"Daily cost at {daily_percentage:.1f}% of limit",
                    "severity": "info"
                })

        # Monthly threshold check
        monthly_cost = cost_data.get("monthly_cost", Decimal("0"))
        monthly_threshold = cost_data.get("monthly_threshold", Decimal("0"))

        if monthly_threshold > 0:
            monthly_percentage = (monthly_cost / monthly_threshold) * 100

            if monthly_percentage >= 100:
                alerts.append({
                    "type": "monthly_limit_exceeded",
                    "message": f"Monthly cost limit exceeded: ${monthly_cost} > ${monthly_threshold}",
                    "severity": "critical"
                })
            elif monthly_percentage >= 90:
                alerts.append({
                    "type": "monthly_limit_warning",
                    "message": f"Monthly cost at {monthly_percentage:.1f}% of limit",
                    "severity": "warning"
                })

        return alerts

    async def record_billing_event(
        self,
        tenant_id: str,
        amount: Decimal,
        usage_data: Dict[str, Any]
    ):
        """Record billing event in Stripe."""
        try:
            import stripe

            # Initialize Stripe with secret key
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Create meter event
            if settings.STRIPE_AI_LABEL_METER_ID:
                event = stripe.billing.meter_event.create(
                    event_name="ai_label_usage",
                    payload={
                        "value": str(usage_data.get("tokens", 0)),
                        "stripe_customer_id": tenant_id
                    },
                    timestamp=int(datetime.utcnow().timestamp()),
                    meter=settings.STRIPE_AI_LABEL_METER_ID
                )

                logger.info(f"Recorded billing event: {event.id}")

        except Exception as e:
            logger.error(f"Failed to record billing event: {str(e)}")

    def _refresh_pricing(self, model: str):
        """Refresh pricing data for a model from provider."""
        # In production, this would fetch latest pricing from provider APIs
        logger.info(f"Refreshing pricing for model: {model}")
        pass

    def get_usage_report(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Generate usage report for tenant."""
        # This would typically query the database
        # For now, return cached data
        if tenant_id in self._tenant_usage:
            return {
                "tenant_id": tenant_id,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "usage": self._tenant_usage[tenant_id]
            }

        return {
            "tenant_id": tenant_id,
            "usage": {
                "monthly_tokens": 0,
                "monthly_cost": Decimal("0"),
                "model_usage": {}
            }
        }