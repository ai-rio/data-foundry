"""
AI Service with LiteLLM Integration

This service provides a unified interface for multiple AI providers through LiteLLM,
including fallback mechanisms, cost tracking, and comprehensive audit trails.

AML Service Extension (P01-009):
- aml_completion() method for AML transaction labeling
- Response validation for AML-specific fields
- Cost tracking integration for AML operations
"""

import json
import logging
import asyncio
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from decimal import Decimal
import time

from pydantic import BaseModel, Field, field_validator, ValidationError

from src.services.litellm_service import LiteLLMService, LiteLLMResponse
from src.core.config import settings
from src.core.prompts.cached_prompt_manager import CachedPromptManager
from src.core.prompts.aml_labeling_prompt import FATF_TYPOLOGIES
from src.services.redis_service import RedisService
from src.services.cost_service import CostService
from src.database.connection import get_db_session
from src.models.usage_tracking import TenantUsage, AuditLog


# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# AML Response Models (P01-009)
# =============================================================================


class AMLLabelResponse(BaseModel):
    """
    Validated AML label response structure.

    This model validates the AI-generated AML classification response,
    ensuring all required fields are present and correctly typed.

    Reference: P01-009 (AI Service Extension for AML)
    """

    risk_level: str = Field(
        ...,
        description="Risk classification: LOW, MEDIUM, HIGH, or CRITICAL"
    )
    typology: str = Field(
        ...,
        description="FATF typology code (e.g., ML, TF, PEP, FRAUD)"
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI model confidence score (0.00 - 1.00)"
    )
    reasoning: str = Field(
        ...,
        min_length=1,
        description="AI model reasoning for explainability"
    )
    regulatory_flags: Optional[List[str]] = Field(
        default=None,
        description="Optional list of regulatory flags detected"
    )

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        """Validate risk level is one of the allowed values."""
        allowed_levels = settings.AML_RISK_LEVELS
        v_upper = v.upper()
        if v_upper not in allowed_levels:
            raise ValueError(
                f"risk_level must be one of {allowed_levels}, got '{v}'"
            )
        return v_upper

    @field_validator("typology")
    @classmethod
    def validate_typology(cls, v: str) -> str:
        """
        Validate typology is a non-empty string and valid FATF typology.

        Ensures the typology matches one of the FATF-standard codes defined
        in the AML labeling prompt (e.g., ML, TF, PEP, FRAUD, SANCTIONS).

        Args:
            v: Typology string to validate

        Returns:
            Uppercase validated typology code

        Raises:
            ValueError: If typology is empty or not a valid FATF typology
        """
        v_stripped = v.strip().upper()
        if not v_stripped:
            raise ValueError("typology cannot be empty")
        if v_stripped not in FATF_TYPOLOGIES:
            raise ValueError(
                f"typology must be one of {sorted(FATF_TYPOLOGIES)}, got '{v_stripped}'"
            )
        return v_stripped

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence_score(cls, v: float) -> float:
        """
        Validate confidence score is within valid range and round for consistency.

        Confidence scores are rounded to 4 decimal places using Python's round()
        function, which uses banker's rounding (round half to even). This ensures
        consistent precision across the system and prevents floating-point anomalies.

        Args:
            v: Confidence score to validate (typically 0.0 to 1.0)

        Returns:
            Rounded confidence score to 4 decimal places

        Raises:
            ValueError: If confidence_score is outside the valid range [0.0, 1.0]
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"confidence_score must be between 0.0 and 1.0, got {v}"
            )
        return round(v, 4)  # Round to 4 decimal places for consistency

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "risk_level": self.risk_level,
            "typology": self.typology,
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "regulatory_flags": self.regulatory_flags or []
        }


class AMLCompletionResult(BaseModel):
    """
    Complete result from AML completion including response and metadata.

    This model encapsulates the validated AML response along with
    cost tracking and usage information.
    """

    # AML Classification Result
    label: Optional[AMLLabelResponse] = Field(
        default=None,
        description="Validated AML label response (None if validation failed)"
    )

    # Metadata
    success: bool = Field(
        default=False,
        description="Whether the completion was successful"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if completion failed"
    )
    validation_errors: Optional[List[str]] = Field(
        default=None,
        description="List of validation errors if response validation failed"
    )

    # Cost Tracking
    model_used: Optional[str] = Field(
        default=None,
        description="Model used for the completion"
    )
    prompt_tokens: int = Field(
        default=0,
        description="Number of prompt tokens used"
    )
    completion_tokens: int = Field(
        default=0,
        description="Number of completion tokens used"
    )
    total_tokens: int = Field(
        default=0,
        description="Total tokens used"
    )
    cost: Decimal = Field(
        default=Decimal("0"),
        description="Cost of the completion in USD"
    )

    # Timing
    response_time_ms: float = Field(
        default=0.0,
        description="Response time in milliseconds"
    )
    from_cache: bool = Field(
        default=False,
        description="Whether the response was from cache"
    )

    # Request tracking
    request_id: Optional[str] = Field(
        default=None,
        description="Request ID for tracing"
    )

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True  # Allow Decimal type

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "label": self.label.to_dict() if self.label else None,
            "success": self.success,
            "error": self.error,
            "validation_errors": self.validation_errors,
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost": str(self.cost),
            "response_time_ms": self.response_time_ms,
            "from_cache": self.from_cache,
            "request_id": self.request_id
        }


class AMLResponseValidationError(Exception):
    """Exception raised when AML response validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


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
        self.created_at = datetime.now(timezone.utc)
        self.cached_at = datetime.now(timezone.utc) if from_cache else None


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

    # =========================================================================
    # AML Service Extension (P01-009)
    # =========================================================================

    async def aml_completion(
        self,
        transaction_data: Dict[str, Any],
        prompt_template: str,
        tenant_id: str = "default",
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        use_cache: bool = True,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform AML transaction labeling completion.

        This method calls the underlying LLM to classify a transaction for
        AML (Anti-Money Laundering) risk assessment. It validates the response
        structure and integrates with cost tracking.

        Args:
            transaction_data: Transaction data to be classified. Should include
                relevant fields like amount, parties, transaction type, etc.
            prompt_template: The AML-specific prompt template string. Should be
                a complete prompt that will be formatted with transaction_data.
            tenant_id: Tenant identifier for multi-tenancy isolation and billing.
            model: Specific model to use (falls back to PRIMARY_MODEL from config).
            timeout: Request timeout in seconds (defaults to AML_LABELING_TIMEOUT_SECONDS).
            use_cache: Whether to use cached responses for identical requests.
            request_id: Optional request ID for tracing and logging.
            metadata: Additional metadata for tracking and audit purposes.

        Returns:
            dict: AML completion result containing:
                - label: Validated AML label (risk_level, typology, confidence_score, reasoning)
                - success: Whether the completion was successful
                - error: Error message if completion failed
                - validation_errors: List of validation errors if response validation failed
                - model_used: Model used for the completion
                - prompt_tokens: Number of prompt tokens used
                - completion_tokens: Number of completion tokens used
                - total_tokens: Total tokens used
                - cost: Cost of the completion in USD (as string)
                - response_time_ms: Response time in milliseconds
                - from_cache: Whether the response was from cache
                - request_id: Request ID for tracing

        Raises:
            asyncio.TimeoutError: If the request exceeds the configured timeout.

        Reference: P01-009 (AI Service Extension for AML - Step 1: Hybrid)

        Example:
            >>> transaction = {"amount": 50000, "sender": "John Doe", "recipient": "Shell Corp"}
            >>> prompt = "Classify this transaction for AML risk: {transaction}"
            >>> result = await ai_service.aml_completion(transaction, prompt)
            >>> if result["success"]:
            ...     print(f"Risk Level: {result['label']['risk_level']}")
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        # Generate request ID if not provided
        request_id = request_id or f"aml_{int(time.time())}_{hash(str(transaction_data)) % 10000}"

        # Use configured timeout if not specified
        timeout = timeout or settings.AML_LABELING_TIMEOUT_SECONDS

        # Use primary model if not specified
        model = model or self.primary_model

        # Prepare result structure
        result = AMLCompletionResult(
            request_id=request_id,
            model_used=model
        )

        try:
            # Format the prompt with transaction data
            formatted_prompt = self._format_aml_prompt(
                prompt_template,
                transaction_data
            )

            # Prepare metadata for cost tracking
            aml_metadata = {
                "operation_type": "aml_labeling",
                "transaction_id": transaction_data.get("transaction_id", "unknown"),
                "tenant_id": tenant_id,
                **(metadata or {})
            }

            # Create AI request with JSON response format
            request = AIRequest(
                prompt=formatted_prompt,
                system_prompt=self._get_aml_system_prompt(),
                model=model,
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=1024,  # Sufficient for AML response
                response_format="json",  # Request JSON output
                tenant_id=tenant_id,
                request_id=request_id,
                metadata=aml_metadata,
                use_cache=use_cache,
                cache_ttl=3600,  # 1 hour cache for AML responses
                max_retries=2,  # Limited retries for timeout scenarios
                timeout=timeout
            )

            # Execute completion with timeout
            try:
                response = await asyncio.wait_for(
                    self.completion(request),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"AML completion timed out after {timeout}s for request {request_id}"
                )
                result.error = f"Request timed out after {timeout} seconds"
                result.response_time_ms = (time.time() - start_time) * 1000
                return result.to_dict()

            # Update result with response metadata
            result.response_time_ms = response.response_time_ms
            result.from_cache = response.from_cache
            result.prompt_tokens = response.usage.prompt_tokens
            result.completion_tokens = response.usage.completion_tokens
            result.total_tokens = response.usage.total_tokens
            result.cost = response.cost
            result.model_used = response.model

            # Parse and validate the response
            try:
                validated_label = self._validate_aml_response(response.content)
                result.label = validated_label
                result.success = True

                logger.info(
                    f"AML completion successful for request {request_id}: "
                    f"risk_level={validated_label.risk_level}, "
                    f"confidence={validated_label.confidence_score}, "
                    f"cost=${result.cost}"
                )

            except AMLResponseValidationError as validation_error:
                result.error = str(validation_error)
                result.validation_errors = validation_error.errors
                logger.warning(
                    f"AML response validation failed for request {request_id}: "
                    f"{validation_error.errors}"
                )

            # Track cost for billing
            await self._track_aml_cost(
                tenant_id=tenant_id,
                result=result,
                transaction_data=transaction_data
            )

            return result.to_dict()

        except asyncio.TimeoutError:
            # Handle timeout from the outer try block
            logger.error(
                f"AML completion timed out for request {request_id}"
            )
            result.error = f"Request timed out after {timeout} seconds"
            result.response_time_ms = (time.time() - start_time) * 1000
            return result.to_dict()

        except Exception as e:
            # Handle all other errors gracefully
            logger.error(
                f"AML completion failed for request {request_id}: {str(e)}",
                exc_info=True
            )
            result.error = f"Completion failed: {str(e)}"
            result.response_time_ms = (time.time() - start_time) * 1000
            return result.to_dict()

    def _format_aml_prompt(
        self,
        prompt_template: str,
        transaction_data: Dict[str, Any]
    ) -> str:
        """
        Format the AML prompt template with transaction data.

        Supports both simple string formatting and Jinja2-style templates.

        Args:
            prompt_template: The prompt template string
            transaction_data: Transaction data to insert into the template

        Returns:
            str: Formatted prompt string
        """
        try:
            # Try simple format() first
            if "{transaction_data}" in prompt_template:
                return prompt_template.format(
                    transaction_data=json.dumps(transaction_data, indent=2)
                )
            elif "{" in prompt_template and "}" in prompt_template:
                # Try to format with transaction data fields
                return prompt_template.format(**transaction_data)
            else:
                # Append transaction data if no placeholders found
                return f"{prompt_template}\n\nTransaction Data:\n{json.dumps(transaction_data, indent=2)}"

        except (KeyError, ValueError) as e:
            logger.warning(
                f"Failed to format AML prompt template: {e}. "
                f"Appending transaction data as JSON."
            )
            return f"{prompt_template}\n\nTransaction Data:\n{json.dumps(transaction_data, indent=2)}"

    def _get_aml_system_prompt(self) -> str:
        """
        Get the system prompt for AML classification.

        Returns:
            str: System prompt instructing the model for AML classification
        """
        return """You are an expert AML (Anti-Money Laundering) analyst assistant.

Your task is to analyze transaction data and provide a risk classification.

You MUST respond with valid JSON in the following format:
{
    "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
    "typology": "<FATF typology code: ML|TF|PEP|FRAUD|SANCTIONS|TAX_EVASION|BRIBERY|SMUGGLING|DRUG_TRAFFICKING|HUMAN_TRAFFICKING|PROLIFERATION|CYBERCRIME|ENVIRONMENTAL>",
    "confidence_score": <float between 0.0 and 1.0>,
    "reasoning": "<detailed explanation of your risk assessment>",
    "regulatory_flags": ["<optional list of regulatory flags detected>"]
}

Guidelines:
- LOW: Normal transaction with no suspicious indicators
- MEDIUM: Some risk indicators present, requires monitoring
- HIGH: Significant risk indicators, requires investigation
- CRITICAL: Clear indicators of potential money laundering or terrorist financing

Always provide clear, concise reasoning for your classification.
"""

    def _validate_aml_response(self, response_content: str) -> AMLLabelResponse:
        """
        Validate and parse the AML response from the LLM.

        This method handles various response formats including:
        - Clean JSON responses
        - JSON embedded in markdown code blocks
        - Malformed JSON with common issues

        Args:
            response_content: Raw response content from the LLM

        Returns:
            AMLLabelResponse: Validated AML label response

        Raises:
            AMLResponseValidationError: If validation fails
        """
        errors = []

        # Clean the response content
        cleaned_content = self._clean_json_response(response_content)

        # Try to parse as JSON
        try:
            response_data = json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON response: {str(e)}")
            logger.error(
                f"Failed to parse AML response as JSON: {e}. "
                f"Content preview: {response_content[:200]}..."
            )
            raise AMLResponseValidationError(
                "Failed to parse response as JSON",
                errors=errors
            )

        # Validate using Pydantic model
        try:
            validated_response = AMLLabelResponse(**response_data)
            return validated_response

        except ValidationError as e:
            # Extract validation error messages
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                msg = error["msg"]
                errors.append(f"{field}: {msg}")

            logger.warning(
                f"AML response validation failed: {errors}. "
                f"Response data: {response_data}"
            )
            raise AMLResponseValidationError(
                "Response validation failed",
                errors=errors
            )

    def _clean_json_response(self, content: str) -> str:
        """
        Clean and extract JSON from response content.

        Handles common issues like:
        - Markdown code blocks
        - Leading/trailing whitespace
        - BOM characters

        Args:
            content: Raw response content

        Returns:
            str: Cleaned JSON string
        """
        # Remove BOM and strip whitespace
        content = content.strip().lstrip('\ufeff')

        # Extract JSON from markdown code blocks
        json_block_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
        matches = re.findall(json_block_pattern, content, re.MULTILINE)

        if matches:
            # Use the first JSON block found
            content = matches[0].strip()

        # Try to find JSON object boundaries if still not clean
        if not content.startswith('{'):
            # Find first { and last }
            start_idx = content.find('{')
            end_idx = content.rfind('}')

            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                content = content[start_idx:end_idx + 1]

        return content

    async def _track_aml_cost(
        self,
        tenant_id: str,
        result: AMLCompletionResult,
        transaction_data: Dict[str, Any]
    ) -> None:
        """
        Track cost for AML completion for billing purposes.

        Integrates with the existing cost tracking system to record
        usage for billing and analytics.

        Args:
            tenant_id: Tenant identifier for billing
            result: The AML completion result
            transaction_data: Original transaction data for context
        """
        if not self.cost_service:
            logger.warning("Cost service not initialized, skipping cost tracking")
            return

        try:
            # Calculate cost if not already set
            if result.total_tokens > 0 and result.model_used:
                try:
                    cost_calculation = await self.cost_service.calculate_cost(
                        model=result.model_used,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        tenant_id=tenant_id,
                        request_id=result.request_id,
                        metadata={
                            "operation_type": "aml_labeling",
                            "transaction_id": transaction_data.get("transaction_id"),
                            "risk_level": result.label.risk_level if result.label else None,
                            "success": result.success
                        }
                    )

                    # Log cost tracking
                    logger.info(
                        f"AML cost tracked for tenant {tenant_id}: "
                        f"tokens={result.total_tokens}, "
                        f"cost=${cost_calculation.total_cost}"
                    )

                except ValueError as e:
                    # Model not in pricing database - use the cost from response
                    logger.debug(
                        f"Model {result.model_used} not in pricing database, "
                        f"using response cost: {result.cost}"
                    )

        except Exception as e:
            # Don't fail the main operation for cost tracking errors
            logger.error(f"Failed to track AML cost: {str(e)}")

    async def batch_aml_completion(
        self,
        transactions: List[Dict[str, Any]],
        prompt_template: str,
        tenant_id: str = "default",
        max_concurrent: int = 5,
        model: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform batch AML transaction labeling with concurrency control.

        Args:
            transactions: List of transaction data dictionaries to classify
            prompt_template: The AML-specific prompt template string
            tenant_id: Tenant identifier for multi-tenancy isolation
            max_concurrent: Maximum concurrent requests (default: 5)
            model: Specific model to use
            timeout: Request timeout in seconds

        Returns:
            List of AML completion results (same order as input transactions)

        Example:
            >>> transactions = [
            ...     {"transaction_id": "T001", "amount": 50000},
            ...     {"transaction_id": "T002", "amount": 100000}
            ... ]
            >>> results = await ai_service.batch_aml_completion(
            ...     transactions,
            ...     "Classify this transaction: {transaction_data}"
            ... )
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(transaction: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.aml_completion(
                    transaction_data=transaction,
                    prompt_template=prompt_template,
                    tenant_id=tenant_id,
                    model=model,
                    timeout=timeout
                )

        tasks = [process_with_semaphore(txn) for txn in transactions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "error": str(result),
                    "label": None,
                    "transaction_id": transactions[i].get("transaction_id", f"index_{i}")
                })
            else:
                processed_results.append(result)

        return processed_results