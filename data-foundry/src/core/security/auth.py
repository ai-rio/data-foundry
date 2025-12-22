"""
Authentication and Authorization System for Incident Response

Provides secure access control for incident management operations.
Implements role-based access control (RBAC) with proper JWT verification.
"""

import logging
from functools import wraps
from typing import Dict, Any, List, Optional, Callable

from src.core.security import get_current_user_token

logger = logging.getLogger(__name__)


class UserRole:
    """User roles for incident response system."""

    SECURITY_ANALYST = "security_analyst"
    INCIDENT_MANAGER = "incident_manager"
    COMPLIENCE_OFFICER = "compliance_officer"
    SYSTEM_ADMIN = "system_admin"
    VIEWER = "viewer"


class IncidentPermissions:
    """Permission definitions for incident operations."""

    # Incident management permissions
    CREATE_INCIDENT = "create_incident"
    VIEW_INCIDENT = "view_incident"
    UPDATE_INCIDENT = "update_incident"
    DELETE_INCIDENT = "delete_incident"

    # Special operations permissions
    INITIATE_GDPR_NOTIFICATION = "initiate_gdpr_notification"
    NOTIFY_DATA_SUBJECTS = "notify_data_subjects"
    EXECUTE_CONTAINMENT = "execute_containment"

    # Management permissions
    VIEW_REPORTS = "view_reports"
    MANAGE_USERS = "manage_users"
    SYSTEM_CONFIG = "system_config"


# Role-based access control matrix
ROLE_PERMISSIONS = {
    UserRole.SECURITY_ANALYST: [
        IncidentPermissions.VIEW_INCIDENT,
        IncidentPermissions.UPDATE_INCIDENT,
        IncidentPermissions.EXECUTE_CONTAINMENT,
        IncidentPermissions.VIEW_REPORTS,
    ],
    UserRole.INCIDENT_MANAGER: [
        IncidentPermissions.CREATE_INCIDENT,
        IncidentPermissions.VIEW_INCIDENT,
        IncidentPermissions.UPDATE_INCIDENT,
        IncidentPermissions.INITIATE_GDPR_NOTIFICATION,
        IncidentPermissions.EXECUTE_CONTAINMENT,
        IncidentPermissions.VIEW_REPORTS,
    ],
    UserRole.COMPLIENCE_OFFICER: [
        IncidentPermissions.VIEW_INCIDENT,
        IncidentPermissions.INITIATE_GDPR_NOTIFICATION,
        IncidentPermissions.NOTIFY_DATA_SUBJECTS,
        IncidentPermissions.VIEW_REPORTS,
    ],
    UserRole.SYSTEM_ADMIN: [
        # System admins have all permissions
        IncidentPermissions.CREATE_INCIDENT,
        IncidentPermissions.VIEW_INCIDENT,
        IncidentPermissions.UPDATE_INCIDENT,
        IncidentPermissions.DELETE_INCIDENT,
        IncidentPermissions.INITIATE_GDPR_NOTIFICATION,
        IncidentPermissions.NOTIFY_DATA_SUBJECTS,
        IncidentPermissions.EXECUTE_CONTAINMENT,
        IncidentPermissions.VIEW_REPORTS,
        IncidentPermissions.MANAGE_USERS,
        IncidentPermissions.SYSTEM_CONFIG,
    ],
    UserRole.VIEWER: [
        IncidentPermissions.VIEW_INCIDENT,
        IncidentPermissions.VIEW_REPORTS,
    ],
}


def get_user_permissions(user: Dict[str, Any]) -> List[str]:
    """
    Get permissions for a user based on their role.

    Args:
        user: User information from JWT token

    Returns:
        List of permission strings
    """
    user_role = user.get("role", UserRole.VIEWER)
    return ROLE_PERMISSIONS.get(user_role, [])


def has_permission(user: Dict[str, Any], permission: str) -> bool:
    """
    Check if user has a specific permission.

    Args:
        user: User information from JWT token
        permission: Permission to check

    Returns:
        True if user has permission, False otherwise
    """
    user_permissions = get_user_permissions(user)
    return permission in user_permissions


def require_authentication(func: Callable) -> Callable:
    """
    Decorator to require authentication.

    This decorator ensures that a valid JWT token is provided
    and extracts user information for further authorization checks.

    Args:
        func: Function to decorate

    Returns:
        Decorated function that requires authentication
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if user is already provided (for internal calls)
        if 'current_user' in kwargs:
            return await func(*args, **kwargs)

        # Get user from token
        try:
            current_user = await get_current_user_token()
            kwargs['current_user'] = current_user
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise PermissionError("Authentication required for this operation")

    return wrapper


def require_role(role: str) -> Callable:
    """
    Decorator to require specific user role.

    Args:
        role: Required role name

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise PermissionError("Authentication required")

            user_role = current_user.get('role')
            if user_role != role:
                raise PermissionError(f"Role '{role}' required for this operation")

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_permission(permission: str) -> Callable:
    """
    Decorator to require specific permission.

    Args:
        permission: Required permission

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise PermissionError("Authentication required")

            if not has_permission(current_user, permission):
                user_permissions = get_user_permissions(current_user)
                logger.warning(
                    f"Permission denied: user {current_user.get('user_id')} "
                    f"with permissions {user_permissions} tried to access "
                    f"operation requiring {permission}"
                )
                raise PermissionError(f"Permission '{permission}' required for this operation")

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_any_permission(*permissions: str) -> Callable:
    """
    Decorator to require any of the specified permissions.

    Args:
        *permissions: List of permissions, any one will suffice

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise PermissionError("Authentication required")

            user_permissions = get_user_permissions(current_user)
            has_any = any(perm in user_permissions for perm in permissions)

            if not has_any:
                logger.warning(
                    f"Permission denied: user {current_user.get('user_id')} "
                    f"with permissions {user_permissions} tried to access "
                    f"operation requiring any of {permissions}"
                )
                raise PermissionError(f"One of permissions {permissions} required for this operation")

            return await func(*args, **kwargs)

        return wrapper
    return decorator


class SecurityContext:
    """
    Security context for incident operations.

    Provides methods to check permissions and log security events.
    """

    def __init__(self, current_user: Dict[str, Any]):
        """
        Initialize security context.

        Args:
            current_user: User information from JWT token
        """
        self.current_user = current_user
        self.user_id = current_user.get('user_id')
        self.user_role = current_user.get('role', UserRole.VIEWER)
        self.permissions = get_user_permissions(current_user)

    def can_create_incident(self) -> bool:
        """Check if user can create incidents."""
        return IncidentPermissions.CREATE_INCIDENT in self.permissions

    def can_view_incident(self) -> bool:
        """Check if user can view incidents."""
        return IncidentPermissions.VIEW_INCIDENT in self.permissions

    def can_update_incident(self) -> bool:
        """Check if user can update incidents."""
        return IncidentPermissions.UPDATE_INCIDENT in self.permissions

    def can_delete_incident(self) -> bool:
        """Check if user can delete incidents."""
        return IncidentPermissions.DELETE_INCIDENT in self.permissions

    def can_initiate_gdpr_notification(self) -> bool:
        """Check if user can initiate GDPR notifications."""
        return IncidentPermissions.INITIATE_GDPR_NOTIFICATION in self.permissions

    def can_notify_data_subjects(self) -> bool:
        """Check if user can notify data subjects."""
        return IncidentPermissions.NOTIFY_DATA_SUBJECTS in self.permissions

    def can_execute_containment(self) -> bool:
        """Check if user can execute containment actions."""
        return IncidentPermissions.EXECUTE_CONTAINMENT in self.permissions

    def can_view_reports(self) -> bool:
        """Check if user can view reports."""
        return IncidentPermissions.VIEW_REPORTS in self.permissions

    def log_access_attempt(self, operation: str, resource_id: str = None, success: bool = True):
        """
        Log access attempt for security auditing.

        Args:
            operation: Operation being attempted
            resource_id: ID of resource being accessed (optional)
            success: Whether access was successful
        """
        logger.info(
            f"Security: User {self.user_id} (role: {self.user_role}) "
            f"{'successfully' if success else 'failed to'} "
            f"{operation} on {resource_id or 'system'}"
        )