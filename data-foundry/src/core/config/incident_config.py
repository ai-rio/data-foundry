"""
Configuration Management for Incident Response System

Provides secure configuration management with environment variable support,
validation, and defaults for all incident response components.
"""

import os
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseSettings, Field, validator

logger = logging.getLogger(__name__)


class SMTPConfig(BaseSettings):
    """SMTP configuration for email notifications."""

    server: str = Field(..., env="SMTP_SERVER")
    port: int = Field(587, env="SMTP_PORT")
    username: str = Field(..., env="SMTP_USERNAME")
    password: str = Field(..., env="SMTP_PASSWORD")
    use_tls: bool = Field(True, env="SMTP_USE_TLS")
    use_ssl: bool = Field(False, env="SMTP_USE_SSL")
    timeout: int = Field(30, env="SMTP_TIMEOUT")

    @validator('port')
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v

    @validator('timeout')
    def validate_timeout(cls, v):
        if v < 1:
            raise ValueError('Timeout must be positive')
        return v


class SlackConfig(BaseSettings):
    """Slack integration configuration."""

    webhook_url: Optional[str] = Field(None, env="SLACK_WEBHOOK_URL")
    channel: str = Field("#incidents", env="SLACK_CHANNEL")
    username: str = Field("Data Foundry Bot", env="SLACK_USERNAME")
    icon_emoji: str = Field(":warning:", env="SLACK_ICON_EMOJI")
    mention_users: List[str] = Field(default_factory=list, env="SLACK_MENTION_USERS")

    @validator('webhook_url')
    def validate_webhook_url(cls, v):
        if v and not v.startswith('https://hooks.slack.com/'):
            raise ValueError('Invalid Slack webhook URL')
        return v


class SMSConfig(BaseSettings):
    """SMS notification configuration."""

    provider: str = Field("twilio", env="SMS_PROVIDER")
    account_sid: Optional[str] = Field(None, env="TWILIO_ACCOUNT_SID")
    auth_token: Optional[str] = Field(None, env="TWILIO_AUTH_TOKEN")
    from_number: Optional[str] = Field(None, env="TWILIO_FROM_NUMBER")
    api_key: Optional[str] = Field(None, env="SMS_API_KEY")

    @validator('provider')
    def validate_provider(cls, v):
        valid_providers = ['twilio', 'aws_sns', 'nexmo']
        if v.lower() not in valid_providers:
            raise ValueError(f'Provider must be one of: {valid_providers}')
        return v.lower()


class GDPRConfig(BaseSettings):
    """GDPR compliance configuration."""

    authority_email: str = Field(..., env="GDPR_AUTHORITY_EMAIL")
    notification_deadline_hours: int = Field(72, env="GDPR_NOTIFICATION_DEADLINE_HOURS")
    data_subject_notification_threshold: str = Field("high", env="GDPR_DATA_SUBJECT_THRESHOLD")
    auto_escalation_enabled: bool = Field(True, env="GDPR_AUTO_ESCALATION_ENABLED")
    incident_report_template: str = Field("templates/gdpr_report.md", env="GDPR_REPORT_TEMPLATE")

    @validator('authority_email')
    def validate_authority_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid GDPR authority email')
        return v

    @validator('notification_deadline_hours')
    def validate_deadline_hours(cls, v):
        if v < 1 or v > 168:  # Max 1 week
            raise ValueError('Notification deadline must be between 1 and 168 hours')
        return v

    @validator('data_subject_notification_threshold')
    def validate_threshold(cls, v):
        valid_thresholds = ['low', 'medium', 'high', 'critical']
        if v.lower() not in valid_thresholds:
            raise ValueError(f'Threshold must be one of: {valid_thresholds}')
        return v.lower()


class SecurityConfig(BaseSettings):
    """Security configuration."""

    rate_limit_enabled: bool = Field(True, env="SECURITY_RATE_LIMIT_ENABLED")
    rate_limit_requests_per_minute: int = Field(60, env="SECURITY_RATE_LIMIT_RPM")
    rate_limit_burst_size: int = Field(100, env="SECURITY_RATE_LIMIT_BURST")
    max_file_size_mb: int = Field(10, env="SECURITY_MAX_FILE_SIZE_MB")
    allowed_file_types: List[str] = Field(
        default_factory=lambda: ['.txt', '.md', '.pdf', '.doc', '.docx'],
        env="SECURITY_ALLOWED_FILE_TYPES"
    )
    session_timeout_minutes: int = Field(480, env="SECURITY_SESSION_TIMEOUT_MINUTES")  # 8 hours
    password_min_length: int = Field(12, env="SECURITY_PASSWORD_MIN_LENGTH")

    @validator('rate_limit_requests_per_minute')
    def validate_rate_limit_rpm(cls, v):
        if v < 1 or v > 1000:
            raise ValueError('Rate limit must be between 1 and 1000 requests per minute')
        return v

    @validator('password_min_length')
    def validate_password_min_length(cls, v):
        if v < 8 or v > 128:
            raise ValueError('Password minimum length must be between 8 and 128')
        return v


class DatabaseConfig(BaseSettings):
    """Database configuration for incident storage."""

    pool_size: int = Field(10, env="DB_POOL_SIZE")
    max_overflow: int = Field(20, env="DB_MAX_OVERFLOW")
    pool_timeout: int = Field(30, env="DB_POOL_TIMEOUT")
    pool_recycle: int = Field(3600, env="DB_POOL_RECYCLE")  # 1 hour
    echo_sql: bool = Field(False, env="DB_ECHO_SQL")

    @validator('pool_size')
    def validate_pool_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError('Pool size must be between 1 and 100')
        return v


class MonitoringConfig(BaseSettings):
    """Monitoring and observability configuration."""

    metrics_enabled: bool = Field(True, env="MONITORING_METRICS_ENABLED")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_format: str = Field("json", env="LOG_FORMAT")  # json or text
    health_check_enabled: bool = Field(True, env="HEALTH_CHECK_ENABLED")
    distributed_tracing_enabled: bool = Field(False, env="DISTRIBUTED_TRACING_ENABLED")
    alert_webhook_url: Optional[str] = Field(None, env="ALERT_WEBHOOK_URL")

    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()

    @validator('log_format')
    def validate_log_format(cls, v):
        valid_formats = ['json', 'text']
        if v.lower() not in valid_formats:
            raise ValueError(f'Log format must be one of: {valid_formats}')
        return v.lower()


class IncidentResponseConfig:
    """
    Main configuration class for the incident response system.

    Loads and validates all configuration from environment variables.
    """

    def __init__(self):
        """Initialize configuration from environment."""
        self.smtp = SMTPConfig()
        self.slack = SlackConfig()
        self.sms = SMSConfig()
        self.gdpr = GDPRConfig()
        self.security = SecurityConfig()
        self.database = DatabaseConfig()
        self.monitoring = MonitoringConfig()

        # Validate configuration consistency
        self._validate_config()

    def _validate_config(self):
        """Validate configuration consistency."""
        # Check if at least one notification channel is configured
        email_configured = all([
            self.smtp.server,
            self.smtp.username,
            self.smtp.password
        ])
        slack_configured = bool(self.slack.webhook_url)
        sms_configured = all([
            self.sms.account_sid,
            self.sms.auth_token,
            self.sms.from_number
        ]) if self.sms.provider == 'twilio' else bool(self.sms.api_key)

        if not any([email_configured, slack_configured, sms_configured]):
            logger.warning(
                "No notification channels configured. "
                "Set SMTP_SERVER, SLACK_WEBHOOK_URL, or SMS_* environment variables."
            )

        # Validate security settings
        if self.security.rate_limit_enabled and self.security.rate_limit_requests_per_minute < 10:
            logger.warning(
                "Rate limit is very low (%d requests per minute). "
                "Consider increasing for better user experience.",
                self.security.rate_limit_requests_per_minute
            )

        # Validate GDPR settings
        if self.gdpr.notification_deadline_hours > 72:
            logger.warning(
                "GDPR notification deadline (%d hours) exceeds 72-hour requirement.",
                self.gdpr.notification_deadline_hours
            )

    def get_notification_config(self, channel: str) -> Dict[str, Any]:
        """
        Get configuration for a specific notification channel.

        Args:
            channel: Notification channel name (email, slack, sms)

        Returns:
            Configuration dictionary for the channel
        """
        if channel == 'email':
            return {
                'smtp_server': self.smtp.server,
                'smtp_port': self.smtp.port,
                'smtp_username': self.smtp.username,
                'smtp_password': self.smtp.password,
                'use_tls': self.smtp.use_tls,
                'use_ssl': self.smtp.use_ssl,
                'timeout': self.smtp.timeout,
            }
        elif channel == 'slack':
            return {
                'webhook_url': self.slack.webhook_url,
                'channel': self.slack.channel,
                'username': self.slack.username,
                'icon_emoji': self.slack.icon_emoji,
                'mention_users': self.slack.mention_users,
            }
        elif channel == 'sms':
            return {
                'provider': self.sms.provider,
                'account_sid': self.sms.account_sid,
                'auth_token': self.sms.auth_token,
                'from_number': self.sms.from_number,
                'api_key': self.sms.api_key,
            }
        else:
            raise ValueError(f"Unknown notification channel: {channel}")

    def get_gdpr_config(self) -> Dict[str, Any]:
        """
        Get GDPR-specific configuration.

        Returns:
            GDPR configuration dictionary
        """
        return {
            'authority_email': self.gdpr.authority_email,
            'notification_deadline_hours': self.gdpr.notification_deadline_hours,
            'data_subject_notification_threshold': self.gdpr.data_subject_notification_threshold,
            'auto_escalation_enabled': self.gdpr.auto_escalation_enabled,
            'incident_report_template': self.gdpr.incident_report_template,
        }

    def get_security_config(self) -> Dict[str, Any]:
        """
        Get security configuration.

        Returns:
            Security configuration dictionary
        """
        return {
            'rate_limit_enabled': self.security.rate_limit_enabled,
            'rate_limit_requests_per_minute': self.security.rate_limit_requests_per_minute,
            'rate_limit_burst_size': self.security.rate_limit_burst_size,
            'max_file_size_mb': self.security.max_file_size_mb,
            'allowed_file_types': self.security.allowed_file_types,
            'session_timeout_minutes': self.security.session_timeout_minutes,
            'password_min_length': self.security.password_min_length,
        }

    def is_production(self) -> bool:
        """
        Check if running in production environment.

        Returns:
            True if production environment
        """
        return os.getenv('ENVIRONMENT', '').lower() == 'production'

    def is_development(self) -> bool:
        """
        Check if running in development environment.

        Returns:
            True if development environment
        """
        return os.getenv('ENVIRONMENT', '').lower() == 'development'

    def get_database_config(self) -> Dict[str, Any]:
        """
        Get database configuration.

        Returns:
            Database configuration dictionary
        """
        return {
            'pool_size': self.database.pool_size,
            'max_overflow': self.database.max_overflow,
            'pool_timeout': self.database.pool_timeout,
            'pool_recycle': self.database.pool_recycle,
            'echo_sql': self.database.echo_sql,
        }


# Global configuration instance
config = IncidentResponseConfig()