#!/usr/bin/env python3
"""
Secret Rotation Script

This script manages secret rotation for the Data Foundry application.
It can check for secrets that need rotation and perform the rotation.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.secret_manager import SecretManager

def check_rotation_status():
    """Check which secrets need rotation."""
    print("🔍 Checking secret rotation status...")

    sm = SecretManager()

    # Common secrets to check
    secrets_to_check = [
        'OPENAI_API_KEY',
        'OPENROUTER_API_KEY',
        'GITHUB_TOKEN',
        'DATABASE_URL'
    ]

    rotation_needed = []

    for secret_key in secrets_to_check:
        if sm.needs_rotation(secret_key):
            rotation_needed.append(secret_key)
            print(f"⚠️  {secret_key} needs rotation")
        else:
            print(f"✅ {secret_key} - no rotation needed")

    return rotation_needed

def rotate_secret(secret_key: str, new_value: str, ttl: int = 86400):
    """Rotate a specific secret."""
    print(f"🔄 Rotating {secret_key}...")

    sm = SecretManager()

    # Store new version
    version_id = sm.store_secret_versioned(secret_key, new_value)
    print(f"✅ Stored new version: {version_id}")

    # Store with rotation timestamp
    timestamp = sm.store_secret_with_rotation(secret_key, new_value, ttl)
    print(f"✅ Set rotation TTL: {ttl}s (timestamp: {timestamp})")

    return version_id, timestamp

def auto_rotate_all(ttl_days: int = 30):
    """Auto-rotate all secrets with default TTL."""
    print(f"🔄 Starting auto-rotation for all secrets (TTL: {ttl_days} days)...")

    sm = SecretManager()
    ttl_seconds = ttl_days * 24 * 60 * 60

    # Get all encrypted secrets from environment
    encrypted_secrets = {}
    for key, value in os.environ.items():
        if key.endswith('_ENCRYPTED'):
            original_key = key.replace('_ENCRYPTED', '')
            encrypted_secrets[original_key] = value

    rotated_count = 0

    for secret_key, encrypted_value in encrypted_secrets.items():
        try:
            # Decrypt current value
            current_value = sm.decrypt_secret(encrypted_value)

            # Rotate with new timestamp
            version_id, timestamp = sm.store_secret_with_rotation(
                secret_key, current_value, ttl_seconds
            )

            print(f"✅ Rotated {secret_key} (version: {version_id[:8]}...)")
            rotated_count += 1

        except Exception as e:
            print(f"❌ Failed to rotate {secret_key}: {e}")

    print(f"\n🎉 Successfully rotated {rotated_count}/{len(encrypted_secrets)} secrets")
    return rotated_count

def generate_rotation_report():
    """Generate a comprehensive rotation status report."""
    print("📊 Generating rotation status report...")

    sm = SecretManager()

    # Get all secrets with timestamps
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'secrets': {},
        'rotation_needed': [],
        'total_secrets': 0
    }

    # Check all encrypted secrets
    for key, value in os.environ.items():
        if key.endswith('_ENCRYPTED'):
            original_key = key.replace('_ENCRYPTED', '')
            secret_info = {
                'key': original_key,
                'has_version': original_key in sm._stored_secrets,
                'needs_rotation': sm.needs_rotation(original_key),
                'access_count': sm._access_counts.get(original_key, 0)
            }

            # Add timestamp info if available
            if original_key in sm._secret_timestamps:
                timestamp_info = sm._secret_timestamps[original_key]
                secret_info['created_at'] = timestamp_info['created']
                secret_info['ttl'] = timestamp_info['ttl']
                secret_info['age_hours'] = (time.time() - timestamp_info['created']) / 3600

            report['secrets'][original_key] = secret_info
            report['total_secrets'] += 1

            if secret_info['needs_rotation']:
                report['rotation_needed'].append(original_key)

    # Print report
    print(f"\n📋 Secret Rotation Report")
    print(f"Generated: {report['timestamp']}")
    print(f"Total secrets: {report['total_secrets']}")
    print(f"Need rotation: {len(report['rotation_needed'])}")

    if report['rotation_needed']:
        print("\n⚠️  Secrets requiring rotation:")
        for key in report['rotation_needed']:
            info = report['secrets'][key]
            age = info.get('age_hours', 0)
            print(f"  - {key} (age: {age:.1f} hours)")
    else:
        print("\n✅ No secrets require rotation")

    return report

def main():
    """Main rotation script entry point."""
    if len(sys.argv) < 2:
        print("Usage: python rotate_secrets.py <command> [options]")
        print("Commands:")
        print("  check              - Check rotation status")
        print("  rotate <key> <val> - Rotate specific secret")
        print("  auto [days]        - Auto-rotate all secrets (default: 30 days)")
        print("  report             - Generate rotation report")
        return 1

    command = sys.argv[1]

    if command == "check":
        rotation_needed = check_rotation_status()
        return 1 if rotation_needed else 0

    elif command == "rotate" and len(sys.argv) >= 4:
        secret_key = sys.argv[2]
        new_value = sys.argv[3]
        ttl = int(sys.argv[4]) if len(sys.argv) > 4 else 86400
        rotate_secret(secret_key, new_value, ttl)
        return 0

    elif command == "auto":
        ttl_days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        auto_rotate_all(ttl_days)
        return 0

    elif command == "report":
        generate_rotation_report()
        return 0

    else:
        print(f"❌ Unknown command: {command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())