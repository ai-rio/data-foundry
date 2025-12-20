"""
Usage tracking and billing models for AI operations.
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
from enum import Enum

from sqlalchemy import JSON, Column, Integer, String, DateTime, Numeric, Boolean, Text
from sqlmodel import Field, SQLModel, Session, select


class UsagePeriod(str, Enum):
    """Usage period enumeration."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class BillingStatus(str, Enum):
    """Billing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class TokenUsage(SQLModel, table=True):
    """Token usage tracking model."""

    __tablename__ = "token_usage"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")
    user_id: Optional[str] = Field(index=True, description="User identifier")

    # Request details
    request_id: str = Field(index=True, description="Request identifier")
    model: str = Field(description="AI model used")
    provider: str = Field(description="AI provider")

    # Token counts
    prompt_tokens: int = Field(description="Prompt tokens used")
    completion_tokens: int = Field(description="Completion tokens used")
    total_tokens: int = Field(description="Total tokens used")

    # Cost information
    input_cost: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Cost for input tokens"
    )
    output_cost: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Cost for output tokens"
    )
    total_cost: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Total cost"
    )
    currency: str = Field(default="USD", description="Currency code")

    # Response details
    response_content: Optional[str] = Field(
        sa_column=Text,
        description="Response content (truncated)"
    )
    response_time_ms: float = Field(description="Response time in milliseconds")

    # Status and metadata
    success: bool = Field(description="Request success status")
    error_message: Optional[str] = Field(description="Error message if failed")
    from_cache: bool = Field(default=False, description="Response from cache")
    fallback_used: bool = Field(default=False, description="Fallback model used")
    retry_count: int = Field(default=0, description="Number of retries")

    # Additional metadata
    additional_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Additional metadata"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class TenantUsage(SQLModel, table=True):
    """Aggregated tenant usage model."""

    __tablename__ = "tenant_usage"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")

    # Period information
    period_type: UsagePeriod = Field(description="Usage period type")
    period_start: date = Field(description="Period start date")
    period_end: date = Field(description="Period end date")

    # Aggregated usage
    total_requests: int = Field(default=0, description="Total requests")
    successful_requests: int = Field(default=0, description="Successful requests")
    failed_requests: int = Field(default=0, description="Failed requests")
    cached_requests: int = Field(default=0, description="Cached requests")

    # Token usage
    total_prompt_tokens: int = Field(default=0, description="Total prompt tokens")
    total_completion_tokens: int = Field(default=0, description="Total completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens")

    # Cost tracking
    total_cost: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        default=Decimal('0'),
        description="Total cost"
    )
    cost_by_model: Optional[Dict[str, Decimal]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Cost breakdown by model"
    )

    # Model usage counts
    model_usage: Optional[Dict[str, int]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Request count by model"
    )

    # Billing information
    billing_status: BillingStatus = Field(default=BillingStatus.PENDING)
    billing_event_id: Optional[str] = Field(description="Billing event identifier")
    invoice_id: Optional[str] = Field(description="Invoice identifier")

    # Limits and thresholds
    cost_limit: Optional[Decimal] = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Cost limit for period"
    )
    token_limit: Optional[int] = Field(description="Token limit for period")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class AuditLog(SQLModel, table=True):
    """Comprehensive audit log model."""

    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")
    user_id: Optional[str] = Field(index=True, description="User identifier")
    session_id: Optional[str] = Field(index=True, description="Session identifier")

    # Operation details
    operation: str = Field(index=True, description="Operation type")
    resource_type: str = Field(index=True, description="Type of resource")
    resource_id: Optional[str] = Field(index=True, description="Resource identifier")

    # Request and response data
    request_method: Optional[str] = Field(description="HTTP method if applicable")
    request_path: Optional[str] = Field(description="Request path")
    request_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Request data (sanitized)"
    )
    response_status: Optional[int] = Field(description="Response status code")
    response_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Response data (sanitized)"
    )

    # Outcome
    success: bool = Field(description="Operation success status")
    error_message: Optional[str] = Field(
        sa_column=Text,
        description="Error message if failed"
    )

    # Performance metrics
    duration_ms: Optional[float] = Field(description="Operation duration")
    cpu_time_ms: Optional[float] = Field(description="CPU time used")
    memory_used_mb: Optional[float] = Field(description="Memory used in MB")

    # Security context
    ip_address: Optional[str] = Field(index=True, description="Client IP address")
    user_agent: Optional[str] = Field(description="Client user agent")
    auth_method: Optional[str] = Field(description="Authentication method")

    # Additional context
    audit_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Additional audit metadata"
    )

    # Timestamps
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)

    class Config:
        use_enum_values = True


class CostAlert(SQLModel, table=True):
    """Cost alert notifications model."""

    __tablename__ = "cost_alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")

    # Alert details
    alert_type: str = Field(description="Alert type")
    severity: str = Field(description="Alert severity")
    title: str = Field(description="Alert title")
    message: str = Field(sa_column=Text, description="Alert message")

    # Threshold information
    threshold_type: str = Field(description="Type of threshold")
    threshold_value: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Threshold value"
    )
    actual_value: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Actual value that triggered alert"
    )

    # Period
    period_start: datetime = Field(description="Alert period start")
    period_end: datetime = Field(description="Alert period end")

    # Status
    acknowledged: bool = Field(default=False, description="Alert acknowledged")
    acknowledged_by: Optional[str] = Field(description="Who acknowledged")
    acknowledged_at: Optional[datetime] = Field(description="Acknowledgment timestamp")

    # Notifications
    notification_sent: bool = Field(default=False, description="Notification sent")
    notification_channels: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Notification channels used"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = Field(description="Resolution timestamp")

    class Config:
        use_enum_values = True


class BillingEvent(SQLModel, table=True):
    """Billing event for Stripe integration."""

    __tablename__ = "billing_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, description="Tenant identifier")
    event_id: str = Field(unique=True, index=True, description="Unique event identifier")

    # Event details
    event_type: str = Field(description="Type of billing event")
    meter_id: str = Field(description="Stripe meter ID")
    quantity: int = Field(description="Quantity for meter")
    unit_amount: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Unit amount in cents"
    )

    # Cost breakdown
    total_cost: Decimal = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Total cost in currency"
    )
    currency: str = Field(default="USD", description="Currency code")

    # Usage details
    usage_period_start: datetime = Field(description="Usage period start")
    usage_period_end: datetime = Field(description="Usage period end")
    usage_data: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Detailed usage data"
    )

    # Status
    status: BillingStatus = Field(default=BillingStatus.PENDING)
    stripe_event_id: Optional[str] = Field(description="Stripe event ID")
    error_message: Optional[str] = Field(
        sa_column=Text,
        description="Error message if failed"
    )
    retry_count: int = Field(default=0, description="Number of retries")

    # Invoicing
    invoice_id: Optional[str] = Field(description="Invoice ID")
    invoice_created: bool = Field(default=False, description="Invoice created")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = Field(description="Processing timestamp")

    class Config:
        use_enum_values = True


# Database operations
async def create_token_usage(
    session: Session,
    tenant_id: str,
    request_id: str,
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    input_cost: Decimal,
    output_cost: Decimal,
    total_cost: Decimal,
    response_time_ms: float,
    success: bool,
    user_id: Optional[str] = None,
    error_message: Optional[str] = None,
    from_cache: bool = False,
    fallback_used: bool = False,
    retry_count: int = 0,
    additional_metadata: Optional[Dict[str, Any]] = None
) -> TokenUsage:
    """Create token usage record."""

    usage = TokenUsage(
        tenant_id=tenant_id,
        user_id=user_id,
        request_id=request_id,
        model=model,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        input_cost=input_cost,
        output_cost=output_cost,
        total_cost=total_cost,
        response_time_ms=response_time_ms,
        success=success,
        error_message=error_message,
        from_cache=from_cache,
        fallback_used=fallback_used,
        retry_count=retry_count,
        additional_metadata=additional_metadata
    )

    session.add(usage)
    await session.commit()
    await session.refresh(usage)

    # Update tenant usage aggregates
    await update_tenant_usage(session, tenant_id, usage)

    return usage


async def update_tenant_usage(
    session: Session,
    tenant_id: str,
    token_usage: TokenUsage
):
    """Update tenant usage aggregates."""

    # Get current period (monthly)
    today = date.today()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    # Find existing tenant usage record
    statement = select(TenantUsage).where(
        TenantUsage.tenant_id == tenant_id,
        TenantUsage.period_type == UsagePeriod.MONTHLY,
        TenantUsage.period_start == period_start
    )

    result = await session.execute(statement)
    tenant_usage = result.scalar_one_or_none()

    if not tenant_usage:
        # Create new record
        tenant_usage = TenantUsage(
            tenant_id=tenant_id,
            period_type=UsagePeriod.MONTHLY,
            period_start=period_start,
            period_end=period_end,
            total_requests=0,
            successful_requests=0,
            failed_requests=0,
            cached_requests=0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_tokens=0,
            total_cost=Decimal('0'),
            cost_by_model={},
            model_usage={}
        )
        session.add(tenant_usage)

    # Update aggregates
    tenant_usage.total_requests += 1
    if token_usage.success:
        tenant_usage.successful_requests += 1
    else:
        tenant_usage.failed_requests += 1

    if token_usage.from_cache:
        tenant_usage.cached_requests += 1

    tenant_usage.total_prompt_tokens += token_usage.prompt_tokens
    tenant_usage.total_completion_tokens += token_usage.completion_tokens
    tenant_usage.total_tokens += token_usage.total_tokens
    tenant_usage.total_cost += token_usage.total_cost

    # Update cost by model
    if not tenant_usage.cost_by_model:
        tenant_usage.cost_by_model = {}
    model_cost = tenant_usage.cost_by_model.get(token_usage.model, Decimal('0'))
    tenant_usage.cost_by_model[token_usage.model] = model_cost + token_usage.total_cost

    # Update model usage
    if not tenant_usage.model_usage:
        tenant_usage.model_usage = {}
    model_count = tenant_usage.model_usage.get(token_usage.model, 0)
    tenant_usage.model_usage[token_usage.model] = model_count + 1

    tenant_usage.updated_at = datetime.utcnow()

    await session.commit()


async def create_audit_log(
    session: Session,
    tenant_id: str,
    operation: str,
    resource_type: str,
    success: bool,
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    request_data: Optional[Dict[str, Any]] = None,
    response_status: Optional[int] = None,
    response_data: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[float] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> AuditLog:
    """Create audit log entry."""

    audit_log = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        request_method=request_method,
        request_path=request_path,
        request_data=request_data,
        response_status=response_status,
        response_data=response_data,
        success=success,
        error_message=error_message,
        duration_ms=duration_ms,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata
    )

    session.add(audit_log)
    await session.commit()
    await session.refresh(audit_log)

    return audit_log


async def get_tenant_usage_report(
    session: Session,
    tenant_id: str,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """Get tenant usage report for date range."""

    # Query token usage
    statement = select(TokenUsage).where(
        TokenUsage.tenant_id == tenant_id,
        TokenUsage.created_at >= datetime.combine(start_date, datetime.min.time()),
        TokenUsage.created_at <= datetime.combine(end_date, datetime.max.time())
    )

    result = await session.execute(statement)
    usages = result.scalars().all()

    # Calculate aggregates
    total_requests = len(usages)
    successful_requests = sum(1 for u in usages if u.success)
    failed_requests = total_requests - successful_requests
    cached_requests = sum(1 for u in usages if u.from_cache)

    total_prompt_tokens = sum(u.prompt_tokens for u in usages)
    total_completion_tokens = sum(u.completion_tokens for u in usages)
    total_tokens = sum(u.total_tokens for u in usages)

    total_cost = sum(u.total_cost for u in usages)

    # Cost by model
    cost_by_model = {}
    model_usage = {}
    for u in usages:
        cost_by_model[u.model] = cost_by_model.get(u.model, Decimal('0')) + u.total_cost
        model_usage[u.model] = model_usage.get(u.model, 0) + 1

    return {
        "tenant_id": tenant_id,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "summary": {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "cached_requests": cached_requests,
            "success_rate": successful_requests / total_requests if total_requests > 0 else 0
        },
        "usage": {
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "average_tokens_per_request": total_tokens / total_requests if total_requests > 0 else 0
        },
        "costs": {
            "total_cost": float(total_cost),
            "average_cost_per_request": float(total_cost / total_requests) if total_requests > 0 else 0,
            "cost_per_million_tokens": float((total_cost / total_tokens) * 1000000) if total_tokens > 0 else 0,
            "cost_by_model": {k: float(v) for k, v in cost_by_model.items()}
        },
        "models": {
            "model_usage": model_usage,
            "most_used_model": max(model_usage.items(), key=lambda x: x[1])[0] if model_usage else None
        }
    }