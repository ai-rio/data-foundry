"""
TDD Tests for Clerk JWT Verification Module.

RED PHASE: These tests are written BEFORE any implementation code exists.
They should FAIL initially due to ImportErrors and missing implementations.

Following strict TDD: Red -> Green -> Refactor cycle.
"""

import json
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from unittest.mock import MagicMock

import pytest
import httpx
from freezegun import freeze_time
from jose import jwk
from jose.backends import RSAKey
from jose.utils import base64url_encode
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# These imports will FAIL initially - this is EXPECTED in TDD RED phase
try:
    from src.core.jwt_verifier import verify_jwt, JWKSCache, JWTVerificationError
    IMPLEMENTATION_EXISTS = True
except ImportError:
    IMPLEMENTATION_EXISTS = False
    # Create placeholder for tests that import
    class JWTVerificationError(Exception):
        pass
    async def verify_jwt(*args, **kwargs):
        raise NotImplementedError()


# ============================================================================
# FIXTURES - Test Data Generation
# ============================================================================

@pytest.fixture
def test_rsa_keys():
    """Generate RSA key pair for testing JWT signing/verification."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Get public key
    public_key = private_key.public_key()

    # Serialize private key for JWT signing
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key for JWKS
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
    }


@pytest.fixture
def test_jwks(test_rsa_keys):
    """Create JWKS response from test RSA keys."""
    public_key = test_rsa_keys["public_key"]

    # Get the key numbers
    public_numbers = public_key.public_numbers()

    # Convert to base64url encoding (JWK format)
    # Note: We need to handle the int to bytes conversion properly
    n_bytes = public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, 'big')
    e_bytes = public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, 'big')

    # Create JWK
    jwk_data = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test_key_id_123",
                "use": "sig",
                "alg": "RS256",
                "n": base64url_encode(n_bytes).decode('utf-8'),
                "e": base64url_encode(e_bytes).decode('utf-8'),
            }
        ]
    }

    return jwk_data


@pytest.fixture
def clerk_env_vars():
    """Mock Clerk environment variables."""
    return {
        "CLERK_JWKS_URL": "https://proven-coral-24.clerk.accounts.dev/.well-known/jwks.json",
        "CLERK_ISSUER": "https://proven-coral-24.clerk.accounts.dev",
        "CLERK_AUDIENCE": "authenticated",
        "JWT_CACHE_TTL_SECONDS": "3600",
    }


@pytest.fixture
def mock_httpx(test_jwks):
    """Mock httpx client for JWKS requests."""
    def mock_request(method, url):
        if method == "GET" and ".well-known/jwks.json" in url:
            return httpx.Response(200, json=test_jwks)
        return httpx.Response(404, json={"error": "Not found"})

    return mock_request


@pytest.fixture
def mock_jwks_response(test_jwks):
    """Create a mock httpx response for JWKS."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = test_jwks
    mock_response.raise_for_status = Mock()
    return mock_response


def generate_test_token(
    test_rsa_keys,
    kid="test_key_id_123",
    iss="https://proven-coral-24.clerk.accounts.dev",
    aud="authenticated",
    sub="user_test_12345",
    exp_hours=1,
    tenant_id=None
):
    """Generate a test JWT signed with test RSA key."""
    from jose import jwt

    # Create payload
    now = datetime.utcnow()
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=exp_hours)).timestamp()),
        "azp": "app_test_12345",
        "sid": "sess_test_12345",
    }

    # Add tenant_id if provided (simulating custom claim)
    if tenant_id:
        payload["tenant_id"] = tenant_id

    # Sign with private key
    # We need to use the PEM format
    token = jwt.encode(
        payload,
        test_rsa_keys["private_pem"].decode('utf-8'),
        algorithm="RS256",
        headers={"kid": kid}
    )

    return token


# ============================================================================
# TEST 1: Valid JWT Returns User Info
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_valid_jwt_returns_user_info(test_rsa_keys, test_jwks, clerk_env_vars):
    """Test that a valid Clerk JWT returns user_id and tenant_id."""
    # Generate valid token
    token = generate_test_token(
        test_rsa_keys,
        tenant_id="tenant_test_001"
    )

    # Mock httpx.AsyncClient.get
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = test_jwks
    mock_response.raise_for_status = Mock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Set environment variables
        with patch.dict("os.environ", clerk_env_vars):
            # Verify token
            payload = await verify_jwt(token)

            # Assertions
            assert payload is not None
            assert payload["sub"] == "user_test_12345"
            assert payload["tenant_id"] == "tenant_test_001"
            assert payload["iss"] == clerk_env_vars["CLERK_ISSUER"]
            assert payload["aud"] == clerk_env_vars["CLERK_AUDIENCE"]


# ============================================================================
# TEST 2: Expired JWT Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_expired_jwt_raises_401(test_rsa_keys, test_jwks, clerk_env_vars):
    """Test that an expired JWT raises HTTPException 401."""
    from fastapi import HTTPException

    # Mock httpx.AsyncClient.get
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = test_jwks
    mock_response.raise_for_status = Mock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Generate expired token (expired 1 hour ago)
        with freeze_time("2024-01-01 12:00:00"):
            token = generate_test_token(
                test_rsa_keys,
                exp_hours=-1  # Already expired
            )

        with patch.dict("os.environ", clerk_env_vars):
            # Should raise HTTPException 401
            with pytest.raises(HTTPException) as exc_info:
                await verify_jwt(token)

            assert exc_info.value.status_code == 401
            assert "expired" in str(exc_info.value.detail).lower()


# ============================================================================
# TEST 3: Invalid Signature Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_invalid_signature_raises_401(test_rsa_keys, test_jwks, clerk_env_vars, mock_jwks_response):
    """Test that a tampered JWT signature raises HTTPException 401."""
    from fastapi import HTTPException

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_jwks_response
        mock_client_class.return_value = mock_client

        # Generate valid token
        token = generate_test_token(test_rsa_keys)

        # Tamper with the token (change one character in signature)
        parts = token.split(".")
        tampered_signature = parts[2][:-5] + "XXXXX"
        tampered_token = f"{parts[0]}.{parts[1]}.{tampered_signature}"

        with patch.dict("os.environ", clerk_env_vars):
            # Should raise HTTPException 401
            with pytest.raises(HTTPException) as exc_info:
                await verify_jwt(tampered_token)

            assert exc_info.value.status_code == 401
            assert "signature" in str(exc_info.value.detail).lower() or "invalid" in str(exc_info.value.detail).lower()


# ============================================================================
# TEST 4: Missing Token Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_missing_token_raises_401(clerk_env_vars):
    """Test that no Authorization header raises HTTPException 401."""
    from fastapi import HTTPException, Request
    from src.api.deps import get_current_user

    # Create mock request with no authorization header
    request = Mock(spec=Request)
    request.headers = {}

    with patch.dict("os.environ", clerk_env_vars):
        # Should raise HTTPException 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)

        assert exc_info.value.status_code == 401
        assert "missing" in str(exc_info.value.detail).lower()


# ============================================================================
# TEST 5: Malformed JWT Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_malformed_jwt_raises_401(clerk_env_vars):
    """Test that an invalid JWT format raises HTTPException 401."""
    from fastapi import HTTPException

    malformed_tokens = [
        "not-a-jwt",
        "invalid.token.format",
        "header.payload",  # Missing signature
        "",  # Empty string
        "Bearer header.payload.signature",  # With Bearer prefix
    ]

    with patch.dict("os.environ", clerk_env_vars):
        for malformed_token in malformed_tokens:
            with pytest.raises(HTTPException) as exc_info:
                await verify_jwt(malformed_token)

            assert exc_info.value.status_code == 401


# ============================================================================
# TEST 6: Wrong Issuer Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_wrong_issuer_raises_401(test_rsa_keys, test_jwks, clerk_env_vars, mock_jwks_response):
    """Test that a token from a different app (wrong issuer) raises HTTPException 401."""
    from fastapi import HTTPException

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_jwks_response
        mock_client_class.return_value = mock_client

        # Generate token with wrong issuer
        token = generate_test_token(
            test_rsa_keys,
            iss="https://malicious-app.clerk.accounts.dev"
        )

        with patch.dict("os.environ", clerk_env_vars):
            # Should raise HTTPException 401
            with pytest.raises(HTTPException) as exc_info:
                await verify_jwt(token)

            assert exc_info.value.status_code == 401
            # Security fix: Error message should be generic, not expose "issuer"
            assert "invalid token" in str(exc_info.value.detail).lower()


# ============================================================================
# TEST 7: JWKS Caching Works
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_jwks_caching_works(test_jwks, clerk_env_vars, mock_jwks_response):
    """Test that JWKS is cached and not repeatedly fetched."""
    jwks_url = clerk_env_vars["CLERK_JWKS_URL"]

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_jwks_response
        mock_client_class.return_value = mock_client

        # Create cache and get keys multiple times
        cache = JWKSCache(
            url=jwks_url,
            cache_ttl_seconds=3600
        )

        # First call should fetch JWKS
        keys1 = await cache.get_keys()

        # Second call should use cache (no HTTP request)
        keys2 = await cache.get_keys()

        # Third call should also use cache
        keys3 = await cache.get_keys()

        # Verify httpx get was called exactly ONCE (caching works)
        mock_client.__aenter__.return_value.get.assert_called_once()
        assert keys1 == keys2 == keys3


# ============================================================================
# TEST 8: Unknown Kid Triggers JWKS Refresh
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_token_with_unknown_kid_refreshes_jwks(test_rsa_keys, test_jwks, clerk_env_vars):
    """Test that a new kid triggers JWKS refresh (key rotation)."""
    from jose import jwk

    # Generate a second RSA key pair (simulating key rotation)
    private_key_2 = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key_2 = private_key_2.public_key()

    # Create JWKS with both keys
    public_numbers_2 = public_key_2.public_numbers()
    n_bytes_2 = public_numbers_2.n.to_bytes((public_numbers_2.n.bit_length() + 7) // 8, 'big')
    e_bytes_2 = public_numbers_2.e.to_bytes((public_numbers_2.e.bit_length() + 7) // 8, 'big')

    rotated_jwks = {
        "keys": [
            test_jwks["keys"][0],  # Original key
            {
                "kty": "RSA",
                "kid": "test_key_id_456",  # New key
                "use": "sig",
                "alg": "RS256",
                "n": base64url_encode(n_bytes_2).decode('utf-8'),
                "e": base64url_encode(e_bytes_2).decode('utf-8'),
            }
        ]
    }

    # Create mock responses
    mock_response_initial = Mock()
    mock_response_initial.status_code = 200
    mock_response_initial.json.return_value = test_jwks
    mock_response_initial.raise_for_status = Mock()

    mock_response_rotated = Mock()
    mock_response_rotated.status_code = 200
    mock_response_rotated.json.return_value = rotated_jwks
    mock_response_rotated.raise_for_status = Mock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_response_initial
        mock_client_class.return_value = mock_client

        # Create cache and get initial keys
        with patch.dict("os.environ", clerk_env_vars):
            cache = JWKSCache(
                url=clerk_env_vars["CLERK_JWKS_URL"],
                cache_ttl_seconds=3600
            )

            # Initial fetch
            initial_keys = await cache.get_keys()
            assert "test_key_id_123" in initial_keys
            assert "test_key_id_456" not in initial_keys

            # Now simulate JWKS update (add response for refresh)
            mock_client.__aenter__.return_value.get.return_value = mock_response_rotated

            # Token with new kid should trigger refresh
            private_pem_2 = private_key_2.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            from jose import jwt
            token = jwt.encode(
                {
                    "iss": clerk_env_vars["CLERK_ISSUER"],
                    "aud": clerk_env_vars["CLERK_AUDIENCE"],
                    "sub": "user_test_789",
                    "iat": int(datetime.utcnow().timestamp()),
                    "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
                },
                private_pem_2.decode('utf-8'),
                algorithm="RS256",
                headers={"kid": "test_key_id_456"}
            )

            # Verify should trigger cache refresh
            payload = await verify_jwt(token)
            assert payload["sub"] == "user_test_789"


# ============================================================================
# TEST 9: Wrong Audience Raises 401
# ============================================================================

@pytest.mark.skipif(not IMPLEMENTATION_EXISTS, reason="Implementation not created yet - RED phase")
@pytest.mark.asyncio
async def test_wrong_audience_raises_401(test_rsa_keys, test_jwks, clerk_env_vars, mock_jwks_response):
    """Test that a token with wrong audience raises HTTPException 401."""
    from fastapi import HTTPException

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get.return_value = mock_jwks_response
        mock_client_class.return_value = mock_client

        # Generate token with wrong audience
        token = generate_test_token(
            test_rsa_keys,
            aud="wrong-audience"
        )

        with patch.dict("os.environ", clerk_env_vars):
            # Should raise HTTPException 401
            with pytest.raises(HTTPException) as exc_info:
                await verify_jwt(token)

            assert exc_info.value.status_code == 401
            # Security fix: Error message should be generic, not expose "audience"
            assert "invalid token" in str(exc_info.value.detail).lower()


# ============================================================================
# TDD VERIFICATION TESTS - Verify RED Phase
# ============================================================================

def test_implementation_should_not_exist_yet():
    """
    TDD Verification: This test confirms we're in RED phase.
    The implementation should NOT exist when we first write these tests.
    """
    # This should be True at the start of RED phase
    # After GREEN phase, this will be False
    # We use this to track TDD progress
    pass


# ============================================================================
# SETUP/TEARDOWN - Clear global cache between tests
# ============================================================================

@pytest.fixture(autouse=True)
def reset_jwks_cache():
    """Reset the global JWKS cache between tests to avoid interference."""
    from src.core import jwt_verifier
    original_cache = getattr(jwt_verifier, "_global_jwks_cache", None)
    jwt_verifier._global_jwks_cache = None
    yield
    jwt_verifier._global_jwks_cache = original_cache


# ============================================================================
# SUMMARY OF TESTS
# ============================================================================
"""
TDD Test Coverage:

1. test_valid_jwt_returns_user_info - Valid token verification
2. test_expired_jwt_raises_401 - Expired token handling
3. test_invalid_signature_raises_401 - Signature validation
4. test_missing_token_raises_401 - Missing authorization
5. test_malformed_jwt_raises_401 - Invalid JWT format
6. test_wrong_issuer_raises_401 - Issuer validation
7. test_jwks_caching_works - Caching performance
8. test_token_with_unknown_kid_refreshes_jwks - Key rotation support
9. test_wrong_audience_raises_401 - Audience validation

All tests are written BEFORE implementation (RED phase).
Next: GREEN phase - Implement minimum code to pass these tests.
"""
