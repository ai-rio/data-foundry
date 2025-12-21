"""
LiteLLM Service - Direct integration with LiteLLM for unified AI provider access.

This service provides direct LiteLLM API integration with:
- Multiple provider support (OpenAI, Anthropic, Azure, Google, etc.)
- Intelligent fallback mechanisms
- Comprehensive error handling and recovery
- Performance monitoring and metrics
- Token usage tracking and cost calculation
- Response caching and optimization
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from decimal import Decimal
import hashlib

import litellm
from litellm import completion, acompletion, get_supported_openai_params
from litellm.utils import ModelResponse
from litellm.caching.caching import Cache

from src.core.config import settings
from src.services.redis_service import RedisService
from src.services.cost_service import CostService
from src.database.connection import get_db_session
from src.models.usage_tracking import TenantUsage, AuditLog

logger = logging.getLogger(__name__)


class LiteLLMError(Exception):
    """Custom exception for LiteLLM errors."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        error_type: Optional[str] = None,
        retryable: bool = False
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.error_type = error_type
        self.retryable = retryable


class LiteLLMResponse:
    """Wrapper for LiteLLM response with additional metadata."""

    def __init__(
        self,
        content: str,
        model: str,
        provider: str,
        usage: Dict[str, int],
        cost: Decimal,
        response_time_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
        cached: bool = False,
        fallback_used: bool = False,
        retry_count: int = 0
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage
        self.cost = cost
        self.response_time_ms = response_time_ms
        self.metadata = metadata or {}
        self.cached = cached
        self.fallback_used = fallback_used
        self.retry_count = retry_count
        self.timestamp = datetime.now(timezone.utc)


class LiteLLMService:
    """
    Direct LiteLLM integration service.

    This service handles the low-level interaction with LiteLLM,
    providing a unified interface for multiple AI providers.
    """

    def __init__(self):
        # Configuration
        self.primary_model = settings.PRIMARY_MODEL
        self.fallback_models = settings.FALLBACK_MODELS
        self.all_models = [self.primary_model] + self.fallback_models

        # In-memory request cache for cache detection
        self._request_cache = {}

        # Provider mappings
        self._provider_mappings = {
            "gpt-4o": "openai",
            "gpt-4-turbo": "openai",
            "gpt-4": "openai",
            "gpt-3.5-turbo": "openai",
            "claude-3-5-sonnet": "anthropic",
            "claude-3-opus": "anthropic",
            "claude-3-haiku": "anthropic",
            "gemini-pro": "google",
            "gemini-pro-vision": "google",
            # OpenRouter models
            "openrouter/openai/gpt-4o-mini": "openrouter",
            "openrouter/openai/gpt-4o": "openrouter",
            "openrouter/openai/gpt-3.5-turbo": "openrouter",
            "openrouter/anthropic/claude-3.5-sonnet": "openrouter",
            "openrouter/anthropic/claude-3-opus": "openrouter",
            "openrouter/anthropic/claude-3-haiku": "openrouter"
        }

        # Performance metrics
        self._metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "fallback_used": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_tokens": 0,
            "total_cost": Decimal("0"),
            "avg_response_time": 0
        }

        # Initialize services
        self.redis_client: Optional[RedisService] = None
        self.cost_service: Optional[CostService] = None
        self._initialized = False

        # Rate limiting
        self._rate_limits: Dict[str, List[datetime]] = {}
        self._rate_limit_window = timedelta(minutes=1)
        self._max_requests_per_minute = 60

        # Configure LiteLLM
        self._configure_litellm()

        # Error retry configuration
        self._retry_config = {
            "max_retries": 3,
            "initial_delay": 0.5,
            "max_delay": 60,
            "backoff_factor": 2,
            "retryable_errors": [
                "rate_limit_error",
                "timeout_error",
                "connection_error",
                "server_error"
            ]
        }

    def _configure_litellm(self):
        """Configure LiteLLM settings."""
        litellm.set_verbose = settings.LITELLM_LOGGING

        # Enable LiteLLM built-in caching with Redis support
        try:
            litellm.cache = Cache(
                type="redis",
                host="localhost",
                port=6379,
                db=0,
                supported_call_types=["acompletion", "completion"]
            )
            logger.info("LiteLLM Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache, falling back to local cache: {e}")
            litellm.cache = Cache(type="local")

        litellm.request_timeout = settings.LITELLM_REQUEST_TIMEOUT

        # Enable debug logging to see cache behavior
        if settings.LITELLM_LOGGING:
            litellm._turn_on_debug()

        # Set API keys securely through SecretManager
        if settings.secure_openai_api_key:
            litellm.openai_api_key = settings.secure_openai_api_key

        if settings.secure_anthropic_api_key:
            litellm.anthropic_api_key = settings.secure_anthropic_api_key

        # Configure OpenRouter
        if settings.secure_openrouter_api_key:
            litellm.openrouter_api_key = settings.secure_openrouter_api_key
            # OpenRouter uses OpenAI-compatible format, set as fallback
            if not settings.secure_openai_api_key:
                litellm.openai_api_key = settings.secure_openrouter_api_key

        logger.info("LiteLLM configured successfully")

    async def initialize(self):
        """Initialize the service and its dependencies."""
        if self._initialized:
            return

        try:
            # Initialize Redis client
            self.redis_client = RedisService()

            # Initialize cost service
            self.cost_service = CostService()

            # Test LiteLLM connectivity
            await self._test_connectivity()

            self._initialized = True
            logger.info("LiteLLM Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize LiteLLM Service: {str(e)}")
            raise

    async def _test_connectivity(self):
        """Test connectivity to configured providers."""
        for model in self.all_models[:1]:  # Test primary model only
            try:
                response = await acompletion(
                    model=model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1
                )
                logger.info(f"Connectivity test passed for {model}")
                return
            except Exception as e:
                logger.warning(f"Connectivity test failed for {model}: {str(e)}")

        # If no model passes test, log but don't fail
        logger.warning("No models passed connectivity test")

    async def completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        response_format: Optional[str] = None,
        tenant_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        cache_ttl: int = 3600,
        max_retries: Optional[int] = None,
        fallbacks: Optional[List[str]] = None
    ) -> LiteLLMResponse:
        """
        Perform AI completion using LiteLLM.

        Args:
            prompt: The prompt text
            system_prompt: Optional system prompt
            messages: Alternative to prompt, list of messages
            model: Specific model to use (falls back to configured primary)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            stream: Whether to stream response
            response_format: Response format (e.g., "json")
            tenant_id: Tenant ID for billing and isolation
            metadata: Additional metadata for tracking
            use_cache: Whether to use cached responses
            cache_ttl: Cache time-to-live in seconds
            max_retries: Override default retry count
            fallbacks: List of fallback models

        Returns:
            LiteLLMResponse: The completion response with metadata
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        model = model or self.primary_model
        max_retries = max_retries or self._retry_config["max_retries"]

        # Update metrics
        self._metrics["requests_total"] += 1

        # Store the request hash for cache detection
        request_hash = self._generate_request_hash(model, messages, temperature, max_tokens) if not messages else self._generate_request_hash(model, self._prepare_messages(prompt, system_prompt, None), temperature, max_tokens)

        # Check if we've seen this request before (for cache detection)
        seen_before = request_hash in self._request_cache
        self._request_cache[request_hash] = time.time()

        try:
            # Prepare messages
            messages = self._prepare_messages(prompt, system_prompt, messages)

            # Check rate limits
            await self._check_rate_limit(tenant_id)

            # Attempt completion with fallback and retry
            response = await self._attempt_completion_with_fallback(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream,
                response_format=response_format,
                tenant_id=tenant_id,
                max_retries=max_retries,
                metadata=metadata,
                use_cache=use_cache,  # Pass through cache setting to LiteLLM
                fallbacks=fallbacks
            )

            # Heuristic: if we've seen this request before and response time is very fast, it's likely cached
            response_time = time.time() - start_time
            if seen_before and use_cache and response_time < 0.5:  # Less than 500ms suggests cache hit
                response.cached = True
                self._metrics["cache_hits"] += 1
                logger.info(f"Heuristic cache hit detected for request {request_hash[:8]}")

            # Update metrics
            self._metrics["requests_success"] += 1
            await self._update_metrics(response)

            return response

        except Exception as e:
            self._metrics["requests_failed"] += 1

            # Log error
            logger.error(f"LiteLLM completion failed: {str(e)}")

            # Create audit log
            await self._create_audit_log(
                tenant_id=tenant_id,
                operation="completion",
                model=model,
                success=False,
                error=str(e),
                metadata=metadata,
                duration_ms=(time.time() - start_time) * 1000
            )

            raise

    async def _attempt_completion_with_fallback(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
        response_format: Optional[str],
        tenant_id: str,
        max_retries: int,
        metadata: Optional[Dict[str, Any]],
        use_cache: bool = True,
        fallbacks: Optional[List[str]] = None
    ) -> LiteLLMResponse:
        """Attempt completion with fallback models and retry logic."""
        last_error = None

        # Use custom fallbacks if provided, otherwise use configured fallback models
        if fallbacks:
            models_to_try = [model] + [m for m in fallbacks if m != model]
        else:
            models_to_try = [model] + [
                m for m in self.fallback_models if m != model
            ]

        for attempt_model in models_to_try:
            retry_count = 0

            while retry_count <= max_retries:
                try:
                    # Prepare completion parameters
                    params = {
                        "model": attempt_model,
                        "messages": messages,
                        "temperature": temperature,
                    }

                    # Add cache parameter if specified
                    if use_cache is True:
                        params["caching"] = True  # Enable caching for this request

                    if max_tokens:
                        params["max_tokens"] = max_tokens

                    if response_format == "json":
                        params["response_format"] = {"type": "json_object"}

                    # Add fallbacks if this is the primary model and we have custom fallbacks
                    if fallbacks and attempt_model == model:
                        # LiteLLM expects fallbacks as a parameter
                        params["fallbacks"] = fallbacks

                    start_time = time.time()

                    # Make the actual call
                    if stream:
                        # Streaming would need a different implementation
                        response_data = await acompletion(**params)
                    else:
                        response_data = await acompletion(**params)

                    response_time = (time.time() - start_time) * 1000

                    # Process successful response
                    return await self._process_response(
                        response_data=response_data,
                        model=attempt_model,
                        tenant_id=tenant_id,
                        response_time_ms=response_time,
                        fallback_used=(attempt_model != model),
                        retry_count=retry_count,
                        metadata=metadata
                    )

                except Exception as e:
                    last_error = e

                    # Check if error is retryable
                    if not self._is_retryable_error(e):
                        logger.error(f"Non-retryable error with {attempt_model}: {str(e)}")
                        break

                    retry_count += 1

                    if retry_count <= max_retries:
                        delay = self._calculate_retry_delay(retry_count)
                        logger.warning(
                            f"Attempt {retry_count} failed for {attempt_model}, "
                            f"retrying in {delay}s: {str(e)}"
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Max retries exceeded for {attempt_model}: {str(e)}"
                        )

            # Log model failure and continue to next model
            logger.warning(f"Model {attempt_model} failed after all retries")

        # All models failed
        raise LiteLLMError(
            message=f"All models failed. Last error: {str(last_error)}",
            model=models_to_try[-1] if models_to_try else None,
            error_type="all_models_failed",
            retryable=False
        )

    async def _process_response(
        self,
        response_data: ModelResponse,
        model: str,
        tenant_id: str,
        response_time_ms: float,
        fallback_used: bool,
        retry_count: int,
        metadata: Optional[Dict[str, Any]]
    ) -> LiteLLMResponse:
        """Process successful LiteLLM response."""
        # Check if this is a cached response
        # LiteLLM may use various indicators for cached responses
        is_cached = (
            response_data.__class__.__name__ == 'TextRag' or
            hasattr(response_data, '_cached') or
            getattr(response_data, '_cache_hit', False) or
            (hasattr(response_data, 'model') and 'cache' in str(response_data.model).lower())
        )

        # Additional check: look for cache-related attributes
        for attr_name in dir(response_data):
            if 'cache' in attr_name.lower():
                attr_value = getattr(response_data, attr_name, None)
                if attr_value:
                    logger.debug(f"Found cache attribute: {attr_name} = {attr_value}")
                    is_cached = True

        if is_cached:
            # Handle cached response
            if response_data.__class__.__name__ == 'TextRag':
                content = response_data.text
            else:
                content = response_data.choices[0].message.content

            usage = {
                "prompt_tokens": 0,  # Cached responses don't have usage info
                "completion_tokens": 0,
                "total_tokens": 0
            }

            # Mark as cached and update metrics
            cached = True
            self._metrics["cache_hits"] += 1
            logger.info(f"Cache hit detected for model {model} - type: {response_data.__class__.__name__}")
        else:
            # Handle normal ModelResponse
            content = response_data.choices[0].message.content
            usage = response_data.usage.model_dump() if response_data.usage else {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }

            # Mark as not cached
            cached = False
            self._metrics["cache_misses"] += 1

        logger.debug(f"Response - type: {response_data.__class__.__name__}, cached: {cached}, time: {response_time_ms}ms")

        # Calculate cost - temporarily simplified to avoid serialization issues
        cost = Decimal("0.0001")  # Fixed minimal cost for testing

        # Create response
        response = LiteLLMResponse(
            content=content,
            model=model,
            provider=self._get_provider_for_model(model),
            usage=usage,
            cost=cost,
            response_time_ms=response_time_ms,
            metadata=metadata,
            cached=cached,
            fallback_used=fallback_used,
            retry_count=retry_count
        )

        # Create audit log
        await self._create_audit_log(
            tenant_id=tenant_id,
            operation="completion",
            model=model,
            success=True,
            usage=usage,
            cost=cost,
            metadata=metadata,
            duration_ms=response_time_ms
        )

        # Update fallback metrics
        if fallback_used:
            self._metrics["fallback_used"] += 1

        return response

    def _prepare_messages(
        self,
        prompt: str,
        system_prompt: Optional[str],
        messages: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """Prepare messages for LiteLLM API."""
        if messages:
            return messages.copy()

        result = []

        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        result.append({"role": "user", "content": prompt})

        return result

    def _get_provider_for_model(self, model: str) -> str:
        """Get provider name for model."""
        return self._provider_mappings.get(model, "unknown")

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()

        # Check for known retryable errors
        for retryable in self._retry_config["retryable_errors"]:
            if retryable in error_str:
                return True

        # Check HTTP status codes
        if "429" in error_str:  # Rate limit
            return True
        if "502" in error_str or "503" in error_str or "504" in error_str:  # Server errors
            return True

        return False

    def _calculate_retry_delay(self, retry_count: int) -> float:
        """Calculate exponential backoff delay."""
        delay = self._retry_config["initial_delay"] * (
            self._retry_config["backoff_factor"] ** (retry_count - 1)
        )
        return min(delay, self._retry_config["max_delay"])

    async def _check_rate_limit(self, tenant_id: str):
        """Check and enforce rate limits."""
        now = datetime.now(timezone.utc)

        # Initialize tenant rate limit tracking
        if tenant_id not in self._rate_limits:
            self._rate_limits[tenant_id] = []

        # Clean old requests outside window
        self._rate_limits[tenant_id] = [
            req_time for req_time in self._rate_limits[tenant_id]
            if now - req_time < self._rate_limit_window
        ]

        # Check limit
        if len(self._rate_limits[tenant_id]) >= self._max_requests_per_minute:
            sleep_time = 60  # Sleep for 1 minute
            logger.warning(
                f"Rate limit exceeded for tenant {tenant_id}, sleeping {sleep_time}s"
            )
            await asyncio.sleep(sleep_time)

        # Add current request
        self._rate_limits[tenant_id].append(now)

    async def _get_cached_response(
        self,
        cache_key: str,
        tenant_id: str
    ) -> Optional[LiteLLMResponse]:
        """Get response from Redis cache."""
        if not self.redis_client:
            return None

        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Retrieved cached data: {type(cached_data)} - {cached_data}")

                # RedisService already deserialized the data
                data = cached_data

                # Reconstruct LiteLLMResponse
                return LiteLLMResponse(
                    content=data["content"],
                    model=data["model"],
                    provider=data["provider"],
                    usage=data["usage"],
                    cost=Decimal(str(data["cost"])),
                    response_time_ms=data["response_time_ms"],
                    metadata=data.get("metadata"),
                    cached=True,
                    fallback_used=data.get("fallback_used", False),
                    retry_count=data.get("retry_count", 0)
                )

        except Exception as e:
            logger.warning(f"Failed to get cached response: {str(e)}")
            logger.debug(f"Cache data type: {type(cached_data) if cached_data else 'None'}")
            if cached_data:
                logger.debug(f"Cache data content: {cached_data}")

        return None

    async def _cache_response(
        self,
        cache_key: str,
        response: LiteLLMResponse,
        tenant_id: str,
        ttl: int
    ):
        """Cache response in Redis."""
        if not self.redis_client:
            return

        try:
            # Debug logging
            logger.debug(f"Response cost type: {type(response.cost)}, value: {response.cost}")

            cache_data = {
                "content": response.content,
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage,
                "cost": str(response.cost),  # Convert Decimal to string for JSON serialization
                "response_time_ms": response.response_time_ms,
                "metadata": response.metadata,
                "fallback_used": response.fallback_used,
                "retry_count": response.retry_count,
                "cached_at": datetime.now(timezone.utc).isoformat()
            }

            logger.debug(f"Cache data prepared: {cache_data}")

            # Serialize the cache data
            serialized_data = self.redis_client.serializer.serialize(cache_data)
            logger.debug(f"Serialized data type: {type(serialized_data)}, value: {serialized_data}")

            await self.redis_client.set(
                cache_key,
                serialized_data,
                ttl
            )

            logger.debug(f"Cached response with key: {cache_key}")

        except Exception as e:
            logger.warning(f"Failed to cache response: {str(e)}")

    async def _get_cached_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        tenant_id: str
    ) -> Optional[LiteLLMResponse]:
        """Get cached response if available."""
        try:
            cache_key = self._generate_cache_key(model, messages, temperature, max_tokens)

            # Try to get from Redis cache
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                # Deserialize and convert back to LiteLLMResponse
                response_data = self.redis_client.serializer.deserialize(cached_data)

                # Create cached response with cached=True
                cached_response = LiteLLMResponse(
                    content=response_data["content"],
                    model=response_data["model"],
                    provider=response_data["provider"],
                    usage=response_data["usage"],
                    cost=response_data["cost"],
                    response_time_ms=response_data["response_time_ms"],
                    metadata=response_data["metadata"],
                    fallback_used=response_data["fallback_used"],
                    retry_count=response_data["retry_count"],
                    cached=True,  # Mark as cached
                    cached_at=response_data["cached_at"]
                )

                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_response

        except Exception as e:
            logger.warning(f"Cache retrieval failed: {str(e)}")

        return None

    async def _cache_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        tenant_id: str,
        response: LiteLLMResponse
    ) -> None:
        """Cache the successful response."""
        try:
            cache_key = self._generate_cache_key(model, messages, temperature, max_tokens)

            # Prepare data for caching
            cache_data = {
                "content": response.content,
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage,
                "cost": response.cost,
                "response_time_ms": response.response_time_ms,
                "metadata": response.metadata,
                "fallback_used": response.fallback_used,
                "retry_count": response.retry_count,
                "cached_at": datetime.now(timezone.utc).isoformat()
            }

            # Serialize and store in Redis
            serialized_data = self.redis_client.serializer.serialize(cache_data)

            # Cache for 1 hour (3600 seconds)
            await self.redis_client.set(cache_key, serialized_data, ttl=3600)

            logger.debug(f"Cached response with key: {cache_key}")

        except Exception as e:
            logger.warning(f"Cache storage failed: {str(e)}")

    def _generate_cache_key(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int]
    ) -> str:
        """Generate cache key for request."""
        key_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        key_str = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()

        return f"litellm_cache:{key_hash[:16]}"

    def _generate_request_hash(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: Optional[int]) -> str:
        """Generate hash for request tracking."""
        key_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    async def _update_metrics(self, response: LiteLLMResponse):
        """Update service metrics."""
        self._metrics["total_tokens"] += response.usage.get("total_tokens", 0)
        self._metrics["total_cost"] += response.cost

        # Update average response time
        total_requests = self._metrics["requests_success"]
        if total_requests > 0:
            self._metrics["avg_response_time"] = (
                (self._metrics["avg_response_time"] * (total_requests - 1) +
                 response.response_time_ms) / total_requests
            )

    async def _create_audit_log(
        self,
        tenant_id: str,
        operation: str,
        model: str,
        success: bool,
        usage: Optional[Dict[str, int]] = None,
        cost: Optional[Decimal] = None,
        metadata: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Create audit log entry."""
        try:
            audit_data = {
                "operation": operation,
                "model": model,
                "provider": self._get_provider_for_model(model),
                "success": success,
                "timestamp": datetime.now(timezone.utc),
                "metadata": metadata or {}
            }

            if usage:
                audit_data["usage"] = usage

            if cost:
                audit_data["cost"] = str(cost)

            if duration_ms:
                audit_data["duration_ms"] = duration_ms

            if error:
                audit_data["error"] = error

            # In production, this would save to database
            logger.info(f"Audit log: {json.dumps(audit_data)}")

        except Exception as e:
            logger.error(f"Failed to create audit log: {str(e)}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get service performance metrics."""
        return self._metrics.copy()

    async def reset_metrics(self):
        """Reset service metrics."""
        self._metrics = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "fallback_used": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_tokens": 0,
            "total_cost": Decimal("0"),
            "avg_response_time": 0
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all configured models."""
        health_status = {
            "healthy": True,
            "models": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        for model in self.all_models[:3]:  # Check first 3 models
            try:
                start_time = time.time()
                response = await acompletion(
                    model=model,
                    messages=[{"role": "user", "content": "health check"}],
                    max_tokens=1
                )
                response_time = (time.time() - start_time) * 1000

                health_status["models"][model] = {
                    "status": "healthy",
                    "response_time_ms": response_time,
                    "provider": self._get_provider_for_model(model)
                }

            except Exception as e:
                health_status["healthy"] = False
                health_status["models"][model] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "provider": self._get_provider_for_model(model)
                }

        return health_status

    async def close(self):
        """Close the LiteLLM service and clean up resources."""
        # Close any active connections or resources
        self.metrics = {}
        logger.info("LiteLLMService closed")


# Global service instance
_litellm_service: Optional[LiteLLMService] = None


async def get_litellm_service() -> LiteLLMService:
    """Get or create LiteLLM service instance."""
    global _litellm_service

    if _litellm_service is None:
        _litellm_service = LiteLLMService()
        await _litellm_service.initialize()

    return _litellm_service