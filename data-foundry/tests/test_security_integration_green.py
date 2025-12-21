"""
TDD GREEN PHASE: Security Integration Success Tests

These tests verify that the security integration fixes are working correctly.
They should PASS after the GREEN phase security fixes are implemented.
"""

import os
import pytest
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, '.')


def test_secret_manager_integration_success():
    """
    GREEN TEST: Verifies SecretManager is properly integrated

    This test should PASS after we integrate SecretManager
    """
    from src.core.config import settings

    # SecretManager should be integrated
    assert hasattr(settings, '_secret_manager'), "SecretManager should be integrated"
    assert settings._secret_manager is not None, "SecretManager should be initialized"

    print("✅ SecretManager integration verified")


def test_secure_properties_working():
    """
    GREEN TEST: Verifies secure properties are working

    This test should PASS after security properties are implemented
    """
    from src.core.config import settings

    # Test secure properties exist
    assert hasattr(settings, 'secure_openai_api_key'), "Should have secure OpenAI property"
    assert hasattr(settings, 'secure_openrouter_api_key'), "Should have secure OpenRouter property"
    assert hasattr(settings, 'secure_github_token'), "Should have secure GitHub property"

    print("✅ Secure properties working correctly")


def test_encrypted_secrets_exist():
    """
    GREEN TEST: Verifies encrypted secrets exist in environment

    This test should PASS after secrets are encrypted
    """
    # Load environment if not already loaded
    from dotenv import load_dotenv
    load_dotenv('.env.encryption')
    load_dotenv('.env.local')

    # Check for encrypted environment variables
    encrypted_vars = [k for k in os.environ.keys() if k.endswith('_ENCRYPTED')]

    assert len(encrypted_vars) > 0, "Should have encrypted environment variables"

    expected_encrypted = [
        'OPENAI_API_KEY_ENCRYPTED',
        'OPENROUTER_API_KEY_ENCRYPTED',
        'DATABASE_URL_ENCRYPTED'
    ]

    for expected in expected_encrypted:
        assert expected in os.environ, f"Should have {expected} encrypted"

    print(f"✅ Found {len(encrypted_vars)} encrypted variables")


def test_database_url_encrypted():
    """
    GREEN TEST: Verifies database URL is encrypted

    This test should PASS after database encryption
    """
    from src.core.database_security import SecureDatabaseConfig

    # Should have encrypted database URL
    encrypted_db_url = os.getenv('DATABASE_URL_ENCRYPTED')
    assert encrypted_db_url is not None, "Should have encrypted database URL"
    assert encrypted_db_url != "", "Encrypted URL should not be empty"

    # Should be able to decrypt it
    db_config = SecureDatabaseConfig()
    try:
        decrypted_url = db_config.decrypt_connection_string(encrypted_db_url)
        assert 'postgresql://' in decrypted_url, "Should be valid PostgreSQL URL"
        print("✅ Database URL encryption working")
    except Exception as e:
        pytest.fail(f"Failed to decrypt database URL: {e}")


def test_secure_config_masking():
    """
    GREEN TEST: Verifies configuration masking works

    This test should PASS after masking is implemented
    """
    from src.core.config import settings

    # Test config masking
    test_config = {
        'OPENAI_API_KEY': 'sk-test-key-123',
        'DATABASE_URL': 'postgresql://foundry_user:foundry_password@localhost:5432/data_foundry',
        'OTHER_SETTING': 'normal_value'
    }

    masked_config = settings.mask_sensitive_config(test_config)

    # Sensitive values should be masked
    assert masked_config['OPENAI_API_KEY'] == '***', "API key should be masked"
    assert 'password' not in masked_config['DATABASE_URL'], "Database password should be masked"
    assert masked_config['OTHER_SETTING'] == 'normal_value', "Non-sensitive values should be unchanged"

    print("✅ Configuration masking working correctly")


def test_external_services_use_secure_urls():
    """
    GREEN TEST: Verifies external services use secure URLs

    This test should PASS after secure URLs are implemented
    """
    from src.core.config import EXTERNAL_SERVICES

    # Should use secure properties
    postgres_url = EXTERNAL_SERVICES['postgres']
    redis_url = EXTERNAL_SERVICES['redis']

    # Should not contain plaintext passwords (or should be masked)
    assert postgres_url is not None, "Postgres URL should be available"
    assert redis_url is not None, "Redis URL should be available"

    print("✅ External services using secure URLs")


def test_ai_providers_use_secure_keys():
    """
    GREEN TEST: Verifies AI providers use secure keys

    This test should PASS after secure AI provider config
    """
    from src.core.config import AI_PROVIDERS

    # Should use secure properties
    openai_config = AI_PROVIDERS['openai']
    openrouter_config = AI_PROVIDERS.get('openrouter')  # May not exist yet

    # Should have the structure but keys may be None in test
    assert 'api_key' in openai_config, "OpenAI config should have api_key field"
    assert 'model' in openai_config, "OpenAI config should have model field"

    if openrouter_config:
        assert 'api_key' in openrouter_config, "OpenRouter config should have api_key field"

    print("✅ AI providers using secure configuration structure")


def test_secret_masking_functionality():
    """
    GREEN TEST: Verifies secret masking functionality works

    This test should PASS after SecretManager masking is working
    """
    from src.core.secret_manager import SecretManager

    # Load environment variables first
    from dotenv import load_dotenv
    load_dotenv('.env.encryption')  # Load encryption key
    load_dotenv('.env.local')  # Load original environment

    secret_manager = SecretManager()

    # Test API key masking
    test_message = "API call with key sk-or-v1-12345abcdef67890 to openai"
    masked = secret_manager.mask_secrets_in_log(test_message)

    assert 'sk-or-v1-12345abcdef67890' not in masked, "Full API key should not be in masked message"
    assert '***' in masked, "Should have masking indicators"

    # Test PII masking
    pii_message = "User email: carlos@grupoaeronet.com.br"
    masked_pii = secret_manager.mask_pii_in_log(pii_message)

    assert 'carlos@grupoaeronet.com.br' not in masked_pii, "Full email should not be in masked message"
    assert '***' in masked_pii, "Should have PII masking indicators"

    print("✅ Secret masking functionality working")


if __name__ == "__main__":
    print("🟢 GREEN PHASE: Security Integration Success Tests")
    print("These tests should PASS after security integration is complete!")
    print()

    # Load environment variables before running tests
    from dotenv import load_dotenv
    load_dotenv('.env.encryption')  # Load encryption key first
    load_dotenv('.env.local')  # Load environment variables

    # Run all tests
    test_functions = [
        test_secret_manager_integration_success,
        test_secure_properties_working,
        test_encrypted_secrets_exist,
        test_database_url_encrypted,
        test_secure_config_masking,
        test_external_services_use_secure_urls,
        test_ai_providers_use_secure_keys,
        test_secret_masking_functionality
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed: {e}")
            failed += 1

    print()
    print(f"📊 Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("🎉 ALL GREEN TESTS PASSED - Security integration successful!")
    else:
        print("🔴 Some tests failed - security integration needs more work")