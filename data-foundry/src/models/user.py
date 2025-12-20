"""
User model for authentication and authorization
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(SQLModel, table=True):
    """User model representing platform users."""

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True, description="Unique user identifier")
    email: str = Field(index=True, unique=True, description="User email address")
    tenant_id: str = Field(index=True, description="Associated tenant ID")

    # Authentication
    hashed_password: str = Field(description="Hashed password")
    role: UserRole = Field(default=UserRole.ANALYST, description="User role")
    status: UserStatus = Field(default=UserStatus.ACTIVE, description="User status")

    # Profile
    first_name: Optional[str] = Field(description="First name")
    last_name: Optional[str] = Field(description="Last name")
    phone: Optional[str] = Field(description="Phone number")

    # Permissions
    can_create_data: bool = Field(default=True, description="Can create new data")
    can_view_data: bool = Field(default=True, description="Can view data")
    can_modify_data: bool = Field(default=False, description="Can modify data")
    can_delete_data: bool = Field(default=False, description="Can delete data")
    can_manage_users: bool = Field(default=False, description="Can manage users")

    # API Access
    api_key: Optional[str] = Field(unique=True, description="API key for service access")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    last_login: Optional[datetime] = Field(description="Last login timestamp")

    # Metadata
    is_system_user: bool = Field(default=False, description="System user (auto-managed)")

    class Config:
        """Pydantic configuration."""
        use_enum_values = True

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