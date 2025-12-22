"""
Incident Response Data Models for Data Foundry

This module defines the SQLModel and domain models for incident response,
providing:
- GDPR-compliant incident tracking and management
- Comprehensive incident timeline tracking
- Automatic escalation and notification support
- Post-incident review and lessons learned functionality
- Audit trail capabilities for compliance
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from pydantic import field_validator, EmailStr
from sqlalchemy import Column, String, DateTime, Text, JSON, Index, Integer
from sqlmodel import SQLModel, Field

from src.models.enums import (
    IncidentSeverity, IncidentStatus, IncidentType,
    NotificationChannel, ContainmentAction
)


class IncidentRecordDB(SQLModel, table=True):
    """
    Incident record database model for GDPR-compliant incident tracking.

    Stores incident records with full audit trail and timeline support.
    Indexed for efficient queries on common patterns (status, severity, type).
    """

    __tablename__ = "incident_records"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core incident fields (required)
    incident_id: str = Field(
        unique=True,
        index=True,
        description="Unique incident identifier for tracking"
    )
    title: str = Field(description="Brief descriptive title of the incident")
    description: str = Field(
        sa_column=Column(Text),
        description="Detailed description of the incident"
    )
    incident_type: IncidentType = Field(
        index=True,
        description="Type of incident (data breach, security, system outage, etc.)"
    )
    severity: IncidentSeverity = Field(
        index=True,
        description="Severity level of the incident"
    )
    status: IncidentStatus = Field(
        default=IncidentStatus.OPEN,
        index=True,
        description="Current status of the incident"
    )
    reported_by: str = Field(description="Email of person who reported the incident")

    # Incident lifecycle fields
    assignee: Optional[str] = Field(
        default=None,
        index=True,
        description="Email of person assigned to handle the incident"
    )
    assigned_by: Optional[str] = Field(
        default=None,
        description="Email of person who assigned the incident"
    )
    assigned_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When the incident was assigned"
    )

    # Incident resolution fields
    closed_by: Optional[str] = Field(
        default=None,
        description="Email of person who closed the incident"
    )
    closed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When the incident was closed"
    )
    closure_details: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Details about incident closure and resolution"
    )

    # Incident metadata and context
    affected_systems: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="List of affected systems or components"
    )
    impact_assessment: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Impact assessment details (GDPR compliance)"
    )
    incident_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional metadata about the incident"
    )

    # External references and tracking
    external_reference_id: Optional[str] = Field(
        default=None,
        index=True,
        description="External reference ID (e.g., ticket system)"
    )
    parent_incident_id: Optional[str] = Field(
        default=None,
        index=True,
        description="Parent incident ID if this is a sub-incident"
    )

    # GDPR compliance tracking
    gdpr_breach_notified: bool = Field(
        default=False,
        description="Whether supervisory authority has been notified"
    )
    gdpr_breach_notified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When GDPR breach notification was sent"
    )
    gdpr_notification_deadline: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="72-hour deadline for GDPR breach notification"
    )
    data_subjects_notified: bool = Field(
        default=False,
        description="Whether data subjects have been notified"
    )

    # Timestamps for audit trail
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="When this incident record was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="When this incident record was last updated"
    )

    # Table indexes for performance
    __table_args__ = (
        Index('idx_incident_severity_status', 'severity', 'status'),
        Index('idx_incident_type_status', 'incident_type', 'status'),
        Index('idx_incident_created_at', 'created_at'),
        Index('idx_incident_assignee', 'assignee'),
        Index('idx_incident_reported_by', 'reported_by'),
    )

    @field_validator('title', 'description', 'reported_by')
    @classmethod
    def validate_required_fields(cls, v, info):
        """Validate that required fields are not empty"""
        field_name = info.field_name
        if field_name == 'reported_by':
            # Email validation for reported_by
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not v or not re.match(email_pattern, v):
                raise ValueError("Reported by must be a valid email address")
        else:
            if not v or (isinstance(v, str) and v.strip() == ""):
                raise ValueError(f"{field_name.replace('_', ' ').title()} cannot be empty")
        return v.strip() if isinstance(v, str) else v

    @field_validator('assignee', 'assigned_by', 'closed_by')
    @classmethod
    def validate_optional_emails(cls, v):
        """Validate optional email fields"""
        if v:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError("Must be a valid email address")
        return v

    def update_status(self, new_status: IncidentStatus) -> None:
        """
        Update incident status with timestamp tracking.

        Args:
            new_status: New status to set
        """
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

    def get_gdpr_notification_deadline(self) -> datetime:
        """
        Calculate GDPR 72-hour breach notification deadline.

        Returns:
            datetime: Deadline for notification to supervisory authority
        """
        if self.incident_type == IncidentType.DATA_BREACH:
            if not self.gdpr_notification_deadline:
                self.gdpr_notification_deadline = self.created_at + timedelta(hours=72)
            return self.gdpr_notification_deadline
        return None

    def is_gdpr_deadline_passed(self) -> bool:
        """
        Check if GDPR 72-hour notification deadline has passed.

        Returns:
            bool: True if deadline has passed
        """
        if self.incident_type != IncidentType.DATA_BREACH:
            return False

        deadline = self.get_gdpr_notification_deadline()
        if not deadline:
            return False

        return datetime.now(timezone.utc) > deadline

    def update_impact_assessment(self, assessment: Dict[str, Any]) -> None:
        """
        Update impact assessment for GDPR compliance.

        Args:
            assessment: Impact assessment details
        """
        self.impact_assessment = assessment
        self.updated_at = datetime.now(timezone.utc)

    def to_domain_model(self):
        """
        Convert to domain model instance.

        Returns:
            IncidentRecord domain model instance
        """
        return IncidentRecord.from_database_model(self)


class IncidentTimelineEntryDB(SQLModel, table=True):
    """
    Incident timeline entry database model.

    Tracks the chronological sequence of actions taken during incident response.
    """

    __tablename__ = "incident_timeline_entries"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Timeline entry fields
    entry_id: str = Field(
        unique=True,
        index=True,
        description="Unique timeline entry identifier"
    )
    incident_id: str = Field(
        index=True,
        description="Incident ID this entry belongs to"
    )
    timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        description="When this action occurred"
    )
    action: str = Field(description="Action taken or event occurred")
    details: Optional[str] = Field(
        sa_column=Column(Text),
        description="Detailed description of the action/event"
    )
    performed_by: str = Field(description="Email of person who performed the action")

    # Supporting evidence and attachments
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Evidence attachments (screenshots, logs, etc.)"
    )
    entry_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional metadata about the timeline entry"
    )

    # Created timestamp
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
        description="When this timeline entry was created"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_timeline_incident_timestamp', 'incident_id', 'timestamp'),
        Index('idx_timeline_performed_by', 'performed_by'),
    )

    @field_validator('action', 'performed_by')
    @classmethod
    def validate_required_fields(cls, v, info):
        """Validate that required fields are not empty"""
        field_name = info.field_name
        if not v or (isinstance(v, str) and v.strip() == ""):
            raise ValueError(f"{field_name.replace('_', ' ').title()} cannot be empty")

        if field_name == 'performed_by' and v != "system":
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError("Performed by must be a valid email address or 'system'")

        return v.strip() if isinstance(v, str) else v


class IncidentRecord:
    """
    Incident record domain model.

    Represents an incident with full lifecycle management, GDPR compliance,
    and comprehensive tracking capabilities.
    """

    def __init__(
        self,
        title: str,
        description: str,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        reported_by: str,
        affected_systems: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        external_reference_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize incident record with validation.

        Args:
            title: Brief descriptive title
            description: Detailed description
            incident_type: Type of incident
            severity: Severity level
            reported_by: Email of reporter
            affected_systems: List of affected systems
            metadata: Additional metadata
            external_reference_id: External reference ID
            incident_id: Optional custom incident ID
        """
        # Validate required fields
        if not title or not title.strip():
            raise ValueError("Title cannot be empty")

        if not description or not description.strip():
            raise ValueError("Description cannot be empty")

        if not reported_by or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', reported_by):
            raise ValueError("Reported by must be a valid email address")

        # Generate unique incident ID if not provided
        if not incident_id:
            incident_id = f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        self.incident_id = incident_id
        self.title = title.strip()
        self.description = description.strip()
        self.incident_type = incident_type
        self.severity = severity
        self.status = IncidentStatus.OPEN
        self.reported_by = reported_by
        self.affected_systems = affected_systems or []
        self.metadata = metadata or {}
        self.external_reference_id = external_reference_id

        # Assignment fields
        self.assignee = None
        self.assigned_by = None
        self.assigned_at = None

        # Closure fields
        self.closed_by = None
        self.closed_at = None
        self.closure_details = None

        # GDPR compliance fields
        self.gdpr_breach_notified = False
        self.gdpr_breach_notified_at = None
        self.gdpr_notification_deadline = None
        self.data_subjects_notified = False

        # Impact assessment
        self.impact_assessment = None

        # Timeline tracking
        self.timeline = []

        # Audit timestamps
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

        # Initialize GDPR deadline for data breaches
        if incident_type == IncidentType.DATA_BREACH:
            self.gdpr_notification_deadline = self.created_at + timedelta(hours=72)

    def update_status(self, new_status: IncidentStatus) -> None:
        """
        Update incident status with timestamp tracking.

        Args:
            new_status: New status to set
        """
        old_status = self.status
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)

        # Add timeline entry
        self.add_timeline_entry(IncidentTimelineEntry(
            timestamp=self.updated_at,
            action=f"Status updated from {old_status} to {new_status}",
            details=f"Incident status changed from {old_status} to {new_status}",
            performed_by="system"
        ))

    def get_gdpr_notification_deadline(self) -> Optional[datetime]:
        """
        Calculate GDPR 72-hour breach notification deadline.

        Returns:
            datetime: Deadline for notification to supervisory authority
        """
        if self.incident_type == IncidentType.DATA_BREACH:
            if not self.gdpr_notification_deadline:
                self.gdpr_notification_deadline = self.created_at + timedelta(hours=72)
            return self.gdpr_notification_deadline
        return None

    def is_gdpr_deadline_passed(self) -> bool:
        """
        Check if GDPR 72-hour notification deadline has passed.

        Returns:
            bool: True if deadline has passed
        """
        if self.incident_type != IncidentType.DATA_BREACH:
            return False

        deadline = self.get_gdpr_notification_deadline()
        if not deadline:
            return False

        return datetime.now(timezone.utc) > deadline

    def update_impact_assessment(self, assessment: Dict[str, Any]) -> None:
        """
        Update impact assessment for GDPR compliance.

        Args:
            assessment: Impact assessment details
        """
        self.impact_assessment = assessment
        self.updated_at = datetime.now(timezone.utc)

        # Add timeline entry
        self.add_timeline_entry(IncidentTimelineEntry(
            timestamp=self.updated_at,
            action="Impact assessment completed",
            details=f"Updated impact assessment: {assessment.get('consequences', 'N/A')}",
            performed_by="dpo@company.com"
        ))

    def add_timeline_entry(self, entry: 'IncidentTimelineEntry') -> None:
        """
        Add an entry to the incident timeline.

        Args:
            entry: Timeline entry to add
        """
        self.timeline.append(entry)
        self.updated_at = datetime.now(timezone.utc)

    def assign_to(self, assignee: str, assigned_by: str, reason: str) -> None:
        """
        Assign incident to personnel.

        Args:
            assignee: Email of person being assigned
            assigned_by: Email of person making assignment
            reason: Reason for assignment
        """
        self.assignee = assignee
        self.assigned_by = assigned_by
        self.assigned_at = datetime.now(timezone.utc)
        self.updated_at = self.assigned_at

        # Add timeline entry
        self.add_timeline_entry(IncidentTimelineEntry(
            timestamp=self.assigned_at,
            action="Incident assigned",
            details=f"Incident assigned to {assignee}. Reason: {reason}",
            performed_by=assigned_by
        ))

    def close_incident(self, closed_by: str, closure_details: Dict[str, Any]) -> None:
        """
        Close incident with validation and documentation.

        Args:
            closed_by: Email of person closing the incident
            closure_details: Details about incident closure
        """
        if not closure_details or 'root_cause' not in closure_details:
            raise ValueError("Closure details must include root cause analysis")

        self.update_status(IncidentStatus.CLOSED)
        self.closed_by = closed_by
        self.closed_at = datetime.now(timezone.utc)
        self.closure_details = closure_details
        self.updated_at = self.closed_at

        # Add timeline entry
        self.add_timeline_entry(IncidentTimelineEntry(
            timestamp=self.closed_at,
            action="Incident closed",
            details=f"Incident closed by {closed_by}. Root cause: {closure_details.get('root_cause', 'N/A')}",
            performed_by=closed_by
        ))

    def to_database_model(self) -> IncidentRecordDB:
        """
        Convert to database model for persistence.

        Returns:
            IncidentRecordDB instance
        """
        return IncidentRecordDB(
            incident_id=self.incident_id,
            title=self.title,
            description=self.description,
            incident_type=self.incident_type,
            severity=self.severity,
            status=self.status,
            reported_by=self.reported_by,
            assignee=self.assignee,
            assigned_by=self.assigned_by,
            assigned_at=self.assigned_at,
            closed_by=self.closed_by,
            closed_at=self.closed_at,
            closure_details=self.closure_details,
            affected_systems=self.affected_systems,
            impact_assessment=self.impact_assessment,
            incident_metadata=self.metadata,
            external_reference_id=self.external_reference_id,
            gdpr_breach_notified=self.gdpr_breach_notified,
            gdpr_breach_notified_at=self.gdpr_breach_notified_at,
            gdpr_notification_deadline=self.gdpr_notification_deadline,
            data_subjects_notified=self.data_subjects_notified,
            created_at=self.created_at,
            updated_at=self.updated_at
        )

    @classmethod
    def from_database_model(cls, db_model: IncidentRecordDB) -> 'IncidentRecord':
        """
        Create domain model from database model.

        Args:
            db_model: IncidentRecordDB instance

        Returns:
            IncidentRecord domain model instance
        """
        incident = cls.__new__(cls)
        incident.incident_id = db_model.incident_id
        incident.title = db_model.title
        incident.description = db_model.description
        incident.incident_type = db_model.incident_type
        incident.severity = db_model.severity
        incident.status = db_model.status
        incident.reported_by = db_model.reported_by
        incident.assignee = db_model.assignee
        incident.assigned_by = db_model.assigned_by
        incident.assigned_at = db_model.assigned_at
        incident.closed_by = db_model.closed_by
        incident.closed_at = db_model.closed_at
        incident.closure_details = db_model.closure_details
        incident.affected_systems = db_model.affected_systems or []
        incident.impact_assessment = db_model.impact_assessment
        incident.metadata = db_model.incident_metadata or {}
        incident.external_reference_id = db_model.external_reference_id
        incident.gdpr_breach_notified = db_model.gdpr_breach_notified
        incident.gdpr_breach_notified_at = db_model.gdpr_breach_notified_at
        incident.gdpr_notification_deadline = db_model.gdpr_notification_deadline
        incident.data_subjects_notified = db_model.data_subjects_notified
        incident.created_at = db_model.created_at
        incident.updated_at = db_model.updated_at
        incident.timeline = []  # Timeline would need to be loaded separately

        return incident

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert incident to dictionary for serialization.

        Returns:
            Dictionary representation of incident
        """
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "incident_type": self.incident_type,
            "severity": self.severity,
            "status": self.status,
            "reported_by": self.reported_by,
            "assignee": self.assignee,
            "assigned_by": self.assigned_by,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "closed_by": self.closed_by,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "closure_details": self.closure_details,
            "affected_systems": self.affected_systems,
            "impact_assessment": self.impact_assessment,
            "metadata": self.metadata,
            "external_reference_id": self.external_reference_id,
            "gdpr_breach_notified": self.gdpr_breach_notified,
            "gdpr_breach_notified_at": self.gdpr_breach_notified_at.isoformat() if self.gdpr_breach_notified_at else None,
            "gdpr_notification_deadline": self.gdpr_notification_deadline.isoformat() if self.gdpr_notification_deadline else None,
            "data_subjects_notified": self.data_subjects_notified,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "timeline": [entry.to_dict() for entry in self.timeline]
        }

    def __repr__(self) -> str:
        """String representation of incident record"""
        return f"IncidentRecord(id='{self.incident_id}', type='{self.incident_type}', severity='{self.severity}', status='{self.status}')"


class IncidentTimelineEntry:
    """
    Incident timeline entry domain model.

    Tracks individual actions and events during incident response.
    """

    def __init__(
        self,
        timestamp: datetime,
        action: str,
        details: Optional[str] = None,
        performed_by: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        entry_id: Optional[str] = None
    ):
        """
        Initialize timeline entry.

        Args:
            timestamp: When the action occurred
            action: Action taken or event occurred
            details: Detailed description
            performed_by: Email of person who performed the action or 'system'
            attachments: Evidence attachments
            entry_id: Optional custom entry ID
        """
        # Validate required fields
        if not action or not action.strip():
            raise ValueError("Action cannot be empty")

        # Allow 'system' as a special case for automated actions
        if performed_by and performed_by != "system":
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', performed_by):
                raise ValueError("Performed by must be a valid email address or 'system'")

        # Generate unique entry ID if not provided
        if not entry_id:
            entry_id = f"TL-{str(uuid.uuid4())[:8].upper()}"

        self.entry_id = entry_id
        self.timestamp = timestamp
        self.action = action.strip()
        self.details = details.strip() if details else None
        self.performed_by = performed_by
        self.attachments = attachments or []

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert timeline entry to dictionary.

        Returns:
            Dictionary representation of timeline entry
        """
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "details": self.details,
            "performed_by": self.performed_by,
            "attachments": self.attachments
        }

    def __repr__(self) -> str:
        """String representation of timeline entry"""
        return f"IncidentTimelineEntry(id='{self.entry_id}', action='{self.action}', timestamp='{self.timestamp.isoformat()}')"


class IncidentClassification:
    """
    Result of automatic incident classification.
    """

    def __init__(
        self,
        incident_type: IncidentType,
        severity: IncidentSeverity,
        confidence: float,
        attack_pattern: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None
    ):
        self.incident_type = incident_type
        self.severity = severity
        self.confidence = confidence
        self.attack_pattern = attack_pattern
        self.suggested_actions = suggested_actions or []


class ContainmentResult:
    """
    Result of automatic containment actions.
    """

    def __init__(
        self,
        success: bool,
        actions_taken: List[ContainmentAction],
        timestamp: datetime,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.actions_taken = actions_taken
        self.timestamp = timestamp
        self.error_message = error_message


class GDPRNotificationResult:
    """
    Result of GDPR breach notification process.
    """

    def __init__(
        self,
        success: bool,
        supervisory_authority_notified: bool,
        notification_deadline: datetime,
        notification_timestamp: Optional[datetime] = None,
        error_message: Optional[str] = None
    ):
        self.success = success
        self.supervisory_authority_notified = supervisory_authority_notified
        self.notification_deadline = notification_deadline
        self.notification_timestamp = notification_timestamp
        self.error_message = error_message


class DataSubjectNotificationRequirements:
    """
    Assessment of data subject notification requirements under GDPR.
    """

    def __init__(
        self,
        requires_notification: bool,
        risk_level: str,
        notification_timeline: Optional[str] = None,
        requirements: Optional[Dict[str, Any]] = None
    ):
        self.requires_notification = requires_notification
        self.risk_level = risk_level
        self.notification_timeline = notification_timeline
        self.requirements = requirements or {}


class GDPRIncidentReport:
    """
    Comprehensive GDPR incident report.
    """

    def __init__(
        self,
        incident_details: Dict[str, Any],
        timeline: List[IncidentTimelineEntry],
        impact_assessment: Dict[str, Any],
        measures_taken: List[str],
        documentation_timestamp: datetime
    ):
        self.incident_details = incident_details
        self.timeline = timeline
        self.impact_assessment = impact_assessment
        self.measures_taken = measures_taken
        self.documentation_timestamp = documentation_timestamp


class PostIncidentReviewResult:
    """
    Result of post-incident review process.
    """

    def __init__(
        self,
        review_completed: bool,
        lessons_learned_documented: bool,
        action_items_created: bool,
        follow_up_required: bool,
        review_findings: Dict[str, Any]
    ):
        self.review_completed = review_completed
        self.lessons_learned_documented = lessons_learned_documented
        self.action_items_created = action_items_created
        self.follow_up_required = follow_up_required
        self.review_findings = review_findings


class IncidentMetrics:
    """
    Incident metrics for reporting and analysis.
    """

    def __init__(
        self,
        total_incidents: int,
        by_severity: Dict[IncidentSeverity, int],
        by_type: Dict[IncidentType, int],
        average_resolution_time: Optional[timedelta],
        gdpr_compliance_rate: float
    ):
        self.total_incidents = total_incidents
        self.by_severity = by_severity
        self.by_type = by_type
        self.average_resolution_time = average_resolution_time
        self.gdpr_compliance_rate = gdpr_compliance_rate


class GDPRDeadlineStatus:
    """
    Status of GDPR notification deadline.
    """

    def __init__(
        self,
        hours_remaining: Optional[float],
        deadline_passed: bool,
        supervisory_authority_notified: bool
    ):
        self.hours_remaining = hours_remaining
        self.deadline_passed = deadline_passed
        self.supervisory_authority_notified = supervisory_authority_notified