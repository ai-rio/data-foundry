"""
Secure Notification Service for Data Foundry

This is a security-enhanced version of the notification service that includes:
- Email header injection protection
- Input sanitization
- Rate limiting
- Secure configuration management
"""

import logging
import asyncio
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Dict, Any, List, Optional

from src.core.security.sanitization import InputSanitizer, InputValidator
from src.core.config.incident_config import config

logger = logging.getLogger(__name__)


class SecureNotificationService:
    """
    Secure notification service with injection protection and rate limiting.
    """

    def __init__(self):
        """Initialize secure notification service."""
        self.sanitizer = InputSanitizer()
        self.config = config
        self._rate_limiter = {}
        self._setup_notification_channels()

    def _setup_notification_channels(self):
        """Setup notification channels based on configuration."""
        self.email_enabled = bool(self.config.smtp.server and self.config.smtp.username)
        self.slack_enabled = bool(self.config.slack.webhook_url)
        self.sms_enabled = bool(
            (self.config.sms.provider == 'twilio' and
             self.config.sms.account_sid and
             self.config.sms.auth_token) or
            self.config.sms.api_key
        )

    async def send_email_notification(
        self,
        to_email: str,
        subject: str,
        message: str,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        html_content: Optional[str] = None
    ) -> bool:
        """
        Send email notification with security protections.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            message: Plain text message content
            from_email: Sender email (optional, uses config default)
            reply_to: Reply-to email (optional)
            html_content: HTML content (optional)

        Returns:
            True if email sent successfully

        Raises:
            ValueError: If input validation fails
        """
        # Rate limiting check
        if not await self._check_rate_limit('email', to_email):
            logger.warning(f"Rate limit exceeded for email to {to_email}")
            return False

        try:
            # Input validation and sanitization
            if not InputValidator.validate_email(to_email):
                raise ValueError(f"Invalid recipient email: {to_email}")

            sanitized_to_email = self.sanitizer.sanitize_email_header(to_email)
            sanitized_subject = self.sanitizer.sanitize_email_header(subject)
            sanitized_message = self.sanitizer.sanitize_string(message, max_length=50000)
            sanitized_reply_to = None
            if reply_to:
                if not InputValidator.validate_email(reply_to):
                    raise ValueError(f"Invalid reply-to email: {reply_to}")
                sanitized_reply_to = self.sanitizer.sanitize_email_header(reply_to)

            # Set sender email
            sender_email = from_email or self.config.smtp.username
            if not InputValidator.validate_email(sender_email):
                raise ValueError(f"Invalid sender email: {sender_email}")

            sanitized_from_email = self.sanitizer.sanitize_email_header(sender_email)

            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = sanitized_subject
            msg['From'] = formataddr((self.config.smtp_username, sanitized_from_email))
            msg['To'] = sanitized_to_email

            if sanitized_reply_to:
                msg['Reply-To'] = sanitized_reply_to

            # Add plain text content
            text_part = MIMEText(sanitized_message, 'plain', 'utf-8')
            msg.attach(text_part)

            # Add HTML content if provided
            if html_content:
                sanitized_html = self.sanitizer.sanitize_html(html_content)
                html_part = MIMEText(sanitized_html, 'html', 'utf-8')
                msg.attach(html_part)

            # Send email
            await self._send_secure_email(msg, sanitized_to_email)

            logger.info(f"Email sent successfully to {sanitized_to_email}")
            return True

        except ValueError as e:
            logger.error(f"Email validation failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_slack_notification(
        self,
        message: str,
        channel: Optional[str] = None,
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        mention_users: Optional[List[str]] = None
    ) -> bool:
        """
        Send Slack notification with security protections.

        Args:
            message: Message to send
            channel: Slack channel (optional, uses config default)
            username: Bot username (optional, uses config default)
            icon_emoji: Bot icon emoji (optional, uses config default)
            mention_users: List of users to mention (optional)

        Returns:
            True if message sent successfully
        """
        if not self.slack_enabled:
            logger.warning("Slack notifications not configured")
            return False

        # Rate limiting check
        if not await self._check_rate_limit('slack', channel or self.config.slack.channel):
            logger.warning(f"Rate limit exceeded for Slack channel {channel}")
            return False

        try:
            # Input sanitization
            sanitized_message = self.sanitizer.sanitize_string(message, max_length=2000)
            sanitized_channel = self.sanitizer.sanitize_string(
                channel or self.config.slack.channel, max_length=100
            )
            sanitized_username = self.sanitizer.sanitize_string(
                username or self.config.slack.username, max_length=50
            )
            sanitized_icon_emoji = self.sanitizer.sanitize_string(
                icon_emoji or self.config.slack.icon_emoji, max_length=50
            )

            # Sanitize mention users
            sanitized_mentions = []
            if mention_users:
                for user in mention_users:
                    sanitized_user = self.sanitizer.sanitize_string(user, max_length=50)
                    # Validate Slack user format
                    if sanitized_user.startswith('@') or sanitized_user.startswith('<@'):
                        sanitized_mentions.append(sanitized_user)

            # Add mentions to message
            if sanitized_mentions:
                sanitized_message = f"{' '.join(sanitized_mentions)} {sanitized_message}"

            # Prepare payload
            payload = {
                'channel': sanitized_channel,
                'username': sanitized_username,
                'icon_emoji': sanitized_icon_emoji,
                'text': sanitized_message,
                'mrkdwn': True
            }

            # Send to Slack
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.slack.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Slack message sent to {sanitized_channel}")
                        return True
                    else:
                        logger.error(f"Slack API error: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False

    async def send_sms_notification(
        self,
        to_number: str,
        message: str,
        from_number: Optional[str] = None
    ) -> bool:
        """
        Send SMS notification with security protections.

        Args:
            to_number: Recipient phone number
            message: SMS message content
            from_number: Sender phone number (optional)

        Returns:
            True if SMS sent successfully
        """
        if not self.sms_enabled:
            logger.warning("SMS notifications not configured")
            return False

        # Rate limiting check
        if not await self._check_rate_limit('sms', to_number):
            logger.warning(f"Rate limit exceeded for SMS to {to_number}")
            return False

        try:
            # Input validation
            sanitized_message = self.sanitizer.sanitize_string(message, max_length=1600)
            sanitized_to_number = self._validate_and_sanitize_phone_number(to_number)
            sanitized_from_number = None

            if from_number:
                sanitized_from_number = self._validate_and_sanitize_phone_number(from_number)

            # Send based on provider
            if self.config.sms.provider == 'twilio':
                return await self._send_twilio_sms(
                    sanitized_to_number,
                    sanitized_message,
                    sanitized_from_number
                )
            else:
                logger.warning(f"SMS provider {self.config.sms.provider} not implemented")
                return False

        except ValueError as e:
            logger.error(f"SMS validation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False

    async def _send_secure_email(self, msg: MIMEMultipart, to_email: str) -> None:
        """
        Send email with security protections.

        Args:
            msg: Email message object
            to_email: Recipient email
        """
        context = None
        try:
            # Create secure SMTP connection
            if self.config.smtp.use_ssl:
                context = smtplib.SMTP_SSL(
                    self.config.smtp.server,
                    self.config.smtp.port,
                    timeout=self.config.smtp.timeout
                )
            else:
                context = smtplib.SMTP(
                    self.config.smtp.server,
                    self.config.smtp.port,
                    timeout=self.config.smtp.timeout
                )
                if self.config.smtp.use_tls:
                    context.starttls()

            # Login and send
            context.login(self.config.smtp.username, self.config.smtp.password)
            context.send_message(msg, to_addrs=[to_email])

        finally:
            if context:
                try:
                    context.quit()
                except Exception:
                    pass

    async def _send_twilio_sms(
        self,
        to_number: str,
        message: str,
        from_number: Optional[str] = None
    ) -> bool:
        """
        Send SMS via Twilio API.

        Args:
            to_number: Recipient phone number
            message: SMS message
            from_number: Sender phone number (optional)

        Returns:
            True if SMS sent successfully
        """
        try:
            from twilio.rest import Client
            from twilio.base.exceptions import TwilioRestException

            client = Client(
                self.config.sms.account_sid,
                self.config.sms.auth_token
            )

            message_obj = client.messages.create(
                body=message,
                from_=from_number or self.config.sms.from_number,
                to=to_number
            )

            logger.info(f"SMS sent via Twilio, SID: {message_obj.sid}")
            return True

        except ImportError:
            logger.error("Twilio library not installed")
            return False
        except TwilioRestException as e:
            logger.error(f"Twilio API error: {e}")
            return False

    def _validate_and_sanitize_phone_number(self, phone_number: str) -> str:
        """
        Validate and sanitize phone number.

        Args:
            phone_number: Phone number to validate

        Returns:
            Sanitized phone number

        Raises:
            ValueError: If phone number format is invalid
        """
        # Remove all non-numeric characters except + and -
        sanitized = ''.join(c for c in phone_number if c.isdigit() or c in '+-')

        # Basic validation
        if not sanitized or len(sanitized) < 10:
            raise ValueError(f"Invalid phone number: {phone_number}")

        # Ensure it starts with + for international format
        if not sanitized.startswith('+'):
            # Assume US number if no country code
            if sanitized.startswith('1') and len(sanitized) == 11:
                sanitized = '+' + sanitized
            elif len(sanitized) == 10:
                sanitized = '+1' + sanitized
            else:
                raise ValueError(f"Invalid phone number format: {phone_number}")

        return sanitized

    async def _check_rate_limit(self, channel: str, identifier: str) -> bool:
        """
        Check rate limiting for notification channel.

        Args:
            channel: Notification channel (email, sms, slack)
            identifier: Identifier to rate limit (email, phone, channel)

        Returns:
            True if within rate limit, False otherwise
        """
        if not self.config.security.rate_limit_enabled:
            return True

        now = datetime.now(timezone.utc)
        key = f"{channel}:{identifier}"

        # Clean old entries
        self._cleanup_rate_limit_entries(now)

        # Check current usage
        if key in self._rate_limiter:
            requests = self._rate_limiter[key]
            recent_requests = [
                req_time for req_time in requests
                if now - req_time < timedelta(minutes=1)
            ]

            if len(recent_requests) >= self.config.security.rate_limit_requests_per_minute:
                return False

            self._rate_limiter[key] = recent_requests + [now]
        else:
            self._rate_limiter[key] = [now]

        return True

    def _cleanup_rate_limit_entries(self, now: datetime) -> None:
        """
        Clean up old rate limit entries.

        Args:
            now: Current timestamp
        """
        cutoff = now - timedelta(minutes=5)
        keys_to_remove = []

        for key, timestamps in self._rate_limiter.items():
            recent = [t for t in timestamps if t > cutoff]
            if not recent:
                keys_to_remove.append(key)
            else:
                self._rate_limiter[key] = recent

        for key in keys_to_remove:
            del self._rate_limiter[key]

    async def send_bulk_notifications(
        self,
        notifications: List[Dict[str, Any]],
        max_concurrent: int = 10
    ) -> Dict[str, int]:
        """
        Send multiple notifications concurrently with rate limiting.

        Args:
            notifications: List of notification dictionaries
            max_concurrent: Maximum concurrent notifications

        Returns:
            Dictionary with success/failure counts
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def send_single(notification):
            async with semaphore:
                channel = notification.get('channel', 'email')

                if channel == 'email':
                    return await self.send_email_notification(**notification)
                elif channel == 'slack':
                    return await self.send_slack_notification(**notification)
                elif channel == 'sms':
                    return await self.send_sms_notification(**notification)
                else:
                    logger.warning(f"Unknown notification channel: {channel}")
                    return False

        # Send notifications concurrently
        tasks = [send_single(notif) for notif in notifications]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        success_count = sum(1 for r in results if r is True)
        failure_count = sum(1 for r in results if r is False)
        exception_count = sum(1 for r in results if isinstance(r, Exception))

        # Log exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Notification {i} failed with exception: {result}")

        return {
            'success': success_count,
            'failure': failure_count,
            'exception': exception_count,
            'total': len(notifications)
        }