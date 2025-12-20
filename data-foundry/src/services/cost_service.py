"""
Cost Service for AI Operations

This service provides accurate cost calculation for AI operations across
different providers, models, and usage patterns.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from functools import lru_cache, wraps
from threading import Lock
import time
import hashlib

from src.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    """AI Provider enumeration."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    GOOGLE = "google"
    COHERE = "cohere"
    MISTRAL = "mistral"
    PERPLEXITY = "perplexity"
    TOGETHER = "together"
    FIREWORKS = "fireworks"


class ModelPricing:
    """Enhanced model pricing information with additional features."""

    def __init__(
        self,
        provider: AIProvider,
        model: str,
        input_token_cost: Decimal,
        output_token_cost: Decimal,
        context_window: int,
        volume_tiers: Optional[Dict[str, Dict[str, Decimal]]] = None,
        currency: str = "USD",
        max_tokens_per_request: Optional[int] = None,
        training_data_cutoff: Optional[datetime] = None,
        capabilities: Optional[List[str]] = None,
        hidden_region: Optional[str] = None,
        additional_fees: Optional[Dict[str, Decimal]] = None
    ):
        self.provider = provider
        self.model = model
        self.input_token_cost = input_token_cost
        self.output_token_cost = output_token_cost
        self.context_window = context_window
        self.volume_tiers = volume_tiers or {}
        self.currency = currency
        self.max_tokens_per_request = max_tokens_per_request or context_window
        self.training_data_cutoff = training_data_cutoff
        self.capabilities = capabilities or []
        self.hidden_region = hidden_region
        self.additional_fees = additional_fees or {}
        self.updated_at = datetime.utcnow()
        self.valid_until = None

    def get_rate(self, token_type: str, volume_tier: str = "default") -> Decimal:
        """Get pricing rate for token type and volume tier."""
        if volume_tier in self.volume_tiers:
            tier_pricing = self.volume_tiers[volume_tier]
            if token_type in tier_pricing:
                return tier_pricing[token_type]

        return getattr(self, f"{token_type}_token_cost")

    def get_effective_rate(
        self,
        token_type: str,
        volume_tier: str = "default",
        include_fees: bool = True
    ) -> Decimal:
        """Get effective rate including any additional fees."""
        base_rate = self.get_rate(token_type, volume_tier)

        if not include_fees or not self.additional_fees:
            return base_rate

        # Add proportional fees
        total_fee = Decimal("0")
        for fee_name, fee_amount in self.additional_fees.items():
            if "percentage" in fee_name.lower():
                # Percentage-based fee
                total_fee += base_rate * (fee_amount / Decimal("100"))
            elif "per_token" in fee_name.lower():
                # Per-token fee
                total_fee += fee_amount / Decimal("1000")  # Convert to per-1K tokens
            else:
                # Fixed fee (not applicable to rate calculation)
                pass

        return base_rate + total_fee

    def supports_capability(self, capability: str) -> bool:
        """Check if model supports a specific capability."""
        return capability in self.capabilities

    def get_tier_discount_percentage(self, volume_tier: str) -> Decimal:
        """Calculate discount percentage for a volume tier."""
        if volume_tier == "default" or volume_tier not in self.volume_tiers:
            return Decimal("0")

        tier_rate = self.volume_tiers[volume_tier].get("input", self.input_token_cost)
        discount = (self.input_token_cost - tier_rate) / self.input_token_cost * Decimal("100")
        return max(discount, Decimal("0"))

    def estimate_tokens_for_content(self, content: str) -> int:
        """Estimate token count for content (rough approximation)."""
        # Rough estimation: ~4 characters per token
        return max(1, len(content) // 4)

    def is_cost_effective_for(self, input_tokens: int, output_tokens: int) -> bool:
        """Check if this model is cost-effective for given token usage."""
        # Compare against similar models (simplified)
        base_cost = (input_tokens + output_tokens) * self.input_token_cost / Decimal("1000")

        # Model is cost-effective if cost per token is below average
        return self.input_token_cost < Decimal("0.01")  # Below 1 cent per 1K tokens

    @property
    def is_current(self) -> bool:
        """Check if pricing data is still current."""
        if not self.valid_until:
            return True
        return datetime.utcnow() < self.valid_until


class CostCalculation:
    """Enhanced cost calculation breakdown with detailed analytics."""

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
        currency: str = "USD",
        discount_applied: Optional[Decimal] = None,
        fees_applied: Optional[Dict[str, Decimal]] = None,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
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
        self.discount_applied = discount_applied or Decimal("0")
        self.fees_applied = fees_applied or {}
        self.request_id = request_id
        self.user_id = user_id
        self.metadata = metadata or {}
        self.calculation_date = datetime.utcnow()

    @property
    def cost_per_token(self) -> Decimal:
        """Calculate cost per token."""
        if self.total_tokens == 0:
            return Decimal("0")
        return self.total_cost / Decimal(self.total_tokens)

    @property
    def cost_per_thousand_tokens(self) -> Decimal:
        """Calculate cost per 1000 tokens."""
        return self.cost_per_token * Decimal("1000")

    @property
    def input_output_ratio(self) -> Decimal:
        """Calculate input to output token ratio."""
        if self.completion_tokens == 0:
            return Decimal("0")
        return Decimal(self.prompt_tokens) / Decimal(self.completion_tokens)

    @property
    def effective_discount_percentage(self) -> Decimal:
        """Calculate effective discount percentage applied."""
        if self.total_cost + self.discount_applied == 0:
            return Decimal("0")
        return self.discount_applied / (self.total_cost + self.discount_applied) * Decimal("100")

    def add_fee(self, fee_name: str, amount: Decimal):
        """Add a fee to the calculation."""
        self.fees_applied[fee_name] = amount
        self.total_cost += amount

    def apply_discount(self, discount_amount: Decimal):
        """Apply a discount to the calculation."""
        self.discount_applied += discount_amount
        self.total_cost = max(Decimal("0"), self.total_cost - discount_amount)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "model": self.model,
            "provider": self.provider.value,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "input_cost": float(self.input_cost),
            "output_cost": float(self.output_cost),
            "total_cost": float(self.total_cost),
            "input_rate": float(self.input_rate),
            "output_rate": float(self.output_rate),
            "tenant_id": self.tenant_id,
            "volume_tier": self.volume_tier,
            "currency": self.currency,
            "discount_applied": float(self.discount_applied),
            "fees_applied": {k: float(v) for k, v in self.fees_applied.items()},
            "cost_per_token": float(self.cost_per_token),
            "cost_per_thousand_tokens": float(self.cost_per_thousand_tokens),
            "input_output_ratio": float(self.input_output_ratio),
            "effective_discount_percentage": float(self.effective_discount_percentage),
            "request_id": self.request_id,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "calculation_date": self.calculation_date.isoformat()
        }


class CostService:
    """Enhanced service for calculating and tracking AI costs with caching and optimizations."""

    def __init__(self, enable_cache: bool = True, cache_ttl: int = 3600):
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

        # Performance and caching
        self._enable_cache = enable_cache
        self._cache_ttl = cache_ttl
        self._calculation_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = Lock()
        self._pricing_cache_timestamp = 0
        self._exchange_rate_cache_timestamp = 0

        # Performance metrics
        self._performance_metrics = {
            "calculations_performed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_calculation_time": 0,
            "total_calculation_time": 0
        }

    def _generate_cache_key(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        volume_tier: str,
        currency: str,
        include_fees: bool
    ) -> str:
        """Generate cache key for cost calculation."""
        key_data = f"{model}:{prompt_tokens}:{completion_tokens}:{volume_tier}:{currency}:{include_fees}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[CostCalculation]:
        """Get calculation result from cache if still valid."""
        if not self._enable_cache:
            return None

        with self._cache_lock:
            if cache_key in self._calculation_cache:
                cached_data = self._calculation_cache[cache_key]
                if time.time() - cached_data["timestamp"] < self._cache_ttl:
                    self._performance_metrics["cache_hits"] += 1
                    return cached_data["calculation"]
                else:
                    # Remove expired cache entry
                    del self._calculation_cache[cache_key]

        self._performance_metrics["cache_misses"] += 1
        return None

    def _store_in_cache(self, cache_key: str, calculation: CostCalculation):
        """Store calculation result in cache."""
        if not self._enable_cache:
            return

        with self._cache_lock:
            self._calculation_cache[cache_key] = {
                "calculation": calculation,
                "timestamp": time.time()
            }

            # Limit cache size to prevent memory issues
            if len(self._calculation_cache) > 10000:
                # Remove oldest entries (simple LRU)
                oldest_keys = sorted(
                    self._calculation_cache.keys(),
                    key=lambda k: self._calculation_cache[k]["timestamp"]
                )[:1000]
                for key in oldest_keys:
                    del self._calculation_cache[key]

    @lru_cache(maxsize=1000)
    def _convert_currency_cached(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str
    ) -> Decimal:
        """Cached currency conversion."""
        return self._convert_currency_internal(amount, from_currency, to_currency)

    def _convert_currency_internal(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str
    ) -> Decimal:
        """Internal currency conversion logic."""
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

    def clear_cache(self):
        """Clear all caches."""
        with self._cache_lock:
            self._calculation_cache.clear()
            self._convert_currency_cached.cache_clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self._performance_metrics["cache_hits"] + self._performance_metrics["cache_misses"]
        cache_hit_rate = (
            self._performance_metrics["cache_hits"] / total_requests
            if total_requests > 0 else 0
        )

        return {
            "cache_enabled": self._enable_cache,
            "cache_ttl": self._cache_ttl,
            "cache_size": len(self._calculation_cache),
            "cache_hits": self._performance_metrics["cache_hits"],
            "cache_misses": self._performance_metrics["cache_misses"],
            "cache_hit_rate": round(cache_hit_rate * 100, 2),
            "calculations_performed": self._performance_metrics["calculations_performed"],
            "average_calculation_time": round(
                self._performance_metrics["average_calculation_time"], 4
            )
        }

    def update_exchange_rates(self, new_rates: Dict[str, Decimal]):
        """Update exchange rates and clear cache."""
        self._exchange_rates.update(new_rates)
        self._exchange_rate_cache_timestamp = time.time()
        self._convert_currency_cached.cache_clear()
        logger.info(f"Updated exchange rates: {new_rates}")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics."""
        return {
            **self._performance_metrics,
            "cache_stats": self.get_cache_stats(),
            "tenant_count": len(self._tenant_usage),
            "model_count": len(self._model_pricing),
            "uptime_seconds": time.time() - self._performance_metrics.get("start_time", time.time())
        }

    def _load_pricing_data(self):
        """Load current pricing data for all models with comprehensive coverage."""

        # OpenAI pricing (as of 2024)
        self._model_pricing.update({
            "gpt-4o": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4o",
                input_token_cost=Decimal("0.005"),  # $0.005 per 1K
                output_token_cost=Decimal("0.015"),  # $0.015 per 1K
                context_window=128000,
                capabilities=["text", "vision", "function_calling", "json_mode"],
                training_data_cutoff=datetime(2023, 10, 1),
                volume_tiers={
                    "small": {"input": Decimal("0.005"), "output": Decimal("0.015")},
                    "medium": {"input": Decimal("0.0045"), "output": Decimal("0.0135")},
                    "large": {"input": Decimal("0.0042"), "output": Decimal("0.0126")},
                    "enterprise": {"input": Decimal("0.004"), "output": Decimal("0.012")}
                }
            ),
            "gpt-4o-mini": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4o-mini",
                input_token_cost=Decimal("0.00015"),  # $0.00015 per 1K
                output_token_cost=Decimal("0.0006"),   # $0.0006 per 1K
                context_window=128000,
                capabilities=["text", "vision", "function_calling"],
                training_data_cutoff=datetime(2023, 10, 1)
            ),
            "gpt-4-turbo": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4-turbo",
                input_token_cost=Decimal("0.01"),
                output_token_cost=Decimal("0.03"),
                context_window=128000,
                capabilities=["text", "vision", "function_calling", "json_mode"],
                training_data_cutoff=datetime(2023, 12, 1)
            ),
            "gpt-4": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-4",
                input_token_cost=Decimal("0.03"),
                output_token_cost=Decimal("0.06"),
                context_window=8192,
                capabilities=["text", "function_calling"],
                training_data_cutoff=datetime(2021, 9, 1)
            ),
            "gpt-3.5-turbo": ModelPricing(
                provider=AIProvider.OPENAI,
                model="gpt-3.5-turbo",
                input_token_cost=Decimal("0.0015"),
                output_token_cost=Decimal("0.002"),
                context_window=16385,
                capabilities=["text", "function_calling"],
                training_data_cutoff=datetime(2021, 9, 1)
            ),
        })

        # Anthropic pricing
        self._model_pricing.update({
            "claude-3-5-sonnet": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-5-sonnet",
                input_token_cost=Decimal("0.003"),
                output_token_cost=Decimal("0.015"),
                context_window=200000,
                capabilities=["text", "vision", "function_calling"],
                training_data_cutoff=datetime(2024, 4, 1),
                volume_tiers={
                    "small": {"input": Decimal("0.003"), "output": Decimal("0.015")},
                    "medium": {"input": Decimal("0.0027"), "output": Decimal("0.0135")},
                    "large": {"input": Decimal("0.0024"), "output": Decimal("0.012")},
                    "enterprise": {"input": Decimal("0.0021"), "output": Decimal("0.0105")}
                }
            ),
            "claude-3-opus": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-opus",
                input_token_cost=Decimal("0.015"),
                output_token_cost=Decimal("0.075"),
                context_window=200000,
                capabilities=["text", "vision", "function_calling"],
                training_data_cutoff=datetime(2024, 2, 1)
            ),
            "claude-3-haiku": ModelPricing(
                provider=AIProvider.ANTHROPIC,
                model="claude-3-haiku",
                input_token_cost=Decimal("0.00025"),
                output_token_cost=Decimal("0.00125"),
                context_window=200000,
                capabilities=["text", "vision"],
                training_data_cutoff=datetime(2024, 2, 1)
            ),
        })

        # Google Gemini pricing
        self._model_pricing.update({
            "gemini-1.5-pro": ModelPricing(
                provider=AIProvider.GOOGLE,
                model="gemini-1.5-pro",
                input_token_cost=Decimal("0.0035"),
                output_token_cost=Decimal("0.0105"),
                context_window=2097152,  # 2M tokens
                capabilities=["text", "vision", "audio", "video", "function_calling"],
                training_data_cutoff=datetime(2024, 2, 1),
                volume_tiers={
                    "small": {"input": Decimal("0.0035"), "output": Decimal("0.0105")},
                    "medium": {"input": Decimal("0.00315"), "output": Decimal("0.00945")},
                    "large": {"input": Decimal("0.0028"), "output": Decimal("0.0084")},
                    "enterprise": {"input": Decimal("0.00245"), "output": Decimal("0.00735")}
                }
            ),
            "gemini-1.5-flash": ModelPricing(
                provider=AIProvider.GOOGLE,
                model="gemini-1.5-flash",
                input_token_cost=Decimal("0.000075"),
                output_token_cost=Decimal("0.00015"),
                context_window=1048576,  # 1M tokens
                capabilities=["text", "vision", "audio", "function_calling"],
                training_data_cutoff=datetime(2024, 2, 1)
            ),
        })

        # Mistral AI pricing
        self._model_pricing.update({
            "mistral-large": ModelPricing(
                provider=AIProvider.MISTRAL,
                model="mistral-large",
                input_token_cost=Decimal("0.008"),
                output_token_cost=Decimal("0.024"),
                context_window=32000,
                capabilities=["text", "function_calling", "json_mode"],
                training_data_cutoff=datetime(2024, 4, 1)
            ),
            "mistral-medium": ModelPricing(
                provider=AIProvider.MISTRAL,
                model="mistral-medium",
                input_token_cost=Decimal("0.0027"),
                output_token_cost=Decimal("0.0081"),
                context_window=32000,
                capabilities=["text", "function_calling"],
                training_data_cutoff=datetime(2024, 3, 1)
            ),
            "mistral-small": ModelPricing(
                provider=AIProvider.MISTRAL,
                model="mistral-small",
                input_token_cost=Decimal("0.00022"),
                output_token_cost=Decimal("0.00066"),
                context_window=32000,
                capabilities=["text"],
                training_data_cutoff=datetime(2024, 3, 1)
            ),
        })

        # Cohere pricing
        self._model_pricing.update({
            "command-r-plus": ModelPricing(
                provider=AIProvider.COHERE,
                model="command-r-plus",
                input_token_cost=Decimal("0.003"),
                output_token_cost=Decimal("0.015"),
                context_window=128000,
                capabilities=["text", "function_calling", "rag"],
                training_data_cutoff=datetime(2024, 3, 1)
            ),
            "command-r": ModelPricing(
                provider=AIProvider.COHERE,
                model="command-r",
                input_token_cost=Decimal("0.0005"),
                output_token_cost=Decimal("0.0015"),
                context_window=128000,
                capabilities=["text", "function_calling", "rag"],
                training_data_cutoff=datetime(2024, 2, 1)
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
        currency: str = "USD",
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        include_fees: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CostCalculation:
        """
        Calculate cost for AI usage with enhanced features and caching.

        Args:
            model: Model name
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used
            tenant_id: Tenant ID for volume pricing
            volume_tier: Volume pricing tier
            currency: Output currency
            request_id: Request identifier for tracking
            user_id: User identifier for tracking
            include_fees: Whether to include additional fees
            metadata: Additional metadata for the calculation

        Returns:
            CostCalculation: Detailed cost calculation breakdown
        """
        start_time = time.time()

        # Validate inputs
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("Token counts cannot be negative")

        if not model:
            raise ValueError("Model name is required")

        # Determine volume tier for caching
        if not volume_tier and tenant_id:
            volume_tier = self._get_volume_tier(tenant_id)
        volume_tier = volume_tier or "default"

        # Check cache first (for calculations without tenant-specific data)
        if not tenant_id and not metadata:  # Only cache generic calculations
            cache_key = self._generate_cache_key(
                model, prompt_tokens, completion_tokens, volume_tier, currency, include_fees
            )
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

        # Get model pricing
        pricing = self.get_model_pricing(model)

        # Determine volume tier
        if not volume_tier and tenant_id:
            volume_tier = self._get_volume_tier(tenant_id)
        volume_tier = volume_tier or "default"

        # Get rates (include fees if requested)
        input_rate = pricing.get_effective_rate("input", volume_tier, include_fees)
        output_rate = pricing.get_effective_rate("output", volume_tier, include_fees)

        # Calculate costs
        input_cost = (Decimal(prompt_tokens) / Decimal(1000)) * input_rate
        output_cost = (Decimal(completion_tokens) / Decimal(1000)) * output_rate
        total_tokens = prompt_tokens + completion_tokens
        total_cost = input_cost + output_cost

        # Apply precision rounding with financial accuracy
        precision_string = f"0.{'0' * (settings.BILLING_PRECISION - 1)}1"
        input_cost = input_cost.quantize(Decimal(precision_string), rounding=ROUND_HALF_UP)
        output_cost = output_cost.quantize(Decimal(precision_string), rounding=ROUND_HALF_UP)
        total_cost = total_cost.quantize(Decimal(precision_string), rounding=ROUND_HALF_UP)

        # Convert currency if needed
        if currency != pricing.currency:
            input_cost = self.convert_currency(input_cost, pricing.currency, currency)
            output_cost = self.convert_currency(output_cost, pricing.currency, currency)
            total_cost = self.convert_currency(total_cost, pricing.currency, currency)
            # Convert rates for display purposes
            input_rate = self.convert_currency(input_rate, pricing.currency, currency)
            output_rate = self.convert_currency(output_rate, pricing.currency, currency)

        # Create detailed calculation object
        calculation = CostCalculation(
            model=model,
            provider=pricing.provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            input_rate=input_rate,
            output_rate=output_rate,
            tenant_id=tenant_id or "default",
            volume_tier=volume_tier,
            currency=currency,
            request_id=request_id,
            user_id=user_id,
            metadata=metadata or {}
        )

        # Apply volume tier discount information
        if volume_tier != "default" and volume_tier in pricing.volume_tiers:
            discount_percentage = pricing.get_tier_discount_percentage(volume_tier)
            if discount_percentage > 0:
                # Calculate what the cost would have been without discount
                default_input_rate = pricing.get_rate("input", "default")
                default_output_rate = pricing.get_rate("output", "default")
                default_input_cost = (Decimal(prompt_tokens) / Decimal(1000)) * default_input_rate
                default_output_cost = (Decimal(completion_tokens) / Decimal(1000)) * default_output_rate
                default_total_cost = default_input_cost + default_output_cost

                discount_amount = default_total_cost - total_cost
                calculation.discount_applied = discount_amount.quantize(
                    Decimal(precision_string), rounding=ROUND_HALF_UP
                )

        # Track usage if tenant provided
        if tenant_id:
            await self._track_usage(
                tenant_id=tenant_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=total_cost,
                calculation=calculation
            )

        # Update performance metrics
        calculation_time = time.time() - start_time
        self._performance_metrics["calculations_performed"] += 1
        self._performance_metrics["total_calculation_time"] += calculation_time
        self._performance_metrics["average_calculation_time"] = (
            self._performance_metrics["total_calculation_time"] /
            self._performance_metrics["calculations_performed"]
        )

        # Cache result if appropriate
        if not tenant_id and not metadata:
            cache_key = self._generate_cache_key(
                model, prompt_tokens, completion_tokens, volume_tier, currency, include_fees
            )
            self._store_in_cache(cache_key, calculation)

        logger.info(
            f"Cost calculated for {model}: {total_cost} {currency} "
            f"({prompt_tokens} input + {completion_tokens} output tokens) "
            f"for tenant {tenant_id}, tier {volume_tier} in {calculation_time:.4f}s"
        )

        return calculation

    async def estimate_cost(
        self,
        model: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        tenant_id: Optional[str] = None,
        currency: str = "USD",
        volume_tier: Optional[str] = None
    ) -> CostCalculation:
        """
        Estimate cost before completion.

        Args:
            model: Model name
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens
            tenant_id: Tenant ID for volume pricing
            currency: Output currency
            volume_tier: Volume pricing tier

        Returns:
            CostCalculation: Estimated cost breakdown
        """
        # Add metadata indicating this is an estimate
        metadata = {
            "is_estimate": True,
            "estimated_at": datetime.utcnow().isoformat(),
            "confidence": "high" if estimated_input_tokens > 0 and estimated_output_tokens > 0 else "low"
        }

        return await self.calculate_cost(
            model=model,
            prompt_tokens=estimated_input_tokens,
            completion_tokens=estimated_output_tokens,
            tenant_id=tenant_id,
            currency=currency,
            volume_tier=volume_tier,
            metadata=metadata
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
        """Convert amount between currencies with caching."""
        return self._convert_currency_cached(amount, from_currency, to_currency)

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
        cost: Decimal,
        calculation: Optional[CostCalculation] = None
    ):
        """Enhanced usage tracking for billing and analytics."""
        if tenant_id not in self._tenant_usage:
            self._tenant_usage[tenant_id] = {
                "monthly_tokens": 0,
                "monthly_cost": Decimal("0"),
                "model_usage": {},
                "usage_history": [],
                "monthly_stats": {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "average_tokens_per_request": 0,
                    "cost_per_request": Decimal("0"),
                    "most_expensive_request": Decimal("0"),
                    "cheapest_request": Decimal("999999.999999")
                }
            }

        usage = self._tenant_usage[tenant_id]
        usage["monthly_tokens"] += prompt_tokens + completion_tokens
        usage["monthly_cost"] += cost

        # Update model usage counts
        if model not in usage["model_usage"]:
            usage["model_usage"][model] = 0
        usage["model_usage"][model] += 1

        # Add to usage history (keep last 1000 entries)
        usage_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "tokens": prompt_tokens + completion_tokens,
            "cost": float(cost),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens
        }
        usage["usage_history"].append(usage_entry)
        if len(usage["usage_history"]) > 1000:
            usage["usage_history"] = usage["usage_history"][-1000:]

        # Update monthly statistics
        stats = usage["monthly_stats"]
        stats["total_requests"] += 1
        if calculation:  # If calculation provided, extract more details
            # For now, assume all requests are successful unless indicated otherwise
            if calculation.metadata.get("success", True):
                stats["successful_requests"] += 1
            else:
                stats["failed_requests"] += 1

        # Calculate averages and extremes
        if stats["total_requests"] > 0:
            stats["average_tokens_per_request"] = usage["monthly_tokens"] / stats["total_requests"]
            stats["cost_per_request"] = usage["monthly_cost"] / Decimal(stats["total_requests"])
            stats["most_expensive_request"] = max(stats["most_expensive_request"], cost)
            stats["cheapest_request"] = min(stats["cheapest_request"], cost)

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
        usage_data: Dict[str, Any],
        calculation: Optional[CostCalculation] = None,
        event_type: str = "ai_usage"
    ) -> Dict[str, Any]:
        """
        Enhanced billing event recording in Stripe with comprehensive tracking.

        Args:
            tenant_id: Tenant identifier (or Stripe customer ID)
            amount: Amount to bill in tenant's currency
            usage_data: Detailed usage information
            calculation: Cost calculation object for detailed tracking
            event_type: Type of billing event (ai_usage, human_review, etc.)

        Returns:
            Dict containing event details and status
        """
        result = {
            "success": False,
            "event_id": None,
            "error": None,
            "retry_count": 0,
            "processed_at": None
        }

        if not settings.STRIPE_SECRET_KEY:
            logger.warning("Stripe secret key not configured, skipping billing event")
            result["error"] = "Stripe not configured"
            return result

        try:
            import stripe

            # Initialize Stripe with secret key
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Prepare event payload with comprehensive data
            event_payload = {
                "stripe_customer_id": tenant_id,
                "event_type": event_type,
                "currency": calculation.currency if calculation else "USD",
                "total_amount": str(amount),
                "recorded_at": datetime.utcnow().isoformat(),
                "data_foundry_version": settings.APP_VERSION
            }

            # Add detailed usage data
            if usage_data:
                event_payload.update({
                    "total_tokens": str(usage_data.get("tokens", 0)),
                    "prompt_tokens": str(usage_data.get("prompt_tokens", 0)),
                    "completion_tokens": str(usage_data.get("completion_tokens", 0)),
                    "models_used": usage_data.get("models", []),
                    "request_count": usage_data.get("request_count", 1),
                    "tenant_id": usage_data.get("tenant_id", tenant_id),
                    "user_id": usage_data.get("user_id")
                })

            # Add calculation details if provided
            if calculation:
                event_payload.update({
                    "model": calculation.model,
                    "provider": calculation.provider.value,
                    "input_rate": str(calculation.input_rate),
                    "output_rate": str(calculation.output_rate),
                    "input_cost": str(calculation.input_cost),
                    "output_cost": str(calculation.output_cost),
                    "volume_tier": calculation.volume_tier,
                    "discount_applied": str(calculation.discount_applied),
                    "request_id": calculation.request_id
                })

            # Record to appropriate meter based on event type
            meter_id = None
            if event_type == "ai_usage" and settings.STRIPE_AI_LABEL_METER_ID:
                meter_id = settings.STRIPE_AI_LABEL_METER_ID
            elif event_type == "human_review" and settings.STRIPE_HUMAN_AUDIT_METER_ID:
                meter_id = settings.STRIPE_HUMAN_AUDIT_METER_ID

            if meter_id:
                # Create meter event with usage value (tokens)
                event = stripe.billing.meter_event.create(
                    event_name=f"data_foundry_{event_type}",
                    payload=event_payload,
                    timestamp=int(datetime.utcnow().timestamp()),
                    meter=meter_id,
                    value=str(usage_data.get("tokens", 0))
                )
            else:
                # Create custom invoice item if no meter configured
                from decimal import Decimal
                amount_cents = int(amount * Decimal(100))  # Convert to cents

                invoice_item = stripe.InvoiceItem.create(
                    customer=tenant_id,
                    amount=amount_cents,
                    currency=calculation.currency if calculation else "USD",
                    description=f"Data Foundry {event_type.replace('_', ' ').title()}",
                    metadata=event_payload
                )
                event = invoice_item

            result.update({
                "success": True,
                "event_id": event.id,
                "processed_at": datetime.utcnow().isoformat(),
                "stripe_object_type": event.object
            })

            logger.info(
                f"Successfully recorded billing event {event.id} for tenant {tenant_id}, "
                f"amount {amount}, type {event_type}"
            )

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error: {str(e)}")
            result["error"] = f"Stripe API error: {str(e)}"
            result["retry_count"] = 1  # Mark for retry

        except Exception as e:
            logger.error(f"Failed to record billing event: {str(e)}")
            result["error"] = f"Unexpected error: {str(e)}"

        return result

    async def create_subscription(
        self,
        tenant_id: str,
        price_id: str,
        trial_period_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create or update a subscription for a tenant.

        Args:
            tenant_id: Tenant identifier (Stripe customer ID)
            price_id: Stripe price ID for the subscription
            trial_period_days: Optional trial period

        Returns:
            Dict containing subscription details
        """
        result = {"success": False, "subscription_id": None, "error": None}

        if not settings.STRIPE_SECRET_KEY:
            result["error"] = "Stripe not configured"
            return result

        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY

            subscription_data = {
                "customer": tenant_id,
                "items": [{"price": price_id}],
                "payment_behavior": "create_if_missing"
            }

            if trial_period_days:
                subscription_data["trial_period_days"] = trial_period_days

            subscription = stripe.Subscription.create(**subscription_data)

            result.update({
                "success": True,
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end
            })

            logger.info(f"Created subscription {subscription.id} for tenant {tenant_id}")

        except stripe.error.StripeError as e:
            logger.error(f"Failed to create subscription: {str(e)}")
            result["error"] = f"Stripe error: {str(e)}"

        return result

    async def get_tenant_billing_info(
        self,
        tenant_id: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive billing information for a tenant.

        Args:
            tenant_id: Tenant identifier (Stripe customer ID)

        Returns:
            Dict containing billing information
        """
        result = {
            "customer_id": tenant_id,
            "subscriptions": [],
            "invoices": [],
            "usage_stats": {}
        }

        if not settings.STRIPE_SECRET_KEY:
            return result

        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Get customer subscriptions
            subscriptions = stripe.Subscription.list(customer=tenant_id, status="active")
            result["subscriptions"] = [sub.id for sub in subscriptions.data]

            # Get recent invoices
            invoices = stripe.Invoice.list(customer=tenant_id, limit=10)
            result["invoices"] = [
                {
                    "id": inv.id,
                    "status": inv.status,
                    "amount": inv.amount_paid / 100,  # Convert from cents
                    "created": inv.created,
                    "due_date": inv.due_date
                }
                for inv in invoices.data
            ]

            # Add usage stats from local tracking if available
            if tenant_id in self._tenant_usage:
                usage = self._tenant_usage[tenant_id]
                result["usage_stats"] = {
                    "monthly_tokens": usage.get("monthly_tokens", 0),
                    "monthly_cost": float(usage.get("monthly_cost", 0)),
                    "model_usage": usage.get("model_usage", {}),
                    "monthly_stats": usage.get("monthly_stats", {})
                }

        except stripe.error.StripeError as e:
            logger.error(f"Failed to get billing info: {str(e)}")
            result["error"] = f"Stripe error: {str(e)}"

        return result

    def generate_cost_forecast(
        self,
        tenant_id: str,
        forecast_days: int = 30,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate cost forecast based on historical usage patterns.

        Args:
            tenant_id: Tenant identifier
            forecast_days: Number of days to forecast
            model: Optional specific model to forecast

        Returns:
            Dict containing forecast data
        """
        forecast = {
            "tenant_id": tenant_id,
            "forecast_days": forecast_days,
            "daily_forecast": [],
            "total_forecasted_cost": Decimal("0"),
            "confidence_score": 0.0,
            "recommendations": []
        }

        if tenant_id not in self._tenant_usage:
            forecast["recommendations"].append("Insufficient historical data for accurate forecasting")
            return forecast

        usage = self._tenant_usage[tenant_id]
        usage_history = usage.get("usage_history", [])

        if len(usage_history) < 7:  # Need at least a week of data
            forecast["confidence_score"] = 0.2
            forecast["recommendations"].append("Limited historical data - forecast accuracy is low")
        else:
            # Calculate daily averages from historical data
            daily_costs = []
            daily_tokens = []

            # Group by day
            daily_data = {}
            for entry in usage_history[-30:]:  # Use last 30 days
                date = entry["timestamp"][:10]  # Extract date
                if date not in daily_data:
                    daily_data[date] = {"cost": 0, "tokens": 0}
                daily_data[date]["cost"] += entry["cost"]
                daily_data[date]["tokens"] += entry["tokens"]

            daily_costs = list(daily_data.values())
            daily_tokens = [d["tokens"] for d in daily_costs]

            if daily_costs:
                avg_daily_cost = sum(d["cost"] for d in daily_costs) / len(daily_costs)
                avg_daily_tokens = sum(daily_tokens) / len(daily_tokens)

                # Calculate growth trend (simple linear approximation)
                if len(daily_costs) >= 14:
                    recent_avg = sum(d["cost"] for d in daily_costs[-7:]) / 7
                    older_avg = sum(d["cost"] for d in daily_costs[-14:-7]) / 7
                    growth_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
                else:
                    growth_rate = 0

                # Generate forecast
                for day in range(forecast_days):
                    # Apply growth trend with some randomization
                    daily_forecast = avg_daily_cost * (1 + growth_rate * (day / forecast_days))

                    # Add seasonal variation (weekday vs weekend)
                    import random
                    weekday_factor = 1.2 if (day % 7) < 5 else 0.8  # Higher usage on weekdays
                    daily_forecast *= weekday_factor

                    # Add some randomness for realistic variation
                    daily_forecast *= (0.9 + random.random() * 0.2)

                    forecast["daily_forecast"].append({
                        "day": day + 1,
                        "date": (datetime.utcnow() + timedelta(days=day + 1)).strftime("%Y-%m-%d"),
                        "predicted_cost": round(daily_forecast, 6),
                        "predicted_tokens": int(avg_daily_tokens * weekday_factor)
                    })

                forecast["total_forecasted_cost"] = sum(
                    Decimal(str(d["predicted_cost"])) for d in forecast["daily_forecast"]
                )
                forecast["confidence_score"] = min(0.9, len(daily_costs) / 30)  # Confidence based on data availability

        # Generate recommendations
        current_monthly_cost = usage.get("monthly_cost", Decimal("0"))
        if forecast["total_forecasted_cost"] > current_monthly_cost * Decimal("1.5"):
            forecast["recommendations"].append(
                "Forecasted cost increase detected - consider optimizing model selection"
            )

        # Check for cost optimization opportunities
        model_usage = usage.get("model_usage", {})
        expensive_models = []
        for model_name, count in model_usage.items():
            if model_name in self._model_pricing:
                pricing = self._model_pricing[model_name]
                if pricing.input_token_cost > Decimal("0.01"):  # More than 1 cent per 1K tokens
                    expensive_models.append((model_name, count))

        if expensive_models:
            forecast["recommendations"].append(
                f"Consider using more cost-effective models instead of: {', '.join(m[0] for m in expensive_models[:3])}"
            )

        return forecast

    def get_cost_optimization_recommendations(
        self,
        tenant_id: str,
        usage_patterns: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate cost optimization recommendations based on usage patterns.

        Args:
            tenant_id: Tenant identifier
            usage_patterns: Optional usage pattern analysis

        Returns:
            Dict containing optimization recommendations
        """
        recommendations = {
            "tenant_id": tenant_id,
            "potential_savings": Decimal("0"),
            "recommendations": [],
            "model_suggestions": {},
            "volume_tier_opportunities": [],
            "usage_optimization": []
        }

        if tenant_id not in self._tenant_usage:
            recommendations["recommendations"].append("No usage data available for optimization")
            return recommendations

        usage = self._tenant_usage[tenant_id]
        model_usage = usage.get("model_usage", {})

        # Analyze model usage for optimization opportunities
        for model_name, count in model_usage.items():
            if model_name in self._model_pricing:
                pricing = self._model_pricing[model_name]

                # Check if there are cheaper alternatives
                cheaper_alternatives = []
                for alt_model, alt_pricing in self._model_pricing.items():
                    if (alt_pricing.input_token_cost < pricing.input_token_cost and
                        alt_pricing.provider == pricing.provider):  # Same provider

                        # Check if alternative has similar capabilities
                        common_capabilities = set(pricing.get("capabilities", [])) & set(alt_pricing.get("capabilities", []))
                        if common_capabilities:
                            savings_percentage = ((pricing.input_token_cost - alt_pricing.input_token_cost) / pricing.input_token_cost) * 100
                            cheaper_alternatives.append({
                                "model": alt_model,
                                "savings_percentage": round(savings_percentage, 2),
                                "shared_capabilities": list(common_capabilities)
                            })

                if cheaper_alternatives:
                    recommendations["model_suggestions"][model_name] = cheaper_alternatives

        # Check volume tier opportunities
        monthly_tokens = usage.get("monthly_tokens", 0)
        monthly_cost = usage.get("monthly_cost", Decimal("0"))

        # Suggest volume tier upgrades
        if monthly_tokens > 1000000:  # 1M tokens monthly
            recommendations["volume_tier_opportunities"].append({
                "tier": "large",
                "reason": "High token volume qualifies for large tier pricing",
                "estimated_savings": "15-20%"
            })
        elif monthly_tokens > 500000:  # 500K tokens monthly
            recommendations["volume_tier_opportunities"].append({
                "tier": "medium",
                "reason": "Medium token volume qualifies for medium tier pricing",
                "estimated_savings": "10%"
            })

        # Usage pattern optimization
        stats = usage.get("monthly_stats", {})
        if stats.get("average_tokens_per_request", 0) > 5000:  # High token usage per request
            recommendations["usage_optimization"].append({
                "type": "token_efficiency",
                "suggestion": "Consider prompt optimization to reduce input tokens",
                "potential_impact": "20-30% cost reduction"
            })

        # Check for batching opportunities
        if stats.get("total_requests", 0) > 1000:
            recommendations["usage_optimization"].append({
                "type": "batch_processing",
                "suggestion": "Consider batching similar requests to reduce overhead",
                "potential_impact": "5-10% cost reduction"
            })

        # Calculate potential savings
        total_suggestions = (len(recommendations["model_suggestions"]) +
                           len(recommendations["volume_tier_opportunities"]) +
                           len(recommendations["usage_optimization"]))

        if total_suggestions > 0:
            # Estimate potential savings (conservative estimate)
            estimated_savings = monthly_cost * Decimal("0.15")  # 15% average savings
            recommendations["potential_savings"] = estimated_savings

        return recommendations

    def compare_models_for_task(
        self,
        task_description: str,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        required_capabilities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare models for a specific task and recommend the most cost-effective option.

        Args:
            task_description: Description of the task
            estimated_input_tokens: Estimated input tokens
            estimated_output_tokens: Estimated output tokens
            required_capabilities: Required model capabilities

        Returns:
            Dict containing model comparison and recommendation
        """
        comparison = {
            "task_description": task_description,
            "estimated_tokens": {
                "input": estimated_input_tokens,
                "output": estimated_output_tokens,
                "total": estimated_input_tokens + estimated_output_tokens
            },
            "model_comparison": [],
            "recommendation": None,
            "cost_range": {"min": None, "max": None}
        }

        required_capabilities = required_capabilities or []

        # Find suitable models
        suitable_models = []
        for model_name, pricing in self._model_pricing.items():
            # Check capabilities if specified
            if required_capabilities:
                model_caps = set(pricing.get("capabilities", []))
                if not required_capabilities.issubset(model_caps):
                    continue

            # Calculate estimated cost
            input_cost = (Decimal(estimated_input_tokens) / Decimal(1000)) * pricing.input_token_cost
            output_cost = (Decimal(estimated_output_tokens) / Decimal(1000)) * pricing.output_token_cost
            total_cost = input_cost + output_cost

            suitable_models.append({
                "model": model_name,
                "provider": pricing.provider.value,
                "input_rate": float(pricing.input_token_cost),
                "output_rate": float(pricing.output_token_cost),
                "estimated_cost": float(total_cost),
                "capabilities": pricing.get("capabilities", []),
                "context_window": pricing.get("context_window", 0)
            })

        # Sort by cost (ascending)
        suitable_models.sort(key=lambda x: x["estimated_cost"])

        if not suitable_models:
            comparison["recommendation"] = {
                "model": None,
                "reason": "No models available with required capabilities"
            }
            return comparison

        comparison["model_comparison"] = suitable_models

        # Set cost range
        costs = [m["estimated_cost"] for m in suitable_models]
        comparison["cost_range"]["min"] = min(costs)
        comparison["cost_range"]["max"] = max(costs)

        # Recommend the most cost-effective model
        cheapest = suitable_models[0]
        most_expensive = suitable_models[-1]

        # If there's a significant difference, recommend the cheapest
        if most_expensive["estimated_cost"] / cheapest["estimated_cost"] > 2:
            recommendation = cheapest.copy()
            recommendation["reason"] = f"Most cost-effective - {((most_expensive['estimated_cost'] / cheapest['estimated_cost'] - 1) * 100):.1f}% cheaper than most expensive option"
            recommendation["savings_vs_expensive"] = most_expensive["estimated_cost"] - cheapest["estimated_cost"]
        else:
            # Costs are similar, recommend the one with best capabilities
            best_capability_model = max(suitable_models, key=lambda x: len(x["capabilities"]))
            recommendation = best_capability_model.copy()
            recommendation["reason"] = "Good balance of cost and capabilities"

        comparison["recommendation"] = recommendation

        return comparison

    def _refresh_pricing(self, model: str):
        """Refresh pricing data for a model from provider."""
        # In production, this would fetch latest pricing from provider APIs
        logger.info(f"Refreshing pricing for model: {model}")

        # Placeholder for actual pricing refresh logic
        # This would typically:
        # 1. Call provider's pricing API
        # 2. Update the model pricing data
        # 3. Cache the new pricing with TTL
        # 4. Notify about significant price changes

        if model in self._model_pricing:
            pricing = self._model_pricing[model]
            logger.info(f"Current pricing for {model}: input={pricing.input_token_cost}, output={pricing.output_token_cost}")

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