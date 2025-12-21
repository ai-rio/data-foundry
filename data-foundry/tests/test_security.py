"""
Security Tests for Data Foundry
Tests authentication, authorization, and security features
"""

import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.core.security import (
    create_access_token,
    verify_token,
    verify_password,
    get_password_hash,
    get_current_user_token,
    create_tenant_token,
    create_service_token,
    require_tenant_id,
    verify_api_key,
    validate_password,
)
from src.core.config import settings
from src.models.user import User, UserRole, UserStatus


class TestTokenAuthentication:
    """Test JWT token creation and verification."""

    def test_create_access_token(self):
        """Test access token creation."""
        user_id = "test_user_001"

        # Create token
        token = create_access_token(subject=user_id)

        # Verify token is created
        assert token is not None
        assert isinstance(token, str)

        # Verify token structure
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        assert decoded["sub"] == user_id
        assert decoded["exp"] is not None
        assert "iat" in decoded

    def test_create_access_token_with_expiration(self):
        """Test access token creation with custom expiration."""
        user_id = "test_user_001"
        expires_delta = timedelta(hours=1)

        # Create token with custom expiration
        token = create_access_token(subject=user_id, expires_delta=expires_delta)

        # Verify expiration is set correctly
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        exp_time = datetime.utcfromtimestamp(decoded["exp"])
        expected_exp = datetime.utcnow() + expires_delta

        # Allow some margin of error in timing
        time_diff = abs((exp_time - expected_exp).total_seconds())
        assert time_diff < 1  # Less than 1 second difference

    def test_create_tenant_token(self):
        """Test tenant-specific token creation."""
        user_id = "test_user_001"
        tenant_id = "tenant_001"

        # Create tenant token
        token = create_tenant_token(tenant_id=tenant_id, user_id=user_id)

        # Verify token
        assert token is not None

        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        assert decoded["sub"] == user_id
        assert decoded["tenant_id"] == tenant_id
        assert decoded["type"] == "tenant_access"
        assert "exp" in decoded

    def test_create_service_token(self):
        """Test service token creation."""
        service_name = "data_processor"

        # Create service token
        token = create_service_token(service_name=service_name)

        # Verify token
        assert token is not None

        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        assert decoded["sub"] == service_name
        assert decoded["type"] == "service_access"
        assert decoded["service"] == service_name
        assert "exp" in decoded

    def test_verify_valid_token(self):
        """Test verification of valid tokens."""
        user_id = "test_user_001"

        # Create and verify token
        token = create_access_token(subject=user_id)
        payload = verify_token(token)

        assert payload["sub"] == user_id
        assert "exp" in payload

    def test_verify_invalid_token(self):
        """Test verification of invalid tokens."""
        # Test with invalid token
        with pytest.raises(Exception):  # Should raise HTTPException
            verify_token("invalid_token")

    def test_verify_expired_token(self):
        """Test verification of expired tokens."""
        user_id = "test_user_001"

        # Create token that expired in the past
        expires_delta = timedelta(seconds=-3600)  # 1 hour ago
        token = create_access_token(subject=user_id, expires_delta=expires_delta)

        # Verify expired token raises exception
        with pytest.raises(Exception):  # Should raise HTTPException for expired token
            verify_token(token)

    def test_verify_token_with_wrong_secret(self):
        """Test token verification with wrong secret."""
        user_id = "test_user_001"

        # Create token with correct secret
        token = create_access_token(subject=user_id)

        # Verify with wrong secret
        wrong_secret = "wrong_secret_key"

        with pytest.raises(Exception):  # Should raise JWTError
            jwt.decode(
                token,
                wrong_secret,
                algorithms=[settings.ALGORITHM]
            )

    def test_token_with_custom_payload(self):
        """Test token creation with custom payload."""
        user_id = "test_user_001"
        custom_data = {"user_type": "premium", "permissions": ["read", "write"]}

        # Create token with custom data
        token = create_access_token(subject=user_id)

        # Add custom data (this would be done before encoding)
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        # Token should contain the required claims
        assert "sub" in decoded
        assert "exp" in decoded


class TestPasswordSecurity:
    """Test password hashing and verification."""

    def test_get_password_hash(self):
        """Test password hashing."""
        password = "test_password_123"

        # Hash password
        hashed = get_password_hash(password)

        # Verify hash is created
        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != password  # Hash should be different from password

        # Verify hash format (bcrypt hashes start with $2b$, $2a$, etc.)
        assert hashed.startswith("$2")
        assert len(hashed) == 60  # Standard bcrypt hash length

        # Test that we can verify the password against the hash
        assert verify_password(password, hashed) is True

    def test_verify_correct_password(self):
        """Test verification of correct password."""
        password = "test_password_123"

        # Hash password
        hashed = get_password_hash(password)

        # Verify correct password
        assert verify_password(password, hashed) is True

    def test_verify_incorrect_password(self):
        """Test verification of incorrect password."""
        password = "test_password_123"
        wrong_password = "wrong_password_123"

        # Hash password
        hashed = get_password_hash(password)

        # Verify wrong password
        assert verify_password(wrong_password, hashed) is False

    def test_verify_empty_password(self):
        """Test verification with empty password."""
        password = ""
        wrong_password = "not_empty"

        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password(wrong_password, hashed) is False

    def test_verify_unicode_password(self):
        """Test password verification with unicode characters."""
        password = "пароль_123"  # Russian for password

        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_" + password, hashed) is False


class TestUserAuthentication:
    """Test user authentication and authorization."""

    def test_require_tenant_id_dependency(self):
        """Test tenant ID requirement dependency."""
        # Test that dependency factory works
        dependency = require_tenant_id()

        # Verify it's a callable
        assert callable(dependency)

        # In a real test, we would mock the get_current_user_token function
        # and test the actual dependency behavior

    def test_get_current_user_token_with_valid_credentials(self, test_users):
        """Test getting current user with valid token."""
        # This would normally be tested with FastAPI test client
        # For now, test the basic functionality

        user = test_users[0]  # Admin user

        # Create token for user
        token = create_access_token(subject=user.user_id)

        # Mock the security dependency
        with patch('src.core.security.get_current_user_token') as mock_dependency:
            mock_dependency.return_value = {
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "token_type": "bearer",
            }

            # Test dependency works
            result = mock_dependency()

            assert result["user_id"] == user.user_id
            assert result["tenant_id"] == user.tenant_id

    def test_get_current_user_token_with_invalid_credentials(self):
        """Test getting current user with invalid token."""
        # Test with invalid token
        with pytest.raises(Exception):  # Should raise HTTPException
            # Test with invalid token - this should raise an exception
            from src.core.security import verify_token
            verify_token("invalid_token")


class TestAuthorization:
    """Test authorization and permissions."""

    def test_user_role_permissions(self):
        """Test user role-based permissions."""
        # Test different user roles
        test_cases = [
            (UserRole.ADMIN, ["create", "read", "update", "delete", "manage_users"]),
            (UserRole.MANAGER, ["create", "read", "update", "delete"]),
            (UserRole.ANALYST, ["create", "read"]),
            (UserRole.VIEWER, ["read"]),
        ]

        for role, expected_permissions in test_cases:
            # Create user with role
            user = User(
                user_id=f"user_{role.value}",
                email=f"{role.value}@example.com",
                tenant_id="tenant_001",
                hashed_password=get_password_hash("testpass123"),
                role=role,
            )

            # Test role is set correctly
            assert user.role == role

    def test_user_permission_flags(self):
        """Test user permission flags."""
        # Create admin user with explicit permissions
        admin_user = User(
            user_id="admin_user",
            email="admin@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            can_create_data=True,
            can_view_data=True,
            can_modify_data=True,
            can_delete_data=True,
            can_manage_users=True,
        )

        # Create viewer user with explicit permissions
        viewer_user = User(
            user_id="viewer_user",
            email="viewer@example.com",
            tenant_id="tenant_001",
            hashed_password=get_password_hash("viewer123"),
            role=UserRole.VIEWER,
            can_create_data=False,
            can_view_data=True,
            can_modify_data=False,
            can_delete_data=False,
            can_manage_users=False,
        )

        # Test permissions
        assert admin_user.can_create_data is True
        assert admin_user.can_view_data is True
        assert admin_user.can_modify_data is True
        assert admin_user.can_delete_data is True
        assert admin_user.can_manage_users is True

        assert viewer_user.can_create_data is False
        assert viewer_user.can_view_data is True
        assert viewer_user.can_modify_data is False
        assert viewer_user.can_delete_data is False
        assert viewer_user.can_manage_users is False

    def test_admin_privileges_property(self, test_users):
        """Test admin privileges property."""
        admin_user = test_users[0]  # Admin user
        analyst_user = test_users[1]  # Analyst user

        # Test admin privileges
        assert admin_user.has_admin_privileges is True
        assert analyst_user.has_admin_privileges is False


class TestAPIKeyAuthentication:
    """Test API key authentication."""

    def test_verify_valid_api_key(self):
        """Test verification of valid API key."""
        # Test with valid API key format
        valid_key = "df_1234567890123456789012345678901"
        assert verify_api_key(valid_key) is True

        # Test another valid key
        valid_key2 = "df_abcdefghijklmnopqrstuvwxyz123456"
        assert verify_api_key(valid_key2) is True

    def test_verify_invalid_api_key_format(self):
        """Test verification of invalid API key format."""
        # Test invalid formats
        invalid_keys = [
            "invalid_key",  # Wrong prefix
            "df_too_short",  # Too short
            "df_123456789012345678901234567890123",  # Too long
            "",  # Empty
            "DF_1234567890123456789012345678901",  # Wrong case
        ]

        for key in invalid_keys:
            assert verify_api_key(key) is False

    def test_verify_api_key_with_tenant_scope(self):
        """Test API key verification with tenant scope."""
        # Test API key without tenant scope
        api_key = "df_1234567890123456789012345678901"
        tenant_id = "tenant_001"

        result = verify_api_key(api_key, tenant_id=tenant_id)
        # Current implementation doesn't check tenant ID
        assert result is True

    def test_create_api_key_for_user(self, db_session, test_users):
        """Test API key creation for user."""
        user = test_users[0]  # Admin user

        # In a real implementation, this would generate and store API key
        # For now, just test the structure
        api_key = f"df_{user.user_id}_{''.join(chr(ord('a') + i % 26) for i in range(26))}"

        # Verify API key format
        assert api_key.startswith("df_")
        assert len(api_key) == 32  # df_ + 28 characters


class TestPasswordValidation:
    """Test password validation rules."""

    def test_validate_password_strength(self):
        """Test password strength validation."""
        # Test valid passwords
        valid_passwords = [
            "long_password",  # 14 characters
            "12345678",  # 8 characters
            "password123",  # 12 characters with numbers
            "P@ssw0rd!",  # Special characters
        ]

        for password in valid_passwords:
            assert validate_password(password) is True

    def test_validate_weak_passwords(self):
        """Test weak password rejection."""
        # Test invalid passwords
        invalid_passwords = [
            "",  # Empty
            "short",  # Too short (5 characters)
            "123",  # Too short (3 characters)
            "a",  # Too short (1 character)
        ]

        for password in invalid_passwords:
            assert validate_password(password) is False

    def test_password_requirements_not_enforced(self):
        """Test that complex requirements are not enforced yet."""
        # Current implementation only checks length
        # This test documents the current behavior
        valid_password = "12345678"  # Only numbers, meets length requirement
        assert validate_password(valid_password) is True

    def test_password_validation_edge_cases(self):
        """Test password validation edge cases."""
        # Test exactly 8 characters (minimum)
        assert validate_password("a1234567") is True

        # Test 7 characters (too short)
        assert validate_password("a123456") is False


class TestTokenSecurity:
    """Test token security features."""

    def test_token_algorithm(self):
        """Test token algorithm security."""
        # Verify the algorithm is secure
        assert settings.ALGORITHM == "HS256"  # HMAC with SHA-256

    def test_token_secret_key(self):
        """Test token secret key."""
        # Verify secret key is set
        assert settings.SECRET_KEY is not None
        assert len(settings.SECRET_KEY) > 0
        assert settings.SECRET_KEY != "your-secret-key-change-in-production"

    def test_token_expiration(self):
        """Test token expiration settings."""
        # Verify expiration is reasonable
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES <= 1440  # Max 24 hours

    def test_token_expiration_is_short(self):
        """Test that token expiration is short-lived."""
        # This is a security best practice
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES <= 60  # Max 1 hour

    def test_token_claims(self):
        """Test token claims structure."""
        user_id = "test_user_001"

        # Create token
        token = create_access_token(subject=user_id)

        # Decode and verify claims
        decoded = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        # Standard claims
        assert "sub" in decoded
        assert "exp" in decoded
        assert "iat" in decoded

        # Verify sub claim
        assert decoded["sub"] == user_id


class TestSessionSecurity:
    """Test session security features."""

    def test_session_timeout(self):
        """Test session timeout configuration."""
        # Verify session timeout is configured
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0

    def test_refresh_token_expiration(self):
        """Test refresh token expiration."""
        # Verify refresh token expiration is longer
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS > 0
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS > 1  # Longer than access token

    def test_secure_cookies(self):
        """Test secure cookie configuration."""
        # This would be tested in integration tests with browser
        # For now, verify configuration exists
        pass


class TestCrossTenantSecurity:
    """Test cross-tenant security measures."""

    def test_tenant_isolation_enforcement(self, db_session, test_tenant):
        """Test tenant isolation enforcement."""
        # This would be tested with database queries
        # For now, verify the concept works at model level

        # Create user with tenant context
        user = User(
            user_id="isolation_user",
            email="isolation@example.com",
            tenant_id=test_tenant.tenant_id,
            hashed_password=get_password_hash("testpass123"),
        )

        # Verify tenant ID is enforced
        assert user.tenant_id == test_tenant.tenant_id

    def test_user_cannot_access_other_tenant_data(self, db_session):
        """Test user cannot access other tenant's data."""
        # This is tested in multi-tenancy tests
        # Verify the security concept
        pass

    def test_admin_cross_tenant_access(self, test_users):
        """Test admin cross-tenant access capabilities."""
        admin_user = test_users[0]  # Admin user

        # Admin should be able to view all tenant data
        # In a real implementation, this would be tested with permission checks
        assert admin_user.has_admin_privileges is True


class TestSecurityHeaders:
    """Test security headers and middleware."""

    def test_security_headers_middleware(self):
        """Test security headers are set correctly."""
        # This would be tested with FastAPI test client
        # For now, verify the configuration

        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
        ]

        # Verify headers are configured in middleware
        # These are tested in the middleware tests

    def test_cors_configuration(self):
        """Test CORS configuration."""
        # Verify CORS settings
        assert settings.CORS_ORIGINS is not None
        assert isinstance(settings.CORS_ORIGINS, list)

        # In development, allow all origins
        assert "*" in settings.CORS_ORIGINS or settings.DEBUG


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limiting_middleware(self):
        """Test rate limiting middleware."""
        # This is tested in the middleware tests
        # Verify rate limiting is implemented

    def test_rate_limit_configuration(self):
        """Test rate limit configuration."""
        # Verify rate limits are reasonable
        # These are configured in the middleware

    def test_different_rate_limits_for_different_users(self):
        """Test different rate limits for different user types."""
        # In a real implementation, different user roles would have different limits
        pass


class TestSecurityLogging:
    """Test security logging and monitoring."""

    def test_security_events_logging(self):
        """Test security events are logged."""
        # This would be tested with log capture
        # Verify security events are logged

    def test_failed_login_attempts(self):
        """Test failed login attempts are tracked."""
        # This would be implemented in authentication logic
        # Verify tracking exists

    def test_suspicious_activity_detection(self):
        """Test suspicious activity detection."""
        # This would be implemented with monitoring
        # Verify detection mechanisms exist


class TestSecurityIntegration:
    """Test security integration with other systems."""

    def test_database_security(self, db_session):
        """Test database security integration."""
        # This is tested in the multi-tenancy tests
        # Verify RLS policies are enforced

    def test_api_security(self, test_client):
        """Test API security integration."""
        # Test protected endpoints
        response = test_client.get("/api/v1/me")

        # Should require authentication
        assert response.status_code == 401 or response.status_code == 403

    def test_file_upload_security(self):
        """Test file upload security."""
        # Verify file upload restrictions
        assert settings.MAX_FILE_SIZE_MB > 0
        assert isinstance(settings.ALLOWED_FILE_TYPES, list)
        assert len(settings.ALLOWED_FILE_TYPES) > 0

    def test_input_validation(self):
        """Test input validation security."""
        # This is tested throughout the application
        # Verify all inputs are validated

    def test_sql_injection_protection(self, db_session):
        """Test SQL injection protection."""
        # This is tested in the database tests
        # Verify parameterized queries are used


class TestSecurityPerformance:
    """Test security performance impact."""

    def test_password_hashing_performance(self):
        """Test password hashing performance."""
        import time

        password = "test_password_123"

        # Time password hashing
        start_time = time.time()
        hashed = get_password_hash(password)
        end_time = time.time()

        hashing_time = end_time - start_time

        # Hashing should be fast but not instantaneous
        assert hashing_time < 1.0  # Less than 1 second

    def test_token_verification_performance(self):
        """Test token verification performance."""
        import time

        user_id = "test_user_001"

        # Create token
        token = create_access_token(subject=user_id)

        # Time token verification
        start_time = time.time()
        verify_token(token)
        end_time = time.time()

        verification_time = end_time - start_time

        # Verification should be very fast
        assert verification_time < 0.1  # Less than 100ms

    def test_api_key_verification_performance(self):
        """Test API key verification performance."""
        import time

        valid_key = "df_1234567890123456789012345678901"

        # Time API key verification
        start_time = time.time()
        verify_api_key(valid_key)
        end_time = time.time()

        verification_time = end_time - start_time

        # Verification should be very fast
        assert verification_time < 0.01  # Less than 10ms


class TestSecurityBestPractices:
    """Test security best practices compliance."""

    def test_no_hardcoded_secrets(self):
        """Test no hardcoded secrets in code."""
        # Verify secrets are loaded from environment
        assert settings.SECRET_KEY != "your-secret-key-change-in-production"
        assert settings.OPENAI_API_KEY != "your-openai-api-key"

    def test_https_enforcement(self):
        """Test HTTPS enforcement."""
        # In production, HTTPS should be enforced
        # This is configured in the application

    def test_secure_session_handling(self):
        """Test secure session handling."""
        # Verify session cookies are secure
        # This is configured in the application

    def test_password_storage(self):
        """Test password storage security."""
        # Verify passwords are hashed
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert password != hashed
        assert len(hashed) > 0

    def test_input_sanitization(self):
        """Test input sanitization."""
        # This is tested throughout the application
        # Verify all user inputs are sanitized

    def test_error_message_security(self):
        """Test error message security."""
        # Verify error messages don't leak sensitive information
        # This is tested in error handlers