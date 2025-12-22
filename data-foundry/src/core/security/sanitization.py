"""
Input Sanitization and Validation for Security

Provides comprehensive input sanitization to prevent XSS, SQL injection,
and other security vulnerabilities in the incident response system.
"""

import html
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class InputSanitizer:
    """
    Comprehensive input sanitization for security.
    """

    # Patterns for SQL injection detection
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"(\b(OR|AND)\s+\d+\s*=\s*\d+)",
        r"(;\s*(DROP|DELETE|UPDATE))",
        r"(\bUNION\s+SELECT\b)",
        r"(--|\/\*|\*\/)",
        r"(\bXOR\b)",
        r"(\bCONCAT\b)",
        r"(\bCAST\b)",
        r"(\bCHAR\b)",
        r"(\bASCII\b)",
        r"(\bHEX\b)",
        r"(\bLOAD_FILE\b)",
        r"(\bINTO\s+OUTFILE\b)",
        r"(\bINTO\s+DUMPFILE\b)",
    ]

    # Patterns for XSS detection
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"vbscript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<link[^>]*>",
        r"<meta[^>]*>",
        r"<style[^>]*>.*?</style>",
        r"<img[^>]*on\w+\s*=",
        r"eval\s*\(",
        r"alert\s*\(",
        r"prompt\s*\(",
        r"confirm\s*\(",
        r"document\.",
        r"window\.",
    ]

    # Email header injection patterns
    EMAIL_INJECTION_PATTERNS = [
        r"[\r\n]",
        r"[\r\n]\s*",
        r"(bcc|to|from|reply-to|subject|cc):",
        r"(content-transfer-encoding|content-type):",
        r"mime-version:",
    ]

    @classmethod
    def sanitize_string(cls, value: Any, max_length: int = 1000) -> str:
        """
        Sanitize a string value for safe processing.

        Args:
            value: Value to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized string

        Raises:
            ValueError: If input contains malicious content
        """
        if value is None:
            return ""

        # Convert to string
        if not isinstance(value, str):
            value = str(value)

        # Check length
        if len(value) > max_length:
            raise ValueError(f"Input too long: max {max_length} characters, got {len(value)}")

        # Check for SQL injection
        if cls.detect_sql_injection(value):
            logger.warning(f"SQL injection attempt detected: {value[:100]}...")
            raise ValueError("Invalid input: potential SQL injection")

        # Check for XSS
        if cls.detect_xss(value):
            logger.warning(f"XSS attempt detected: {value[:100]}...")
            raise ValueError("Invalid input: potential XSS")

        # HTML encode
        sanitized = html.escape(value)

        # Remove control characters
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)

        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())

        return sanitized

    @classmethod
    def sanitize_html(cls, value: Any, allowed_tags: List[str] = None) -> str:
        """
        Sanitize HTML content, allowing only safe tags.

        Args:
            value: HTML content to sanitize
            allowed_tags: List of allowed HTML tags (e.g., ['p', 'br', 'strong'])

        Returns:
            Sanitized HTML
        """
        if value is None:
            return ""

        if not isinstance(value, str):
            value = str(value)

        # For now, just escape all HTML
        # In production, consider using a library like bleach
        return html.escape(value)

    @classmethod
    def sanitize_email_header(cls, value: Any) -> str:
        """
        Sanitize email header values to prevent injection.

        Args:
            value: Email header value

        Returns:
            Sanitized header value
        """
        if value is None:
            return ""

        if not isinstance(value, str):
            value = str(value)

        # Check for header injection
        for pattern in cls.EMAIL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"Email header injection attempt detected: {value[:100]}...")
                raise ValueError("Invalid input: potential email header injection")

        # Remove newlines and carriage returns
        sanitized = re.sub(r'[\r\n]', '', value)

        # Remove control characters
        sanitized = re.sub(r'[\x00-\x1F\x7F]', '', sanitized)

        return sanitized.strip()

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize filename for safe file operations.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed"

        # Remove path separators
        sanitized = re.sub(r'[\\/]', '_', filename)

        # Remove control characters
        sanitized = re.sub(r'[\x00-\x1F\x7F]', '', sanitized)

        # Remove dangerous characters
        sanitized = re.sub(r'[<>:"|?*]', '', sanitized)

        # Limit length
        if len(sanitized) > 255:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = name[:255-len(ext)-1] + '.' + ext if ext else name[:255]

        return sanitized or "unnamed"

    @classmethod
    def detect_sql_injection(cls, value: str) -> bool:
        """
        Detect potential SQL injection in input.

        Args:
            value: Input to check

        Returns:
            True if SQL injection detected
        """
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return True
        return False

    @classmethod
    def detect_xss(cls, value: str) -> bool:
        """
        Detect potential XSS in input.

        Args:
            value: Input to check

        Returns:
            True if XSS detected
        """
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE | re.DOTALL):
                return True
        return False

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], max_length: int = 1000) -> Dict[str, Any]:
        """
        Sanitize all string values in a dictionary.

        Args:
            data: Dictionary to sanitize
            max_length: Maximum string length

        Returns:
            Sanitized dictionary
        """
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value, max_length)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_dict(value, max_length)
            elif isinstance(value, list):
                sanitized[key] = cls.sanitize_list(value, max_length)
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def sanitize_list(cls, data: List[Any], max_length: int = 1000) -> List[Any]:
        """
        Sanitize all string values in a list.

        Args:
            data: List to sanitize
            max_length: Maximum string length

        Returns:
            Sanitized list
        """
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(cls.sanitize_string(item, max_length))
            elif isinstance(item, dict):
                sanitized.append(cls.sanitize_dict(item, max_length))
            elif isinstance(item, list):
                sanitized.append(cls.sanitize_list(item, max_length))
            else:
                sanitized.append(item)
        return sanitized


class InputValidator:
    """
    Input validation utilities for common data types.
    """

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address format.

        Args:
            email: Email address to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.

        Args:
            url: URL to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, url))

    @staticmethod
    def validate_uuid(uuid_str: str) -> bool:
        """
        Validate UUID format.

        Args:
            uuid_str: UUID string to validate

        Returns:
            True if valid, False otherwise
        """
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(pattern, uuid_str.lower()))

    @staticmethod
    def validate_severity(severity: str) -> bool:
        """
        Validate severity level.

        Args:
            severity: Severity to validate

        Returns:
            True if valid, False otherwise
        """
        valid_severities = ['critical', 'high', 'medium', 'low']
        return severity.lower() in valid_severities

    @staticmethod
    def validate_incident_type(incident_type: str) -> bool:
        """
        Validate incident type.

        Args:
            incident_type: Incident type to validate

        Returns:
            True if valid, False otherwise
        """
        valid_types = [
            'data_breach', 'security_incident', 'system_failure',
            'privacy_violation', 'compliance_violation', 'other'
        ]
        return incident_type.lower() in valid_types