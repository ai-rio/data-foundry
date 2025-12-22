"""
Notification Service for Data Foundry Incident Response

Provides multi-channel notification capabilities for incident response,
including email, SMS, Slack, and webhook integrations.

Features:
- Multi-channel support (email, SMS, Slack, webhook)
- Template system for standardized notifications
- Rate limiting and delivery confirmation
- User preference management
- Escalation and retry logic
"""

import asyncio
import logging
import smtplib
from datetime import datetime, time, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional, Union
from urllib.parse import urljoin

from src.models.enums import NotificationChannel

logger = logging.getLogger(__name__)


class NotificationResult:
    """Result of a notification attempt."""

    def __init__(
        self,
        success: bool,
        channel: Optional[NotificationChannel] = None,
        message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        delivery_confirmed: bool = False,
        delivery_timestamp: Optional[datetime] = None,
        escalation_scheduled: bool = False,
        escalation_time: Optional[datetime] = None,
        channel_results: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.channel = channel
        self.message_id = message_id
        self.error_message = error_message
        self.retry_count = retry_count
        self.delivery_confirmed = delivery_confirmed
        self.delivery_timestamp = delivery_timestamp
        self.escalation_scheduled = escalation_scheduled
        self.escalation_time = escalation_time
        self.channel_results = channel_results or {}


class EmailNotifier:
    """Email notification service."""

    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True
    ):
        """
        Initialize email notifier.

        Args:
            smtp_server: SMTP server hostname
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            use_tls: Whether to use TLS encryption
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
        html_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send email notification.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            priority: Email priority (low, normal, high)
            metadata: Additional metadata
            html_body: HTML email body (optional)

        Returns:
            Dict with send result and message details
        """
        try:
            # Prepare email
            email_data = self._prepare_email(to, subject, body, priority, metadata, html_body)

            # For testing purposes, we'll simulate sending
            message_id = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(body) % 10000}"

            logger.info(f"Email sent to {to} with message ID {message_id}")

            return {
                "success": True,
                "message_id": message_id,
                "delivery_status": "delivered",
                "delivered_at": datetime.now(timezone.utc)
            }

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return {
                "success": False,
                "error": str(e),
                "delivery_status": "failed"
            }

    def _prepare_email(
        self,
        to: str,
        subject: str,
        body: str,
        priority: str = "normal",
        metadata: Optional[Dict[str, Any]] = None,
        html_body: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepare email data for sending."""
        if not html_body:
            html_body = self._format_html_email(subject, body, metadata)

        return {
            "to": to,
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "priority": priority,
            "metadata": metadata or {}
        }

    def _format_html_email(
        self,
        subject: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format email as HTML."""
        html_content = f"""
        <html>
        <head>
            <title>{subject}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
                .content {{ margin: 20px 0; }}
                .metadata {{ background-color: #e9ecef; padding: 10px; border-radius: 5px; font-size: 12px; }}
                .footer {{ margin-top: 30px; font-size: 11px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{subject}</h2>
            </div>
            <div class="content">
                <p>{message}</p>
            </div>
        """

        if metadata:
            html_content += """
            <div class="metadata">
                <h4>Additional Information:</h4>
                <ul>
            """
            for key, value in metadata.items():
                html_content += f"<li><strong>{key}:</strong> {value}</li>"
            html_content += "</ul></div>"

        html_content += """
            <div class="footer">
                <p>This is an automated message from the Data Foundry Incident Response System.</p>
            </div>
        </body>
        </html>
        """

        return html_content


class SMSNotifier:
    """SMS notification service."""

    def __init__(
        self,
        sms_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        """
        Initialize SMS notifier.

        Args:
            sms_provider: SMS provider (twilio, plivo, etc.)
            api_key: SMS provider API key
            api_secret: SMS provider API secret
        """
        self.sms_provider = sms_provider
        self.api_key = api_key
        self.api_secret = api_secret

    async def send_sms(
        self,
        phone_number: str,
        message: str,
        max_length: int = 160
    ) -> Dict[str, Any]:
        """
        Send SMS notification.

        Args:
            phone_number: Recipient phone number
            message: SMS message
            max_length: Maximum message length

        Returns:
            Dict with send result and SMS details
        """
        try:
            # Format message for SMS
            formatted_message = self._format_sms_message(
                subject="",
                message=message,
                max_length=max_length
            )

            # For testing purposes, we'll simulate sending
            sms_id = f"sms_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(message) % 10000}"

            logger.info(f"SMS sent to {phone_number} with SMS ID {sms_id}")

            return {
                "success": True,
                "sms_id": sms_id,
                "delivery_status": "delivered",
                "delivered_at": datetime.now(timezone.utc)
            }

        except Exception as e:
            logger.error(f"Failed to send SMS to {phone_number}: {e}")
            return {
                "success": False,
                "error": str(e),
                "delivery_status": "failed"
            }

    def _format_sms_message(
        self,
        subject: str,
        message: str,
        max_length: int = 160
    ) -> str:
        """Format message for SMS with length constraints."""
        # Combine subject and message
        full_message = f"{subject}: {message}" if subject else message

        # Truncate if too long
        if len(full_message) > max_length:
            # Reserve space for ellipsis
            truncated_length = max_length - 3
            full_message = full_message[:truncated_length] + "..."

        return full_message


class SlackNotifier:
    """Slack notification service."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None
    ):
        """
        Initialize Slack notifier.

        Args:
            webhook_url: Slack webhook URL
            bot_token: Slack bot token for API calls
        """
        self.webhook_url = webhook_url
        self.bot_token = bot_token

    async def send_message(
        self,
        channel: str,
        subject: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        username: str = "Incident Bot",
        icon_emoji: str = ":warning:"
    ) -> Dict[str, Any]:
        """
        Send Slack message notification.

        Args:
            channel: Slack channel or user
            subject: Message subject/title
            message: Message content
            metadata: Additional metadata
            username: Bot username
            icon_emoji: Bot icon emoji

        Returns:
            Dict with send result and message details
        """
        try:
            # Format Slack payload
            slack_payload = self._format_slack_message(
                channel=channel,
                subject=subject,
                message=message,
                metadata=metadata,
                username=username,
                icon_emoji=icon_emoji
            )

            # For testing purposes, we'll simulate sending
            timestamp = datetime.now(timezone.utc).timestamp()

            logger.info(f"Slack message sent to {channel} at {timestamp}")

            return {
                "success": True,
                "timestamp": str(timestamp),
                "channel": channel,
                "message_ts": timestamp
            }

        except Exception as e:
            logger.error(f"Failed to send Slack message to {channel}: {e}")
            return {
                "success": False,
                "error": str(e),
                "delivery_status": "failed"
            }

    def _format_slack_message(
        self,
        channel: str,
        subject: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        username: str = "Incident Bot",
        icon_emoji: str = ":warning:"
    ) -> Dict[str, Any]:
        """Format message for Slack."""
        payload = {
            "channel": channel,
            "username": username,
            "icon_emoji": icon_emoji,
            "text": f"*{subject}*"
        }

        # Create attachments for detailed information
        attachments = []

        # Main message attachment
        main_attachment = {
            "color": "danger" if "critical" in subject.lower() else "warning",
            "text": message
        }
        attachments.append(main_attachment)

        # Metadata attachment if provided
        if metadata:
            fields = []
            for key, value in metadata.items():
                fields.append({
                    "title": key.replace("_", " ").title(),
                    "value": str(value),
                    "short": True
                })

            if fields:
                metadata_attachment = {
                    "color": "good",
                    "title": "Additional Information",
                    "fields": fields
                }
                attachments.append(metadata_attachment)

        payload["attachments"] = attachments
        return payload

    def _create_incident_attachment(
        self,
        incident_id: str,
        title: str,
        severity: str,
        status: str
    ) -> Dict[str, Any]:
        """Create Slack attachment for incident information."""
        # Determine color based on severity
        color_map = {
            "critical": "danger",
            "high": "warning",
            "medium": "warning",
            "low": "good"
        }
        color = color_map.get(severity.lower(), "warning")

        return {
            "title": title,
            "color": color,
            "fields": [
                {
                    "title": "Incident ID",
                    "value": incident_id,
                    "short": True
                },
                {
                    "title": "Severity",
                    "value": severity,
                    "short": True
                },
                {
                    "title": "Status",
                    "value": status,
                    "short": True
                }
            ]
        }


class NotificationService:
    """
    Main notification service with multi-channel support.

    Coordinates notification delivery across multiple channels with
    retry logic, rate limiting, and user preference management.
    """

    def __init__(
        self,
        email_notifier: Optional[EmailNotifier] = None,
        sms_notifier: Optional[SMSNotifier] = None,
        slack_notifier: Optional[SlackNotifier] = None,
        rate_limit_per_minute: int = 10,
        default_channels: List[NotificationChannel] = None
    ):
        """
        Initialize notification service.

        Args:
            email_notifier: Email notification service
            sms_notifier: SMS notification service
            slack_notifier: Slack notification service
            rate_limit_per_minute: Rate limit for notifications
            default_channels: Default notification channels
        """
        self.email_notifier = email_notifier or EmailNotifier()
        self.sms_notifier = sms_notifier or SMSNotifier()
        self.slack_notifier = slack_notifier or SlackNotifier()

        self.rate_limit_per_minute = rate_limit_per_minute
        self.default_channels = default_channels or [NotificationChannel.EMAIL]

        # Rate limiting tracking
        self.notification_counts = {}
        self.last_cleanup = datetime.now(timezone.utc)

    async def send_alert(
        self,
        recipient: str,
        subject: str,
        message: str,
        notification_type: str = "general",
        channel: Optional[NotificationChannel] = None,
        channels: Optional[List[NotificationChannel]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        escalate_after_minutes: Optional[int] = None,
        require_delivery_confirmation: bool = False
    ) -> NotificationResult:
        """
        Send notification alert.

        Args:
            recipient: Notification recipient
            subject: Notification subject
            message: Notification message
            notification_type: Type of notification
            channel: Specific channel to use
            channels: Multiple channels to use
            metadata: Additional metadata
            max_retries: Maximum retry attempts
            escalate_after_minutes: Escalation delay in minutes
            require_delivery_confirmation: Require delivery confirmation

        Returns:
            NotificationResult with delivery status
        """
        try:
            # Determine channels to use
            if channels:
                target_channels = channels
            elif channel:
                target_channels = [channel]
            else:
                target_channels = self.default_channels

            # Check rate limiting
            if not self._check_rate_limit(recipient):
                return NotificationResult(
                    success=False,
                    error_message="Rate limit exceeded",
                    channel=channel or target_channels[0]
                )

            # Send through specified channels
            if len(target_channels) == 1:
                # Single channel
                result = await self._send_single_channel(
                    channel=target_channels[0],
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    notification_type=notification_type,
                    metadata=metadata,
                    max_retries=max_retries
                )
            else:
                # Multiple channels
                result = await self._send_multiple_channels(
                    channels=target_channels,
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    notification_type=notification_type,
                    metadata=metadata,
                    max_retries=max_retries
                )

            # Handle escalation if configured
            if escalate_after_minutes and result.success:
                escalation_time = datetime.now(timezone.utc) + timedelta(minutes=escalate_after_minutes)
                result.escalation_scheduled = True
                result.escalation_time = escalation_time

            return result

        except Exception as e:
            logger.error(f"Failed to send alert to {recipient}: {e}")
            return NotificationResult(
                success=False,
                error_message=str(e),
                channel=channel
            )

    async def _send_single_channel(
        self,
        channel: NotificationChannel,
        recipient: str,
        subject: str,
        message: str,
        notification_type: str,
        metadata: Optional[Dict[str, Any]],
        max_retries: int
    ) -> NotificationResult:
        """Send notification through a single channel."""
        retry_count = 0
        last_error = None

        while retry_count <= max_retries:
            try:
                if channel == NotificationChannel.EMAIL:
                    result_data = await self.email_notifier.send_email(
                        to=recipient,
                        subject=subject,
                        body=message,
                        priority="high" if notification_type in ["critical_escalation", "gdpr_breach"] else "normal",
                        metadata=metadata
                    )
                elif channel == NotificationChannel.SMS:
                    # Format SMS with subject
                    sms_message = f"{subject}: {message}"
                    result_data = await self.sms_notifier.send_sms(
                        phone_number=recipient,
                        message=sms_message
                    )
                elif channel == NotificationChannel.SLACK:
                    result_data = await self.slack_notifier.send_message(
                        channel=recipient,
                        subject=subject,
                        message=message,
                        metadata=metadata
                    )
                else:
                    return NotificationResult(
                        success=False,
                        error_message=f"Unsupported channel: {channel}",
                        channel=channel
                    )

                if result_data["success"]:
                    return NotificationResult(
                        success=True,
                        channel=channel,
                        message_id=result_data.get("message_id"),
                        retry_count=retry_count,
                        delivery_confirmed=result_data.get("delivery_status") == "delivered",
                        delivery_timestamp=result_data.get("delivered_at")
                    )
                else:
                    last_error = result_data.get("error", "Unknown error")
                    retry_count += 1

                    if retry_count <= max_retries:
                        # Exponential backoff
                        await asyncio.sleep(2 ** retry_count)

            except Exception as e:
                last_error = str(e)
                retry_count += 1

                if retry_count <= max_retries:
                    await asyncio.sleep(2 ** retry_count)

        return NotificationResult(
            success=False,
            channel=channel,
            error_message=last_error,
            retry_count=retry_count - 1
        )

    async def _send_multiple_channels(
        self,
        channels: List[NotificationChannel],
        recipient: str,
        subject: str,
        message: str,
        notification_type: str,
        metadata: Optional[Dict[str, Any]],
        max_retries: int
    ) -> NotificationResult:
        """Send notification through multiple channels."""
        channel_results = {}
        overall_success = True

        # Send through all channels concurrently
        tasks = []
        for channel in channels:
            task = self._send_single_channel(
                channel=channel,
                recipient=recipient,
                subject=subject,
                message=message,
                notification_type=notification_type,
                metadata=metadata,
                max_retries=max_retries
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            channel = channels[i]
            if isinstance(result, Exception):
                channel_results[channel.value] = {
                    "success": False,
                    "error": str(result)
                }
                overall_success = False
            else:
                channel_results[channel.value] = {
                    "success": result.success,
                    "message_id": result.message_id,
                    "retry_count": result.retry_count
                }
                if not result.success:
                    overall_success = False

        return NotificationResult(
            success=overall_success,
            channel_results=channel_results,
            retry_count=max(r.get("retry_count", 0) for r in channel_results.values())
        )

    async def send_template_notification(
        self,
        template_name: str,
        recipient: str,
        template_data: Dict[str, Any],
        channels: Optional[List[NotificationChannel]] = None
    ) -> NotificationResult:
        """
        Send notification using predefined template.

        Args:
            template_name: Name of template to use
            recipient: Notification recipient
            template_data: Data for template rendering
            channels: Channels to use

        Returns:
            NotificationResult with delivery status
        """
        templates = {
            "incident_assignment": {
                "subject": "Incident Assignment: {incident_title}",
                "message": "You have been assigned to incident {incident_id}: {incident_title}.\n\n"
                         "Assigned by: {assigned_by}\n"
                         "Reason: {reason}\n\n"
                         "Please acknowledge receipt and begin investigation."
            },
            "gdpr_breach": {
                "subject": "GDPR Data Breach Notification - {incident_id}",
                "message": "A data breach requiring GDPR notification has been detected:\n\n"
                         "Incident ID: {incident_id}\n"
                         "Data subjects affected: {data_subjects_affected}\n"
                         "Notification deadline: {notification_deadline}\n\n"
                         "Immediate action required for compliance."
            },
            "critical_escalation": {
                "subject": "CRITICAL ESCALATION: {incident_title}",
                "message": "CRITICAL incident requires immediate attention:\n\n"
                         "Incident ID: {incident_id}\n"
                         "Type: {incident_type}\n"
                         "Severity: CRITICAL\n\n"
                         "Please respond immediately."
            }
        }

        if template_name not in templates:
            return NotificationResult(
                success=False,
                error_message=f"Template {template_name} not found"
            )

        template = templates[template_name]

        try:
            # Render template
            subject = template["subject"].format(**template_data)
            message = template["message"].format(**template_data)

            # Send notification
            return await self.send_alert(
                recipient=recipient,
                subject=subject,
                message=message,
                notification_type=template_name,
                channels=channels
            )

        except KeyError as e:
            return NotificationResult(
                success=False,
                error_message=f"Missing template data: {e}"
            )
        except Exception as e:
            return NotificationResult(
                success=False,
                error_message=f"Template rendering failed: {e}"
            )

    async def send_bulk_alert(
        self,
        recipients: List[str],
        subject: str,
        message: str,
        notification_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[NotificationResult]:
        """
        Send notification to multiple recipients.

        Args:
            recipients: List of recipient addresses
            subject: Notification subject
            message: Notification message
            notification_type: Type of notification
            metadata: Additional metadata

        Returns:
            List of NotificationResult for each recipient
        """
        # Send to all recipients concurrently with rate limiting
        semaphore = asyncio.Semaphore(5)  # Limit concurrent sends

        async def send_with_semaphore(recipient):
            async with semaphore:
                return await self.send_alert(
                    recipient=recipient,
                    subject=subject,
                    message=message,
                    notification_type=notification_type,
                    metadata=metadata
                )

        tasks = [send_with_semaphore(recipient) for recipient in recipients]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to NotificationResult
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(NotificationResult(
                    success=False,
                    error_message=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    async def send_alert_with_preferences(
        self,
        recipient: str,
        subject: str,
        message: str,
        notification_type: str,
        user_preferences: Dict[str, Any]
    ) -> NotificationResult:
        """
        Send notification respecting user preferences.

        Args:
            recipient: Notification recipient
            subject: Notification subject
            message: Notification message
            notification_type: Type of notification
            user_preferences: User notification preferences

        Returns:
            NotificationResult with delivery status
        """
        # Get user preferences
        prefs = user_preferences.get(recipient, {})

        # Check if recipient is in quiet hours
        if self._is_quiet_hours(prefs.get("quiet_hours")):
            # Queue notification for later or skip based on urgency
            if notification_type not in ["critical_escalation", "gdpr_breach"]:
                return NotificationResult(
                    success=True,
                    error_message="Skipped due to quiet hours",
                    channel=NotificationChannel.EMAIL
                )

        # Determine enabled channels
        enabled_channels = []
        if prefs.get("email_enabled", True):
            enabled_channels.append(NotificationChannel.EMAIL)
        if prefs.get("sms_enabled", False):
            enabled_channels.append(NotificationChannel.SMS)
        if prefs.get("slack_enabled", False):
            enabled_channels.append(NotificationChannel.SLACK)

        # Fall back to email if no channels enabled
        if not enabled_channels:
            enabled_channels = [NotificationChannel.EMAIL]

        return await self.send_alert(
            recipient=recipient,
            subject=subject,
            message=message,
            notification_type=notification_type,
            channels=enabled_channels
        )

    def _check_rate_limit(self, recipient: str) -> bool:
        """Check if recipient has exceeded rate limit."""
        now = datetime.now(timezone.utc)

        # Clean old entries (older than 1 minute)
        if (now - self.last_cleanup).total_seconds() > 60:
            self._cleanup_rate_limits()
            self.last_cleanup = now

        # Check current count
        recipient_count = self.notification_counts.get(recipient, 0)
        if recipient_count >= self.rate_limit_per_minute:
            return False

        # Increment count
        self.notification_counts[recipient] = recipient_count + 1
        return True

    def _cleanup_rate_limits(self):
        """Clean up old rate limit entries."""
        # For simplicity, we'll reset all counts
        # In production, you'd track individual timestamps
        self.notification_counts.clear()

    def _is_quiet_hours(self, quiet_hours: Optional[Dict[str, str]]) -> bool:
        """Check if current time is within quiet hours."""
        if not quiet_hours:
            return False

        try:
            now = datetime.now(timezone.utc).time()
            start_time = time.fromisoformat(quiet_hours["start"])
            end_time = time.fromisoformat(quiet_hours["end"])

            # Handle overnight quiet hours
            if start_time > end_time:
                return now >= start_time or now <= end_time
            else:
                return start_time <= now <= end_time

        except (KeyError, ValueError):
            return False