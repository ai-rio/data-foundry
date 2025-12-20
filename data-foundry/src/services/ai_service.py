"""
AI Service with LiteLLM Integration

This service provides a unified interface for multiple AI providers through LiteLLM,
including fallback mechanisms, cost tracking, and comprehensive audit trails.
"""

import json
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from decimal import Decimal
import time

from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.core.config import settings
from src.core.prompts.cached_prompt_manager import CachedPromptManager
from src.services.redis_service import RedisService
from src.services.cost_service import CostService
from src.database.connection import get_db_session
from src.models.usage_tracking import TenantUsage, AuditLog


# Configure logging
logger = logging.getLogger(__name__)


class SimpleTokenUsage:
    """Simple token usage information (non-SQLModel version)."""

    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens

    @property
    def cost_per_token(self) -> Optional[Decimal]:
        """Calculate cost per token if pricing is available."""
        return None


class AIRequest:
    """AI completion request model."""

    def __init__(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        response_format: Optional[str] = None,
        prompt_template: Optional[str] = None,
        template_vars: Optional[Dict[str, Any]] = None,
        tenant_id: str = "",
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        cache_ttl: Optional[int] = 3600,
        max_retries: int = 3,
        timeout: Optional[int] = 30
    ):
        self.prompt = prompt
        self.system_prompt = system_prompt
        self.messages = messages or []
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.response_format = response_format
        self.prompt_template = prompt_template
        self.template_vars = template_vars or {}
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.request_id = request_id or self._generate_request_id()
        self.metadata = metadata or {}
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.max_retries = max_retries
        self.timeout = timeout

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        return f"req_{int(time.time())}_{hash(self.prompt) % 10000}"

    def to_messages(self) -> List[Dict[str, str]]:
        """Convert request to message format."""
        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if self.messages:
            messages.extend(self.messages)
        else:
            messages.append({"role": "user", "content": self.prompt})

        return messages


class AIResponse:
    """AI completion response model."""

    def __init__(
        self,
        content: str,
        model: str,
        usage: SimpleTokenUsage,
        cost: Decimal,
        response_time_ms: float,
        tenant_id: str,
        completion_id: str,
        status: str = "completed",
        from_cache: bool = False,
        error: Optional[str] = None,
        fallback_used: bool = False,
        retry_count: int = 0,
        request_id: Optional[str] = None
    ):
        self.content = content
        self.model = model
        self.usage = usage
        self.cost = cost
        self.response_time_ms = response_time_ms
        self.tenant_id = tenant_id
        self.completion_id = completion_id
        self.status = status
        self.from_cache = from_cache
        self.error = error
        self.fallback_used = fallback_used
        self.retry_count = retry_count
        self.request_id = request_id
        self.created_at = datetime.utcnow()
        self.cached_at = datetime.utcnow() if from_cache else None


class AIService:
    """AI Service with LiteLLM integration."""

    def __init__(self):
        self.primary_model = settings.PRIMARY_MODEL
        self.fallback_models = settings.FALLBACK_MODELS
        self.all_models = [self.primary_model] + self.fallback_models
        self.prompt_manager: Optional[CachedPromptManager] = None
        self.redis_client: Optional[RedisService] = None
        self.cost_service: Optional[CostService] = None
        self.litellm_service: Optional[LiteLLMService] = None
        self._initialized = False

    async def initialize(self):
        """Initialize the AI service and its dependencies."""
        if self._initialized:
            return

        try:
            # Initialize prompt manager
            self.prompt_manager = CachedPromptManager()

            # Initialize Redis client (no connect method needed)
            self.redis_client = RedisService()

            # Initialize cost service
            self.cost_service = CostService()

            # Initialize LiteLLM service
            self.litellm_service = LiteLLMService()
            await self.litellm_service.initialize()

            self._initialized = True
            logger.info("AI Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize AI Service: {str(e)}")
            raise

    async def completion(self, request: AIRequest) -> AIResponse:
        """
        Perform AI completion with fallback and caching.

        Args:
            request: The AI request to process

        Returns:
            AIResponse: The completion response
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Handle prompt template if provided
            if request.prompt_template and self.prompt_manager:
                template_data = await self.prompt_manager.get_template(
                    request.prompt_template,
                    tenant_id=request.tenant_id
                )

                if template_data:
                    system_prompt = template_data.get("system_prompt")
                    user_prompt = template_data.get("user_prompt", "")

                    # Apply template variables
                    if request.template_vars:
                        user_prompt = user_prompt.format(**request.template_vars)

                    # Use template prompts
                    messages = []
                    if system_prompt:
                        messages.append({"role": "system", "content": system_prompt})
                    messages.append({"role": "user", "content": user_prompt})

                    # Call LiteLLM service with prepared messages
                    litellm_response = await self.litellm_service.completion(
                        messages=messages,
                        model=request.model,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        stream=request.stream,
                        response_format=request.response_format,
                        tenant_id=request.tenant_id,
                        metadata=request.metadata,
                        use_cache=request.use_cache,
                        cache_ttl=request.cache_ttl,
                        max_retries=request.max_retries
                    )
                else:
                    # Template not found, proceed with regular prompt
                    litellm_response = await self.litellm_service.completion(
                        prompt=request.prompt,
                        system_prompt=request.system_prompt,
                        messages=request.messages,
                        model=request.model,
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                        stream=request.stream,
                        response_format=request.response_format,
                        tenant_id=request.tenant_id,
                        metadata=request.metadata,
                        use_cache=request.use_cache,
                        cache_ttl=request.cache_ttl,
                        max_retries=request.max_retries
                    )
            else:
                # No template, use direct prompt
                litellm_response = await self.litellm_service.completion(
                    prompt=request.prompt,
                    system_prompt=request.system_prompt,
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=request.stream,
                    response_format=request.response_format,
                    tenant_id=request.tenant_id,
                    metadata=request.metadata,
                    use_cache=request.use_cache,
                    cache_ttl=request.cache_ttl,
                    max_retries=request.max_retries
                )

            # Convert LiteLLMResponse to AIResponse
            usage = SimpleTokenUsage(
                prompt_tokens=litellm_response.usage.get("prompt_tokens", 0),
                completion_tokens=litellm_response.usage.get("completion_tokens", 0),
                total_tokens=litellm_response.usage.get("total_tokens", 0)
            )

            response = AIResponse(
                content=litellm_response.content,
                model=litellm_response.model,
                usage=usage,
                cost=litellm_response.cost,
                response_time_ms=litellm_response.response_time_ms,
                tenant_id=request.tenant_id,
                completion_id=f"comp_{int(time.time())}_{hash(litellm_response.content[:100]) % 10000}",
                status="completed",
                from_cache=litellm_response.cached,
                fallback_used=litellm_response.fallback_used,
                retry_count=litellm_response.retry_count,
                request_id=request.request_id
            )

            return response

        except Exception as e:
            logger.error(f"AI completion failed: {str(e)}")
            raise

    async def batch_completion(
        self,
        requests: List[AIRequest],
        max_concurrent: int = 5
    ) -> List[AIResponse]:
        """
        Perform batch completions with concurrency control.

        Args:
            requests: List of AI requests
            max_concurrent: Maximum concurrent requests

        Returns:
            List of AI responses
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(req: AIRequest) -> AIResponse:
            async with semaphore:
                return await self.completion(req)

        tasks = [process_with_semaphore(req) for req in requests]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def stream_completion(
        self,
        request: AIRequest
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion response.

        Args:
            request: The AI request to process

        Yields:
            str: Response chunks
        """
        if not self._initialized:
            await self.initialize()

        # Use LiteLLM service for streaming
        # Note: This is a simplified implementation
        # In production, you might want to implement proper async streaming
        response = await self.litellm_service.completion(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            response_format=request.response_format,
            tenant_id=request.tenant_id,
            metadata=request.metadata,
            use_cache=False,  # Disable cache for streaming
            max_retries=request.max_retries
        )

        # For now, yield the complete response
        # In a real implementation, you'd stream chunks as they arrive
        yield response.content

    async def get_service_metrics(self) -> Dict[str, Any]:
        """Get service metrics from LiteLLM service."""
        if not self._initialized:
            await self.initialize()

        return await self.litellm_service.get_metrics()

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on AI service."""
        if not self._initialized:
            await self.initialize()

        # Get health status from LiteLLM service
        litellm_health = await self.litellm_service.health_check()

        # Add AI service specific health checks
        health_status = {
            "service": "ai_service",
            "initialized": self._initialized,
            "prompt_manager": self.prompt_manager is not None,
            "redis_client": self.redis_client is not None,
            "cost_service": self.cost_service is not None,
            "litellm_service": litellm_health
        }

        return health_status