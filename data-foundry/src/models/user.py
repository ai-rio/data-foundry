"""
User model for authentication and authorization

This module defines the User model which represents individual users within
tenant organizations. It handles authentication, authorization, permissions,
and user-specific settings.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import field_validator, model_validator
from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """User role enumeration defining permission levels.

    ADMIN: Full administrative access to all tenant resources
    MANAGER: Can manage users, data, and billing for the tenant
    ANALYST: Can create, view, and modify data
    VIEWER: Read-only access to data
    """

    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User status enumeration.

    ACTIVE: User can access the platform normally
    INACTIVE: User deactivated (e.g., left the organization)
    SUSPENDED: User temporarily blocked (e.g., for security reasons)
    PENDING: User registration pending verification
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class AuthMethod(str, Enum):
    """Authentication method enumeration."""

    PASSWORD = "password"
    SSO = "sso"
    API_KEY = "api_key"
    OAUTH = "oauth"


class User(SQLModel, table=True):
    """User model representing platform users.

    This model stores user authentication data, profile information,
    permissions, and activity tracking. Each user belongs to a tenant.
    """

    __tablename__ = "users"

    # Primary identification
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(
        index=True,
        unique=True,
        description="Unique user identifier (UUID)"
    )
    email: str = Field(
        index=True,
        unique=True,
        description="User email address (also login username)"
    )
    tenant_id: str = Field(
        index=True,
        description="Associated tenant ID for data isolation"
    )

    # Authentication
    hashed_password: Optional[str] = Field(description="Hashed password (null for SSO users)")
    role: UserRole = Field(default=UserRole.ANALYST, description="User role")
    status: UserStatus = Field(default=UserStatus.ACTIVE, description="User status")
    auth_method: AuthMethod = Field(default=AuthMethod.PASSWORD, description="Primary auth method")
    mfa_enabled: bool = Field(default=False, description="Multi-factor authentication enabled")
    mfa_secret: Optional[str] = Field(description="MFA secret (encrypted)")

    # Profile information
    first_name: Optional[str] = Field(description="First name")
    last_name: Optional[str] = Field(description="Last name")
    phone: Optional[str] = Field(description="Phone number")
    avatar_url: Optional[str] = Field(description="Profile avatar URL")
    timezone: Optional[str] = Field(default="UTC", description="User timezone")
    language: Optional[str] = Field(default="en", description="Preferred language")

    # Department and organization
    department: Optional[str] = Field(description="Department within organization")
    job_title: Optional[str] = Field(description="Job title")
    manager_id: Optional[str] = Field(index=True, description="Manager's user ID")

    # Granular permissions (overrides role-based permissions)
    can_create_data: bool = Field(default=True, description="Can create new data")
    can_view_data: bool = Field(default=True, description="Can view data")
    can_modify_data: bool = Field(default=False, description="Can modify existing data")
    can_delete_data: bool = Field(default=False, description="Can delete data")
    can_manage_users: bool = Field(default=False, description="Can manage tenant users")
    can_view_billing: bool = Field(default=False, description="Can view billing information")
    can_manage_billing: bool = Field(default=False, description="Can manage billing settings")
    can_export_data: bool = Field(default=True, description="Can export data")

    # API and integration access
    api_key: Optional[str] = Field(
        unique=True,
        index=True,
        description="API key for service access"
    )
    api_key_expires_at: Optional[datetime] = Field(description="API key expiration")
    allowed_ips: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Whitelisted IP addresses for API access"
    )

    # User preferences and settings
    preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="User-specific preferences"
    )
    notifications: Optional[Dict[str, bool]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Notification preferences"
    )

    # Usage tracking
    data_records_created: int = Field(default=0, description="Number of data records created")
    data_records_processed: int = Field(default=0, description="Number of records processed")
    last_activity: Optional[datetime] = Field(description="Last activity timestamp")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    last_login: Optional[datetime] = Field(description="Last successful login")
    password_changed_at: Optional[datetime] = Field(description="When password was last changed")
    suspended_at: Optional[datetime] = Field(description="When user was suspended")
    deactivated_at: Optional[datetime] = Field(description="When user was deactivated")

    # Metadata
    is_system_user: bool = Field(default=False, description="System user (auto-managed)")
    invitation_token: Optional[str] = Field(description="Invitation token for new users")
    invitation_expires_at: Optional[datetime] = Field(description="Invitation expiration")
    notes: Optional[str] = Field(description="Admin notes about user")

    @model_validator(mode='after')
    def set_role_based_permissions(self):
        """Set permission flags based on user role."""
        if self.role == UserRole.ADMIN:
            # Admin gets all permissions
            self.can_create_data = True
            self.can_modify_data = True
            self.can_delete_data = True
            self.can_manage_users = True
            self.can_view_billing = True
            self.can_manage_billing = True
            self.can_export_data = True
        elif self.role == UserRole.MANAGER:
            # Manager gets most permissions except billing management
            self.can_create_data = True
            self.can_modify_data = True
            self.can_delete_data = True
            self.can_manage_users = True
            self.can_view_billing = True
            self.can_manage_billing = False  # Managers can't manage billing
            self.can_export_data = True
        elif self.role == UserRole.ANALYST:
            # Analyst can create and modify but not delete
            self.can_create_data = True
            self.can_modify_data = True
            self.can_delete_data = False
            self.can_manage_users = False
            self.can_view_billing = False
            self.can_manage_billing = False
            self.can_export_data = True
        elif self.role == UserRole.VIEWER:
            # Viewer only gets view permissions
            self.can_create_data = False
            self.can_modify_data = False
            self.can_delete_data = False
            self.can_manage_users = False
            self.can_view_billing = False
            self.can_manage_billing = False
            self.can_export_data = False  # Viewers can't export

        return self

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

    # Table indexes for optimal performance
    __table_args__ = (
        Index('idx_users_tenant_status', 'tenant_id', 'status'),
        Index('idx_users_tenant_role', 'tenant_id', 'role'),
        Index('idx_users_email_tenant', 'email', 'tenant_id'),
        Index('idx_users_manager', 'manager_id'),
        Index('idx_users_last_login', 'last_login'),
        Index('idx_users_api_key', 'api_key'),
    )

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email or "Unknown User"

    @property
    def has_admin_privileges(self) -> bool:
        """Check if user has admin privileges."""
        return self.role == UserRole.ADMIN

    @property
    def can_manage_tenant(self) -> bool:
        """Check if user can manage tenant settings."""
        return self.role in [UserRole.ADMIN, UserRole.MANAGER]

    @property
    def is_active(self) -> bool:
        """Check if user is active and can access the platform."""
        return self.status == UserStatus.ACTIVE

    @property
    def requires_password_change(self) -> bool:
        """Check if user needs to change password."""
        if not self.hashed_password or self.auth_method != AuthMethod.PASSWORD:
            return False
        if not self.password_changed_at:
            return True
        # Require password change every 90 days
        days_since_change = (datetime.now(timezone.utc) - self.password_changed_at).days
        return days_since_change > 90

    @property
    def display_name(self) -> str:
        """Get display name for UI."""
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name[0]}."
            return self.first_name
        return self.email.split("@")[0] if "@" in self.email else self.email