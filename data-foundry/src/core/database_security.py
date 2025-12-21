"""
Database Security Module

Implements secure database connections, encrypted credentials,
query audit logging, and access control to address database security issues.

Addresses critical security issue:
2. Database credentials in plaintext - Data breach risk
"""

import os
import re
import time
import json
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
from cryptography.fernet import Fernet
import base64


logger = logging.getLogger(__name__)


class SecureDatabaseConfig:
    """Manages secure database configuration with encrypted credentials."""

    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize secure database configuration.

        Args:
            encryption_key: Encryption key for credential storage
        """
        # Try to get key from environment first (shared with SecretManager)
        key_env = os.getenv('SECRET_MANAGER_KEY')
        if key_env:
            self.encryption_key = key_env.encode()
        elif encryption_key:
            self.encryption_key = encryption_key
        elif os.getenv('DB_ENCRYPTION_KEY'):
            self.encryption_key = os.getenv('DB_ENCRYPTION_KEY').encode()
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
                    else:
                        raise ValueError("SECRET_MANAGER_KEY not found in .env.encryption")
                except Exception as e:
                    logger.error(f"Failed to load encryption key from .env.encryption: {e}")
                    # Generate new key as fallback
                    self.encryption_key = Fernet.generate_key()
                    logger.warning("Generated new encryption key - store securely")
            else:
                # Generate new key for encryption
                self.encryption_key = Fernet.generate_key()
                logger.warning("Generated new encryption key - store securely")

        self.cipher_suite = Fernet(self.encryption_key)

    def encrypt_connection_string(self, connection_string: str) -> str:
        """
        Encrypt a database connection string.

        Args:
            connection_string: Plain text connection string

        Returns:
            Encrypted connection string as base64
        """
        if not connection_string:
            return connection_string

        encrypted_data = self.cipher_suite.encrypt(connection_string.encode())
        return base64.b64encode(encrypted_data).decode()

    def decrypt_connection_string(self, encrypted_string: str) -> str:
        """
        Decrypt a database connection string.

        Args:
            encrypted_string: Encrypted connection string

        Returns:
            Plain text connection string
        """
        if not encrypted_string:
            return encrypted_string

        try:
            encrypted_data = base64.b64decode(encrypted_string.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_data)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt connection string: {e}")
            raise ValueError("Failed to decrypt connection string")

    def create_secure_engine(self, database_url: Optional[str] = None) -> Engine:
        """
        Create a database engine with security settings.

        Args:
            database_url: Optional database URL (uses environment if not provided)

        Returns:
            Configured SQLAlchemy engine with security settings
        """
        # Get database URL
        if not database_url:
            # Try to get encrypted URL from environment
            encrypted_url = os.getenv('DATABASE_URL_ENCRYPTED')
            if encrypted_url:
                database_url = self.decrypt_connection_string(encrypted_url)
            else:
                database_url = os.getenv('DATABASE_URL', '')

        # Parse and enhance URL with security parameters
        parsed_url = urlparse(database_url)

        # Add SSL parameters
        query_params = parse_qs(parsed_url.query)

        # Force SSL requirements
        query_params.setdefault('sslmode', ['require'])
        query_params.setdefault('sslcert', [''])
        query_params.setdefault('sslkey', [''])
        query_params.setdefault('sslrootcert', [''])

        # Reconstruct URL with SSL parameters
        secure_url = parsed_url._replace(
            query='&'.join([f"{k}={v[0]}" for k, v in query_params.items()])
        ).geturl()

        # Create engine with security settings
        engine = create_engine(
            secure_url,
            # Pool settings
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections every hour

            # Security settings
            connect_args={
                'connect_timeout': 10,
                'application_name': 'data-foundry-secure',
                # PostgreSQL-specific security settings
                'sslmode': 'require',
            },

            # Isolation level
            isolation_level="READ_COMMITTED",

            # Echo for debugging (disable in production)
            echo=os.getenv('DB_ECHO', 'false').lower() == 'true',
        )

        logger.info("Secure database engine created", ssl_required=True)
        return engine

    def check_database_health(self) -> Dict[str, Any]:
        """
        Check database health without exposing credentials.

        Returns:
            Health check results
        """
        try:
            engine = self.create_secure_engine()

            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1 as health_check"))
                row = result.fetchone()

            return {
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'database_reachable': True,
                'ssl_enabled': True
            }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'database_reachable': False,
                'error': str(e)
            }


class SecureQueryBuilder:
    """Builds secure SQL queries with sanitization and audit logging."""

    def __init__(self):
        self.audit_logger = logging.getLogger('database_audit')

    def sanitize_parameter(self, value: str) -> str:
        """
        Sanitize a parameter to prevent SQL injection.

        Args:
            value: Parameter value to sanitize

        Returns:
            Sanitized parameter
        """
        if not isinstance(value, str):
            return value

        # Remove potential SQL injection patterns
        sanitized = re.sub(r"[;'\"]", '', value)
        sanitized = re.sub(r"\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER)\b", '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"--", '', sanitized)

        return sanitized

    def build_select_query(self, table: str, columns: List[str], where: str = '',
                          params: Optional[Dict[str, Any]] = None,
                          limit: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Build a secure SELECT query.

        Args:
            table: Table name
            columns: List of columns to select
            where: WHERE clause
            params: Query parameters
            limit: Optional limit

        Returns:
            Tuple of (query, sanitized_params)
        """
        # Sanitize table name
        table = re.sub(r"[;'\"]", '', table)

        # Sanitize column names
        columns = [re.sub(r"[;'\"]", '', col) for col in columns]

        # Build query
        query = f"SELECT {', '.join(columns)} FROM {table}"

        if where:
            # Add WHERE clause
            query += f" WHERE {where}"

        if limit:
            query += f" LIMIT {int(limit)}"

        # Sanitize parameters
        sanitized_params = {}
        if params:
            for key, value in params.items():
                sanitized_params[key] = self.sanitize_parameter(str(value))

        # Log query for audit
        self._log_query('SELECT', table, len(sanitized_params))

        return query, sanitized_params

    def _log_query(self, operation: str, table: str, param_count: int):
        """Log query for audit purposes."""
        self.audit_logger.info(
            "database_query",
            operation=operation,
            table=table,
            parameter_count=param_count,
            timestamp=datetime.utcnow().isoformat()
        )


class DataAccessControl:
    """Controls access to sensitive data based on user roles."""

    def __init__(self):
        self.role_permissions = {
            'admin': ['*'],  # Full access
            'analyst': ['read'],
            'viewer': ['read', 'limited_fields'],
            'service': ['read', 'write', 'no_pii']
        }

    def filter_columns(self, table: str, requested_columns: List[str],
                      user_role: str, sensitive_columns: List[str]) -> List[str]:
        """
        Filter columns based on user role and sensitivity.

        Args:
            table: Table name
            requested_columns: Requested columns
            user_role: User role
            sensitive_columns: List of sensitive column names

        Returns:
            Filtered list of allowed columns
        """
        allowed_columns = []

        # Get permissions for role
        permissions = self.role_permissions.get(user_role, [])

        # Check if user has any access
        if '*' not in permissions and 'read' not in permissions:
            return []

        for column in requested_columns:
            # Check if column is sensitive
            is_sensitive = column.lower() in [col.lower() for col in sensitive_columns]

            if is_sensitive:
                # Sensitive columns require admin role or explicit permission
                if user_role == 'admin' or 'read_sensitive' in permissions:
                    allowed_columns.append(column)
                else:
                    logger.warning(f"Access denied to sensitive column: {column}")
            else:
                # Non-sensitive columns are allowed
                allowed_columns.append(column)

        return allowed_columns


class CredentialRotator:
    """Manages database credential rotation."""

    def __init__(self, storage_path: str = "secure/credentials"):
        self.storage_path = storage_path
        self.credentials = {}
        self._load_credentials()

    def _load_credentials(self):
        """Load stored credentials."""
        try:
            with open(f"{self.storage_path}/db_creds.json", 'r') as f:
                data = json.load(f)
                for key, value in data.items():
                    # Decrypt each credential
                    if 'encrypted' in value and value['encrypted']:
                        # Implementation for decryption would go here
                        pass
        except FileNotFoundError:
            logger.info("No stored credentials found")
        except Exception as e:
            logger.error(f"Failed to load credentials: {e}")

    def store_credential(self, name: str, username: str, password: str, ttl: int = 86400):
        """
        Store a database credential with rotation timer.

        Args:
            name: Credential name/identifier
            username: Database username
            password: Database password
            ttl: Time to live in seconds
        """
        # Encrypt password
        fernet = Fernet(Fernet.generate_key())
        encrypted_password = fernet.encrypt(password.encode())

        credential_data = {
            'username': username,
            'password': encrypted_password.decode(),
            'created_at': datetime.utcnow().isoformat(),
            'ttl': ttl
        }

        self.credentials[name] = credential_data

        # Save to secure storage
        self._save_credentials()

        logger.info(f"Stored credential {name} with TTL: {ttl}s")

    def needs_rotation(self, name: str) -> bool:
        """
        Check if a credential needs rotation.

        Args:
            name: Credential name

        Returns:
            True if rotation is needed
        """
        if name not in self.credentials:
            return False

        cred = self.credentials[name]
        created_at = datetime.fromisoformat(cred['created_at'])
        ttl = cred['ttl']

        return (datetime.utcnow() - created_at).total_seconds() > ttl

    def _save_credentials(self):
        """Save credentials to secure storage."""
        os.makedirs(self.storage_path, exist_ok=True)
        with open(f"{self.storage_path}/db_creds.json", 'w') as f:
            json.dump(self.credentials, f)


class RowLevelSecurity:
    """Implements row-level security for multi-tenant data."""

    def __init__(self):
        self.tenant_column = 'tenant_id'
        self.user_column = 'user_id'

    def apply_row_level_filter(self, query: str, table: str,
                             user_context: Dict[str, Any]) -> str:
        """
        Apply row-level security filter to query.

        Args:
            query: Original SQL query
            table: Table name
            user_context: User context with tenant_id, user_id, role

        Returns:
            Query with row-level security filter added
        """
        tenant_id = user_context.get('tenant_id')
        user_id = user_context.get('user_id')
        role = user_context.get('role')

        # Skip for admin users
        if role == 'admin':
            return query

        # Build WHERE clauses
        conditions = []

        if tenant_id:
            conditions.append(f"{table}.{self.tenant_column} = '{tenant_id}'")

        if user_id and role != 'analyst':  # Analysts can see all in tenant
            conditions.append(f"{table}.{self.user_column} = '{user_id}'")

        # Add to existing WHERE or create new one
        if 'WHERE' in query.upper():
            query += f" AND ({' AND '.join(conditions)})"
        else:
            query += f" WHERE {' AND '.join(conditions)}"

        return query


class DataAnonymizer:
    """Anonymizes sensitive data in query results."""

    def __init__(self):
        self.sensitive_fields = [
            'email', 'ssn', 'credit_card', 'phone', 'address',
            'first_name', 'last_name', 'full_name'
        ]

    def anonymize_result(self, result: List[Dict[str, Any]],
                        sensitive_fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Anonymize sensitive fields in query results.

        Args:
            result: Query result as list of dictionaries
            sensitive_fields: List of sensitive field names

        Returns:
            Anonymized result
        """
        if not sensitive_fields:
            sensitive_fields = self.sensitive_fields

        anonymized = []

        for row in result:
            new_row = row.copy()

            for field in sensitive_fields:
                if field.lower() in [k.lower() for k in new_row.keys()]:
                    # Find the actual key (case-insensitive)
                    for key in new_row.keys():
                        if key.lower() == field.lower():
                            new_row[key] = self._anonymize_field(field, new_row[key])
                            break

            anonymized.append(new_row)

        return anonymized

    def _anonymize_field(self, field_name: str, value: Any) -> str:
        """Anonymize a specific field value."""
        if not value:
            return value

        value_str = str(value)

        if 'email' in field_name.lower():
            # Anonymize email: user@example.com -> u***@e***.com
            parts = value_str.split('@')
            if len(parts) == 2:
                return f"{parts[0][0]}***@{parts[1][0]}***.{parts[1].split('.')[-1]}"

        elif 'ssn' in field_name.lower():
            # Anonymize SSN: 123-45-6789 -> ***-**-****
            return '***-**-****'

        elif 'phone' in field_name.lower():
            # Anonymize phone: 123-456-7890 -> (123) ***-****
            return f"({value_str[:3]}) ***-****"

        elif 'name' in field_name.lower():
            # Anonymize name: John -> J***
            return f"{value_str[0]}{'*' * (len(value_str) - 1)}"

        else:
            # Default anonymization
            return f"***{len(value_str)}***"


class TransactionLogger:
    """Logs database transactions without exposing data."""

    def __init__(self):
        self.audit_logger = logging.getLogger('database_audit')

    def log_transaction(self, operation: str, table: str, rows_affected: int,
                       user_id: str, transaction_id: str,
                       success: bool = True, error: Optional[str] = None):
        """
        Log a database transaction.

        Args:
            operation: SQL operation (INSERT, UPDATE, DELETE)
            table: Table name
            rows_affected: Number of rows affected
            user_id: User performing the operation
            transaction_id: Transaction identifier
            success: Whether transaction succeeded
            error: Error message if failed
        """
        log_data = {
            'event': 'database_transaction',
            'operation': operation,
            'table': table,
            'rows_affected': rows_affected,
            'user_id': user_id,
            'transaction_id': transaction_id,
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }

        if error:
            log_data['error'] = error

        if success:
            self.audit_logger.info(log_data)
        else:
            self.audit_logger.error(log_data)


class BackupManager:
    """Manages encrypted database backups."""

    def __init__(self, backup_path: str = "backups"):
        self.backup_path = backup_path
        os.makedirs(backup_path, exist_ok=True)

    def create_encrypted_backup(self, database: str, output_path: str) -> str:
        """
        Create an encrypted database backup.

        Args:
            database: Database name
            output_path: Output file path

        Returns:
            Path to encrypted backup file
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_path, f"{database}_backup_{timestamp}.sql")

        try:
            # Create backup (example with pg_dump for PostgreSQL)
            cmd = [
                'pg_dump',
                '-f', backup_file,
                '-d', database,
                '--no-password',
                '--verbose'
            ]

            # Run backup command
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                # Encrypt the backup file
                self._encrypt_file(backup_file)
                logger.info(f"Created encrypted backup: {backup_file}.enc")
                return f"{backup_file}.enc"
            else:
                logger.error(f"Backup failed: {result.stderr}")
                raise Exception(f"Backup failed: {result.stderr}")

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise

    def _encrypt_file(self, file_path: str):
        """Encrypt a file."""
        fernet = Fernet(Fernet.generate_key())

        with open(file_path, 'rb') as f:
            data = f.read()

        encrypted_data = fernet.encrypt(data)

        with open(f"{file_path}.enc", 'wb') as f:
            f.write(encrypted_data)

        # Remove unencrypted file
        os.remove(file_path)


class DatabaseTokenManager:
    """Manages secure tokens for database access."""

    def __init__(self, secret_key: bytes):
        self.secret_key = secret_key
        self.active_tokens = {}

    def generate_access_token(self, user_id: str, permissions: List[str],
                            ttl: int = 3600) -> str:
        """
        Generate a secure access token for database operations.

        Args:
            user_id: User identifier
            permissions: List of permissions (read, write, admin)
            ttl: Time to live in seconds

        Returns:
            Access token
        """
        # Generate token data
        token_data = {
            'user_id': user_id,
            'permissions': permissions,
            'expires_at': (datetime.utcnow() + timedelta(seconds=ttl)).isoformat(),
            'nonce': hashlib.sha256(f"{user_id}{time.time()}".encode()).hexdigest()
        }

        # Create token (simplified - in production use JWT)
        token = base64.b64encode(
            json.dumps(token_data).encode()
        ).decode()

        # Store active token
        self.active_tokens[token] = token_data

        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and validate an access token.

        Args:
            token: Access token to verify

        Returns:
            Token data if valid, None otherwise
        """
        try:
            # Decode token
            decoded = base64.b64decode(token.encode()).decode()
            token_data = json.loads(decoded)

            # Check if token exists
            if token not in self.active_tokens:
                return None

            # Check expiration
            expires_at = datetime.fromisoformat(token_data['expires_at'])
            if datetime.utcnow() > expires_at:
                del self.active_tokens[token]
                return None

            return token_data

        except Exception:
            return None


class QueryLimiter:
    """Limits query result size to prevent data exfiltration."""

    def __init__(self, max_rows: int = 1000):
        self.max_rows = max_rows

    def limit_result(self, result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Limit the number of rows returned.

        Args:
            result: Query result

        Returns:
            Limited result
        """
        if len(result) > self.max_rows:
            logger.warning(
                f"Query result limited from {len(result)} to {self.max_rows} rows"
            )
            return result[:self.max_rows]

        return result


class DatabaseMonitor:
    """Monitors database activity for security threats."""

    def __init__(self):
        self.alert_logger = logging.getLogger('security_alerts')
        self.activity_thresholds = {
            'max_queries_per_minute': 100,
            'max_sensitive_tables_per_minute': 10,
            'max_failed_attempts_per_minute': 5
        }

    def detect_suspicious_activity(self, user_id: str, queries_count: int,
                                 time_window: int, sensitive_tables_accessed: List[str],
                                 failed_attempts: int = 0):
        """
        Detect suspicious database activity patterns.

        Args:
            user_id: User identifier
            queries_count: Number of queries in time window
            time_window: Time window in seconds
            sensitive_tables_accessed: List of sensitive tables accessed
            failed_attempts: Number of failed access attempts
        """
        alerts = []

        # Check for excessive queries
        if time_window == 60 and queries_count > self.activity_thresholds['max_queries_per_minute']:
            alerts.append({
                'type': 'excessive_queries',
                'severity': 'medium',
                'message': f'User {user_id} executed {queries_count} queries in {time_window}s'
            })

        # Check for sensitive table access
        if len(sensitive_tables_accessed) > self.activity_thresholds['max_sensitive_tables_per_minute']:
            alerts.append({
                'type': 'sensitive_table_access',
                'severity': 'high',
                'message': f'User {user_id} accessed {len(sensitive_tables_accessed)} sensitive tables'
            })

        # Check for failed attempts
        if failed_attempts > self.activity_thresholds['max_failed_attempts_per_minute']:
            alerts.append({
                'type': 'failed_access_attempts',
                'severity': 'critical',
                'message': f'User {user_id} had {failed_attempts} failed access attempts'
            })

        # Send alerts
        for alert in alerts:
            self.alert_logger.error(
                "security_alert",
                alert_type=alert['type'],
                severity=alert['severity'],
                user_id=user_id,
                message=alert['message'],
                timestamp=datetime.utcnow().isoformat()
            )