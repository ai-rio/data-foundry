"""
Security tests for SecretManager - TDD Red Phase
Tests for credential masking, encryption, and secure secret management
"""

import pytest
import os
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# These tests will fail initially - we'll implement SecretManager to make them pass


class TestSecretManager:
    """Test suite for SecretManager security functionality"""

    def test_api_key_masking_in_logs(self):
        """Test that API keys are properly masked in logs"""
        # This should fail until we implement SecretManager
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Test API key masking
        log_message = "API request with key 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 failed"
        masked = secret_manager.mask_secrets_in_log(log_message)

        # API keys should be masked
        assert "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" not in masked
        assert "sk-or-v1***" in masked
        assert len(masked) < len(log_message)  # Should be shorter due to masking

    def test_database_credential_masking(self):
        """Test that database credentials are masked in logs"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Test database URL masking
        db_url = "postgresql://foundry_user:foundry_password@localhost:5432/data_foundry"
        masked = secret_manager.mask_secrets_in_log(f"Connecting to database: {db_url}")

        assert "foundry_password" not in masked
        assert "***" in masked
        assert "foundry_user:" in masked  # Username should remain

    def test_pii_detection_in_logs(self):
        """Test that PII is detected and redacted in logs"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Test email detection
        log_with_email = "User carlos@grupoaeronet.com.br logged in"
        masked = secret_manager.mask_pii_in_log(log_with_email)

        assert "carlos@grupoaeronet.com.br" not in masked
        assert "***@***.com" in masked or "email" in masked.lower()

    def test_secret_encryption_at_rest(self):
        """Test that secrets are encrypted when stored"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Test encryption
        secret_value = "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        encrypted = secret_manager.encrypt_secret(secret_value)

        # Encrypted value should be different from original
        assert encrypted != secret_value
        assert len(encrypted) > len(secret_value)  # encryption adds overhead

    def test_secret_decryption(self):
        """Test that encrypted secrets can be decrypted"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        original_secret = "test-secret-key-123"
        encrypted = secret_manager.encrypt_secret(original_secret)
        decrypted = secret_manager.decrypt_secret(encrypted)

        assert decrypted == original_secret

    def test_secure_environment_loading(self):
        """Test that environment variables are loaded securely"""
        from src.core.secret_manager import SecretManager

        # Create a temporary .env file with secrets
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("API_KEY=secret-key-123\n")
            f.write("PASSWORD=secret-password\n")
            temp_env_path = f.name

        try:
            secret_manager = SecretManager()

            # Load environment securely
            with patch('os.getenv') as mock_getenv:
                mock_getenv.return_value = "masked-value"
                secrets = secret_manager.load_environment_secrets(temp_env_path)

                # Secrets should be loaded and masked
                assert 'API_KEY' in secrets
                assert secrets['API_KEY'] != 'secret-key-123'  # Should be encrypted/masked

        finally:
            os.unlink(temp_env_path)

    def test_audit_logging_for_secret_access(self):
        """Test that secret access is properly audited"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        with patch('src.core.security.logger') as mock_logger:
            # Access a secret
            secret = secret_manager.get_secret('API_KEY')

            # Should log the access attempt
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args[0][0]
            assert 'secret_access' in call_args.lower()
            assert 'API_KEY' in call_args

    def test_vault_integration(self):
        """Test HashiCorp Vault integration for production"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        with patch('hvac.Client') as mock_vault:
            mock_client = Mock()
            mock_vault.return_value = mock_client
            mock_client.secrets.kv.v2.read_secret_version.return_value = {
                'data': {'data': {'API_KEY': 'vault-secret-key'}}
            }

            # Get secret from vault
            secret = secret_manager.get_vault_secret('API_KEY')

            assert secret == 'vault-secret-key'
            mock_client.secrets.kv.v2.read_secret_version.assert_called_once()

    def test_credential_rotation(self):
        """Test automatic credential rotation"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Mock time to simulate rotation
        with patch('time.time') as mock_time:
            mock_time.side_effect = [0, 259200]  # 3 days later

            # Store credential with timestamp
            secret_manager.store_secret_with_rotation('API_KEY', 'initial-key', ttl=86400)

            # Check if rotation is needed
            needs_rotation = secret_manager.needs_rotation('API_KEY')

            assert needs_rotation

    def test_memory_sanitization(self):
        """Test that secrets are cleared from memory after use"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # This is a harder test in Python due to GC, but we can test interface
        secret = "sensitive-secret-data"

        # Use secret
        result = secret_manager.use_secret_safely(secret, lambda x: x.upper())
        assert result == "SENSITIVE-SECRET-DATA"

        # Secret should be cleared from manager's memory
        assert not hasattr(secret_manager, '_active_secrets')

    def test_config_validation(self):
        """Test that configuration is validated for security issues"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Test insecure configuration detection
        insecure_config = {
            'SECRET_KEY': 'your-secret-key-change-in-production',  # Default value
            'DATABASE_URL': 'postgresql://foundry_user:foundry_password@localhost:5432/data_foundry',  # Plaintext password
            'DEBUG': True  # Debug in production risk
        }

        issues = secret_manager.validate_security_config(insecure_config)

        assert len(issues) > 0
        assert any('default secret key' in issue.lower() for issue in issues)
        assert any('plaintext password' in issue.lower() for issue in issues)
        assert any('debug enabled' in issue.lower() for issue in issues)

    def test_rate_limiting_secret_access(self):
        """Test that secret access is rate limited to prevent brute force"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Simulate multiple rapid accesses
        access_results = []
        for i in range(10):
            result = secret_manager.check_rate_limit('test-key')
            access_results.append(result)

        # Should start allowing access, then limit
        assert access_results[0] == True  # First access allowed
        assert False in access_results[5:]  # Later accesses should be limited

    def test_secret_versioning(self):
        """Test that secret versions are managed properly"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Store first version
        v1 = secret_manager.store_secret_versioned('API_KEY', 'version-1')

        # Store second version
        v2 = secret_manager.store_secret_versioned('API_KEY', 'version-2')

        # Get latest version
        latest = secret_manager.get_latest_secret('API_KEY')
        assert latest == 'version-2'

        # Get specific version
        v1_retrieved = secret_manager.get_secret_version('API_KEY', v1)
        assert v1_retrieved == 'version-1'

    def test_environment_specific_secrets(self):
        """Test that secrets are isolated by environment"""
        from src.core.secret_manager import SecretManager

        secret_manager = SecretManager()

        # Store secrets for different environments
        secret_manager.store_environment_secret('API_KEY', 'dev-key', 'development')
        secret_manager.store_environment_secret('API_KEY', 'prod-key', 'production')

        # Get environment-specific secrets
        dev_key = secret_manager.get_environment_secret('API_KEY', 'development')
        prod_key = secret_manager.get_environment_secret('API_KEY', 'production')

        assert dev_key == 'dev-key'
        assert prod_key == 'prod-key'
        assert dev_key != prod_key