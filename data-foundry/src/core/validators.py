"""
Input validation module for Data Foundry
"""

import re
from typing import Any, Dict, List, Optional


def validate_input(input_str: str) -> bool:
    """
    Validate input for common injection attacks.

    Args:
        input_str: Input string to validate

    Returns:
        True if input is safe, False if potentially malicious
    """
    # Check for SQL injection patterns
    sql_patterns = [
        r"'(\s*|;.*)or\s+'1'='1",
        r"'(\s*|;.*)union\s+select",
        r"';\s*drop\s+table",
        r"';\s*insert\s+into",
        r"'(\s*|;.*)and\s+1=1",
        r"'(\s*|;.*)waitfor\s+delay",
        r"'(\s*|;.*)select\s+sleep",
    ]

    # Check for XSS patterns
    xss_patterns = [
        r"<script[^>]*>",
        r"<img[^>]*onerror",
        r"<svg[^>]*onload",
        r"javascript:",
        r"<iframe[^>]*>",
        r"<div[^>]*onmouseover",
        r"<body[^>]*onload",
        r"<.*onclick",
    ]

    # Check for command injection patterns
    cmd_patterns = [
        r";\s*rm\s+-rf",
        r"\|\s*rm\s+-rf",
        r"&&\s*rm\s+-rf",
        r"\$\(.*\)",
        r"`.*`",
        r"\|\|\s*rm\s+-rf",
        r"powershell\s+-Command",
        r"Invoke-Expression",
    ]

    # Check for path traversal patterns
    path_patterns = [
        r"\.\./.*\.\./",
        r"\.\.\\\.\.\\",
        r"\.\.%2f",
        r"%2e%2e%2f",
        r"\.\.%5c",
    ]

    all_patterns = sql_patterns + xss_patterns + cmd_patterns + path_patterns

    for pattern in all_patterns:
        if re.search(pattern, input_str, re.IGNORECASE):
            return False

    return True


def validate_email(email: str) -> bool:
    """
    Validate email format and check for injection attempts.

    Args:
        email: Email address to validate

    Returns:
        True if email is valid, False otherwise
    """
    # Basic email format validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False

    # Check for email injection attempts
    injection_patterns = [
        r"\r\n",
        r"\n",
        r"\r",
        r"CC:",
        r"BCC:",
        r"Subject:",
        r"From:",
        r"Reply-To:",
        r"X-Mailer:",
    ]

    for pattern in injection_patterns:
        if pattern in email:
            return False

    # Check for consecutive dots
    if ".." in email:
        return False

    # Check for domain starting with dot
    if email.startswith("@."):
        return False

    return True


def validate_phone(phone: str) -> bool:
    """
    Validate phone number format.

    Args:
        phone: Phone number to validate

    Returns:
        True if phone is valid format, False otherwise
    """
    # Remove common formatting characters
    cleaned = re.sub(r'[\s\-\(\)\+\.]', '', phone)

    # Check for only digits after cleaning
    if not cleaned.isdigit():
        return False

    # Check for reasonable length (10-15 digits)
    if not (10 <= len(cleaned) <= 15):
        return False

    # Check for injection attempts in original phone
    if not validate_input(phone):
        return False

    return True


def validate_safe_string(input_str: str) -> bool:
    """
    Validate that string contains only safe characters.

    Args:
        input_str: String to validate

    Returns:
        True if string contains only safe characters
    """
    # Allow only alphanumeric, spaces, and basic punctuation
    safe_pattern = r'^[a-zA-Z0-9\s\-_.,!?@#$%^&*()+=\[\]{}|;:<>~`\'"/\\]*$'
    return bool(re.match(safe_pattern, input_str))


def validate_safe_html(input_str: str) -> bool:
    """
    Validate HTML input for safety.

    Args:
        input_str: HTML string to validate

    Returns:
        True if HTML is safe, False otherwise
    """
    # Check for dangerous HTML elements and attributes
    dangerous_patterns = [
        r"<script[^>]*>.*?</script>",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<form[^>]*>",
        r"<input[^>]*>",
        r"javascript:",
        r"vbscript:",
        r"data:text/html",
        r"on\w+\s*=",  # Event handlers
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, input_str, re.IGNORECASE | re.DOTALL):
            return False

    return True


def validate_safe_command(input_str: str) -> bool:
    """
    Validate command input for safety.

    Args:
        input_str: Command string to validate

    Returns:
        True if command is safe, False otherwise
    """
    # Check for dangerous command characters
    dangerous_chars = [';', '|', '&', '$', '`', '(', ')', '{', '}', '[', ']', '<', '>']

    for char in dangerous_chars:
        if char in input_str:
            return False

    # Check for dangerous command keywords
    dangerous_keywords = [
        'rm', 'del', 'format', 'fdisk', 'dd', 'shutdown', 'reboot',
        'sudo', 'su', 'chmod', 'chown', 'passwd', 'crontab',
        'wget', 'curl', 'nc', 'netcat', 'telnet', 'ssh',
        'powershell', 'cmd.exe', 'bash', 'sh', 'zsh',
    ]

    for keyword in dangerous_keywords:
        if re.search(r'\b' + keyword + r'\b', input_str, re.IGNORECASE):
            return False

    return True


def validate_safe_path(input_str: str) -> bool:
    """
    Validate file path for safety.

    Args:
        input_str: Path string to validate

    Returns:
        True if path is safe, False otherwise
    """
    # Check for path traversal attempts
    if '../' in input_str or '..\\' in input_str:
        return False

    # Check for null bytes
    if '\x00' in input_str:
        return False

    # Check for dangerous characters in filenames
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*']
    for char in dangerous_chars:
        if char in input_str.split('/')[-1].split('\\')[-1]:
            return False

    # Check for absolute paths (may want to restrict depending on use case)
    if input_str.startswith('/') or (len(input_str) > 1 and input_str[1] == ':'):
        # Allow absolute paths only if explicitly configured
        pass

    return True


def validate_safe_email(input_str: str) -> bool:
    """
    Validate email with additional security checks.

    Args:
        input_str: Email to validate

    Returns:
        True if email is safe, False otherwise
    """
    if not validate_email(input_str):
        return False

    # Additional security checks
    # Check for suspicious TLDs
    suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.zip', '.rar']
    for tld in suspicious_tlds:
        if input_str.lower().endswith(tld):
            return False

    # Check for too many subdomains
    if input_str.count('.') > 4:
        return False

    # Check for very long local part
    if '@' in input_str:
        local_part = input_str.split('@')[0]
        if len(local_part) > 64:
            return False

    return True


def validate_safe_phone(input_str: str) -> bool:
    """
    Validate phone number with additional security checks.

    Args:
        input_str: Phone number to validate

    Returns:
        True if phone is safe, False otherwise
    """
    if not validate_phone(input_str):
        return False

    # Check for premium rate number prefixes (example prefixes)
    premium_prefixes = ['1900', '1910', '1919', '0900', '0909']
    cleaned = re.sub(r'[\s\-\(\)\+\.]', '', input_str)

    for prefix in premium_prefixes:
        if cleaned.startswith(prefix):
            return False

    # Check for obviously invalid numbers
    if cleaned == '0000000000' or cleaned == '1111111111' or cleaned == '1234567890':
        return False

    return True