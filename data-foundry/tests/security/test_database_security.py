"""
Security tests for database connection and query security - TDD Red Phase
Tests for encrypted connections, credential management, and audit logging
"""

import pytest
import sqlalchemy
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import urlparse


class TestDatabaseSecurity:
    """Test suite for database security implementation"""

    def test_encrypted_connection_string(self):
        """Test that database connection strings are encrypted"""
        # This should fail until we implement database security
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        # Test encryption of connection string
        plain_url = "postgresql://foundry_user:foundry_password@localhost:5432/data_foundry"
        encrypted_url = config.encrypt_connection_string(plain_url)

        # Encrypted URL should be different
        assert encrypted_url != plain_url
        assert len(encrypted_url) > len(plain_url)

    def test_ssl_enforcement(self):
        """Test that SSL is enforced for database connections"""
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        # Test SSL configuration
        with patch('sqlalchemy.create_engine') as mock_create:
            config.create_secure_engine()

            # Verify SSL parameters are set
            call_args = mock_create.call_args[0][0]
            assert 'sslmode' in call_args
            assert call_args['sslmode'] in ['require', 'verify-full', 'verify-ca']

    def test_connection_pool_security(self):
        """Test that connection pool has security settings"""
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        with patch('sqlalchemy.create_engine') as mock_create:
            config.create_secure_engine()

            # Check pool settings
            call_kwargs = mock_create.call_args[1]
            assert 'pool_size' in call_kwargs
            assert 'max_overflow' in call_kwargs
            assert call_kwargs['pool_size'] > 0

    def test_query_parameter_sanitization(self):
        """Test that query parameters are sanitized to prevent injection"""
        from src.core.database_security import SecureQueryBuilder

        builder = SecureQueryBuilder()

        # Test SQL injection attempt
        malicious_input = "'; DROP TABLE users; --"
        sanitized = builder.sanitize_parameter(malicious_input)

        # Malicious code should be escaped or removed
        assert "'; DROP TABLE" not in sanitized
        assert "--" not in sanitized

    def test_query_audit_logging(self):
        """Test that all database queries are audited"""
        from src.core.database_security import SecureQueryBuilder

        builder = SecureQueryBuilder()

        with patch('src.core.database_security.audit_logger') as mock_audit:
            # Build a query
            query = builder.build_select_query(
                table='users',
                columns=['id', 'email'],
                where='id = :user_id',
                params={'user_id': 123}
            )

            # Verify audit logging
            mock_audit.log_query.assert_called_once()
            call_args = mock_audit.log_query.call_args[1]
            assert call_args['table'] == 'users'
            assert call_args['operation'] == 'SELECT'
            assert 'SELECT' in call_args['query'].upper()

    def test_sensitive_data_access_control(self):
        """Test that access to sensitive data is controlled"""
        from src.core.database_security import DataAccessControl

        access_control = DataAccessControl()

        # Define sensitive columns
        sensitive_columns = ['ssn', 'credit_card', 'password_hash']
        user_role = 'analyst'  # Limited access role

        # Test access control
        allowed_columns = access_control.filter_columns(
            table='users',
            requested_columns=['id', 'email', 'ssn', 'credit_card'],
            user_role=user_role,
            sensitive_columns=sensitive_columns
        )

        # Sensitive columns should be filtered out
        assert 'ssn' not in allowed_columns
        assert 'credit_card' not in allowed_columns
        assert 'id' in allowed_columns
        assert 'email' in allowed_columns

    def test_database_credential_rotation(self):
        """Test automatic database credential rotation"""
        from src.core.database_security import CredentialRotator

        rotator = CredentialRotator()

        with patch('time.time') as mock_time:
            # Simulate time passing
            mock_time.side_effect = [0, 2592000]  # 30 days later

            # Store credential with timestamp
            rotator.store_credential('main_db', 'user1', 'password1', ttl=864000)  # 10 days

            # Check if rotation is needed
            needs_rotation = rotator.needs_rotation('main_db')

            assert needs_rotation

    def test_row_level_security(self):
        """Test row-level security implementation"""
        from src.core.database_security import RowLevelSecurity

        rls = RowLevelSecurity()

        # Test query modification for row-level security
        original_query = "SELECT * FROM documents"
        user_context = {
            'user_id': 123,
            'tenant_id': 'tenant_1',
            'role': 'user'
        }

        secured_query = rls.apply_row_level_filter(
            query=original_query,
            table='documents',
            user_context=user_context
        )

        # Query should include WHERE clause for user filtering
        assert 'WHERE' in secured_query.upper()
        assert 'tenant_id' in secured_query
        assert 'user_id' in secured_query

    def test_data_anonymization_for_queries(self):
        """Test that sensitive data is anonymized in query results"""
        from src.core.database_security import DataAnonymizer

        anonymizer = DataAnonymizer()

        # Mock query result with sensitive data
        query_result = [
            {'id': 1, 'name': 'John Doe', 'email': 'john@example.com', 'ssn': '123-45-6789'},
            {'id': 2, 'name': 'Jane Smith', 'email': 'jane@example.com', 'ssn': '987-65-4321'}
        ]

        anonymized = anonymizer.anonymize_result(
            result=query_result,
            sensitive_fields=['email', 'ssn']
        )

        # Check sensitive fields are anonymized
        for row in anonymized:
            assert row['email'] != query_result[0]['email']  # Should be masked
            assert row['ssn'] != query_result[0]['ssn']  # Should be masked
            assert row['name'] == query_result[0]['name']  # Non-sensitive should remain

    def test_database_connection_timeout(self):
        """Test that database connections have appropriate timeouts"""
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        with patch('sqlalchemy.create_engine') as mock_create:
            config.create_secure_engine()

            # Check timeout settings
            call_kwargs = mock_create.call_args[1]
            assert 'connect_timeout' in call_kwargs
            assert call_kwargs['connect_timeout'] > 0
            assert call_kwargs['connect_timeout'] <= 30  # Reasonable timeout

    def test_connection_isolation(self):
        """Test that database connections are properly isolated"""
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        with patch('sqlalchemy.create_engine') as mock_create:
            config.create_secure_engine()

            # Check isolation level
            call_kwargs = mock_create.call_args[1]
            if 'isolation_level' in call_kwargs:
                # Should use a secure isolation level
                assert call_kwargs['isolation_level'] in ['READ_COMMITTED', 'REPEATABLE_READ', 'SERIALIZABLE']

    def test_database_health_check_with_security(self):
        """Test database health checks without exposing sensitive info"""
        from src.core.database_security import SecureDatabaseConfig

        config = SecureDatabaseConfig()

        with patch('sqlalchemy.create_engine') as mock_create:
            mock_engine = Mock()
            mock_create.return_value = mock_engine

            # Perform health check
            health = config.check_database_health()

            # Health check should not expose credentials
            assert 'password' not in str(health).lower()
            assert 'secret' not in str(health).lower()
            assert 'credential' not in str(health).lower()

    def test_transaction_logging_without_data(self):
        """Test that transactions are logged without exposing data"""
        from src.core.database_security import TransactionLogger

        logger = TransactionLogger()

        with patch('src.core.database_security.audit_logger') as mock_audit:
            # Log a transaction
            logger.log_transaction(
                operation='UPDATE',
                table='users',
                rows_affected=5,
                user_id='user123',
                transaction_id='tx_12345'
            )

            # Verify logging
            mock_audit.log_transaction.assert_called_once()
            call_args = mock_audit.log_transaction.call_args[1]

            # Should log metadata but not actual data
            assert call_args['operation'] == 'UPDATE'
            assert call_args['table'] == 'users'
            assert call_args['rows_affected'] == 5
            assert 'data' not in call_args  # Should not log actual data

    def test_encrypted_backups(self):
        """Test that database backups are encrypted"""
        from src.core.database_security import BackupManager

        backup_manager = BackupManager()

        with patch('src.core.database_security.encrypt_file') as mock_encrypt:
            with patch('subprocess.run') as mock_subprocess:
                # Create backup
                backup_path = backup_manager.create_encrypted_backup(
                    database='test_db',
                    output_path='/tmp/backup.sql'
                )

                # Verify encryption
                mock_encrypt.assert_called_once()
                mock_subprocess.assert_called()

    def test_access_token_generation_for_db(self):
        """Test secure token generation for database access"""
        from src.core.database_security import DatabaseTokenManager

        token_manager = DatabaseTokenManager()

        # Generate token
        token = token_manager.generate_access_token(
            user_id='user123',
            permissions=['read', 'write'],
            ttl=3600
        )

        # Token should be non-trivial
        assert len(token) > 32
        assert token != 'user123'  # Should not be just user_id

        # Verify token
        verified = token_manager.verify_token(token)
        assert verified is not None
        assert verified['user_id'] == 'user123'
        assert 'read' in verified['permissions']

    def test_query_result_size_limit(self):
        """Test that query results are limited to prevent data exfiltration"""
        from src.core.database_security import QueryLimiter

        limiter = QueryLimiter(max_rows=1000)

        # Mock a large result set
        large_result = [{'id': i} for i in range(5000)]

        limited_result = limiter.limit_result(large_result)

        # Should be limited
        assert len(limited_result) <= 1000

    def test_database_monitoring(self):
        """Test database security monitoring and alerting"""
        from src.core.database_security import DatabaseMonitor

        monitor = DatabaseMonitor()

        with patch('src.core.database_security.security_alert') as mock_alert:
            # Simulate suspicious activity
            monitor.detect_suspicious_activity(
                user_id='user123',
                queries_count=1000,  # High number of queries
                time_window=60,  # In 1 minute
                sensitive_tables_accessed=['users', 'credit_cards']
            )

            # Should trigger alert
            mock_alert.assert_called_once()
            alert_data = mock_alert.call_args[1]
            assert alert_data['type'] == 'suspicious_database_activity'
            assert alert_data['user_id'] == 'user123'