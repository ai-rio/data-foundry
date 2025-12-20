"""
Tenant model for multi-tenancy support

This module defines the Tenant model which represents organizations or customers
using the Data Foundry platform. Each tenant has isolated data, user management,
and billing configuration.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from decimal import Decimal

from sqlalchemy import JSON, Column, Index, Numeric
from sqlmodel import Field, SQLModel


class TenantStatus(str, Enum):
    """Tenant status enumeration.

    ACTIVE: Tenant can access the platform normally
    SUSPENDED: Tenant temporarily blocked (e.g., for non-payment)
    INACTIVE: Tenant deactivated (e.g., closed account)
    """
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class Tenant(SQLModel, table=True):
    """Tenant model representing organizations using the platform.

    This model stores tenant-specific configuration including limits, settings,
    billing information, and preferences. All data is isolated by tenant_id.
    """

    __tablename__ = "tenants"

    # Primary identification
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(
        index=True,
        unique=True,
        description="Unique tenant identifier used for data isolation"
    )
    name: str = Field(description="Tenant organization name")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Tenant status")

    # Optional identification
    domain: Optional[str] = Field(
        index=True,
        description="Tenant domain for SSO integration (optional)"
    )

    # Resource limits
    max_users: int = Field(default=10, description="Maximum number of users allowed")
    max_data_records: int = Field(default=100000, description="Maximum data records allowed")
    storage_limit_gb: float = Field(default=10.0, description="Storage limit in GB")

    # AI and processing settings
    enable_pii_redaction: bool = Field(default=True, description="Enable automatic PII redaction")
    enable_ai_labeling: bool = Field(default=True, description="Enable AI-powered data labeling")
    enable_human_review: bool = Field(default=True, description="Enable human review workflow")

    # Cost control settings
    monthly_cost_limit: Optional[Decimal] = Field(
        sa_column=Numeric(precision=19, scale=6),
        description="Monthly cost limit in currency"
    )
    alert_thresholds: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Alert thresholds for usage and costs"
    )

    # Billing configuration
    billing_plan: str = Field(default="free", description="Billing plan identifier")
    stripe_customer_id: Optional[str] = Field(
        index=True,
        description="Stripe customer ID for billing"
    )
    billing_email: Optional[str] = Field(description="Email for billing notifications")
    billing_address: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Billing address information"
    )

    # Feature flags and preferences
    features: Optional[Dict[str, bool]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Feature flags for this tenant"
    )
    preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Tenant preferences and settings"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    suspended_at: Optional[datetime] = Field(description="When tenant was suspended")

    # Metadata
    created_by: Optional[str] = Field(description="User who created the tenant")
    notes: Optional[str] = Field(description="Internal notes about tenant")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    # Table indexes for optimal performance
    __table_args__ = (
        Index('idx_tenants_status_created', 'status', 'created_at'),
        Index('idx_tenants_domain_active', 'domain', 'status'),
        Index('idx_tenants_stripe_customer', 'stripe_customer_id'),
    )

    @property
    def is_active(self) -> bool:
        """Check if tenant is active and can access the platform."""
        return self.status == TenantStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        """Check if tenant is suspended."""
        return self.status == TenantStatus.SUSPENDED

    @property
    def can_create_users(self) -> bool:
        """Check if tenant can create more users based on limits."""
        # This would require checking current user count in implementation
        return self.is_active

    @property
    def can_ingest_data(self) -> bool:
        """Check if tenant can ingest more data based on limits."""
        # This would require checking current data usage in implementation
        return self.is_active