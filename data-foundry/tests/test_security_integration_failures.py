"""
TDD RED PHASE: Security Integration Failure Tests

These tests demonstrate the critical security vulnerabilities that exist
because security modules are created but NOT INTEGRATED into the application.

These tests MUST FAIL initially because the security issues are real.
They will pass once we fix the integration issues in GREEN phase.
"""

import os
import pytest
import logging
from unittest.mock import patch
from pathlib import Path

# Import the modules we're testing
from src.core.config import get_settings, settings
from src.core.secret_manager import SecretManager
from src.core.database_security import SecureDatabaseConfig


class TestCriticalSecurityIntegrationFailures:
    """RED PHASE: Tests that demonstrate critical security integration failures"""

    def test_plaintext_api_keys_in_environment_file(self):
        """
        RED TEST: Demonstrates API keys are exposed in plaintext

        This test FAILS because security issue exists.
        It will PASS after we fix the integration.
        """
        env_file_path = Path(".env.local")
        assert env_file_path.exists(), ".env.local file should exist"

        # Read environment file and check for exposed secrets
        with open(env_file_path, 'r') as f:
            env_content = f.read()

        # These assertions demonstrate the security vulnerabilities
        # They SHOULD FAIL initially because the vulnerabilities exist
        assert "sk-or-v1-" not in env_content, "OpenRouter API key should not be exposed"
        assert "sk-proj-" not in env_content, "OpenAI API key should not be exposed"
        assert "github_pat_" not in env_content, "GitHub token should not be exposed"
        assert "password" not in env_content.lower(), "Passwords should not be in plaintext"

    def test_config_module_uses_insecure_settings(self):
        """
        RED TEST: Demonstrates config module doesn't use SecretManager

        This test FAILS because the configuration is insecure.
        It will PASS after we integrate SecretManager.
        """
        # Get settings - should use SecretManager but doesn't
        current_settings = get_settings()

        # These assertions demonstrate that SecretManager is not being used
        # They SHOULD FAIL initially because the integration doesn't exist
        assert hasattr(current_settings, '_secret_manager'), "Settings should use SecretManager"
        assert current_settings.OPENAI_API_KEY is None, "API keys should be None if not using SecretManager"
        assert current_settings.OPENROUTER_API_KEY is None, "API keys should be None if not using SecretManager"

    @patch.dict(os.environ, {
        'OPENAI_API_KEY': 'sk-test-key-12345',
        'OPENROUTER_API_KEY': 'sk-or-v1-test-key-67890'
    })
    def test_secrets_not_encrypted_in_environment(self):
        """
        RED TEST: Demonstrates secrets are not encrypted in environment

        This test FAILS because secrets are stored in plaintext.
        It will PASS after we implement encryption.
        """
        # Check if encrypted versions exist
        openai_encrypted = os.getenv('OPENAI_API_KEY_ENCRYPTED')
        openrouter_encrypted = os.getenv('OPENROUTER_API_KEY_ENCRYPTED')

        # These should fail because encryption is not implemented
        assert openai_encrypted is not None, "OpenAI API key should be encrypted"
        assert openrouter_encrypted is not None, "OpenRouter API key should be encrypted"
        assert openai_encrypted != os.getenv('OPENAI_API_KEY'), "Encrypted key should differ from plaintext"

        # Test that SecretManager can decrypt them
        secret_manager = SecretManager()
        decrypted_openai = secret_manager.decrypt_secret(openai_encrypted)
        decrypted_openrouter = secret_manager.decrypt_secret(openrouter_encrypted)

        assert decrypted_openai == os.getenv('OPENAI_API_KEY'), "Should be able to decrypt to original"
        assert decrypted_openrouter == os.getenv('OPENROUTER_API_KEY'), "Should be able to decrypt to original"

    def test_database_connection_not_secure(self):
        """
        RED TEST: Demonstrates database connection is not secure

        This test FAILS because database connections use insecure patterns.
        It will PASS after we integrate SecureDatabaseConfig.
        """
        # Check current database URL
        db_url = settings.DATABASE_URL

        # These assertions demonstrate security vulnerabilities
        # They SHOULD FAIL initially because the connection is insecure
        assert "ssl=require" in db_url.lower(), "Database connection should require SSL"
        assert db_url.count("@") <= 1, "Should not have exposed credentials in URL"

        # Test that SecureDatabaseConfig is being used (it's not currently)
        # This will fail because the integration doesn't exist
        secure_config = SecureDatabaseConfig()
        encrypted_url = os.getenv('DATABASE_URL_ENCRYPTED')
        assert encrypted_url is not None, "Database URL should be encrypted"

        decrypted_url = secure_config.decrypt_connection_string(encrypted_url)
        assert decrypted_url == db_url, "Should be able to decrypt database URL"

    def test_logging_exposes_secrets(self):
        """
        RED TEST: Demonstrates that logging exposes secrets

        This test FAILS because PII and secrets are not redacted.
        It will PASS after we integrate secure logging.
        """
        # Create a log message with secrets
        log_message = "API call with key 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 to openai"

        # Test that SecretManager would mask this (it's not being used currently)
        secret_manager = SecretManager()
        masked_message = secret_manager.mask_secrets_in_log(log_message)

        # These assertions should fail because masking is not integrated
        assert "sk-or-v1-" not in masked_message, "API keys should be masked in logs"
        assert "***" in masked_message, "Secrets should be replaced with ***"

    def test_missing_security_module_imports(self):
        """
        RED TEST: Demonstrates security modules are not imported in main application

        This test FAILS because security modules exist but aren't used.
        It will PASS after we integrate them.
        """
        # Try to import main application modules - they should use security
        try:
            from src.main import app
            from src.core.config import settings

            # These should fail because security is not integrated
            assert hasattr(settings, 'secret_manager'), "Settings should have secret_manager attribute"
            assert 'src.core.secret_manager' in app.__dict__.get('_imports', ''), "Security manager should be imported"

        except ImportError as e:
            # If imports fail, that also demonstrates the integration issue
            pytest.fail(f"Application imports failed due to missing security integration: {e}")

    def test_pii_not_redacted_in_configuration(self):
        """
        RED TEST: Demonstrates PII is not redacted in configuration

        This test FAILS because PII redaction is not implemented.
        It will PASS after we integrate PII redaction.
        """
        # Test with PII data
        pii_email = "carlos@grupoaeronet.com.br"
        pii_phone = "555-123-4567"

        secret_manager = SecretManager()

        # These should fail because PII redaction is not integrated
        masked_email = secret_manager.mask_pii_in_log(f"User email: {pii_email}")
        masked_phone = secret_manager.mask_pii_in_log(f"User phone: {pii_phone}")

        assert pii_email not in masked_email, "Email should be masked"
        assert "@" not in masked_email or "@" in "***", "Email structure should be obscured"
        assert pii_phone not in masked_phone, "Phone should be masked"
        assert "***" in masked_phone, "Phone should be partially redacted"

    def test_missing_encrypted_storage_mechanism(self):
        """
        RED TEST: Demonstrates secrets are not stored in encrypted storage

        This test FAILS because encrypted storage is not implemented.
        It will PASS after we implement encrypted storage.
        """
        # Check for encrypted storage files or mechanisms
        secure_storage_path = Path("secure")
        encrypted_files = list(secure_storage_path.glob("*.enc")) if secure_storage_path.exists() else []

        # These should fail because encrypted storage doesn't exist
        assert len(encrypted_files) > 0, "Should have encrypted storage files"
        assert os.getenv('SECRET_MANAGER_KEY') is not None, "Should have encryption key for storage"

        # Test that secrets can be loaded from encrypted storage
        secret_manager = SecretManager()
        loaded_secrets = secret_manager.load_environment_secrets()
        assert len(loaded_secrets) > 0, "Should load secrets from encrypted storage"

    def test_rate_limiting_not_implemented_for_secrets(self):
        """
        RED TEST: Demonstrates secret access is not rate limited

        This test FAILS because rate limiting is not integrated.
        It will PASS after we implement rate limiting.
        """
        secret_manager = SecretManager()

        # These should fail because rate limiting is not integrated
        # Test rapid access attempts
        for i in range(15):  # More than typical rate limit
            secret = secret_manager.get_secret('TEST_API_KEY', 'test-key')

        # Should have been rate limited after 10 attempts
        assert secret is None, "Should be rate limited after excessive attempts"

    def test_missing_security_audit_logging(self):
        """
        RED TEST: Demonstrates security audit logging is not implemented

        This test FAILS because audit logging is not integrated.
        It will PASS after we implement audit logging.
        """
        # Check for audit logs
        audit_log_path = Path("logs/security_audit.log")

        # This should fail because audit logging doesn't exist
        assert audit_log_path.exists(), "Security audit log should exist"

        if audit_log_path.exists():
            with open(audit_log_path, 'r') as f:
                log_content = f.read()

            # Should contain security events
            assert "secret_access" in log_content, "Should log secret access events"
            assert "database_transaction" in log_content, "Should log database transactions"


class TestSecurityModuleIntegrationVerification:
    """Tests to verify security modules are properly integrated"""

    def test_secret_manager_integration(self):
        """
        RED TEST: Verifies SecretManager is properly integrated

        This test FAILS because SecretManager is not integrated.
        It will PASS after integration.
        """
        # SecretManager should be used in configuration
        from src.core.config import settings

        # This should fail because SecretManager is not integrated
        assert hasattr(settings, '_secret_manager_instance'), "Settings should use SecretManager instance"

        # Should be able to get secrets securely
        api_key = settings.OPENAI_API_KEY
        assert api_key is not None, "Should be able to get API key through secure configuration"

    def test_database_security_integration(self):
        """
        RED TEST: Verifies database security is properly integrated

        This test FAILS because database security is not integrated.
        It will PASS after integration.
        """
        # Should use SecureDatabaseConfig for connections
        # This will fail because it's not integrated
        try:
            from src.core.database import get_db_engine
            engine = get_db_engine()

            # Engine should be created with security settings
            assert hasattr(engine, 'secure'), "Database engine should be secure"
            assert engine.pool.size() >= 10, "Should have secure connection pooling"

        except ImportError:
            pytest.fail("Database module should use secure configuration")

    def test_security_middleware_integration(self):
        """
        RED TEST: Verifies security middleware is properly integrated

        This test FAILS because security middleware is not integrated.
        It will PASS after integration.
        """
        try:
            from src.main import app

            # Should have security middleware
            middleware_names = [str(middleware.cls) for middleware in app.user_middleware]

            # These should fail because security middleware is not integrated
            assert any("security" in name.lower() for name in middleware_names), "Should have security middleware"
            assert any("audit" in name.lower() for name in middleware_names), "Should have audit middleware"

        except Exception as e:
            pytest.fail(f"Security middleware integration failed: {e}")


if __name__ == "__main__":
    # Run the RED phase tests
    pytest.main([__file__, "-v", "--tb=short"])