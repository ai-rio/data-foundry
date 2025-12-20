"""
Tenant model for multi-tenancy support
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class TenantStatus(str, Enum):
    """Tenant status enumeration."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class Tenant(SQLModel, table=True):
    """Tenant model representing organizations using the platform."""

    __tablename__ = "tenants"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True, unique=True, description="Unique tenant identifier")
    name: str = Field(description="Tenant organization name")
    status: TenantStatus = Field(default=TenantStatus.ACTIVE, description="Tenant status")
    domain: Optional[str] = Field(description="Tenant domain (optional)")
    max_users: int = Field(default=10, description="Maximum number of users")
    max_data_records: int = Field(default=100000, description="Maximum data records")
    storage_limit_gb: float = Field(default=10.0, description="Storage limit in GB")

    # Settings
    enable_pii_redaction: bool = Field(default=True, description="Enable PII redaction")
    enable_ai_labeling: bool = Field(default=True, description="Enable AI labeling")
    enable_human_review: bool = Field(default=True, description="Enable human review")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # Metadata
    created_by: Optional[str] = Field(description="User who created the tenant")
    billing_plan: Optional[str] = Field(default="free", description="Billing plan")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    @property
    def is_active(self) -> bool:
        """Check if tenant is active."""
        return self.status == TenantStatus.ACTIVE