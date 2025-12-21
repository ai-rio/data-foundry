#!/usr/bin/env python3
"""
Secret Re-encryption Script

This script re-encrypts all secrets from the backup .env.local file
using the new encryption key and stores them in environment variables.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.secret_manager import SecretManager

def reencrypt_secrets():
    """Re-encrypt all secrets from backup file."""
    print("🔐 Starting secret re-encryption process...")

    # Load secrets from backup
    backup_file = Path(__file__).parent.parent / ".env.local.backup"
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return False

    print(f"📁 Loading secrets from {backup_file}")
    load_dotenv(backup_file)

    # Initialize SecretManager
    sm = SecretManager()
    print("✅ SecretManager initialized")

    # List of secrets to encrypt
    secrets_to_encrypt = [
        'REDDIT_PUBLIC',
        'REDDIT_SECRET',
        'DATABASE_URL',
        'OPENROUTER_API_KEY',
        'OPENAI_API_KEY',
        'GITHUB_TOKEN',
        'PRODUCTHUNT_API_KEY',
        'PRODUCTHUNT_API_SECRET',
        'DATAFORSEO_LOGIN',
        'DATAFORSEO_PASSWORD'
    ]

    encrypted_count = 0

    for secret_key in secrets_to_encrypt:
        secret_value = os.getenv(secret_key)
        if secret_value:
            try:
                # Encrypt the secret
                encrypted = sm.encrypt_secret(secret_value)

                # Store in environment with _ENCRYPTED suffix
                os.environ[f"{secret_key}_ENCRYPTED"] = encrypted

                print(f"✅ Encrypted {secret_key} ({len(secret_value)} chars)")
                encrypted_count += 1

            except Exception as e:
                print(f"❌ Failed to encrypt {secret_key}: {e}")
        else:
            print(f"⚠️  {secret_key} not found in backup")

    print(f"\n🎉 Successfully encrypted {encrypted_count}/{len(secrets_to_encrypt)} secrets")

    # Create .env.encrypted file for persistence
    encrypted_file = Path(__file__).parent.parent / ".env.encrypted"
    with open(encrypted_file, 'w') as f:
        f.write("# Data Foundry Encrypted Secrets\n")
        f.write("# Do NOT commit to version control\n")
        f.write("# Access via SecretManager.get_secret()\n\n")

        for secret_key in secrets_to_encrypt:
            encrypted_key = f"{secret_key}_ENCRYPTED"
            if encrypted_key in os.environ:
                f.write(f"{encrypted_key}={os.environ[encrypted_key]}\n")

    print(f"💾 Encrypted secrets saved to {encrypted_file}")
    return True

if __name__ == "__main__":
    success = reencrypt_secrets()
    sys.exit(0 if success else 1)