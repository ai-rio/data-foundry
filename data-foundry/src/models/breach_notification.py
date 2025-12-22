"""
Breach Notification Data Models for Data Foundry

This module defines the SQLModel and domain models for advanced breach notification workflows,
providing:
- Multi-jurisdiction compliance tracking
- Approval workflow management
- Template-based notification systems
- Comprehensive audit trails for regulatory reporting
- Deadline monitoring and escalation procedures
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from pydantic import field_validator, EmailStr
from sqlalchemy import Column, String, DateTime, Text, JSON, Index, Integer, Boolean, ForeignKey
from sqlmodel import SQLModel, Field, Relationship

from src.models.enums import (
    IncidentSeverity, IncidentStatus, IncidentType,
    NotificationChannel
)


class BreachNotificationWorkflowDB(SQLModel, table=True):
    """
    Breach notification workflow database model.

    Tracks the complete lifecycle of breach notification workflows across multiple
    jurisdictions with comprehensive audit trails and compliance monitoring.
    """

    __tablename__ = "breach_notification_workflows"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core workflow fields
    workflow_id: str = Field(
        unique=True,
        index=True,
        description="Unique workflow identifier"
    )
    incident_id: str = Field(
        index=True,
        description="Associated incident ID"
    )
    workflow_type: str = Field(
        description="Type of notification workflow (e.g., 'gdpr_breach', 'ccpa_notification')"
    )
    status: str = Field(
        default="initiated",
        index=True,
        description="Current workflow status"
    )

    # Jurisdiction and compliance fields
    jurisdictions: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="List of jurisdictions applicable to this breach"
    )
    compliance_assessments: Optional[Dict[str, Any]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Compliance assessments by jurisdiction"
    )
    risk_level: Optional[str] = Field(
        default=None,
        description="Overall risk level assessment"
    )

    # Workflow configuration
    auto_assessment: bool = Field(
        default=True,
        description="Whether to perform automated compliance assessment"
    )
    approval_required: bool = Field(
        default=None,
        description="Whether approval workflow is required"
    )
    approval_threshold: Optional[float] = Field(
        default=None,
        description="Approval threshold (0.0-1.0)"
    )

    # Deadlines and timing
    notification_deadlines: Optional[Dict[str, datetime]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Notification deadlines by jurisdiction"
    )
    escalated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When workflow was escalated"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When workflow was completed"
    )

    # Workflow metadata
    initiated_by: str = Field(description="Email of person who initiated workflow")
    assignee: Optional[str] = Field(
        default=None,
        index=True,
        description="Email of person assigned to manage workflow"
    )
    workflow_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional workflow metadata"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When workflow was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When workflow was last updated"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_workflow_incident_status', 'incident_id', 'status'),
        Index('idx_workflow_created_at', 'created_at'),
        Index('idx_workflow_initiated_by', 'initiated_by'),
        Index('idx_workflow_jurisdictions', 'jurisdictions'),
    )

    @field_validator('initiated_by', 'assignee')
    @classmethod
    def validate_email_fields(cls, v):
        """Validate email fields"""
        if v and "@" not in v:
            raise ValueError("Must be a valid email address")
        return v


class ApprovalWorkflowDB(SQLModel, table=True):
    """
    Approval workflow database model.

    Tracks approval processes for sensitive breach notifications with multi-level
    approval capabilities and delegation support.
    """

    __tablename__ = "approval_workflows"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core approval fields
    approval_id: str = Field(
        unique=True,
        index=True,
        description="Unique approval workflow identifier"
    )
    parent_workflow_id: Optional[str] = Field(
        index=True,
        description="ID of parent breach notification workflow"
    )
    notification_type: str = Field(
        description="Type of notification requiring approval"
    )
    status: str = Field(
        default="pending_approval",
        index=True,
        description="Current approval status"
    )

    # Approval configuration
    approval_threshold: float = Field(
        description="Approval threshold (0.0-1.0)"
    )
    deadline_hours: int = Field(
        description="Deadline in hours for approval completion"
    )
    deadline_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        description="Approval deadline timestamp"
    )

    # Approval content
    content_subject: str = Field(description="Subject of content requiring approval")
    content_body: str = Field(
        sa_column=Column(Text),
        description="Body of content requiring approval"
    )
    content_attachments: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="List of content attachments"
    )
    content_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Content metadata and compliance information"
    )

    # Escalation information
    escalation_level: int = Field(
        default=0,
        description="Current escalation level"
    )
    escalation_triggered: bool = Field(
        default=False,
        description="Whether escalation has been triggered"
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="Reason for escalation"
    )

    # Workflow metadata
    requester: str = Field(description="Email of person requesting approval")
    delegated_to: Optional[str] = Field(
        default=None,
        description="Email of person approval was delegated to"
    )
    approval_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional approval metadata"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When approval workflow was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When approval workflow was last updated"
    )
    decided_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When final decision was made"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_approval_parent_status', 'parent_workflow_id', 'status'),
        Index('idx_approval_deadline', 'deadline_at'),
        Index('idx_approval_requester', 'requester'),
        Index('idx_approval_type', 'notification_type'),
    )


class ApprovalDecisionDB(SQLModel, table=True):
    """
    Individual approval decision database model.

    Tracks individual decisions within approval workflows with detailed
    audit information and delegation tracking.
    """

    __tablename__ = "approval_decisions"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Core decision fields
    decision_id: str = Field(
        unique=True,
        index=True,
        description="Unique decision identifier"
    )
    approval_id: str = Field(
        index=True,
        description="Associated approval workflow ID"
    )
    approver_email: str = Field(
        index=True,
        description="Email of approver"
    )
    approver_role: str = Field(
        description="Role of approver in organization"
    )
    decision: str = Field(
        index=True,
        description="Approval decision (approved/rejected/abstained)"
    )
    required: bool = Field(
        default=True,
        description="Whether this approval is required for completion"
    )

    # Decision details
    comments: Optional[str] = Field(
        sa_column=Column(Text),
        description="Approver comments and reasoning"
    )
    confidence_level: Optional[str] = Field(
        default=None,
        description="Approver confidence level in decision"
    )
    blocking_issues: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="List of blocking issues for rejection"
    )

    # Delegation information
    delegated: bool = Field(
        default=False,
        description="Whether decision was made by delegate"
    )
    delegation_id: Optional[str] = Field(
        default=None,
        description="ID of delegation arrangement"
    )
    original_approver: Optional[str] = Field(
        default=None,
        description="Email of original approver if delegated"
    )

    # Compliance validation
    compliance_confirmation: Optional[Dict[str, bool]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Compliance confirmation checkboxes"
    )
    risk_assessment: Optional[str] = Field(
        default=None,
        description="Approver risk assessment"
    )

    # Metadata
    decision_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional decision metadata"
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="IP address of approver"
    )
    user_agent: Optional[str] = Field(
        sa_column=Column(Text),
        default=None,
        description="User agent of approver's browser"
    )

    # Timestamps
    decided_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        description="When decision was made"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When decision record was created"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_decision_approval_approver', 'approval_id', 'approver_email'),
        Index('idx_decision_decided_at', 'decided_at'),
        Index('idx_decision_decision', 'decision'),
    )


class NotificationTemplateDB(SQLModel, table=True):
    """
    Notification template database model.

    Stores multilingual notification templates with versioning and
    customization capabilities for different jurisdictions and channels.
    """

    __tablename__ = "notification_templates"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Template identification
    template_id: str = Field(
        unique=True,
        index=True,
        description="Unique template identifier"
    )
    template_name: str = Field(
        index=True,
        description="Human-readable template name"
    )
    template_type: str = Field(
        description="Template type (e.g., 'supervisory_authority', 'data_subject')"
    )
    jurisdiction: Optional[str] = Field(
        default=None,
        index=True,
        description="Target jurisdiction (e.g., 'GDPR', 'CCPA')"
    )
    language: str = Field(
        default="en",
        index=True,
        description="Template language code"
    )
    version: str = Field(
        default="1.0",
        description="Template version"
    )

    # Template content
    subject_template: str = Field(
        description="Email subject template with placeholders"
    )
    body_template: str = Field(
        sa_column=Column(Text),
        description="Plain text body template with placeholders"
    )
    html_template: Optional[str] = Field(
        sa_column=Column(Text),
        default=None,
        description="HTML body template with placeholders"
    )
    sms_template: Optional[str] = Field(
        sa_column=Column(Text),
        default=None,
        description="SMS-specific template variant"
    )

    # Template configuration
    variables: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Template variable definitions"
    )
    required_variables: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="List of required template variables"
    )
    localization_keys: Optional[Dict[str, str]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Localization key mappings"
    )

    # Compliance and validation
    compliance_requirements: Optional[Dict[str, List[str]]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Compliance requirements by jurisdiction"
    )
    validation_rules: Optional[Dict[str, Any]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Template validation rules"
    )
    accessibility_features: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Accessibility compliance features"
    )

    # Template status
    active: bool = Field(
        default=True,
        index=True,
        description="Whether template is active for use"
    )
    parent_template_id: Optional[str] = Field(
        default=None,
        description="ID of parent template (for versioning)"
    )

    # Template metadata
    created_by: str = Field(description="Email of template creator")
    description: Optional[str] = Field(
        default=None,
        description="Template description and usage notes"
    )
    template_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional template metadata"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When template was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When template was last updated"
    )
    effective_from: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When template becomes effective"
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When template expires"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_template_name_type', 'template_name', 'template_type'),
        Index('idx_template_jurisdiction_language', 'jurisdiction', 'language'),
        Index('idx_template_active_version', 'active', 'version'),
        Index('idx_template_created_at', 'created_at'),
    )


class NotificationDeliveryDB(SQLModel, table=True):
    """
    Notification delivery tracking database model.

    Tracks delivery of notifications across multiple channels with retry
    logic, delivery confirmation, and performance metrics.
    """

    __tablename__ = "notification_deliveries"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Delivery identification
    delivery_id: str = Field(
        unique=True,
        index=True,
        description="Unique delivery identifier"
    )
    workflow_id: Optional[str] = Field(
        index=True,
        description="Associated workflow ID"
    )
    template_id: Optional[str] = Field(
        index=True,
        description="Template ID used for notification"
    )
    notification_type: str = Field(
        description="Type of notification sent"
    )
    channel: str = Field(
        index=True,
        description="Delivery channel"
    )

    # Recipient information
    recipient: str = Field(
        index=True,
        description="Notification recipient (email, phone, etc.)"
    )
    recipient_type: str = Field(
        description="Recipient type (e.g., 'data_subject', 'authority', 'internal')"
    )
    personalization_data: Optional[Dict[str, Any]] = Field(
        default={},
        sa_column=Column(JSON),
        description="Personalization data used in notification"
    )

    # Delivery content
    subject: str = Field(description="Notification subject")
    content: str = Field(
        sa_column=Column(Text),
        description="Notification content"
    )
    html_content: Optional[str] = Field(
        sa_column=Column(Text),
        default=None,
        description="HTML notification content"
    )
    attachments: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Notification attachments"
    )

    # Delivery status
    status: str = Field(
        default="pending",
        index=True,
        description="Delivery status"
    )
    attempts: int = Field(
        default=0,
        description="Number of delivery attempts"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts"
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When last delivery attempt was made"
    )
    delivered_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When notification was successfully delivered"
    )
    confirmed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When delivery was confirmed by recipient"
    )

    # Delivery metadata
    message_id: Optional[str] = Field(
        default=None,
        description="External message ID from delivery service"
    )
    delivery_service: str = Field(
        description="Delivery service used"
    )
    delivery_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional delivery metadata"
    )
    error_details: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Error details from failed attempts"
    )

    # Performance metrics
    send_duration_ms: Optional[int] = Field(
        default=None,
        description="Time to send notification in milliseconds"
    )
    delivery_duration_ms: Optional[int] = Field(
        default=None,
        description="Time to deliver notification in milliseconds"
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When delivery record was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When delivery record was last updated"
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When next retry should be attempted"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_delivery_workflow_status', 'workflow_id', 'status'),
        Index('idx_delivery_channel_recipient', 'channel', 'recipient'),
        Index('idx_delivery_created_at', 'created_at'),
        Index('idx_delivery_next_retry', 'next_retry_at'),
    )


class BreachNotificationAuditDB(SQLModel, table=True):
    """
    Comprehensive audit trail database model for breach notifications.

    Tracks all activities, decisions, and communications for regulatory
    compliance and internal audit requirements.
    """

    __tablename__ = "breach_notification_audits"

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Audit identification
    audit_id: str = Field(
        unique=True,
        index=True,
        description="Unique audit entry identifier"
    )
    incident_id: Optional[str] = Field(
        index=True,
        description="Associated incident ID"
    )
    workflow_id: Optional[str] = Field(
        index=True,
        description="Associated workflow ID"
    )
    approval_id: Optional[str] = Field(
        index=True,
        description="Associated approval workflow ID"
    )
    delivery_id: Optional[str] = Field(
        index=True,
        description="Associated delivery ID"
    )

    # Event information
    event_type: str = Field(
        index=True,
        description="Type of event (e.g., 'workflow_initiated', 'approval_submitted')"
    )
    event_category: str = Field(
        index=True,
        description="Event category (e.g., 'workflow', 'approval', 'delivery', 'compliance')"
    )
    event_description: str = Field(
        description="Detailed description of the event"
    )
    event_severity: Optional[str] = Field(
        default=None,
        description="Event severity level"
    )

    # Actor information
    actor_email: str = Field(
        index=True,
        description="Email of person who performed the action"
    )
    actor_role: Optional[str] = Field(
        default=None,
        description="Role of the actor"
    )
    actor_type: str = Field(
        description="Actor type (e.g., 'user', 'system', 'service')"
    )

    # Event details
    old_state: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="State before the event"
    )
    new_state: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="State after the event"
    )
    event_data: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional event data"
    )

    # Compliance information
    compliance_impact: Optional[str] = Field(
        default=None,
        description="Compliance impact of the event"
    )
    regulatory_references: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Applicable regulatory references"
    )
    retention_period_days: Optional[int] = Field(
        default=None,
        description="Retention period in days for this audit entry"
    )

    # Security and forensics
    ip_address: Optional[str] = Field(
        default=None,
        description="IP address of the actor"
    )
    user_agent: Optional[str] = Field(
        sa_column=Column(Text),
        default=None,
        description="User agent string"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier"
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Request identifier for correlation"
    )

    # Event outcome
    success: bool = Field(
        default=True,
        index=True,
        description="Whether the event was successful"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if event failed"
    )
    warnings: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Warning messages generated by the event"
    )

    # Metadata
    audit_metadata: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON),
        description="Additional audit metadata"
    )
    tags: Optional[List[str]] = Field(
        default=[],
        sa_column=Column(JSON),
        description="Audit tags for categorization and search"
    )

    # Timestamps
    event_timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        description="When the event occurred"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True)),
        description="When audit entry was created"
    )
    last_accessed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="When audit entry was last accessed"
    )

    # Table indexes
    __table_args__ = (
        Index('idx_audit_incident_event', 'incident_id', 'event_type'),
        Index('idx_audit_workflow_event', 'workflow_id', 'event_type'),
        Index('idx_audit_actor_timestamp', 'actor_email', 'event_timestamp'),
        Index('idx_audit_event_timestamp', 'event_timestamp'),
        Index('idx_audit_category_severity', 'event_category', 'event_severity'),
    )