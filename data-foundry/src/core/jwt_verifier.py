"""
Clerk JWT Verification Module for FastAPI.

Implements JWT signature verification using Clerk's JWKS (JSON Web Key Set).
No Clerk SDK needed - pure JWT verification using JWKS.

Environment Variables Required:
    CLERK_JWKS_URL: URL to fetch Clerk's JWKS
    CLERK_ISSUER: Expected JWT issuer (iss claim)
    CLERK_AUDIENCE: Expected JWT audience (aud claim)
    JWT_CACHE_TTL_SECONDS: Cache TTL for JWKS (default: 3600)

Usage:
    from src.core.jwt_verifier import verify_jwt

    # In FastAPI route
    def protected_route(token: str = Depends(get_jwt_from_header)):
        payload = verify_jwt(token)
        user_id = payload["sub"]
        tenant_id = payload.get("tenant_id")
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException, Request, status
from jose import jwk, jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

logger = logging.getLogger(__name__)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class JWTVerificationError(Exception):
    """Base exception for JWT verification failures."""
    pass


class JWKSFetchError(JWTVerificationError):
    """Raised when JWKS fetch fails."""
    pass


class InvalidTokenError(JWTVerificationError):
    """Raised when token validation fails."""
    pass


# ============================================================================
# JWKS CACHE
# ============================================================================

class JWKSCache:
    """
    Cache for Clerk's JWKS (JSON Web Key Set).

    Fetches and caches JWKS to avoid repeated HTTP requests.
    Implements TTL-based cache expiration and automatic refresh on unknown kid.
    """

    def __init__(
        self,
        url: str,
        cache_ttl_seconds: int = 3600,
        http_timeout: float = 5.0
    ):
        """
        Initialize JWKS cache.

        Args:
            url: JWKS endpoint URL
            cache_ttl_seconds: Cache time-to-live in seconds (default: 1 hour)
            http_timeout: HTTP request timeout in seconds
        """
        self.url = url
        self.cache_ttl_seconds = cache_ttl_seconds
        self.http_timeout = http_timeout

        self._keys: Dict[str, Dict[str, Any]] = {}
        self._last_fetch_time: Optional[float] = None
        self._lock = asyncio.Lock()

    def _is_cache_expired(self) -> bool:
        """Check if cached JWKS has expired."""
        if self._last_fetch_time is None:
            return True
        age = time.time() - self._last_fetch_time
        return age >= self.cache_ttl_seconds

    async def _fetch_jwks(self) -> Dict[str, Any]:
        """
        Fetch JWKS from Clerk endpoint.

        Returns:
            JWKS dictionary

        Raises:
            JWKSFetchError: If fetch fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.get(self.url)
                response.raise_for_status()
                data = response.json()

                logger.debug(f"Successfully fetched JWKS from {self.url}")
                return data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching JWKS: {e.response.status_code}")
            raise JWKSFetchError(f"Failed to fetch JWKS: HTTP {e.response.status_code}")

        except httpx.RequestError as e:
            logger.error(f"Network error fetching JWKS: {e}")
            raise JWKSFetchError(f"Failed to fetch JWKS: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error fetching JWKS: {e}")
            raise JWKSFetchError(f"Failed to fetch JWKS: {str(e)}")

    def _parse_jwks(self, jwks_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Parse JWKS and build kid -> key mapping.

        Args:
            jwks_data: Raw JWKS data

        Returns:
            Dictionary mapping kid to key data
        """
        keys = {}
        for key_data in jwks_data.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                # Build RSA key from JWK
                rsa_key = jwk.construct(key_data, algorithm="RS256")
                keys[kid] = {
                    "key": rsa_key,
                    "algorithm": key_data.get("alg", "RS256"),
                }

        logger.debug(f"Parsed {len(keys)} keys from JWKS")
        return keys

    async def get_keys(self, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Get JWKS keys, using cache if available and fresh.

        Args:
            force_refresh: Force cache refresh even if not expired

        Returns:
            Dictionary mapping kid to key data
        """
        async with self._lock:
            # Return cached keys if fresh and not forcing refresh
            if not force_refresh and not self._is_cache_expired() and self._keys:
                logger.debug("Using cached JWKS")
                return self._keys

            # Fetch fresh JWKS
            logger.info("Fetching fresh JWKS")
            jwks_data = await self._fetch_jwks()
            self._keys = self._parse_jwks(jwks_data)
            self._last_fetch_time = time.time()

            return self._keys

    def get_key_sync(self, kid: str) -> Optional[Dict[str, Any]]:
        """
        Get key by kid (synchronous, for use in verification).

        Args:
            kid: Key ID

        Returns:
            Key data or None if not found
        """
        return self._keys.get(kid)


# ============================================================================
# GLOBAL CACHE INSTANCE
# =================================================================init

_global_jwks_cache: Optional[JWKSCache] = None


def get_jwks_cache() -> JWKSCache:
    """
    Get or create global JWKS cache instance.

    Returns:
        JWKSCache instance
    """
    global _global_jwks_cache

    if _global_jwks_cache is None:
        jwks_url = os.getenv("CLERK_JWKS_URL")
        if not jwks_url:
            raise JWTVerificationError("CLERK_JWKS_URL environment variable not set")

        cache_ttl = int(os.getenv("JWT_CACHE_TTL_SECONDS", "3600"))
        _global_jwks_cache = JWKSCache(url=jwks_url, cache_ttl_seconds=cache_ttl)

    return _global_jwks_cache


# ============================================================================
# JWT VERIFICATION
# ============================================================================

def get_jwt_claim(payload: Dict[str, Any], claim: str, default: Any = None) -> Any:
    """
    Extract a claim from JWT payload.

    Args:
        payload: JWT payload dictionary
        claim: Claim name to extract
        default: Default value if claim not found

    Returns:
        Claim value or default
    """
    return payload.get(claim, default)


async def verify_jwt(token: str) -> Dict[str, Any]:
    """
    Verify Clerk JWT signature and claims.

    Args:
        token: JWT token string

    Returns:
        Decoded JWT payload with claims

    Raises:
        HTTPException: If verification fails (401 status)
    """
    # Get configuration from environment
    issuer = os.getenv("CLERK_ISSUER")
    audience = os.getenv("CLERK_AUDIENCE", "authenticated")

    if not issuer:
        logger.error("CLERK_ISSUER environment variable not set")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT verification configuration error"
        )

    # Check if token is empty or invalid format
    if not token or not isinstance(token, str):
        logger.warning("Empty or invalid token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )

    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    # Basic JWT format check (3 parts separated by dots)
    parts = token.split(".")
    if len(parts) != 3:
        logger.warning("Malformed JWT: incorrect number of parts")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )

    try:
        # Decode header to get kid (key ID)
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if not kid:
            logger.warning("JWT missing kid in header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing key ID"
            )

        # Get JWKS cache and fetch keys
        cache = get_jwks_cache()

        # Try to get the key from cache
        key_data = cache.get_key_sync(kid)

        # If key not found or cache is empty, force refresh
        if key_data is None:
            logger.info(f"Key {kid} not found in cache, forcing JWKS refresh")
            await cache.get_keys(force_refresh=True)
            key_data = cache.get_key_sync(kid)

            if key_data is None:
                logger.warning(f"Key {kid} not found after refresh")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: unknown key ID"
                )

        # Verify JWT signature and decode
        public_key = key_data["key"]
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=[key_data["algorithm"]],
            audience=audience,
            issuer=issuer
        )

        logger.debug(f"Successfully verified JWT for user {payload.get('sub')}")
        return payload

    except ExpiredSignatureError:
        logger.warning("JWT verification failed: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )

    except JWTClaimsError as e:
        logger.warning(f"JWT claims validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims"
        )

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature or format"
        )

    except HTTPException:
        # Re-raise HTTPException as-is
        raise

    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed"
        )


# ============================================================================
# FASTAPI DEPENDENCIES
# ============================================================================

async def get_jwt_from_header(request: Request) -> str:
    """
    FastAPI dependency to extract JWT from Authorization header.

    Args:
        request: FastAPI Request object

    Returns:
        JWT token string

    Raises:
        HTTPException: If no valid Authorization header
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

    return auth_header[7:]  # Remove "Bearer " prefix
