"""
Test data models and fixtures for AI and Cost services.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field


class AIProvider(str, Enum):
    """AI Provider enumeration."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    GOOGLE = "google"
    COHERE = "cohere"


class CompletionStatus(str, Enum):
    """Completion status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class TokenUsage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = Field(ge=0, description="Number of prompt tokens")
    completion_tokens: int = Field(ge=0, description="Number of completion tokens")
    total_tokens: int = Field(ge=0, description="Total number of tokens")

    @property
    def cost_per_token(self) -> Optional[Decimal]:
        """Calculate cost per token if pricing is available."""
        return None


class AIRequest(BaseModel):
    """AI completion request model."""
    prompt: str = Field(description="The main prompt or question")
    system_prompt: Optional[str] = Field(default=None, description="System prompt for context")
    messages: Optional[List[Dict[str, str]]] = Field(default=None, description="Full message history")
    model: Optional[str] = Field(default=None, description="Specific model to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="Maximum tokens to generate")
    stream: bool = Field(default=False, description="Enable streaming response")
    response_format: Optional[str] = Field(default=None, description="Response format (e.g., 'json')")

    # Template support
    prompt_template: Optional[str] = Field(default=None, description="Prompt template name")
    template_vars: Optional[Dict[str, Any]] = Field(default=None, description="Template variables")

    # Metadata
    tenant_id: str = Field(description="Tenant identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier")
    request_id: Optional[str] = Field(default=None, description="Request identifier")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")

    # Behavior controls
    use_cache: bool = Field(default=True, description="Use cached responses if available")
    cache_ttl: Optional[int] = Field(default=3600, description="Cache TTL in seconds")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    timeout: Optional[int] = Field(default=30, description="Request timeout in seconds")

    class Config:
        use_enum_values = True


class AIResponse(BaseModel):
    """AI completion response model."""
    content: str = Field(description="Generated content")
    model: str = Field(description="Model used for generation")
    usage: TokenUsage = Field(description="Token usage information")
    cost: Decimal = Field(description="Calculated cost")
    response_time_ms: float = Field(description="Response time in milliseconds")

    # Metadata
    tenant_id: str = Field(description="Tenant identifier")
    request_id: Optional[str] = Field(default=None, description="Original request ID")
    completion_id: str = Field(description="Completion identifier")
    status: CompletionStatus = Field(description="Completion status")
    from_cache: bool = Field(default=False, description="Response from cache")

    # Error information
    error: Optional[str] = Field(default=None, description="Error message if failed")
    fallback_used: bool = Field(default=False, description="Fallback model was used")
    retry_count: int = Field(default=0, description="Number of retries attempted")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    cached_at: Optional[datetime] = Field(default=None, description="When response was cached")

    class Config:
        use_enum_values = True


class ModelPricing(BaseModel):
    """Model pricing information."""
    provider: AIProvider = Field(description="AI provider")
    model: str = Field(description="Model name")
    input_token_cost: Decimal = Field(description="Cost per 1K input tokens")
    output_token_cost: Decimal = Field(description="Cost per 1K output tokens")
    context_window: int = Field(description="Maximum context window")

    # Tiered pricing
    volume_tiers: Optional[Dict[str, Dict[str, Decimal]]] = Field(
        default=None,
        description="Pricing tiers based on volume"
    )

    # Currency
    currency: str = Field(default="USD", description="Currency code")

    # Metadata
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    valid_until: Optional[datetime] = Field(default=None, description="Pricing validity end date")

    class Config:
        use_enum_values = True


class CostCalculation(BaseModel):
    """Cost calculation breakdown."""
    model: str = Field(description="Model used")
    provider: AIProvider = Field(description="AI provider")
    prompt_tokens: int = Field(description="Number of prompt tokens used")
    completion_tokens: int = Field(description="Number of completion tokens used")
    total_tokens: int = Field(description="Total tokens used")
    input_cost: Decimal = Field(description="Cost for input tokens")
    output_cost: Decimal = Field(description="Cost for output tokens")
    total_cost: Decimal = Field(description="Total cost")

    # Pricing details
    input_rate: Decimal = Field(description="Input token rate")
    output_rate: Decimal = Field(description="Output token rate")
    volume_tier: Optional[str] = Field(default=None, description="Volume tier applied")

    # Metadata
    tenant_id: str = Field(description="Tenant identifier")
    calculation_date: datetime = Field(default_factory=datetime.utcnow)
    currency: str = Field(default="USD", description="Currency code")

    class Config:
        use_enum_values = True


class UsageTracking(BaseModel):
    """Usage tracking record."""
    tenant_id: str = Field(description="Tenant identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier")
    date: datetime = Field(description="Usage date (grouped by day)")

    # Token usage
    total_prompt_tokens: int = Field(default=0, description="Total prompt tokens")
    total_completion_tokens: int = Field(default=0, description="Total completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens")

    # Cost tracking
    total_cost: Decimal = Field(default=Decimal('0'), description="Total cost")
    cost_by_model: Optional[Dict[str, Decimal]] = Field(
        default=None,
        description="Cost breakdown by model"
    )

    # Request counts
    total_requests: int = Field(default=0, description="Total requests")
    successful_requests: int = Field(default=0, description="Successful requests")
    failed_requests: int = Field(default=0, description="Failed requests")
    cached_requests: int = Field(default=0, description="Requests served from cache")

    # Model usage
    model_usage: Optional[Dict[str, int]] = Field(
        default=None,
        description="Request count by model"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class BillingEvent(BaseModel):
    """Billing event for Stripe integration."""
    tenant_id: str = Field(description="Tenant identifier")
    event_id: str = Field(description="Unique event identifier")
    timestamp: datetime = Field(description="Event timestamp")

    # Usage details
    meter_id: str = Field(description="Stripe meter ID")
    quantity: int = Field(description="Quantity for meter")
    unit_amount: Decimal = Field(description="Unit amount in cents")

    # Cost breakdown
    total_cost: Decimal = Field(description="Total cost in currency")
    currency: str = Field(default="USD", description="Currency code")

    # Metadata
    metadata: Dict[str, Any] = Field(description="Additional metadata for billing")

    # Status
    status: str = Field(default="pending", description="Billing event status")
    stripe_event_id: Optional[str] = Field(default=None, description="Stripe event ID")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    class Config:
        use_enum_values = True


class AuditLog(BaseModel):
    """Audit log for AI operations."""
    id: Optional[str] = Field(default=None, primary_key=True)
    tenant_id: str = Field(description="Tenant identifier")
    user_id: Optional[str] = Field(default=None, description="User identifier")

    # Operation details
    operation: str = Field(description="Operation type")
    resource_type: str = Field(description="Type of resource")
    resource_id: Optional[str] = Field(default=None, description="Resource identifier")

    # Request/Response details
    request_data: Optional[Dict[str, Any]] = Field(default=None, description="Request data")
    response_data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")

    # Outcome
    success: bool = Field(description="Operation success status")
    error: Optional[str] = Field(default=None, description="Error message if failed")

    # Timing
    duration_ms: Optional[float] = Field(default=None, description="Operation duration")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # IP and user agent
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client user agent")

    class Config:
        use_enum_values = True


# Test fixtures
@pytest.fixture
def sample_ai_request():
    """Sample AI request for testing."""
    return AIRequest(
        prompt="Analyze this data record",
        system_prompt="You are a data analysis expert",
        tenant_id="test_tenant_001",
        user_id="test_user_001",
        temperature=0.3,
        max_tokens=200,
        use_cache=True
    )


@pytest.fixture
def sample_ai_response():
    """Sample AI response for testing."""
    return AIResponse(
        content='{"category": "high_value", "confidence": 0.95}',
        model="gpt-4o",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=50, total_tokens=200),
        cost=Decimal('0.001234'),
        response_time_ms=1250.5,
        tenant_id="test_tenant_001",
        completion_id="comp_test_123",
        status=CompletionStatus.COMPLETED
    )


@pytest.fixture
def sample_model_pricing():
    """Sample model pricing for testing."""
    return ModelPricing(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        input_token_cost=Decimal('0.005'),
        output_token_cost=Decimal('0.015'),
        context_window=128000,
        volume_tiers={
            "small": {"input": Decimal('0.005'), "output": Decimal('0.015')},
            "medium": {"input": Decimal('0.004'), "output": Decimal('0.012')},
            "enterprise": {"input": Decimal('0.003'), "output": Decimal('0.010')}
        }
    )


@pytest.fixture
def sample_cost_calculation():
    """Sample cost calculation for testing."""
    return CostCalculation(
        model="gpt-4o",
        provider=AIProvider.OPENAI,
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
        input_cost=Decimal('0.005'),
        output_cost=Decimal('0.0075'),
        total_cost=Decimal('0.0125'),
        input_rate=Decimal('0.005'),
        output_rate=Decimal('0.015'),
        tenant_id="test_tenant_001"
    )


@pytest.fixture
def sample_usage_tracking():
    """Sample usage tracking record."""
    return UsageTracking(
        tenant_id="test_tenant_001",
        date=datetime(2024, 1, 15),
        total_prompt_tokens=10000,
        total_completion_tokens=5000,
        total_tokens=15000,
        total_cost=Decimal('12.50'),
        cost_by_model={"gpt-4o": Decimal('8.00'), "gpt-3.5-turbo": Decimal('4.50')},
        total_requests=100,
        successful_requests=95,
        failed_requests=3,
        cached_requests=2,
        model_usage={"gpt-4o": 60, "gpt-3.5-turbo": 40}
    )


@pytest.fixture
def sample_billing_event():
    """Sample billing event."""
    return BillingEvent(
        tenant_id="test_tenant_001",
        event_id="evt_test_123",
        timestamp=datetime.utcnow(),
        meter_id="meter_ai_labels_001",
        quantity=1000,
        unit_amount=Decimal('0.05'),
        total_cost=Decimal('0.05'),
        currency="USD",
        metadata={"model": "gpt-4o", "tokens": 1000}
    )


@pytest.fixture
def sample_audit_log():
    """Sample audit log entry."""
    return AuditLog(
        tenant_id="test_tenant_001",
        user_id="test_user_001",
        operation="ai_completion",
        resource_type="ai_request",
        resource_id="req_test_123",
        request_data={"prompt": "Test prompt"},
        response_data={"content": "Test response"},
        metadata={"model": "gpt-4o", "tokens": 100},
        success=True,
        duration_ms=1250.5,
        ip_address="192.168.1.1",
        user_agent="TestAgent/1.0"
    )