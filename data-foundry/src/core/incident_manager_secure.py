"""
Secure Incident Manager for Data Foundry

This is a security-enhanced version of the incident manager that includes:
- Authentication and authorization
- Input sanitization
- Secure database operations
- Configuration management

Import this module instead of incident_manager for production use.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from src.core.security.auth import (
    require_authentication, require_permission, SecurityContext,
    IncidentPermissions
)
from src.core.security.sanitization import InputSanitizer, InputValidator
from src.core.config.incident_config import config
from src.models.incident import (
    IncidentRecord, IncidentTimelineEntry, IncidentClassification,
    ContainmentResult, GDPRNotificationResult, DataSubjectNotificationRequirements,
    GDPRIncidentReport, PostIncidentReviewResult, IncidentMetrics,
    GDPRDeadlineStatus
)
from src.models.enums import (
    IncidentSeverity, IncidentStatus, IncidentType,
    NotificationChannel, ContainmentAction
)

logger = logging.getLogger(__name__)


class SecureIncidentManager:
    """
    Secure incident manager with authentication, authorization, and input validation.
    """

    def __init__(self, db_manager, audit_service, notification_service):
        """
        Initialize secure incident manager with dependencies.

        Args:
            db_manager: Database manager for persistence
            audit_service: Audit service for compliance logging
            notification_service: Notification service for alerts
        """
        self.db_manager = db_manager
        self.audit_service = audit_service
        self.notification_service = notification_service
        self.sanitizer = InputSanitizer()
        self.config = config

    @require_authentication
    @require_permission(IncidentPermissions.CREATE_INCIDENT)
    async def create_incident(
        self,
        title: str,
        description: str,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        reported_by: str,
        affected_systems: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        external_reference_id: Optional[str] = None,
        current_user: Optional[Dict[str, Any]] = None
    ) -> IncidentRecord:
        """
        Create a new incident record with security validation.

        Args:
            title: Brief descriptive title
            description: Detailed description
            incident_type: Type of incident
            severity: Severity level
            reported_by: Email of reporter
            affected_systems: List of affected systems
            metadata: Additional metadata
            external_reference_id: External reference ID
            current_user: Authenticated user context

        Returns:
            Created IncidentRecord

        Raises:
            PermissionError: If user lacks required permissions
            ValueError: If input validation fails
        """
        # Security context for logging
        security_ctx = SecurityContext(current_user)

        # Input validation and sanitization
        try:
            sanitized_title = self.sanitizer.sanitize_string(title, max_length=200)
            sanitized_description = self.sanitizer.sanitize_string(description, max_length=5000)
            sanitized_reported_by = self.sanitizer.sanitize_string(reported_by, max_length=255)

            if not InputValidator.validate_email(sanitized_reported_by):
                raise ValueError("Invalid email format for reported_by")

            if not InputValidator.validate_severity(severity.value):
                raise ValueError("Invalid severity level")

            if not InputValidator.validate_incident_type(incident_type.value):
                raise ValueError("Invalid incident type")

            # Validate and sanitize affected systems
            sanitized_systems = []
            if affected_systems:
                for system in affected_systems:
                    sanitized_systems.append(self.sanitizer.sanitize_string(system, max_length=100))

            # Sanitize metadata
            sanitized_metadata = {}
            if metadata:
                sanitized_metadata = self.sanitizer.sanitize_dict(metadata, max_length=1000)

            # Validate external reference ID
            sanitized_external_id = None
            if external_reference_id:
                sanitized_external_id = self.sanitizer.sanitize_string(
                    external_reference_id, max_length=100
                )

        except ValueError as e:
            security_ctx.log_access_attempt("create_incident", failed=True)
            raise ValueError(f"Input validation failed: {str(e)}")

        # Create incident record with sanitized data
        incident = IncidentRecord(
            title=sanitized_title,
            description=sanitized_description,
            incident_type=incident_type,
            severity=severity,
            reported_by=sanitized_reported_by,
            affected_systems=sanitized_systems,
            metadata=sanitized_metadata,
            external_reference_id=sanitized_external_id
        )

        # Store in database using parameterized queries
        try:
            db_incident = incident.to_database_model()
            incident_id = await self._secure_create_incident(db_incident)
        except Exception as e:
            logger.error(f"Database error creating incident: {e}")
            security_ctx.log_access_attempt("create_incident", failed=True)
            raise RuntimeError("Failed to create incident due to database error")

        # Add creation timeline entry
        incident.add_timeline_entry(IncidentTimelineEntry(
            timestamp=incident.created_at,
            action="Incident created",
            details=f"Incident reported by {sanitized_reported_by}",
            performed_by=current_user.get('user_id', 'system')
        ))

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_incident_created(
                    incident_id=incident.incident_id,
                    incident_type=incident_type.value,
                    severity=severity.value,
                    reported_by=sanitized_reported_by,
                    user_id=current_user.get('user_id'),
                    metadata={
                        "title": sanitized_title,
                        "affected_systems": sanitized_systems,
                        "external_reference_id": sanitized_external_id
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log incident creation: {e}")

        # Send notifications based on severity
        await self._send_initial_notifications(incident, current_user)

        security_ctx.log_access_attempt("create_incident", incident.incident_id, success=True)
        return incident

    @require_authentication
    @require_permission(IncidentPermissions.VIEW_INCIDENT)
    async def get_incident(
        self,
        incident_id: str,
        current_user: Optional[Dict[str, Any]] = None
    ) -> Optional[IncidentRecord]:
        """
        Retrieve an incident by ID with access control.

        Args:
            incident_id: Unique identifier for the incident
            current_user: Authenticated user context

        Returns:
            IncidentRecord if found, None otherwise

        Raises:
            PermissionError: If user lacks required permissions
        """
        security_ctx = SecurityContext(current_user)

        # Validate incident ID format
        if not InputValidator.validate_uuid(incident_id):
            security_ctx.log_access_attempt("get_incident", incident_id, success=False)
            raise ValueError("Invalid incident ID format")

        try:
            # Secure database query with parameterized input
            db_incident = await self._secure_get_incident_by_id(incident_id)

            if not db_incident:
                security_ctx.log_access_attempt("get_incident", incident_id, success=True)
                return None

            incident = IncidentRecord.from_database_model(db_incident)

            # Log access to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_incident_viewed(
                        incident_id=incident_id,
                        user_id=current_user.get('user_id'),
                        metadata={"access_granted": True}
                    )
                except Exception as e:
                    logger.warning(f"Failed to log incident access: {e}")

            security_ctx.log_access_attempt("get_incident", incident_id, success=True)
            return incident

        except Exception as e:
            logger.error(f"Database error retrieving incident {incident_id}: {e}")
            security_ctx.log_access_attempt("get_incident", incident_id, success=False)
            raise RuntimeError("Failed to retrieve incident due to database error")

    @require_authentication
    @require_permission(IncidentPermissions.UPDATE_INCIDENT)
    async def update_incident_status(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        reason: str,
        current_user: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update incident status with audit trail.

        Args:
            incident_id: Unique identifier for the incident
            new_status: New status to set
            reason: Reason for status change
            current_user: Authenticated user context

        Returns:
            True if update successful

        Raises:
            PermissionError: If user lacks required permissions
        """
        security_ctx = SecurityContext(current_user)

        # Input validation
        if not InputValidator.validate_uuid(incident_id):
            raise ValueError("Invalid incident ID format")

        sanitized_reason = self.sanitizer.sanitize_string(reason, max_length=1000)

        try:
            # Get current incident
            incident = await self.get_incident(incident_id, current_user)
            if not incident:
                raise ValueError("Incident not found")

            # Update status
            old_status = incident.status
            incident.update_status(new_status)

            # Add timeline entry
            incident.add_timeline_entry(IncidentTimelineEntry(
                timestamp=datetime.now(timezone.utc),
                action=f"Status updated from {old_status} to {new_status}",
                details=sanitized_reason,
                performed_by=current_user.get('user_id')
            ))

            # Update in database
            await self._secure_update_incident(incident)

            # Log to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_incident_updated(
                        incident_id=incident_id,
                        user_id=current_user.get('user_id'),
                        changes={"status": {"old": old_status, "new": new_status}},
                        reason=sanitized_reason
                    )
                except Exception as e:
                    logger.warning(f"Failed to log incident update: {e}")

            security_ctx.log_access_attempt("update_incident_status", incident_id, success=True)
            return True

        except Exception as e:
            logger.error(f"Error updating incident status: {e}")
            security_ctx.log_access_attempt("update_incident_status", incident_id, success=False)
            raise RuntimeError(f"Failed to update incident status: {str(e)}")

    @require_authentication
    @require_permission(IncidentPermissions.INITIATE_GDPR_NOTIFICATION)
    async def initiate_gdpr_breach_notification(
        self,
        incident_id: str,
        risk_assessment: str,
        affected_data_subjects_count: int,
        data_categories: List[str],
        contact_email: str,
        current_user: Optional[Dict[str, Any]] = None
    ) -> GDPRNotificationResult:
        """
        Initiate GDPR breach notification process with security validation.

        Args:
            incident_id: Unique identifier for the incident
            risk_assessment: Risk assessment details
            affected_data_subjects_count: Number of affected data subjects
            data_categories: Categories of personal data affected
            contact_email: Contact email for data subjects
            current_user: Authenticated user context

        Returns:
            GDPRNotificationResult with notification details

        Raises:
            PermissionError: If user lacks required permissions
        """
        security_ctx = SecurityContext(current_user)

        # Input validation and sanitization
        try:
            if not InputValidator.validate_uuid(incident_id):
                raise ValueError("Invalid incident ID format")

            if not InputValidator.validate_email(contact_email):
                raise ValueError("Invalid contact email format")

            sanitized_risk_assessment = self.sanitizer.sanitize_string(
                risk_assessment, max_length=2000
            )
            sanitized_data_categories = []
            for category in data_categories:
                sanitized_data_categories.append(
                    self.sanitizer.sanitize_string(category, max_length=100)
                )

            if affected_data_subjects_count < 0:
                raise ValueError("Affected data subjects count cannot be negative")

        except ValueError as e:
            security_ctx.log_access_attempt("initiate_gdpr_notification", incident_id, success=False)
            raise ValueError(f"Input validation failed: {str(e)}")

        try:
            # Get incident
            incident = await self.get_incident(incident_id, current_user)
            if not incident:
                raise ValueError("Incident not found")

            # Check if this is a data breach incident
            if incident.incident_type != IncidentType.DATA_BREACH:
                raise ValueError("GDPR notification only applies to data breach incidents")

            # Initiate notification workflow
            result = await self._initiate_secure_gdpr_notification(
                incident=incident,
                risk_assessment=sanitized_risk_assessment,
                affected_data_subjects_count=affected_data_subjects_count,
                data_categories=sanitized_data_categories,
                contact_email=contact_email,
                initiated_by=current_user.get('user_id')
            )

            # Log to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_gdpr_notification_initiated(
                        incident_id=incident_id,
                        user_id=current_user.get('user_id'),
                        authority_notified=result.authority_notified,
                        deadline=result.notification_deadline,
                        metadata={
                            "affected_subjects_count": affected_data_subjects_count,
                            "data_categories": sanitized_data_categories,
                            "contact_email": contact_email
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to log GDPR notification: {e}")

            security_ctx.log_access_attempt("initiate_gdpr_notification", incident_id, success=True)
            return result

        except Exception as e:
            logger.error(f"Error initiating GDPR notification: {e}")
            security_ctx.log_access_attempt("initiate_gdpr_notification", incident_id, success=False)
            raise RuntimeError(f"Failed to initiate GDPR notification: {str(e)}")

    # Private secure database methods
    async def _secure_create_incident(self, db_incident) -> str:
        """
        Securely create incident in database with parameterized queries.

        Args:
            db_incident: Database model instance

        Returns:
            Created incident ID
        """
        async with self.db_manager.transaction() as conn:
            # Use SQLModel's built-in parameterized query support
            result = await conn.execute(
                """
                INSERT INTO incidents (
                    incident_id, title, description, incident_type, severity,
                    status, reported_by, affected_systems, incident_metadata,
                    external_reference_id, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                ) RETURNING incident_id
                """,
                db_incident.incident_id,
                db_incident.title,
                db_incident.description,
                db_incident.incident_type,
                db_incident.severity,
                db_incident.status,
                db_incident.reported_by,
                db_incident.affected_systems,
                db_incident.incident_metadata,
                db_incident.external_reference_id,
                db_incident.created_at,
                db_incident.updated_at
            )
            return result.fetchone()[0]

    async def _secure_get_incident_by_id(self, incident_id: str):
        """
        Securely retrieve incident by ID with parameterized query.

        Args:
            incident_id: Incident ID to retrieve

        Returns:
            Database model instance or None
        """
        async with self.db_manager.transaction() as conn:
            result = await conn.execute(
                "SELECT * FROM incidents WHERE incident_id = $1",
                incident_id
            )
            row = result.fetchone()
            return row

    async def _secure_update_incident(self, incident: IncidentRecord) -> None:
        """
        Securely update incident in database with parameterized queries.

        Args:
            incident: Updated incident record
        """
        db_incident = incident.to_database_model()
        async with self.db_manager.transaction() as conn:
            await conn.execute(
                """
                UPDATE incidents SET
                    title = $2, description = $3, incident_type = $4,
                    severity = $5, status = $6, reported_by = $7,
                    affected_systems = $8, incident_metadata = $9,
                    external_reference_id = $10, updated_at = $11
                WHERE incident_id = $1
                """,
                db_incident.incident_id,
                db_incident.title,
                db_incident.description,
                db_incident.incident_type,
                db_incident.severity,
                db_incident.status,
                db_incident.reported_by,
                db_incident.affected_systems,
                db_incident.incident_metadata,
                db_incident.external_reference_id,
                db_incident.updated_at
            )

    async def _initiate_secure_gdpr_notification(
        self,
        incident: IncidentRecord,
        risk_assessment: str,
        affected_data_subjects_count: int,
        data_categories: List[str],
        contact_email: str,
        initiated_by: str
    ) -> GDPRNotificationResult:
        """
        Initiate secure GDPR breach notification process.

        Args:
            incident: Incident record
            risk_assessment: Risk assessment details
            affected_data_subjects_count: Number of affected data subjects
            data_categories: Categories of personal data affected
            contact_email: Contact email for data subjects
            initiated_by: User who initiated the notification

        Returns:
            GDPRNotificationResult with notification details
        """
        # Get GDPR configuration
        gdpr_config = self.config.get_gdpr_config()

        # Calculate deadline (72 hours from incident creation)
        notification_deadline = incident.created_at + timedelta(
            hours=gdpr_config['notification_deadline_hours']
        )

        # Notify supervisory authority
        authority_notified = False
        try:
            authority_email = gdpr_config['authority_email']
            await self.notification_service.send_email_notification(
                to_email=authority_email,
                subject=f"Data Breach Notification - {incident.incident_id}",
                message=self._generate_gdpr_authority_report(
                    incident, risk_assessment, affected_data_subjects_count,
                    data_categories, contact_email, notification_deadline
                )
            )
            authority_notified = True
        except Exception as e:
            logger.error(f"Failed to notify GDPR authority: {e}")

        return GDPRNotificationResult(
            notification_sent=authority_notified,
            notification_deadline=notification_deadline,
            authority_contact=gdpr_config['authority_email'],
            risk_level=incident.severity,
            affected_data_subjects_count=affected_data_subjects_count,
            data_categories_affected=data_categories,
            notification_timestamp=datetime.now(timezone.utc) if authority_notified else None
        )

    def _generate_gdpr_authority_report(
        self,
        incident: IncidentRecord,
        risk_assessment: str,
        affected_data_subjects_count: int,
        data_categories: List[str],
        contact_email: str,
        deadline: datetime
    ) -> str:
        """
        Generate GDPR breach notification report for authorities.

        Args:
            incident: Incident details
            risk_assessment: Risk assessment
            affected_data_subjects_count: Number of affected subjects
            data_categories: Affected data categories
            contact_email: Contact email
            deadline: Notification deadline

        Returns:
            Formatted report string
        """
        # Sanitize all report content
        report_template = f"""
DATA BREACH NOTIFICATION - GDPR Article 33

Incident ID: {incident.incident_id}
Date of Breach: {incident.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}
Notification Deadline: {deadline.strftime('%Y-%m-%d %H:%M:%S UTC')}

INCIDENT DETAILS:
- Title: {incident.title}
- Description: {incident.description}
- Severity: {incident.severity.value}
- Affected Systems: {', '.join(incident.affected_systems or [])}

RISK ASSESSMENT:
{risk_assessment}

IMPACT ASSESSMENT:
- Number of Data Subjects Affected: {affected_data_subjects_count}
- Categories of Personal Data: {', '.join(data_categories)}
- Likely Consequences: [To be assessed based on risk assessment]

CONTACT INFORMATION:
- Data Protection Officer: {contact_email}
- Reporting Organization: Data Foundry

This notification is sent in accordance with GDPR Article 33.
        """.strip()

        return self.sanitizer.sanitize_string(report_template, max_length=10000)

    async def _send_initial_notifications(
        self,
        incident: IncidentRecord,
        current_user: Dict[str, Any]
    ) -> None:
        """
        Send initial notifications for new incident with security.

        Args:
            incident: Created incident
            current_user: User who created the incident
        """
        try:
            # Send email notification if configured
            if self.config.smtp.server:
                await self.notification_service.send_email_notification(
                    to_email=self.config.security_team_email,
                    subject=f"New Security Incident: {incident.title}",
                    message=f"Incident {incident.incident_id} created with severity {incident.severity.value}"
                )

            # Send Slack notification if configured
            if self.config.slack.webhook_url:
                await self.notification_service.send_slack_notification(
                    message=f"🚨 New Security Incident: {incident.title} (Severity: {incident.severity.value})"
                )

        except Exception as e:
            logger.warning(f"Failed to send initial notifications: {e}")


# Export the secure manager for production use
SecureIncidentManager = SecureIncidentManager