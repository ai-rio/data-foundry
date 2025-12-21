"""
Secure Structured Logging with PII Filtering

Implements secure logging using structlog with PII detection, API key masking,
and comprehensive audit logging to prevent data leakage.

Addresses critical security issue:
3. API responses partially logged - PII exposure and compliance violations
"""

import logging
import json
import re
import time
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import StringIO
import structlog
from structlog.stdlib import LoggerFactory
from structlog.processors import JSONRenderer
from pathlib import Path


class PIIProcessor:
    """Processor for detecting and redacting PII in log entries."""

    # PII detection patterns
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    CREDIT_CARD_PATTERN = re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b')
    PHONE_PATTERN = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

    def __call__(self, logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process log event to redact PII."""
        redacted = event_dict.copy()

        # Redact PII in all string values
        for key, value in redacted.items():
            if isinstance(value, str):
                redacted[key] = self._redact_pii(value)
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = self._redact_list(value)

        return redacted

    def _redact_pii(self, text: str) -> str:
        """Redact PII from text."""
        if not isinstance(text, str):
            return text

        # Redact emails
        text = self.EMAIL_PATTERN.sub('***@***.***', text)

        # Redact SSNs
        text = self.SSN_PATTERN.sub('***-**-****', text)

        # Redact credit cards
        text = self.CREDIT_CARD_PATTERN.sub(lambda m: f"{m.group(0)[:4]}-****-****-{m.group(0)[-4:]}", text)

        # Redact phone numbers
        text = self.PHONE_PATTERN.sub(r'(\1) ***-****', text)

        # Partially redact IPs (keep first octet)
        text = self.IP_PATTERN.sub(lambda m: f"{m.group(0).split('.')[0]}.***.*.***", text)

        return text

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact PII in dictionary."""
        redacted = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted[key] = self._redact_pii(value)
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = self._redact_list(value)
            else:
                redacted[key] = value
        return redacted

    def _redact_list(self, data: List[Any]) -> List[Any]:
        """Recursively redact PII in list."""
        redacted = []
        for item in data:
            if isinstance(item, str):
                redacted.append(self._redact_pii(item))
            elif isinstance(item, dict):
                redacted.append(self._redact_dict(item))
            elif isinstance(item, list):
                redacted.append(self._redact_list(item))
            else:
                redacted.append(item)
        return redacted


class APIKeyProcessor:
    """Processor for detecting and masking API keys in log entries."""

    API_KEY_PATTERNS = [
        re.compile(r'sk-[a-zA-Z0-9]{20,}'),
        re.compile(r'sk-or-v1-[a-zA-Z0-9]{48,}'),
        re.compile(r'github_pat_[a-zA-Z0-9_]{20,}'),
        re.compile(r'ghp_[a-zA-Z0-9]{36}'),
        re.compile(r'xoxb-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24}'),  # Slack
        re.compile(r'AKIA[0-9A-Z]{16}'),  # AWS
    ]

    def __call__(self, logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process log event to mask API keys."""
        masked = event_dict.copy()

        for key, value in masked.items():
            if isinstance(value, str):
                masked[key] = self._mask_api_keys(value)
            elif isinstance(value, dict):
                masked[key] = self._mask_dict(value)
            elif isinstance(value, list):
                masked[key] = self._mask_list(value)

        return masked

    def _mask_api_keys(self, text: str) -> str:
        """Mask API keys in text."""
        if not isinstance(text, str):
            return text

        masked_text = text
        for pattern in self.API_KEY_PATTERNS:
            masked_text = pattern.sub(lambda m: f"{m.group(0)[:8]}***", masked_text)

        return masked_text

    def _mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively mask API keys in dictionary."""
        masked = {}
        for key, value in data.items():
            if isinstance(value, str):
                masked[key] = self._mask_api_keys(value)
            elif isinstance(value, dict):
                masked[key] = self._mask_dict(value)
            elif isinstance(value, list):
                masked[key] = self._mask_list(value)
            else:
                masked[key] = value
        return masked

    def _mask_list(self, data: List[Any]) -> List[Any]:
        """Recursively mask API keys in list."""
        masked = []
        for item in data:
            if isinstance(item, str):
                masked.append(self._mask_api_keys(item))
            elif isinstance(item, dict):
                masked.append(self._mask_dict(item))
            elif isinstance(item, list):
                masked.append(self._mask_list(item))
            else:
                masked.append(item)
        return masked


class SensitiveDataProcessor:
    """Processor for detecting and masking various sensitive data patterns."""

    SENSITIVE_PATTERNS = {
        'password': re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\s\}]+)', re.IGNORECASE),
        'secret': re.compile(r'secret["\']?\s*[:=]\s*["\']?([^"\'\s\}]+)', re.IGNORECASE),
        'token': re.compile(r'token["\']?\s*[:=]\s*["\']?([^"\'\s\}]+)', re.IGNORECASE),
        'key': re.compile(r'(?:api[_-]?key|private[_-]?key|access[_-]?key)["\']?\s*[:=]\s*["\']?([^"\'\s\}]+)', re.IGNORECASE),
    }

    def __call__(self, logger, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process log event to mask sensitive data."""
        masked = event_dict.copy()

        # Mask in event message
        if 'event' in masked:
            masked['event'] = self._mask_sensitive_data(masked['event'])

        # Mask in all string fields
        for key, value in masked.items():
            if isinstance(value, str) and key != 'event':
                masked[key] = self._mask_sensitive_data(value)

        return masked

    def _mask_sensitive_data(self, text: str) -> str:
        """Mask sensitive data patterns in text."""
        if not isinstance(text, str):
            return text

        masked_text = text
        for pattern_name, pattern in self.SENSITIVE_PATTERNS.items():
            masked_text = pattern.sub(f'{pattern_name}: "***"', masked_text)

        return masked_text


class SecureJSONRenderer:
    """JSON renderer with additional security checks."""

    def __init__(self, serializer=json.dumps):
        self.serializer = serializer

    def __call__(self, logger, method_name: str, event_dict: Dict[str, Any]) -> str:
        """Render log event as secure JSON."""
        # Additional security checks before rendering
        secured_event = self._secure_event(event_dict)
        return self.serializer(secured_event)

    def _secure_event(self, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Apply additional security measures to event."""
        secured = event_dict.copy()

        # Ensure no sensitive fields are exposed
        sensitive_fields = ['password', 'secret', 'token', 'api_key', 'private_key']
        for field in sensitive_fields:
            if field in secured:
                secured[field] = '***'

        # Add security metadata
        secured['_logged_at'] = datetime.utcnow().isoformat()
        secured['_security_processed'] = True

        return secured


class LogSanitizationMiddleware:
    """Middleware for sanitizing all log outputs."""

    def __init__(self):
        self.processors = [
            PIIProcessor(),
            APIKeyProcessor(),
            SensitiveDataProcessor()
        ]

    def wrap_handler(self, handler):
        """Wrap a log handler with sanitization."""
        original_emit = handler.emit

        def sanitized_emit(record):
            # Sanitize the message
            for processor in self.processors:
                record.msg = processor._redact_pii(str(record.msg))
                if record.args:
                    record.args = tuple(
                        processor._redact_pii(str(arg)) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
            original_emit(record)

        handler.emit = sanitized_emit
        return handler


class SecureLogger:
    """Secure logger wrapper with enhanced security features."""

    def __init__(self, name: str):
        self.logger = structlog.get_logger(name)
        self._security_events = []

    def info(self, event: str, **kwargs):
        """Log info message with security processing."""
        self.logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs):
        """Log warning message with security processing."""
        self.logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs):
        """Log error message with security processing."""
        self.logger.error(event, **kwargs)

    def debug(self, event: str, **kwargs):
        """Log debug message with security processing."""
        self.logger.debug(event, **kwargs)

    def log_security_event(self, event_type: str, severity: str = 'medium', **kwargs):
        """Log a security event with appropriate level."""
        security_data = {
            'event': 'security_event',
            'security_event_type': event_type,
            'severity': severity,
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }

        if severity.lower() in ['high', 'critical']:
            self.logger.error(security_data)
        else:
            self.logger.warning(security_data)

        self._security_events.append(security_data)

    def get_security_events(self) -> List[Dict[str, Any]]:
        """Get all logged security events."""
        return self._security_events.copy()


class AuditLogger:
    """Specialized logger for audit trail logging."""

    def __init__(self, log_file: Optional[str] = None):
        self.logger = structlog.get_logger('audit')
        self.log_file = log_file

        if log_file:
            # Setup file handler for audit logs
            handler = logging.FileHandler(log_file)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            logging.getLogger('audit').addHandler(handler)

    def log_access(self, resource: str, resource_id: str, user_id: str, action: str,
                  success: bool = True, ip_address: Optional[str] = None, **kwargs):
        """Log resource access for audit trail."""
        audit_entry = {
            'event': 'audit_access',
            'timestamp': datetime.utcnow().isoformat(),
            'resource': resource,
            'resource_id': resource_id,
            'user_id': user_id,
            'action': action,
            'success': success,
            'ip_address': ip_address,
            **kwargs
        }

        if success:
            self.logger.info(audit_entry)
        else:
            self.logger.error(audit_entry)

    def log_data_access(self, table: str, operation: str, rows_affected: int,
                       user_id: str, query: Optional[str] = None, **kwargs):
        """Log database access for audit trail."""
        audit_entry = {
            'event': 'audit_data_access',
            'timestamp': datetime.utcnow().isoformat(),
            'table': table,
            'operation': operation.upper(),
            'rows_affected': rows_affected,
            'user_id': user_id,
            **kwargs
        }

        # Never log the actual query with data, just metadata
        if query:
            audit_entry['query_hash'] = hashlib.sha256(query.encode()).hexdigest()[:16]

        self.logger.info(audit_entry)


class EncryptedLogHandler(logging.Handler):
    """Log handler that encrypts sensitive logs before storage."""

    def __init__(self, filename: str, encryption_key: bytes):
        super().__init__()
        self.filename = filename
        self.encryption_key = encryption_key

    def emit(self, record):
        """Emit log record with encryption."""
        try:
            from cryptography.fernet import Fernet
            cipher = Fernet(self.encryption_key)

            # Format the record
            log_entry = self.format(record)

            # Encrypt the log entry
            encrypted_entry = cipher.encrypt(log_entry.encode())

            # Write to file
            with open(self.filename, 'ab') as f:
                f.write(encrypted_entry + b'\n')

        except Exception:
            self.handleError(record)


class LogManager:
    """Manages log retention and lifecycle for security compliance."""

    def __init__(self, log_directory: str = "logs"):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(exist_ok=True)

    def apply_retention_policy(self, days: int = 30, sensitive_days: int = 7):
        """Apply retention policy to log files."""
        current_time = time.time()

        for log_file in self.log_directory.glob("*.log"):
            file_age = current_time - log_file.stat().st_mtime

            # More aggressive retention for sensitive logs
            if 'sensitive' in log_file.name.lower():
                if file_age > sensitive_days * 86400:
                    log_file.unlink()
                    logging.info(f"Deleted sensitive log file: {log_file}")
            else:
                if file_age > days * 86400:
                    log_file.unlink()
                    logging.info(f"Deleted log file: {log_file}")


class LogForwarder:
    """Forwards logs to external services with sanitization."""

    def __init__(self, endpoint_url: str, api_key: Optional[str] = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.processors = [
            PIIProcessor(),
            APIKeyProcessor(),
            SensitiveDataProcessor()
        ]

    def forward(self, log_data: Dict[str, Any]):
        """Forward log data after sanitization."""
        # Apply all processors
        sanitized_data = log_data.copy()
        for processor in self.processors:
            sanitized_data = processor(None, None, sanitized_data)

        # Add metadata
        sanitized_data['forwarded_at'] = datetime.utcnow().isoformat()
        sanitized_data['source'] = 'data-foundry'

        # In production, this would send to external service
        # For now, just log the action
        logging.info(f"Would forward sanitized log to {self.endpoint_url}")


def configure_secure_logging(level: int = logging.INFO,
                           log_file: Optional[str] = None,
                           enable_json: bool = True) -> structlog.BoundLogger:
    """
    Configure structlog with security processors.

    Args:
        level: Logging level
        log_file: Optional log file path
        enable_json: Whether to use JSON formatting

    Returns:
        Configured structlog logger
    """
    # Configure processors chain
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),

        # Security processors
        PIIProcessor(),
        APIKeyProcessor(),
        SensitiveDataProcessor(),
    ]

    # Add renderer
    if enable_json:
        processors.append(SecureJSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler()]
    )

    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        logging.getLogger().addHandler(file_handler)

    return structlog.get_logger()


# Initialize secure logging when module is imported
secure_logger = configure_secure_logging()