"""
Security module for Data Foundry
Based on patterns from tiangolo/full-stack-fastapi-template
"""

from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer for token authentication
security = HTTPBearer()


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: The subject to encode (usually user ID or email)
        expires_delta: Optional expiration time delta

    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> dict:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token to verify

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password
        hashed_password: Hashed password

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Generate password hash.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return pwd_context.hash(password)


async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to get current user from JWT token.

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Decoded token payload with user information

    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    payload = verify_token(token)

    # Extract user ID from token
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Add tenant_id extraction if present
    tenant_id = payload.get("tenant_id")

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "exp": payload.get("exp"),
        "token": token
    }


# Multi-tenant authentication decorator
def require_tenant_id():
    """
    Decorator to ensure tenant_id is present in token.
    """
    def dependency(current_user: dict = Depends(get_current_user_token)):
        if not current_user.get("tenant_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant ID required for this operation"
            )
        return current_user
    return dependency


# API Key authentication (for service-to-service communication)
def verify_api_key(api_key: str, tenant_id: Optional[str] = None) -> bool:
    """
    Verify API key for service authentication.

    Args:
        api_key: API key to verify
        tenant_id: Optional tenant ID for scoping

    Returns:
        True if API key is valid

    TODO: Implement actual API key verification against database
    """
    # Placeholder implementation
    # In production, this would check against a database table
    return api_key.startswith("df_") and len(api_key) == 32


def create_tenant_token(tenant_id: str, user_id: str) -> str:
    """
    Create a JWT token with tenant context.

    Args:
        tenant_id: Tenant ID
        user_id: User ID

    Returns:
        Encoded JWT token with tenant context
    """
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta

    to_encode = {
        "exp": expire,
        "sub": user_id,
        "tenant_id": tenant_id,
        "type": "tenant_access"
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def create_service_token(service_name: str) -> str:
    """
    Create a JWT token for service-to-service communication.

    Args:
        service_name: Name of the service

    Returns:
        Encoded JWT token for service authentication
    """
    expires_delta = timedelta(days=1)  # Service tokens can be longer lived
    expire = datetime.utcnow() + expires_delta

    to_encode = {
        "exp": expire,
        "sub": service_name,
        "type": "service_access",
        "service": service_name
    }

    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt


# Password validation
def validate_password(password: str) -> bool:
    """
    Validate password strength.

    Args:
        password: Password to validate

    Returns:
        True if password meets requirements

    TODO: Implement proper password validation rules
    """
    # Basic validation - at least 8 characters
    return len(password) >= 8