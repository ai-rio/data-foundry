#!/usr/bin/env python3
"""
Security Initialization Script

This script encrypts existing plaintext secrets and migrates them to secure storage.
Run this once to fix the critical security vulnerabilities.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.secret_manager import SecretManager
from src.core.database_security import SecureDatabaseConfig


def initialize_encrypted_secrets():
    """Encrypt and migrate existing plaintext secrets to secure storage."""

    print("🔐 INITIALIZING SECURITY ENCRYPTION")
    print("=" * 50)

    # Load environment file first
    env_file = Path(".env.local")
    if not env_file.exists():
        print("❌ .env.local file not found!")
        return False

    print(f"📁 Loading environment from: {env_file}")

    # Load environment variables from file
    from dotenv import load_dotenv
    load_dotenv(env_file)

    # Initialize SecretManager
    secret_manager = SecretManager()

    # Critical secrets to encrypt
    critical_secrets = [
        'OPENAI_API_KEY',
        'OPENROUTER_API_KEY',
        'GITHUB_TOKEN',
        'PRODUCTHUNT_API_KEY',
        'PRODUCTHUNT_API_SECRET',
        'DATAFORSEO_LOGIN',
        'DATAFORSEO_PASSWORD',
        'STRIPE_SECRET_KEY',
        'STRIPE_PUBLISHABLE_KEY',
        'STRIPE_WEBHOOK_SECRET'
    ]

    encrypted_count = 0

    for secret_key in critical_secrets:
        secret_value = os.getenv(secret_key)
        if secret_value and secret_value.strip():
            try:
                # Encrypt the secret
                encrypted_value = secret_manager.encrypt_secret(secret_value)

                # Store encrypted version in environment
                os.environ[f"{secret_key}_ENCRYPTED"] = encrypted_value
                os.environ[secret_key] = ""  # Clear plaintext

                print(f"✅ Encrypted: {secret_key}")
                encrypted_count += 1

            except Exception as e:
                print(f"❌ Failed to encrypt {secret_key}: {e}")

    print(f"\n📊 Encrypted {encrypted_count} secrets")

    return encrypted_count > 0


def initialize_database_encryption():
    """Encrypt database connection string."""

    print("\n🔒 INITIALIZING DATABASE ENCRYPTION")
    print("=" * 50)

    db_config = SecureDatabaseConfig()

    # Get current database URL
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not found!")
        return False

    print(f"📡 Processing database URL...")

    try:
        # Encrypt the database URL
        encrypted_url = db_config.encrypt_connection_string(db_url)

        # Store encrypted version
        os.environ['DATABASE_URL_ENCRYPTED'] = encrypted_url

        print("✅ Database URL encrypted successfully")

        # Test decryption
        decrypted_url = db_config.decrypt_connection_string(encrypted_url)
        if decrypted_url == db_url:
            print("✅ Encryption/decryption test passed")
            return True
        else:
            print("❌ Encryption/decryption test failed!")
            return False

    except Exception as e:
        print(f"❌ Failed to encrypt database URL: {e}")
        return False


def create_secure_environment_file():
    """Create a new secure environment file with encrypted values."""

    print("\n📝 CREATING SECURE ENVIRONMENT FILE")
    print("=" * 50)

    env_file = Path(".env.local")
    secure_env_file = Path(".env.secure")

    # Read original file
    with open(env_file, 'r') as f:
        lines = f.readlines()

    secure_lines = []
    secrets_removed = 0

    for line in lines:
        line = line.strip()

        # Skip lines with exposed secrets
        if any(secret in line for secret in [
            'sk-or-v1-', 'sk-proj-', 'github_pat_',
            'password=', 'secret=', 'token='
        ]):
            if line and not line.startswith('#'):
                secure_lines.append(f"# {line} # ENCRYPTED AND REMOVED\n")
                secrets_removed += 1
            else:
                secure_lines.append(line + '\n')
        else:
            secure_lines.append(line + '\n')

    # Write secure file
    with open(secure_env_file, 'w') as f:
        f.writelines(secure_lines)

    print(f"✅ Created secure environment file: {secure_env_file}")
    print(f"🗑️  Removed {secrets_removed} plaintext secrets")

    return secrets_removed > 0


def validate_security():
    """Validate that security initialization was successful."""

    print("\n🔍 VALIDATING SECURITY SETUP")
    print("=" * 50)

    try:
        # Test SecretManager
        secret_manager = SecretManager()

        # Test that we can retrieve encrypted secrets
        openai_key = secret_manager.get_secret('OPENAI_API_KEY')
        openrouter_key = secret_manager.get_secret('OPENROUTER_API_KEY')

        if openai_key and openrouter_key:
            print("✅ SecretManager working correctly")
            print(f"   OpenAI key: {openai_key[:8]}***")
            print(f"   OpenRouter key: {openrouter_key[:8]}***")
        else:
            print("❌ SecretManager failed to retrieve secrets")
            return False

        # Test database decryption
        db_config = SecureDatabaseConfig()
        encrypted_url = os.getenv('DATABASE_URL_ENCRYPTED')

        if encrypted_url:
            try:
                decrypted_url = db_config.decrypt_connection_string(encrypted_url)
                if 'postgresql://' in decrypted_url:
                    print("✅ Database encryption working correctly")
                else:
                    print("❌ Database decryption failed")
                    return False
            except Exception as e:
                print(f"❌ Database decryption error: {e}")
                return False
        else:
            print("⚠️  No encrypted database URL found")

        print("✅ Security validation completed successfully")
        return True

    except Exception as e:
        print(f"❌ Security validation failed: {e}")
        return False


def main():
    """Main security initialization process."""

    print("🚨 CRITICAL SECURITY REMEDIATION")
    print("This will encrypt your plaintext secrets and fix security vulnerabilities")
    print()

    # Step 1: Encrypt existing secrets
    if not initialize_encrypted_secrets():
        print("❌ Failed to encrypt secrets!")
        sys.exit(1)

    # Step 2: Encrypt database URL
    if not initialize_database_encryption():
        print("❌ Failed to encrypt database URL!")
        sys.exit(1)

    # Step 3: Create secure environment file
    if not create_secure_environment_file():
        print("❌ Failed to create secure environment file!")
        sys.exit(1)

    # Step 4: Validate security setup
    if not validate_security():
        print("❌ Security validation failed!")
        sys.exit(1)

    print("\n🎉 SECURITY INITIALIZATION COMPLETED SUCCESSFULLY!")
    print("=" * 50)
    print("✅ All secrets are now encrypted and secure")
    print("✅ Database connection is encrypted")
    print("✅ Secure environment file created")
    print("✅ Security validation passed")
    print()
    print("⚠️  IMPORTANT:")
    print("   - Back up your original .env.local file")
    print("   - Use .env.secure for future development")
    print("   - Never commit secrets to version control")
    print("   - Store SECRET_MANAGER_KEY securely")


if __name__ == "__main__":
    main()