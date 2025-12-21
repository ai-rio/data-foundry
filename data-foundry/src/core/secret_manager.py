"""
Data Foundry Secret Manager - Security Hardening Implementation

Provides secure secret management, credential masking, encryption, and audit logging
to address critical security vulnerabilities identified in the QA audit.

Critical Security Issues Addressed:
1. API keys exposed in `.env.local` file
2. Database credentials in plaintext
3. API responses partially logged
"""

import os
import re
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

# Optional imports for extended functionality
try:
    import hvac  # HashiCorp Vault client
    HAS_VAULT = True
except ImportError:
    HAS_VAULT = False

try:
    from dotenv_vault import load_dotenv
    HAS_DOTENV_VAULT = True
except ImportError:
    try:
        from dotenv import load_dotenv
        HAS_DOTENV_VAULT = True
    except ImportError:
        HAS_DOTENV_VAULT = False


logger = logging.getLogger(__name__)


class SecretManager:
    """
    Secure secret management with encryption, masking, and audit logging.

    Features:
    - Secret encryption at rest using Fernet symmetric encryption
    - API key and credential masking in logs
    - PII detection and redaction
    - HashiCorp Vault integration for production
    - Credential rotation support
    - Rate limiting for secret access
    - Comprehensive audit logging
    """

    # Regex patterns for detecting sensitive data
    API_KEY_PATTERNS = [
        r'sk-[a-zA-Z0-9]{20,}',  # OpenAI/Skype style keys
        r'sk-or-v1-[a-zA-Z0-9-]{8,}',  # OpenRouter keys (corrected pattern)
        r'github_pat_[a-zA-Z0-9_]{20,}',  # GitHub PAT
        r'ghp_[a-zA-Z0-9]{36}',  # GitHub OAuth tokens
        r'[a-zA-Z0-9]{32}-oauth2',  # OAuth2 tokens
    ]

    PII_PATTERNS = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # Phone number
    ]

    def __init__(self, vault_url: Optional[str] = None, vault_token: Optional[str] = None):
        """
        Initialize SecretManager with optional Vault integration.

        Args:
            vault_url: HashiCorp Vault URL for production environments
            vault_token: Vault authentication token
        """
        self.vault_url = vault_url or os.getenv('VAULT_URL')
        self.vault_token = vault_token or os.getenv('VAULT_TOKEN')
        self.vault_client = None

        # Initialize encryption key
        self._init_encryption_key()

        # In-memory storage with timestamps for rotation
        self._stored_secrets = {}
        self._secret_timestamps = {}

        # Rate limiting
        self._access_counts = {}
        self._access_window = {}

        # Initialize Vault if configured
        if self.vault_url and self.vault_token:
            self._init_vault_client()

        # Log initialization (without sensitive data)
        logger.info(
            f"SecretManager initialized - vault_configured: {bool(self.vault_url)}, encryption_enabled: True"
        )

    def _init_encryption_key(self) -> None:
        """Initialize encryption key from environment or generate new one."""
        # Try to get key from environment first
        key_env = os.getenv('SECRET_MANAGER_KEY')
        if key_env:
            self.encryption_key = key_env.encode()
            logger.info("Using encryption key from environment")
        else:
            # Try to load from .env.encryption file
            env_encryption_file = Path(".env.encryption")
            if env_encryption_file.exists():
                try:
                    from dotenv import load_dotenv
                    load_dotenv(env_encryption_file)
                    key_env = os.getenv('SECRET_MANAGER_KEY')
                    if key_env:
                        self.encryption_key = key_env.encode()
                        logger.info("Loaded encryption key from .env.encryption")
                    else:
                        raise ValueError("SECRET_MANAGER_KEY not found in .env.encryption")
                except Exception as e:
                    logger.error(f"Failed to load encryption key from .env.encryption: {e}")
                    # Generate new key as fallback
                    self.encryption_key = Fernet.generate_key()
                    logger.warning("Generated new encryption key - persist for production")
            else:
                # Generate new key if not exists
                self.encryption_key = Fernet.generate_key()
                logger.warning("Generated new encryption key - persist for production")

        self.cipher_suite = Fernet(self.encryption_key)

    def _init_vault_client(self) -> None:
        """Initialize HashiCorp Vault client."""
        if not HAS_VAULT:
            logger.warning("Vault client not available - hvac module not installed")
            self.vault_client = None
            return

        try:
            self.vault_client = hvac.Client(
                url=self.vault_url,
                token=self.vault_token
            )

            # Test connection
            if self.vault_client.is_authenticated():
                logger.info("Vault client initialized successfully")
            else:
                logger.error("Vault authentication failed")
                self.vault_client = None

        except Exception as e:
            logger.error(f"Failed to initialize Vault client: {e}")
            self.vault_client = None

    def mask_secrets_in_log(self, log_message: str) -> str:
        """
        Mask API keys and secrets in log messages.

        Args:
            log_message: Original log message that may contain secrets

        Returns:
            Log message with secrets masked
        """
        masked_message = log_message

        # Mask API keys
        for pattern in self.API_KEY_PATTERNS:
            masked_message = re.sub(
                pattern,
                lambda m: f"{m.group(0)[:8]}***",
                masked_message,
                flags=re.IGNORECASE
            )

        # Mask database passwords
        db_pattern = r'postgresql://([^:]+):([^@]+)@'
        masked_message = re.sub(
            db_pattern,
            r'postgresql://\1:***@',
            masked_message
        )

        # Mask common secret patterns
        secret_patterns = [
            (r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', 'password:***'),
            (r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)', 'secret:***'),
            (r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)', 'token:***'),
        ]

        for pattern, replacement in secret_patterns:
            masked_message = re.sub(
                pattern,
                replacement,
                masked_message,
                flags=re.IGNORECASE
            )

        return masked_message

    def mask_pii_in_log(self, log_message: str) -> str:
        """
        Mask PII in log messages.

        Args:
            log_message: Log message that may contain PII

        Returns:
            Log message with PII masked
        """
        masked_message = log_message

        # Mask emails
        email_pattern = r'\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+)\.([A-Z|a-z]{2,})\b'
        masked_message = re.sub(
            email_pattern,
            lambda m: f"{'*' * len(m.group(1))}@{'*' * len(m.group(2))}.{m.group(3)}",
            masked_message
        )

        # Mask SSN
        ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
        masked_message = re.sub(ssn_pattern, '***-**-****', masked_message)

        # Mask credit cards
        cc_pattern = r'\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b'
        masked_message = re.sub(cc_pattern, r'\1-****-****-\4', masked_message)

        # Mask phone numbers
        phone_pattern = r'\b(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})\b'
        masked_message = re.sub(phone_pattern, r'(\1) ***-****', masked_message)

        return masked_message

    def encrypt_secret(self, secret: str) -> str:
        """
        Encrypt a secret for storage at rest.

        Args:
            secret: Plain text secret to encrypt

        Returns:
            Encrypted secret as base64 string
        """
        if not secret:
            return secret

        encrypted_data = self.cipher_suite.encrypt(secret.encode())
        return base64.b64encode(encrypted_data).decode()

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """
        Decrypt a secret from storage.

        Args:
            encrypted_secret: Encrypted secret as base64 string

        Returns:
            Decrypted plain text secret
        """
        if not encrypted_secret:
            return encrypted_secret

        try:
            encrypted_data = base64.b64decode(encrypted_secret.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_data)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt secret: {e}")
            raise ValueError("Failed to decrypt secret")

    def load_environment_secrets(self, env_file: str = ".env") -> Dict[str, str]:
        """
        Load environment variables securely with encryption.

        Args:
            env_file: Path to environment file

        Returns:
            Dictionary of loaded and encrypted secrets
        """
        try:
            # Load using dotenv if available
            if HAS_DOTENV_VAULT:
                load_dotenv(env_file)
            else:
                logger.warning("dotenv not available - using existing environment variables")

            secrets = {}

            # Get sensitive environment variables and encrypt them
            sensitive_keys = [
                'API_KEY', 'SECRET', 'PASSWORD', 'TOKEN',
                'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY',
                'GITHUB_TOKEN', 'DATABASE_URL', 'REDIS_PASSWORD'
            ]

            for key in os.environ:
                if any(sensitive in key.upper() for sensitive in sensitive_keys):
                    value = os.getenv(key)
                    if value and not key.endswith('_ENCRYPTED'):
                        # Store encrypted version
                        encrypted_value = self.encrypt_secret(value)
                        secrets[key] = encrypted_value

                        # Also store with _ENCRYPTED suffix
                        os.environ[f"{key}_ENCRYPTED"] = encrypted_value

            logger.info(f"Loaded and encrypted {len(secrets)} secrets from {env_file}")
            return secrets

        except Exception as e:
            logger.error(f"Failed to load environment secrets: {e}")
            return {}

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret with decryption and audit logging.

        Args:
            key: Secret key/name
            default: Default value if secret not found

        Returns:
            Decrypted secret value or default
        """
        # Rate limiting check
        if not self.check_rate_limit(key):
            logger.warning(f"Rate limit exceeded for secret access: {key}")
            return default

        # Try to get from environment first (encrypted)
        encrypted_key = f"{key}_ENCRYPTED"
        encrypted_value = os.getenv(encrypted_key)

        if encrypted_value:
            try:
                value = self.decrypt_secret(encrypted_value)
                self._log_secret_access(key, success=True)
                return value
            except Exception as e:
                logger.error(f"Failed to decrypt secret {key}: {e}")
                self._log_secret_access(key, success=False, error=str(e))
                return default

        # Try Vault if configured
        if self.vault_client:
            try:
                vault_value = self.get_vault_secret(key)
                if vault_value:
                    self._log_secret_access(key, success=True, source="vault")
                    return vault_value
            except Exception as e:
                logger.error(f"Failed to get secret {key} from Vault: {e}")
                self._log_secret_access(key, success=False, source="vault", error=str(e))

        # Fallback to plain environment (insecure, last resort)
        value = os.getenv(key)
        if value:
            logger.warning(f"Using unencrypted environment variable for {key}")
            self._log_secret_access(key, success=True, source="plaintext")
            return value

        self._log_secret_access(key, success=False, error="not_found")
        return default

    def get_vault_secret(self, key: str, mount_point: str = "secret") -> Optional[str]:
        """
        Get secret from HashiCorp Vault.

        Args:
            key: Secret key/path
            mount_point: Vault mount point for secrets

        Returns:
            Secret value from Vault
        """
        if not self.vault_client:
            return None

        try:
            secret_path = f"{mount_point}/data/{key}"
            response = self.vault_client.secrets.kv.v2.read_secret_version(path=key)

            if response and 'data' in response and 'data' in response['data']:
                return response['data']['data'].get(key)

        except Exception as e:
            logger.error(f"Vault secret retrieval failed for {key}: {e}")

        return None

    def store_secret_with_rotation(self, key: str, value: str, ttl: int = 86400) -> str:
        """
        Store a secret with rotation timestamp.

        Args:
            key: Secret key
            value: Secret value
            ttl: Time to live in seconds

        Returns:
            Timestamp for the stored secret
        """
        timestamp = str(int(time.time()))

        # Store encrypted
        encrypted_value = self.encrypt_secret(value)
        self._stored_secrets[key] = encrypted_value
        self._secret_timestamps[key] = {
            'created': int(time.time()),
            'ttl': ttl
        }

        logger.info(f"Stored secret {key} with rotation TTL: {ttl}s")
        return timestamp

    def needs_rotation(self, key: str) -> bool:
        """
        Check if a secret needs rotation.

        Args:
            key: Secret key to check

        Returns:
            True if rotation is needed
        """
        if key not in self._secret_timestamps:
            return False

        timestamp_info = self._secret_timestamps[key]
        created_time = timestamp_info['created']
        ttl = timestamp_info['ttl']

        return (time.time() - created_time) > ttl

    def check_rate_limit(self, key: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
        """
        Check if secret access is rate limited.

        Args:
            key: Secret key
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds

        Returns:
            True if access is allowed
        """
        current_time = time.time()

        # Clean old entries
        if key in self._access_window:
            self._access_window[key] = [
                t for t in self._access_window[key]
                if current_time - t < window_seconds
            ]
        else:
            self._access_window[key] = []

        # Check limit
        if len(self._access_window[key]) >= max_requests:
            return False

        # Add current access
        self._access_window[key].append(current_time)
        return True

    def store_secret_versioned(self, key: str, value: str) -> str:
        """
        Store a secret with version tracking.

        Args:
            key: Secret key
            value: Secret value

        Returns:
            Version ID of the stored secret
        """
        version_id = hashlib.sha256(f"{key}{time.time()}".encode()).hexdigest()[:16]

        version_data = {
            'key': key,
            'value': self.encrypt_secret(value),
            'version': version_id,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        # Store in memory (in production, use secure storage)
        if key not in self._stored_secrets:
            self._stored_secrets[key] = {}

        if 'versions' not in self._stored_secrets[key]:
            self._stored_secrets[key]['versions'] = {}

        self._stored_secrets[key]['versions'][version_id] = version_data
        self._stored_secrets[key]['latest'] = version_id

        return version_id

    def get_latest_secret(self, key: str) -> Optional[str]:
        """Get the latest version of a secret."""
        if key in self._stored_secrets and 'latest' in self._stored_secrets[key]:
            latest_version = self._stored_secrets[key]['latest']
            return self.get_secret_version(key, latest_version)
        return None

    def get_secret_version(self, key: str, version_id: str) -> Optional[str]:
        """Get a specific version of a secret."""
        if (key in self._stored_secrets and
            'versions' in self._stored_secrets[key] and
            version_id in self._stored_secrets[key]['versions']):

            version_data = self._stored_secrets[key]['versions'][version_id]
            return self.decrypt_secret(version_data['value'])

        return None

    def store_environment_secret(self, key: str, value: str, environment: str) -> None:
        """Store a secret for a specific environment."""
        env_key = f"{environment}_{key}"
        self.store_secret_versioned(env_key, value)

    def get_environment_secret(self, key: str, environment: str) -> Optional[str]:
        """Get a secret for a specific environment."""
        env_key = f"{environment}_{key}"
        return self.get_latest_secret(env_key)

    def use_secret_safely(self, secret: str, func, *args, **kwargs):
        """
        Use a secret securely and clear it from memory after use.

        Args:
            secret: Secret to use
            func: Function to call with the secret
            *args, **kwargs: Additional arguments for the function

        Returns:
            Result of the function call
        """
        try:
            result = func(secret, *args, **kwargs)
            return result
        finally:
            # Clear secret from memory (best effort in Python)
            if 'secret' in locals():
                del secret

    def validate_security_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration for security issues.

        Args:
            config: Configuration dictionary to validate

        Returns:
            List of security issues found
        """
        issues = []

        # Check for default/weak secret keys
        if config.get('SECRET_KEY') == 'your-secret-key-change-in-production':
            issues.append("Default secret key detected - must be changed in production")

        # Check for plaintext passwords
        if 'DATABASE_URL' in config:
            db_url = config['DATABASE_URL']
            if 'password' in db_url.lower() and ':' in db_url.split('@')[0]:
                issues.append("Plaintext password detected in DATABASE_URL")

        # Check debug mode
        if config.get('DEBUG', False) and config.get('ENVIRONMENT', '').lower() == 'production':
            issues.append("DEBUG mode enabled in production environment")

        # Check for weak algorithms
        if config.get('ALGORITHM') == 'HS256':
            issues.append("Weak algorithm HS256 detected - consider stronger algorithm")

        # Check for missing SSL
        if not config.get('SSL_ENABLED', True):
            issues.append("SSL/TLS not enabled")

        return issues

    def _log_secret_access(self, key: str, success: bool, source: str = "env", error: Optional[str] = None):
        """Log secret access attempts for auditing."""
        log_data = {
            'event': 'secret_access',
            'secret_key': key,
            'success': success,
            'source': source,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        if error:
            log_data['error'] = error

        if success:
            logger.info(f"Secret access: {key} from {source}")
        else:
            logger.warning(f"Secret access failed: {key} - {error}")


# Global instance for application use
secret_manager = SecretManager()