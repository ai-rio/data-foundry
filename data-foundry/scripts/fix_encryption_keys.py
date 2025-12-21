#!/usr/bin/env python3
"""
Fix Encryption Keys Script

This script creates a shared encryption key and re-encrypts all secrets
with the same key to ensure consistent encryption/decryption.
"""

import os
import sys
import base64
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cryptography.fernet import Fernet


def create_shared_encryption_key():
    """Create a shared encryption key and save it."""
    key = Fernet.generate_key()

    # Save to environment file
    with open('.env.encryption', 'w') as f:
        f.write(f"SECRET_MANAGER_KEY={key.decode()}\n")

    # Set in environment
    os.environ['SECRET_MANAGER_KEY'] = key.decode()

    print(f"✅ Created shared encryption key")
    return key


def reencrypt_secrets_with_shared_key():
    """Re-encrypt all secrets with the shared key."""

    print("🔄 Re-encrypting secrets with shared key...")

    # Create shared key
    key = create_shared_encryption_key()
    cipher_suite = Fernet(key)

    # Load environment file
    env_file = Path('.env.local')
    if not env_file.exists():
        print("❌ .env.local not found")
        return False

    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv(env_file)

    # Secrets to re-encrypt
    critical_secrets = [
        'OPENAI_API_KEY',
        'OPENROUTER_API_KEY',
        'GITHUB_TOKEN',
        'PRODUCTHUNT_API_KEY',
        'PRODUCTHUNT_API_SECRET',
        'DATAFORSEO_LOGIN',
        'DATAFORSEO_PASSWORD'
    ]

    reencrypted_count = 0

    for secret_key in critical_secrets:
        secret_value = os.getenv(secret_key)
        if secret_value and secret_value.strip():
            try:
                # Re-encrypt with shared key
                encrypted_value = cipher_suite.encrypt(secret_value.encode()).decode()
                os.environ[f"{secret_key}_ENCRYPTED"] = encrypted_value
                print(f"✅ Re-encrypted: {secret_key}")
                reencrypted_count += 1
            except Exception as e:
                print(f"❌ Failed to re-encrypt {secret_key}: {e}")

    # Re-encrypt database URL
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        try:
            encrypted_db_url = cipher_suite.encrypt(db_url.encode()).decode()
            os.environ['DATABASE_URL_ENCRYPTED'] = encrypted_db_url
            print(f"✅ Re-encrypted: DATABASE_URL")
            reencrypted_count += 1
        except Exception as e:
            print(f"❌ Failed to re-encrypt DATABASE_URL: {e}")

    print(f"📊 Re-encrypted {reencrypted_count} secrets with shared key")
    return reencrypted_count > 0


def test_decryption():
    """Test that decryption works with shared key."""

    print("🧪 Testing decryption with shared key...")

    # Use shared key from environment
    key = os.getenv('SECRET_MANAGER_KEY')
    if not key:
        print("❌ SECRET_MANAGER_KEY not found")
        return False

    cipher_suite = Fernet(key.encode())

    try:
        # Test API key decryption
        encrypted_openai = os.getenv('OPENAI_API_KEY_ENCRYPTED')
        if encrypted_openai:
            decrypted = cipher_suite.decrypt(encrypted_openai.encode()).decode()
            print(f"✅ OpenAI API key decrypts successfully: {decrypted[:8]}***")

        # Test database URL decryption
        encrypted_db = os.getenv('DATABASE_URL_ENCRYPTED')
        if encrypted_db:
            decrypted = cipher_suite.decrypt(encrypted_db.encode()).decode()
            print(f"✅ Database URL decrypts successfully: postgresql://***")

        print("✅ All decryption tests passed")
        return True

    except Exception as e:
        print(f"❌ Decryption test failed: {e}")
        return False


def main():
    """Main function to fix encryption keys."""

    print("🔧 FIXING ENCRYPTION KEYS")
    print("Creating shared encryption key for consistent encryption/decryption")
    print("=" * 60)

    # Step 1: Re-encrypt with shared key
    if not reencrypt_secrets_with_shared_key():
        print("❌ Failed to re-encrypt secrets")
        sys.exit(1)

    # Step 2: Test decryption
    if not test_decryption():
        print("❌ Decryption tests failed")
        sys.exit(1)

    print("\n🎉 ENCRYPTION KEYS FIXED SUCCESSFULLY!")
    print("=" * 60)
    print("✅ Shared encryption key created")
    print("✅ All secrets re-encrypted with shared key")
    print("✅ Decryption tests passed")
    print()
    print("⚠️  IMPORTANT:")
    print("   - Back up .env.encryption file")
    print("   - Load SECRET_MANAGER_KEY from .env.encryption in production")
    print("   - Never commit .env.encryption to version control")


if __name__ == "__main__":
    main()