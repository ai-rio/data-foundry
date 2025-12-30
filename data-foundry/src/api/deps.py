"""
FastAPI Dependencies Module.

Contains common FastAPI dependency functions for authentication,
authorization, and request processing.

P4-005 Updates:
- Added require_admin dependency with database verification
- Added require_role dependency for role-based access control
"""

from typing import Dict, Any, Optional
import logging

from fastapi import Depends, HTTPException, Request
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core.jwt_verifier import verify_jwt
from src.database.connection import db_connection
from src.models.user import User, UserRole


logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE DEPENDENCIES
# ============================================================================

async def get_db_session() -> AsyncSession:
    """Get async database session for FastAPI dependency injection."""
    async with db_connection.get_session() as session:
        yield session


# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency to verify Clerk JWT and extract user info.

    This dependency:
    1. Extracts JWT from Authorization header
    2. Verifies JWT signature using Clerk JWKS
    3. Validates claims (issuer, audience, expiration)
    4. Returns decoded payload

    Args:
        request: FastAPI Request object

    Returns:
        JWT payload dictionary containing:
            - sub: User ID
            - tenant_id: Tenant ID (if present as custom claim)
            - iss: Issuer
            - aud: Audience
            - exp: Expiration timestamp
            - iat: Issued at timestamp

    Raises:
        HTTPException: If token is missing, invalid, or expired (401)

    Usage in FastAPI routes:
        ```python
        from fastapi import APIRouter, Depends
        from src.api.deps import get_current_user

        router = APIRouter()

        @router.get("/protected")
        async def protected_route(current_user: dict = Depends(get_current_user)):
            user_id = current_user["sub"]
            return {"message": f"Hello, user {user_id}"}
        ```
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format (expected 'Bearer <token>')"
        )

    token = auth_header.replace("Bearer ", "")
    payload = await verify_jwt(token)

    return payload


async def get_optional_user(request: Request) -> Dict[str, Any] | None:
    """
    Optional JWT verification - returns None if no valid token.

    Unlike get_current_user, this does NOT raise an exception
    if authentication fails, making it useful for routes that
    work for both authenticated and unauthenticated users.

    Args:
        request: FastAPI Request object

    Returns:
        JWT payload dictionary if token valid, None otherwise

    Usage:
        ```python
        @router.get("/public")
        async def public_route(user: dict | None = Depends(get_optional_user)):
            if user:
                return {"message": f"Hello, {user['sub']}"}
            return {"message": "Hello, anonymous user"}
        ```
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    try:
        token = auth_header.replace("Bearer ", "")
        payload = await verify_jwt(token)
        return payload
    except HTTPException:
        return None


def get_user_id(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """
    Extract user_id from current user dependency.

    Convenience dependency for routes that only need the user_id.

    Args:
        current_user: Current user from get_current_user dependency

    Returns:
        User ID (sub claim from JWT)

    Usage:
        ```python
        @router.get("/my-data")
        async def get_my_data(user_id: str = Depends(get_user_id)):
            return {"user_id": user_id}
        ```
    """
    return current_user.get("sub", "")


def get_tenant_id(current_user: Dict[str, Any] = Depends(get_current_user)) -> str | None:
    """
    Extract tenant_id from current user dependency.

    Convenience dependency for multi-tenant applications.
    Returns None if tenant_id is not present in JWT.

    Args:
        current_user: Current user from get_current_user dependency

    Returns:
        Tenant ID (custom claim from JWT) or None

    Usage:
        ```python
        @router.get("/tenant-data")
        async def get_tenant_data(tenant_id: str | None = Depends(get_tenant_id)):
            return {"tenant_id": tenant_id}
        ```
    """
    return current_user.get("tenant_id")


# ============================================================================
# ADMIN AUTHORIZATION DEPENDENCIES (P4-005)
# ============================================================================

async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Verify that the current user has admin role in the database.

    This dependency performs database verification of admin role to prevent
    JWT tampering and ensure authorization is enforced at the database level.

    Args:
        current_user: Current user from JWT verification
        session: Database session for querying user roles

    Returns:
        User object with admin role

    Raises:
        HTTPException 401: If user not found in database
        HTTPException 403: If user does not have admin role

    Usage:
        ```python
        @router.post("/admin-only")
        async def admin_endpoint(admin_user: User = Depends(require_admin)):
            return {"message": f"Hello, Admin {admin_user.email}"}
        ```
    """
    user_id = current_user.get("sub")

    if not user_id:
        logger.warning("require_admin: No user_id in JWT payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    # Query database for user
    query = select(User).where(User.user_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"require_admin: User {user_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Verify admin role
    if user.role != UserRole.ADMIN:
        logger.warning(
            f"require_admin: User {user_id} has role {user.role}, not admin"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Check user status
    if user.status != "active":
        logger.warning(
            f"require_admin: User {user_id} has status {user.status}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    logger.info(f"require_admin: User {user_id} verified as admin")
    return user


async def require_role(
    required_role: UserRole,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    """
    Verify that the current user has the required role in the database.

    This dependency performs database verification of user roles to prevent
    JWT tampering and ensure authorization is enforced at the database level.

    Args:
        required_role: Minimum role required for access
        current_user: Current user from JWT verification
        session: Database session for querying user roles

    Returns:
        User object with required role

    Raises:
        HTTPException 401: If user not found in database
        HTTPException 403: If user does not have required role

    Usage:
        ```python
        from src.models.user import UserRole

        @router.post("/manager-only")
        async def manager_endpoint(
            user: User = Depends(lambda: require_role(UserRole.MANAGER))
        ):
            return {"message": f"Hello, Manager {user.email}"}
        ```
    """
    user_id = current_user.get("sub")

    if not user_id:
        logger.warning(f"require_role: No user_id in JWT payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token"
        )

    # Query database for user
    query = select(User).where(User.user_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"require_role: User {user_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Define role hierarchy
    role_hierarchy = {
        UserRole.VIEWER: 0,
        UserRole.ANALYST: 1,
        UserRole.MANAGER: 2,
        UserRole.ADMIN: 3,
    }

    user_level = role_hierarchy.get(user.role, -1)
    required_level = role_hierarchy.get(required_role, -1)

    if user_level < required_level:
        logger.warning(
            f"require_role: User {user_id} has role {user.role}, "
            f"required {required_role}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Role {required_role.value} required."
        )

    # Check user status
    if user.status != "active":
        logger.warning(
            f"require_role: User {user_id} has status {user.status}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )

    return user
