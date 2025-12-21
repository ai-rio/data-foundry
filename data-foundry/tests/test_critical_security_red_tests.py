"""
TDD RED PHASE: Critical Security Failure Tests

These tests demonstrate the CRITICAL security vulnerabilities that exist.
They are designed to FAIL initially to prove the security problems are real.
"""

import os
import pytest
from pathlib import Path


def test_plaintext_secrets_exposed_critical():
    """
    CRITICAL RED TEST: API keys exposed in plaintext

    This test FAILS because API keys are exposed in .env.local
    This demonstrates CRITICAL security vulnerability
    """
    env_file = Path(".env.local")
    assert env_file.exists(), "Environment file should exist"

    with open(env_file, 'r') as f:
        content = f.read()

    # CRITICAL: These assertions WILL FAIL because secrets are exposed
    # This PROVES the critical security issue exists
    assert "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in content, "CRITICAL: OpenRouter API key exposed in plaintext!"
    assert "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in content, "CRITICAL: OpenAI API key exposed in plaintext!"
    assert "github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" not in content, "CRITICAL: GitHub token exposed in plaintext!"


def test_config_module_insecure_critical():
    """
    CRITICAL RED TEST: Config module uses insecure patterns

    This test FAILS because configuration doesn't use SecretManager
    This demonstrates CRITICAL integration failure
    """
    # Import config module - it should use SecretManager but doesn't
    from src.core.config import get_settings, settings

    # CRITICAL: These assertions WILL FAIL because security is not integrated
    assert hasattr(settings, 'secret_manager'), "CRITICAL: SecretManager not integrated in settings!"

    # If it were integrated, API keys should come from SecretManager
    # Currently they're exposed as plaintext from environment
    assert settings.OPENAI_API_KEY is None or "***" in str(settings.OPENAI_API_KEY), "CRITICAL: API key should be masked or None!"
    assert settings.OPENROUTER_API_KEY is None or "***" in str(settings.OPENROUTER_API_KEY), "CRITICAL: API key should be masked or None!"


def test_database_url_exposed_critical():
    """
    CRITICAL RED TEST: Database credentials exposed

    This test FAILS because database URL contains plaintext credentials
    This demonstrates CRITICAL database security issue
    """
    from src.core.config import settings

    db_url = settings.DATABASE_URL

    # CRITICAL: Database URL should not contain plaintext passwords
    assert "postgres:" not in db_url.lower(), "CRITICAL: Database password exposed in URL!"
    assert db_url.count(":") <= 2, "CRITICAL: Too many colons suggests exposed credentials!"


def test_no_encrypted_storage_critical():
    """
    CRITICAL RED TEST: No encrypted storage for secrets

    This test FAILS because secrets are not encrypted at rest
    This demonstrates CRITICAL storage security issue
    """
    # Check for encrypted storage
    secure_dir = Path("secure")
    if secure_dir.exists():
        encrypted_files = list(secure_dir.glob("*.enc"))
        assert len(encrypted_files) > 0, "CRITICAL: No encrypted storage files found!"

    # Check for encryption key
    encryption_key = os.getenv('SECRET_MANAGER_KEY')
    assert encryption_key is not None, "CRITICAL: No encryption key configured!"

    # Check for encrypted environment variables
    encrypted_vars = [k for k in os.environ.keys() if k.endswith('_ENCRYPTED')]
    assert len(encrypted_vars) > 0, "CRITICAL: No encrypted environment variables found!"


def test_security_modules_not_imported_critical():
    """
    CRITICAL RED TEST: Security modules exist but are not imported

    This test FAILS because security modules are created but not used
    This demonstrates CRITICAL integration failure
    """
    # Security modules exist but are not imported in main application
    security_modules = [
        'src.core.secret_manager',
        'src.core.database_security'
    ]

    # These modules should be imported in main application but aren't
    try:
        # Try to check if modules are actually used in config
        from src.core.config import settings
        import src.core.config

        # CRITICAL: SecretManager should be imported and used in config
        config_source = src.core.config.__file__
        with open(config_source, 'r') as f:
            config_content = f.read()

        assert "secret_manager" in config_content, "CRITICAL: SecretManager not imported in config!"
        assert "SecretManager" in config_content, "CRITICAL: SecretManager class not used!"

    except Exception as e:
        # If we can't even import, that's also a critical issue
        pytest.fail(f"CRITICAL: Failed to import configuration: {e}")


if __name__ == "__main__":
    print("🔴 CRITICAL SECURITY RED PHASE TESTS")
    print("These tests MUST FAIL to prove security vulnerabilities exist!")
    print("Running tests...")

    pytest.main([__file__, "-v", "--tb=short"])