"""
Shared enumerations for Data Foundry models.

This module contains common enums used across multiple models to avoid
circular imports and maintain consistency.
"""

from enum import Enum


class ConsentStatus(str, Enum):
    """Consent status enumeration for GDPR compliance"""
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class IncidentSeverity(str, Enum):
    """Incident severity levels following standard classification"""
    CRITICAL = "critical"  # System-wide outage, data breach, security compromise
    HIGH = "high"         # Significant impact, partial service degradation
    MEDIUM = "medium"     # Limited impact, some users affected
    LOW = "low"          # Minor issue, minimal impact


class IncidentStatus(str, Enum):
    """Incident status workflow for incident response lifecycle"""
    OPEN = "open"                    # Initial incident creation
    INVESTIGATING = "investigating"  # Investigation in progress
    IDENTIFIED = "identified"        # Cause identified
    MONITORING = "monitoring"        # Monitoring after containment
    RESOLVED = "resolved"           # Incident resolved
    CLOSED = "closed"               # Incident closed with review complete


class IncidentType(str, Enum):
    """Types of security and compliance incidents"""
    DATA_BREACH = "data_breach"           # Unauthorized access to personal data
    SECURITY_INCIDENT = "security_incident" # Security breach/vulnerability
    SYSTEM_OUTAGE = "system_outage"        # System/service unavailability
    PRIVACY_VIOLATION = "privacy_violation" # Privacy policy violation
    COMPLIANCE_VIOLATION = "compliance_violation"  # Regulatory compliance issue
    PERFORMANCE_DEGRADATION = "performance_degradation"  # Performance issues
    DATA_CORRUPTION = "data_corruption"    # Data integrity issues
    UNAUTHORIZED_ACCESS = "unauthorized_access"  # Access without permission
    MALWARE_DETECTED = "malware_detected"  # Malware infection
    PHISHING_ATTACK = "phishing_attack"    # Phishing/social engineering attack
    DENIAL_OF_SERVICE = "denial_of_service"  # DoS/DDoS attack
    MISCONFIGURATION = "misconfiguration"   # System/Security misconfiguration


class NotificationChannel(str, Enum):
    """Available notification channels for incident alerts"""
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class ContainmentAction(str, Enum):
    """Automatic containment actions for incident response"""
    ISOLATE_SYSTEM = "isolate_system"           # Network/system isolation
    DISABLE_ACCOUNT = "disable_account"         # Disable compromised accounts
    BLOCK_IP = "block_ip"                       # Block malicious IP addresses
    ROTATE_CREDENTIALS = "rotate_credentials"   # Rotate API keys/passwords
    STOP_SERVICE = "stop_service"               # Stop affected services
    ENABLE_MFA = "enable_mfa"                   # Enable multi-factor authentication
    REVOKE_SESSIONS = "revoke_sessions"         # Revoke active sessions
    PATCH_VULNERABILITY = "patch_vulnerability"  # Apply security patches