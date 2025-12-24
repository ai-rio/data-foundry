"""
FastAPI Dependencies Module.

Contains common FastAPI dependency functions for authentication,
authorization, and request processing.
"""

from typing import Dict, Any

from fastapi import Depends, HTTPException, Request
from fastapi import status

from src.core.jwt_verifier import verify_jwt


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
