"""
Incident Manager for Data Foundry

Implements comprehensive incident response system with GDPR compliance,
automatic classification, notification workflows, and containment procedures.

Follows TDD principles - implementation driven by comprehensive tests.

GDPR References:
- Article 33: Notification of personal data breach to supervisory authority (72 hours)
- Article 34: Communication of personal data breach to data subjects
- Article 32: Security of processing and incident response
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

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


class IncidentClassifier:
    """
    Automatic incident classification based on incident data and patterns.
    """

    def __init__(self):
        """Initialize incident classifier with patterns and rules."""
        self.classification_rules = {
            IncidentType.DATA_BREACH: {
                "keywords": ["unauthorized access", "data breach", "personal data", "compromised"],
                "severity_mapping": {
                    "critical": ["personal data", "special category data", "large scale"],
                    "high": ["customer data", "sensitive information", "multiple records"]
                }
            },
            IncidentType.SECURITY_INCIDENT: {
                "keywords": ["security", "attack", "malware", "vulnerability", "unauthorized"],
                "severity_mapping": {
                    "critical": ["system compromise", "privilege escalation", "persistent"],
                    "high": ["injection", "malware", "brute force", "multiple attempts"]
                }
            },
            IncidentType.SYSTEM_OUTAGE: {
                "keywords": ["down", "outage", "unavailable", "error", "failure"],
                "severity_mapping": {
                    "critical": ["complete outage", "all services", "production down"],
                    "high": ["partial outage", "multiple services", "degraded performance"]
                }
            },
            IncidentType.PERFORMANCE_DEGRADATION: {
                "keywords": ["slow", "performance", "response time", "latency", "degradation"],
                "severity_mapping": {
                    "high": ["response time > 5s", "high error rate", "significant impact"],
                    "medium": ["response time > 2s", "moderate impact"],
                    "low": ["minor slowdown", "limited impact"]
                }
            }
        }

    async def classify_incident(self, incident_data: Dict[str, Any]) -> IncidentClassification:
        """
        Automatically classify incident based on provided data.

        Args:
            incident_data: Incident description and context

        Returns:
            IncidentClassification with type, severity, and confidence
        """
        description = incident_data.get("description", "").lower()
        evidence = incident_data.get("evidence", {})
        metrics = incident_data.get("metrics", {})

        # Determine incident type
        incident_type = self._determine_incident_type(description, evidence, metrics)
        severity = self._determine_severity(incident_type, description, evidence, metrics)
        confidence = self._calculate_confidence(incident_type, severity, incident_data)
        attack_pattern = self._identify_attack_pattern(incident_type, description, evidence)
        suggested_actions = self._suggest_actions(incident_type, severity, attack_pattern)

        return IncidentClassification(
            incident_type=incident_type,
            severity=severity,
            confidence=confidence,
            attack_pattern=attack_pattern,
            suggested_actions=suggested_actions
        )

    def _determine_incident_type(self, description: str, evidence: Dict, metrics: Dict) -> IncidentType:
        """Determine incident type based on keywords and evidence."""
        type_scores = {}

        for incident_type, rules in self.classification_rules.items():
            score = 0
            keywords = rules["keywords"]

            # Check keyword matches in description
            for keyword in keywords:
                if keyword in description:
                    score += 1

            # Check evidence indicators
            if incident_type == IncidentType.DATA_BREACH and evidence.get("data_access"):
                score += 2
            elif incident_type == IncidentType.SECURITY_INCIDENT and evidence.get("failed_attempts"):
                score += 2
            elif incident_type == IncidentType.PERFORMANCE_DEGRADATION and metrics.get("response_time"):
                score += 2

            type_scores[incident_type] = score

        # Return type with highest score, default to SECURITY_INCIDENT
        if not type_scores or max(type_scores.values()) == 0:
            return IncidentType.SECURITY_INCIDENT

        return max(type_scores, key=type_scores.get)

    def _determine_severity(self, incident_type: IncidentType, description: str,
                          evidence: Dict, metrics: Dict) -> IncidentSeverity:
        """Determine severity based on incident characteristics."""
        if incident_type not in self.classification_rules:
            return IncidentSeverity.MEDIUM

        severity_rules = self.classification_rules[incident_type]["severity_mapping"]

        # Check for critical indicators
        for indicator in severity_rules.get("critical", []):
            if indicator.lower() in description or indicator.lower() in str(evidence):
                return IncidentSeverity.CRITICAL

        # Check for high indicators
        for indicator in severity_rules.get("high", []):
            if indicator.lower() in description or indicator.lower() in str(evidence):
                return IncidentSeverity.HIGH

        # Check for medium indicators
        if "medium" in severity_rules:
            for indicator in severity_rules["medium"]:
                if indicator.lower() in description:
                    return IncidentSeverity.MEDIUM

        return IncidentSeverity.LOW

    def _calculate_confidence(self, incident_type: IncidentType, severity: IncidentSeverity,
                            incident_data: Dict) -> float:
        """Calculate confidence level for classification."""
        confidence = 0.5  # Base confidence

        description = incident_data.get("description", "").lower()
        evidence = incident_data.get("evidence", {})

        # Increase confidence based on evidence quality
        if evidence and len(evidence) > 0:
            confidence += 0.2

        # Increase confidence for clear indicators
        if incident_type == IncidentType.DATA_BREACH and "personal data" in description:
            confidence += 0.2
        elif incident_type == IncidentType.SECURITY_INCIDENT and "attack" in description:
            confidence += 0.2

        # Cap at 0.95 (never 100% certain)
        return min(confidence, 0.95)

    def _identify_attack_pattern(self, incident_type: IncidentType, description: str,
                               evidence: Dict) -> Optional[str]:
        """Identify specific attack patterns for security incidents."""
        if incident_type != IncidentType.SECURITY_INCIDENT:
            return None

        description_lower = description.lower()

        if "brute force" in description_lower or evidence.get("failed_attempts"):
            return "brute_force_attack"
        elif "phishing" in description_lower:
            return "phishing_attack"
        elif "malware" in description_lower or "virus" in description_lower:
            return "malware_infection"
        elif "injection" in description_lower or "sql" in description_lower:
            return "code_injection"
        elif "denial of service" in description_lower or "dos" in description_lower:
            return "denial_of_service"

        return "unknown_attack_pattern"

    def _suggest_actions(self, incident_type: IncidentType, severity: IncidentSeverity,
                        attack_pattern: Optional[str]) -> List[str]:
        """Suggest immediate actions based on incident classification."""
        actions = []

        if incident_type == IncidentType.DATA_BREACH:
            actions.extend([
                "Identify and contain data breach",
                "Assess scope of affected data",
                "Document breach details for GDPR compliance"
            ])
        elif incident_type == IncidentType.SECURITY_INCIDENT:
            if attack_pattern == "brute_force_attack":
                actions.append("Block source IP addresses")
            if attack_pattern == "malware_infection":
                actions.append("Isolate affected systems")
            actions.extend([
                "Investigate security incident",
                "Check for additional compromises"
            ])

        if severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]:
            actions.append("Initiate emergency response protocol")
            actions.append("Notify security team leadership")

        return actions


class IncidentManager:
    """
    Incident management business logic with GDPR compliance.

    Handles the complete incident response lifecycle from detection through
    closure, including automatic classification, notifications, and containment.
    """

    def __init__(self, db_manager, audit_service, notification_service):
        """
        Initialize incident manager with required services.

        Args:
            db_manager: Database manager for incident persistence
            audit_service: Audit service for compliance logging
            notification_service: Notification service for alerts
        """
        self.db_manager = db_manager
        self.audit_service = audit_service
        self.notification_service = notification_service
        self.classifier = IncidentClassifier()

        # Configuration for automatic responses
        self.auto_containment_enabled = True
        self.escalation_thresholds = {
            IncidentSeverity.CRITICAL: {"escalate_immediately": True, "notify_levels": ["executive", "dpo", "security_team"]},
            IncidentSeverity.HIGH: {"escalate_immediately": False, "notify_levels": ["security_team", "dpo"]},
            IncidentSeverity.MEDIUM: {"escalate_immediately": False, "notify_levels": ["security_team"]},
            IncidentSeverity.LOW: {"escalate_immediately": False, "notify_levels": []}
        }

    async def create_incident(
        self,
        title: str,
        description: str,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        reported_by: str,
        affected_systems: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        external_reference_id: Optional[str] = None
    ) -> IncidentRecord:
        """
        Create a new incident record with validation and notifications.

        Args:
            title: Brief descriptive title
            description: Detailed description
            incident_type: Type of incident
            severity: Severity level
            reported_by: Email of reporter
            affected_systems: List of affected systems
            metadata: Additional metadata
            external_reference_id: External reference ID

        Returns:
            Created IncidentRecord
        """
        # Validate input
        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        if not description or not description.strip():
            raise ValueError("Description cannot be empty")

        # Create incident record
        incident = IncidentRecord(
            title=title,
            description=description,
            incident_type=incident_type,
            severity=severity,
            reported_by=reported_by,
            affected_systems=affected_systems,
            metadata=metadata or {},
            external_reference_id=external_reference_id
        )

        # Store in database
        db_incident = incident.to_database_model()
        incident_id = await self.db_manager.create_incident(db_incident)

        # Add creation timeline entry
        incident.add_timeline_entry(IncidentTimelineEntry(
            timestamp=incident.created_at,
            action="Incident created",
            details=f"Incident reported by {reported_by}",
            performed_by=reported_by
        ))

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_incident_created(
                    incident_id=incident.incident_id,
                    incident_type=incident_type.value,
                    severity=severity.value,
                    reported_by=reported_by,
                    metadata={
                        "title": title,
                        "affected_systems": affected_systems or [],
                        "external_reference_id": external_reference_id
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log incident creation: {e}")

        # Send notifications based on severity
        await self._send_initial_notifications(incident)

        return incident

    async def create_incident_with_classification(
        self,
        title: str,
        description: str,
        reported_by: str,
        affected_systems: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> IncidentRecord:
        """
        Create incident with automatic classification.

        Args:
            title: Brief descriptive title
            description: Detailed description
            reported_by: Email of reporter
            affected_systems: List of affected systems
            metadata: Additional metadata

        Returns:
            Created and classified IncidentRecord
        """
        # Prepare data for classification
        incident_data = {
            "description": description,
            "evidence": metadata.get("evidence", {}) if metadata else {},
            "metrics": metadata.get("metrics", {}) if metadata else {},
            "affected_systems": affected_systems or []
        }

        # Classify incident
        classification = await self.classifier.classify_incident(incident_data)

        # Create incident with classification
        incident = await self.create_incident(
            title=title,
            description=f"{description} [AUTO-CLASSIFIED: {classification.incident_type.value}]",
            incident_type=classification.incident_type,
            severity=classification.severity,
            reported_by=reported_by,
            affected_systems=affected_systems,
            metadata={
                **(metadata or {}),
                "auto_classification": {
                    "incident_type": classification.incident_type.value,
                    "severity": classification.severity.value,
                    "confidence": classification.confidence,
                    "attack_pattern": classification.attack_pattern,
                    "suggested_actions": classification.suggested_actions
                }
            }
        )

        return incident

    async def update_incident_status(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        updated_by: str,
        notes: Optional[str] = None
    ) -> IncidentRecord:
        """
        Update incident status with timeline tracking.

        Args:
            incident_id: Incident identifier
            new_status: New status to set
            updated_by: Email of person updating status
            notes: Optional notes about status change

        Returns:
            Updated IncidentRecord
        """
        # Get current incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)
        old_status = incident.status

        # Update status
        incident.update_status(new_status)

        # Add timeline entry
        details = f"Status changed from {old_status} to {new_status}"
        if notes:
            details += f". Notes: {notes}"

        incident.add_timeline_entry(IncidentTimelineEntry(
            timestamp=datetime.now(timezone.utc),
            action="Status updated",
            details=details,
            performed_by=updated_by
        ))

        # Update in database
        await self.db_manager.update_incident(incident.to_database_model())

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_incident_updated(
                    incident_id=incident_id,
                    update_type="status_change",
                    updated_by=updated_by,
                    old_value=old_status.value,
                    new_value=new_status.value,
                    metadata={"notes": notes}
                )
            except Exception as e:
                logger.warning(f"Failed to log incident status update: {e}")

        return incident

    async def assign_incident(
        self,
        incident_id: str,
        assignee: str,
        assigned_by: str,
        reason: str
    ) -> IncidentRecord:
        """
        Assign incident to personnel.

        Args:
            incident_id: Incident identifier
            assignee: Email of person to assign
            assigned_by: Email of person making assignment
            reason: Reason for assignment

        Returns:
            Updated IncidentRecord
        """
        # Get current incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)

        # Assign incident
        incident.assign_to(assignee, assigned_by, reason)

        # Update in database
        await self.db_manager.update_incident(incident.to_database_model())

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_incident_updated(
                    incident_id=incident_id,
                    update_type="assignment",
                    updated_by=assigned_by,
                    new_value=assignee,
                    metadata={"reason": reason}
                )
            except Exception as e:
                logger.warning(f"Failed to log incident assignment: {e}")

        # Send notification to assignee
        await self.notification_service.send_alert(
            recipient=assignee,
            subject=f"Incident Assigned: {incident.title}",
            message=f"You have been assigned to incident {incident.incident_id}: {incident.title}. Reason: {reason}",
            notification_type="assignment"
        )

        return incident

    async def close_incident(
        self,
        incident_id: str,
        closed_by: str,
        closure_details: Dict[str, Any]
    ) -> IncidentRecord:
        """
        Close incident with validation and documentation.

        Args:
            incident_id: Incident identifier
            closed_by: Email of person closing incident
            closure_details: Details about incident closure

        Returns:
            Closed IncidentRecord
        """
        # Get current incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)

        # Validate closure requirements
        if not closure_details or 'root_cause' not in closure_details:
            raise ValueError("Closure details must include root cause analysis")

        # Close incident
        incident.close_incident(closed_by, closure_details)

        # Update in database
        await self.db_manager.update_incident(incident.to_database_model())

        # Log to audit trail
        if self.audit_service:
            try:
                await self.audit_service.log_incident_closed(
                    incident_id=incident_id,
                    closed_by=closed_by,
                    closure_details=closure_details
                )
            except Exception as e:
                logger.warning(f"Failed to log incident closure: {e}")

        return incident

    async def search_incidents(
        self,
        severity: Optional[IncidentSeverity] = None,
        status: Optional[IncidentStatus] = None,
        incident_type: Optional[IncidentType] = None,
        date_range: Optional[Dict[str, datetime]] = None,
        assignee: Optional[str] = None,
        **kwargs
    ) -> List[IncidentRecord]:
        """
        Search incidents with filtering criteria.

        Args:
            severity: Filter by severity level
            status: Filter by status
            incident_type: Filter by incident type
            date_range: Date range filter
            assignee: Filter by assignee
            **kwargs: Additional filter criteria

        Returns:
            List of matching IncidentRecord instances
        """
        # Build search criteria
        search_criteria = {}
        if severity:
            search_criteria["severity"] = severity
        if status:
            search_criteria["status"] = status
        if incident_type:
            search_criteria["incident_type"] = incident_type
        if date_range:
            search_criteria.update(date_range)
        if assignee:
            search_criteria["assignee"] = assignee

        search_criteria.update(kwargs)

        # Search in database
        db_incidents = await self.db_manager.list_incidents(**search_criteria)

        # Convert to domain models
        incidents = [IncidentRecord.from_database_model(db_inc) for db_inc in db_incidents]

        return incidents

    async def get_incident_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> IncidentMetrics:
        """
        Calculate incident metrics for reporting.

        Args:
            start_date: Start of reporting period
            end_date: End of reporting period

        Returns:
            IncidentMetrics with calculated values
        """
        # Get all incidents in date range
        incidents = await self.search_incidents(
            date_range={"start": start_date, "end": end_date}
        )

        # Calculate metrics
        total_incidents = len(incidents)
        by_severity = {severity: 0 for severity in IncidentSeverity}
        by_type = {incident_type: 0 for incident_type in IncidentType}

        resolution_times = []
        gdpr_compliant_count = 0

        for incident in incidents:
            # Count by severity and type
            by_severity[incident.severity] += 1
            by_type[incident.incident_type] += 1

            # Calculate resolution time
            if incident.closed_at:
                resolution_time = incident.closed_at - incident.created_at
                resolution_times.append(resolution_time)

            # Check GDPR compliance for data breaches
            if incident.incident_type == IncidentType.DATA_BREACH:
                if incident.gdpr_breach_notified or not incident.is_gdpr_deadline_passed():
                    gdpr_compliant_count += 1

        data_breach_count = by_type[IncidentType.DATA_BREACH]
        gdpr_compliance_rate = (gdpr_compliant_count / data_breach_count) if data_breach_count > 0 else 1.0

        # Calculate average resolution time
        avg_resolution_time = None
        if resolution_times:
            avg_resolution_time = sum(resolution_times, timedelta(0)) / len(resolution_times)

        return IncidentMetrics(
            total_incidents=total_incidents,
            by_severity=by_severity,
            by_type=by_type,
            average_resolution_time=avg_resolution_time,
            gdpr_compliance_rate=gdpr_compliance_rate
        )

    async def _send_initial_notifications(self, incident: IncidentRecord) -> None:
        """Send initial notifications based on incident severity and type."""
        severity_config = self.escalation_thresholds[incident.severity]

        # Send to configured notification levels
        for level in severity_config["notify_levels"]:
            await self.notification_service.send_alert(
                recipient=f"{level}@company.com",
                subject=f"Security Incident: {incident.title}",
                message=f"Incident {incident.incident_id} reported:\n\n"
                        f"Type: {incident.incident_type.value}\n"
                        f"Severity: {incident.severity.value}\n"
                        f"Description: {incident.description}\n"
                        f"Reported by: {incident.reported_by}",
                notification_type=level
            )

        # Immediate escalation for critical incidents
        if severity_config["escalate_immediately"]:
            await self.notification_service.send_alert(
                recipient="executive@company.com",
                subject=f"CRITICAL: Immediate Response Required - {incident.title}",
                message=f"CRITICAL incident requires immediate attention:\n\n"
                        f"Incident ID: {incident.incident_id}\n"
                        f"Type: {incident.incident_type.value}\n"
                        f"Severity: {incident.severity.value}\n"
                        f"Description: {incident.description}",
                notification_type="critical_escalation"
            )

    async def initiate_gdpr_breach_notification(
        self,
        incident_id: str,
        data_subjects_affected: int,
        data_types_involved: List[str],
        contact_email: str
    ) -> GDPRNotificationResult:
        """
        Initiate GDPR breach notification workflow.

        Args:
            incident_id: Incident identifier
            data_subjects_affected: Number of affected data subjects
            data_types_involved: Types of personal data involved
            contact_email: Contact email for notifications

        Returns:
            GDPRNotificationResult with notification status
        """
        try:
            # Get incident
            db_incident = await self.db_manager.get_incident(incident_id)
            if not db_incident:
                raise ValueError(f"Incident {incident_id} not found")

            incident = IncidentRecord.from_database_model(db_incident)

            # Verify this is a data breach
            if incident.incident_type != IncidentType.DATA_BREACH:
                raise ValueError("GDPR notification only applies to data breaches")

            # Prepare notification data
            notification_data = {
                "incident_id": incident_id,
                "data_subjects_affected": data_subjects_affected,
                "data_types_involved": data_types_involved,
                "contact_email": contact_email,
                "notification_timestamp": datetime.now(timezone.utc).isoformat(),
                "deadline": incident.get_gdpr_notification_deadline().isoformat()
            }

            # Send notification to supervisory authority
            await self.notification_service.send_alert(
                recipient="supervisory_authority@privacy.gov",
                subject=f"GDPR Data Breach Notification - {incident_id}",
                message=f"Data breach notification under GDPR Article 33:\n\n"
                        f"Incident ID: {incident_id}\n"
                        f"Data subjects affected: {data_subjects_affected}\n"
                        f"Data types involved: {', '.join(data_types_involved)}\n"
                        f"Contact: {contact_email}",
                notification_type="gdpr_supervisory_authority",
                metadata=notification_data
            )

            # Update incident record
            incident.gdpr_breach_notified = True
            incident.gdpr_breach_notified_at = datetime.now(timezone.utc)
            await self.db_manager.update_incident(incident.to_database_model())

            # Add timeline entry
            incident.add_timeline_entry(IncidentTimelineEntry(
                timestamp=datetime.now(timezone.utc),
                action="GDPR breach notification sent",
                details=f"Notification sent to supervisory authority. {data_subjects_affected} data subjects affected.",
                performed_by="dpo@company.com"
            ))

            return GDPRNotificationResult(
                success=True,
                supervisory_authority_notified=True,
                notification_deadline=incident.get_gdpr_notification_deadline(),
                notification_timestamp=datetime.now(timezone.utc)
            )

        except Exception as e:
            logger.error(f"Failed to initiate GDPR breach notification: {e}")
            return GDPRNotificationResult(
                success=False,
                supervisory_authority_notified=False,
                notification_deadline=datetime.now(timezone.utc) + timedelta(hours=72),
                error_message=str(e)
            )

    async def apply_automatic_containment(self, incident_id: str) -> ContainmentResult:
        """
        Apply automatic containment measures for security incidents.

        Args:
            incident_id: Incident identifier

        Returns:
            ContainmentResult with actions taken
        """
        try:
            # Get incident
            db_incident = await self.db_manager.get_incident(incident_id)
            if not db_incident:
                raise ValueError(f"Incident {incident_id} not found")

            incident = IncidentRecord.from_database_model(db_incident)

            # Determine containment actions based on incident type and metadata
            actions_taken = []
            timestamp = datetime.now(timezone.utc)

            if incident.incident_type == IncidentType.SECURITY_INCIDENT:
                metadata = incident.metadata

                # Block malicious IPs
                if metadata.get("source_ip"):
                    actions_taken.append(ContainmentAction.BLOCK_IP)

                # Disable compromised accounts
                if metadata.get("compromised_accounts"):
                    actions_taken.append(ContainmentAction.DISABLE_ACCOUNT)

                # Revoke sessions for authentication breaches
                if "authentication" in incident.description.lower():
                    actions_taken.append(ContainmentAction.REVOKE_SESSIONS)

                # Isolate affected systems
                if incident.affected_systems:
                    actions_taken.append(ContainmentAction.ISOLATE_SYSTEM)

            elif incident.incident_type == IncidentType.DATA_BREACH:
                # For data breaches, focus on access control
                actions_taken.extend([
                    ContainmentAction.REVOKE_SESSIONS,
                    ContainmentAction.ROTATE_CREDENTIALS
                ])

            # Execute containment actions
            for action in actions_taken:
                await self._execute_containment_action(action, incident)

            # Add timeline entry
            incident.add_timeline_entry(IncidentTimelineEntry(
                timestamp=timestamp,
                action="Automatic containment applied",
                details=f"Applied automatic containment actions: {[a.value for a in actions_taken]}",
                performed_by="system"
            ))

            return ContainmentResult(
                success=True,
                actions_taken=actions_taken,
                timestamp=timestamp
            )

        except Exception as e:
            logger.error(f"Failed to apply automatic containment: {e}")
            return ContainmentResult(
                success=False,
                actions_taken=[],
                timestamp=datetime.now(timezone.utc),
                error_message=str(e)
            )

    async def _execute_containment_action(self, action: ContainmentAction, incident: IncidentRecord) -> None:
        """Execute a specific containment action."""
        # This would integrate with actual systems to execute containment
        # For now, we'll simulate the action
        logger.info(f"Executing containment action {action.value} for incident {incident.incident_id}")

    async def check_gdpr_notification_deadline(self, incident_id: str) -> GDPRDeadlineStatus:
        """
        Check GDPR notification deadline status for a data breach.

        Args:
            incident_id: Incident identifier

        Returns:
            GDPRDeadlineStatus with deadline information
        """
        # Get incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)

        if incident.incident_type != IncidentType.DATA_BREACH:
            return GDPRDeadlineStatus(
                hours_remaining=None,
                deadline_passed=False,
                supervisory_authority_notified=False
            )

        deadline = incident.get_gdpr_notification_deadline()
        if not deadline:
            return GDPRDeadlineStatus(
                hours_remaining=None,
                deadline_passed=False,
                supervisory_authority_notified=False
            )

        now = datetime.now(timezone.utc)
        hours_remaining = (deadline - now).total_seconds() / 3600

        return GDPRDeadlineStatus(
            hours_remaining=max(0, hours_remaining),
            deadline_passed=incident.is_gdpr_deadline_passed(),
            supervisory_authority_notified=incident.gdpr_breach_notified
        )

    async def assess_data_subject_notification_requirements(
        self,
        incident_id: str
    ) -> DataSubjectNotificationRequirements:
        """
        Assess if data subject notification is required under GDPR.

        Args:
            incident_id: Incident identifier

        Returns:
            DataSubjectNotificationRequirements with assessment
        """
        # Get incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)

        if incident.incident_type != IncidentType.DATA_BREACH:
            return DataSubjectNotificationRequirements(
                requires_notification=False,
                risk_level="low"
            )

        # Assess risk based on incident data
        metadata = incident.metadata
        requires_notification = False
        risk_level = "low"
        notification_timeline = None

        # High risk indicators
        high_risk_indicators = [
            metadata.get("high_risk_to_data_subjects", False),
            metadata.get("special_category_data", False),
            metadata.get("large_scale_breach", False)
        ]

        if any(high_risk_indicators):
            requires_notification = True
            risk_level = "high"
            notification_timeline = "Without undue delay"
        elif metadata.get("personal_data_affected", False):
            # Medium risk if personal data affected but no high-risk indicators
            requires_notification = metadata.get("data_subjects_count", 0) > 100
            risk_level = "medium" if requires_notification else "low"
            notification_timeline = "Within 72 hours if high risk determined"

        requirements = {
            "assessment_basis": metadata,
            "affected_data_subjects": metadata.get("data_subjects_count", 0),
            "data_types_involved": metadata.get("data_types_involved", []),
            "mitigation_measures": metadata.get("mitigation_measures", [])
        }

        return DataSubjectNotificationRequirements(
            requires_notification=requires_notification,
            risk_level=risk_level,
            notification_timeline=notification_timeline,
            requirements=requirements
        )

    async def generate_gdpr_incident_report(self, incident_id: str) -> GDPRIncidentReport:
        """
        Generate comprehensive GDPR incident report.

        Args:
            incident_id: Incident identifier

        Returns:
            GDPRIncidentReport with complete incident documentation
        """
        # Get incident
        db_incident = await self.db_manager.get_incident(incident_id)
        if not db_incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident = IncidentRecord.from_database_model(db_incident)

        # Get timeline entries
        db_timeline = await self.db_manager.get_incident_timeline(incident_id)
        timeline = [IncidentTimelineEntry(
            timestamp=entry.timestamp,
            action=entry.action,
            details=entry.details,
            performed_by=entry.performed_by,
            attachments=entry.attachments
        ) for entry in db_timeline]

        # Prepare incident details
        incident_details = {
            "incident_id": incident.incident_id,
            "title": incident.title,
            "description": incident.description,
            "incident_type": incident.incident_type.value,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "reported_by": incident.reported_by,
            "created_at": incident.created_at.isoformat(),
            "affected_systems": incident.affected_systems,
            "external_reference_id": incident.external_reference_id
        }

        # Prepare impact assessment
        impact_assessment = incident.impact_assessment or {
            "assessment_status": "pending",
            "notes": "Impact assessment not yet completed"
        }

        # Compile measures taken
        measures_taken = []
        for entry in timeline:
            if "containment" in entry.action.lower() or "remediation" in entry.action.lower():
                measures_taken.append(entry.action)

        return GDPRIncidentReport(
            incident_details=incident_details,
            timeline=timeline,
            impact_assessment=impact_assessment,
            measures_taken=measures_taken,
            documentation_timestamp=datetime.now(timezone.utc)
        )

    async def conduct_post_incident_review(
        self,
        incident_id: str,
        reviewer: str,
        review_findings: Dict[str, Any]
    ) -> PostIncidentReviewResult:
        """
        Conduct post-incident review and document lessons learned.

        Args:
            incident_id: Incident identifier
            reviewer: Email of person conducting review
            review_findings: Detailed review findings

        Returns:
            PostIncidentReviewResult with review status
        """
        try:
            # Get incident
            db_incident = await self.db_manager.get_incident(incident_id)
            if not db_incident:
                raise ValueError(f"Incident {incident_id} not found")

            incident = IncidentRecord.from_database_model(db_incident)

            # Validate review findings
            required_sections = ["root_cause_analysis", "timeline_gaps", "process_improvements"]
            for section in required_sections:
                if section not in review_findings:
                    raise ValueError(f"Review findings must include {section}")

            # Add review timeline entry
            incident.add_timeline_entry(IncidentTimelineEntry(
                timestamp=datetime.now(timezone.utc),
                action="Post-incident review completed",
                details=f"Review conducted by {reviewer}. Key findings: {len(review_findings)} sections analyzed.",
                performed_by=reviewer
            ))

            # Create action items from findings
            action_items_created = False
            if "process_improvements" in review_findings and review_findings["process_improvements"]:
                action_items_created = True

            # Determine if follow-up is required
            follow_up_required = (
                len(review_findings.get("technical_improvements", [])) > 0 or
                len(review_findings.get("training_needs", [])) > 0
            )

            # Update incident with review findings
            incident.metadata["post_incident_review"] = {
                "reviewer": reviewer,
                "review_date": datetime.now(timezone.utc).isoformat(),
                "findings": review_findings
            }
            await self.db_manager.update_incident(incident.to_database_model())

            # Log to audit trail
            if self.audit_service:
                try:
                    await self.audit_service.log_incident_updated(
                        incident_id=incident_id,
                        update_type="post_incident_review",
                        updated_by=reviewer,
                        metadata={"review_sections": list(review_findings.keys())}
                    )
                except Exception as e:
                    logger.warning(f"Failed to log post-incident review: {e}")

            return PostIncidentReviewResult(
                review_completed=True,
                lessons_learned_documented=True,
                action_items_created=action_items_created,
                follow_up_required=follow_up_required,
                review_findings=review_findings
            )

        except Exception as e:
            logger.error(f"Failed to conduct post-incident review: {e}")
            return PostIncidentReviewResult(
                review_completed=False,
                lessons_learned_documented=False,
                action_items_created=False,
                follow_up_required=False,
                review_findings={"error": str(e)}
            )