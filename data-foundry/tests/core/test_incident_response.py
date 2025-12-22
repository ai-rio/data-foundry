"""
Test-Driven Development for Incident Response System

This test file defines the expected behavior of the incident response system
before implementation begins, following TDD principles.

Tests are written first, then implementation follows to make them pass.

GDPR References:
- Article 33: Notification of personal data breach to supervisory authority (72 hours)
- Article 34: Communication of personal data breach to data subjects
- Article 32: Security of processing
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock
from typing import Optional, Dict, Any

# Import the classes we will create (these will fail initially)
try:
    from src.models.incident import IncidentRecord, IncidentTimelineEntry
    from src.core.incident_manager import IncidentManager, IncidentClassifier
    from src.models.enums import (
        IncidentSeverity, IncidentStatus, IncidentType,
        NotificationChannel, ContainmentAction
    )
except ImportError:
    # These imports will fail until we implement the classes
    pytest.skip("Incident response modules not yet implemented", allow_module_level=True)


class TestIncidentRecord:
    """Test the IncidentRecord data model following TDD principles"""

    def test_incident_record_creation_minimal(self):
        """Test creating incident record with minimal required fields"""
        # Test will fail until IncidentRecord is implemented
        incident = IncidentRecord(
            title="Data Breach Detected",
            description="Unauthorized access to customer database",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="security_team@company.com"
        )

        assert incident.title == "Data Breach Detected"
        assert incident.description == "Unauthorized access to customer database"
        assert incident.incident_type == IncidentType.DATA_BREACH
        assert incident.severity == IncidentSeverity.CRITICAL
        assert incident.status == IncidentStatus.OPEN  # Default should be OPEN
        assert incident.reported_by == "security_team@company.com"
        assert incident.created_at is not None
        assert incident.updated_at is not None
        assert incident.incident_id is not None
        assert len(incident.incident_id) > 10  # Should be a meaningful ID

    def test_incident_record_with_all_fields(self):
        """Test creating incident record with all optional fields"""
        affected_systems = ["customer_db", "auth_service", "api_gateway"]
        metadata = {
            "source_ip": "192.168.1.100",
            "attack_vector": "SQL Injection",
            "affected_records": 15000
        }

        incident = IncidentRecord(
            title="Security Incident",
            description="SQL injection attack detected",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.HIGH,
            affected_systems=affected_systems,
            metadata=metadata,
            reported_by="analyst@company.com",
            external_reference_id="EXT-2024-001"
        )

        assert incident.affected_systems == affected_systems
        assert incident.metadata == metadata
        assert incident.external_reference_id == "EXT-2024-001"

    def test_incident_status_transitions(self):
        """Test incident status workflow transitions"""
        incident = IncidentRecord(
            title="Test Incident",
            description="Test description",
            incident_type=IncidentType.SYSTEM_OUTAGE,
            severity=IncidentSeverity.MEDIUM,
            reported_by="user@company.com"
        )

        # Initial status should be OPEN
        assert incident.status == IncidentStatus.OPEN

        # Test valid status transitions
        incident.update_status(IncidentStatus.INVESTIGATING)
        assert incident.status == IncidentStatus.INVESTIGATING

        incident.update_status(IncidentStatus.IDENTIFIED)
        assert incident.status == IncidentStatus.IDENTIFIED

        incident.update_status(IncidentStatus.RESOLVED)
        assert incident.status == IncidentStatus.RESOLVED

        incident.update_status(IncidentStatus.CLOSED)
        assert incident.status == IncidentStatus.CLOSED

        # Verify updated_at timestamp changes
        first_update = incident.updated_at
        incident.update_status(IncidentStatus.OPEN)
        assert incident.updated_at > first_update

    def test_incident_severity_levels(self):
        """Test all severity levels can be assigned"""
        severities = [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH,
                     IncidentSeverity.MEDIUM, IncidentSeverity.LOW]

        for severity in severities:
            incident = IncidentRecord(
                title=f"Test {severity} Incident",
                description="Test description",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=severity,
                reported_by="user@company.com"
            )
            assert incident.severity == severity

    def test_incident_type_classification(self):
        """Test all incident types can be assigned"""
        incident_types = [IncidentType.DATA_BREACH, IncidentType.SECURITY_INCIDENT,
                         IncidentType.SYSTEM_OUTAGE, IncidentType.PRIVACY_VIOLATION,
                         IncidentType.COMPLIANCE_VIOLATION, IncidentType.PERFORMANCE_DEGRADATION]

        for incident_type in incident_types:
            incident = IncidentRecord(
                title=f"Test {incident_type}",
                description="Test description",
                incident_type=incident_type,
                severity=IncidentSeverity.MEDIUM,
                reported_by="user@company.com"
            )
            assert incident.incident_type == incident_type

    def test_gdpr_breach_notification_deadline(self):
        """Test GDPR 72-hour breach notification deadline tracking"""
        incident = IncidentRecord(
            title="Personal Data Breach",
            description="Unauthorized access to personal data",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="dpo@company.com"
        )

        # Should track 72-hour deadline for GDPR notification
        deadline = incident.get_gdpr_notification_deadline()
        expected_deadline = incident.created_at + timedelta(hours=72)

        assert abs((deadline - expected_deadline).total_seconds()) < 60  # Within 1 minute

        # Test if deadline has passed
        assert not incident.is_gdpr_deadline_passed()

        # Mock time passage beyond 72 hours
        incident.created_at = datetime.now(timezone.utc) - timedelta(hours=73)
        assert incident.is_gdpr_deadline_passed()

    def test_incident_impact_assessment(self):
        """Test incident impact assessment functionality"""
        incident = IncidentRecord(
            title="Data Breach",
            description="Customer data compromised",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.HIGH,
            reported_by="security@company.com"
        )

        # Should be able to update impact assessment
        impact_assessment = {
            "data_subjects_affected": 5000,
            "data_types_involved": ["personal_data", "email_addresses", "phone_numbers"],
            "consequences": ["identity_theft_risk", "privacy_violation"],
            "likelihood_of_harm": "high",
            "measures_taken": ["account_suspension", "password_reset"]
        }

        incident.update_impact_assessment(impact_assessment)
        assert incident.impact_assessment == impact_assessment

    def test_incident_timeline_tracking(self):
        """Test incident timeline entry tracking"""
        incident = IncidentRecord(
            title="Test Incident",
            description="Test description",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.MEDIUM,
            reported_by="user@company.com"
        )

        # Add timeline entries
        entry1 = IncidentTimelineEntry(
            timestamp=datetime.now(timezone.utc),
            action="Incident detected",
            details="Security monitoring alert triggered",
            performed_by="system"
        )

        entry2 = IncidentTimelineEntry(
            timestamp=datetime.now(timezone.utc),
            action="Investigation started",
            details="Security team assigned",
            performed_by="analyst@company.com"
        )

        incident.add_timeline_entry(entry1)
        incident.add_timeline_entry(entry2)

        assert len(incident.timeline) == 2
        assert incident.timeline[0].action == "Incident detected"
        assert incident.timeline[1].action == "Investigation started"

    def test_incident_assignment(self):
        """Test incident assignment to personnel"""
        incident = IncidentRecord(
            title="Security Incident",
            description="Security breach detected",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.HIGH,
            reported_by="system@company.com"
        )

        # Assign incident
        incident.assign_to(
            assignee="security_lead@company.com",
            assigned_by="manager@company.com",
            reason="Primary incident responder"
        )

        assert incident.assignee == "security_lead@company.com"
        assert incident.assigned_at is not None
        assert incident.assigned_by == "manager@company.com"

    def test_incident_closure_validation(self):
        """Test incident closure requires required fields"""
        incident = IncidentRecord(
            title="Test Incident",
            description="Test description",
            incident_type=IncidentType.SYSTEM_OUTAGE,
            severity=IncidentSeverity.LOW,
            reported_by="user@company.com"
        )

        incident.update_status(IncidentStatus.RESOLVED)

        # Should require closure information before final closure
        closure_info = {
            "root_cause": "Configuration error in load balancer",
            "resolution": "Load balancer configuration updated",
            "prevention_measures": ["configuration_review_process"],
            "lessons_learned": "Need better change management"
        }

        incident.close_incident(
            closed_by="engineer@company.com",
            closure_details=closure_info
        )

        assert incident.status == IncidentStatus.CLOSED
        assert incident.closed_at is not None
        assert incident.closed_by == "engineer@company.com"
        assert incident.closure_details == closure_info

    def test_incident_validation(self):
        """Test incident record validation"""
        # Test empty title
        with pytest.raises(ValueError, match="Title cannot be empty"):
            IncidentRecord(
                title="",
                description="Test description",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.MEDIUM,
                reported_by="user@company.com"
            )

        # Test empty description
        with pytest.raises(ValueError, match="Description cannot be empty"):
            IncidentRecord(
                title="Test Incident",
                description="",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.MEDIUM,
                reported_by="user@company.com"
            )

        # Test invalid reported_by
        with pytest.raises(ValueError, match="Reported by must be valid email"):
            IncidentRecord(
                title="Test Incident",
                description="Test description",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.MEDIUM,
                reported_by="invalid_email"
            )


class TestIncidentTimelineEntry:
    """Test the IncidentTimelineEntry data model"""

    def test_timeline_entry_creation(self):
        """Test creating timeline entry"""
        timestamp = datetime.now(timezone.utc)
        entry = IncidentTimelineEntry(
            timestamp=timestamp,
            action="System isolation",
            details="Affected system isolated from network",
            performed_by="security_admin@company.com"
        )

        assert entry.timestamp == timestamp
        assert entry.action == "System isolation"
        assert entry.details == "Affected system isolated from network"
        assert entry.performed_by == "security_admin@company.com"
        assert entry.entry_id is not None

    def test_timeline_entry_with_attachments(self):
        """Test timeline entry with evidence attachments"""
        attachments = [
            {"type": "screenshot", "url": "/path/to/screenshot.png"},
            {"type": "log_file", "url": "/path/to/error.log"}
        ]

        entry = IncidentTimelineEntry(
            timestamp=datetime.now(timezone.utc),
            action="Evidence collection",
            details="Collected forensic evidence",
            performed_by="forensics_team@company.com",
            attachments=attachments
        )

        assert entry.attachments == attachments

    def test_timeline_entry_validation(self):
        """Test timeline entry validation"""
        # Test empty action
        with pytest.raises(ValueError, match="Action cannot be empty"):
            IncidentTimelineEntry(
                timestamp=datetime.now(timezone.utc),
                action="",
                details="Test details",
                performed_by="user@company.com"
            )


class TestIncidentClassifier:
    """Test the IncidentClassifier component"""

    @pytest.mark.asyncio
    async def test_classify_data_breach(self):
        """Test automatic classification of data breach incidents"""
        classifier = IncidentClassifier()

        incident_data = {
            "description": "Unauthorized access to customer database containing personal information",
            "affected_systems": ["customer_db"],
            "evidence": {"data_access": True, "personal_data": True}
        }

        classification = await classifier.classify_incident(incident_data)

        assert classification.incident_type == IncidentType.DATA_BREACH
        assert classification.severity == IncidentSeverity.CRITICAL
        assert classification.confidence > 0.8

    @pytest.mark.asyncio
    async def test_classify_performance_issue(self):
        """Test automatic classification of performance incidents"""
        classifier = IncidentClassifier()

        incident_data = {
            "description": "API response times exceeding 5 seconds",
            "metrics": {"response_time": 5000, "error_rate": 0.02},
            "affected_systems": ["api_gateway"]
        }

        classification = await classifier.classify_incident(incident_data)

        assert classification.incident_type == IncidentType.PERFORMANCE_DEGRADATION
        assert classification.severity in [IncidentSeverity.MEDIUM, IncidentSeverity.HIGH]
        assert classification.suggested_actions is not None

    @pytest.mark.asyncio
    async def test_classify_security_incident(self):
        """Test automatic classification of security incidents"""
        classifier = IncidentClassifier()

        incident_data = {
            "description": "Multiple failed login attempts detected",
            "evidence": {"failed_attempts": 1000, "source_ips": ["192.168.1.100"]},
            "affected_systems": ["auth_service"]
        }

        classification = await classifier.classify_incident(incident_data)

        assert classification.incident_type == IncidentType.SECURITY_INCIDENT
        assert classification.severity == IncidentSeverity.HIGH
        assert "brute_force" in classification.attack_pattern.lower()


class TestIncidentManager:
    """Test the IncidentManager business logic following TDD principles"""

    @pytest.fixture
    def mock_db_manager(self):
        """Mock database manager for incident storage"""
        mock_db = AsyncMock()
        mock_db.create_incident = AsyncMock(return_value="incident_123")
        mock_db.get_incident = AsyncMock(return_value=None)
        mock_db.update_incident = AsyncMock()
        mock_db.list_incidents = AsyncMock(return_value=[])
        return mock_db

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service for compliance logging"""
        mock_audit = AsyncMock()
        mock_audit.log_incident_created = AsyncMock()
        mock_audit.log_incident_updated = AsyncMock()
        mock_audit.log_incident_closed = AsyncMock()
        return mock_audit

    @pytest.fixture
    def mock_notification_service(self):
        """Mock notification service for alerts"""
        mock_notify = AsyncMock()
        mock_notify.send_alert = AsyncMock()
        return mock_notify

    @pytest.fixture
    def incident_manager(self, mock_db_manager, mock_audit_service, mock_notification_service):
        """Create incident manager with mocked dependencies"""
        return IncidentManager(
            db_manager=mock_db_manager,
            audit_service=mock_audit_service,
            notification_service=mock_notification_service
        )

    @pytest.mark.asyncio
    async def test_create_incident_success(self, incident_manager, mock_db_manager, mock_audit_service):
        """Test successful incident creation"""
        # Given
        incident_data = {
            "title": "Security Breach Detected",
            "description": "Unauthorized access to sensitive data",
            "incident_type": IncidentType.DATA_BREACH,
            "severity": IncidentSeverity.CRITICAL,
            "reported_by": "security@company.com",
            "affected_systems": ["database", "api"]
        }

        # When
        incident = await incident_manager.create_incident(**incident_data)

        # Then
        assert incident.title == incident_data["title"]
        assert incident.status == IncidentStatus.OPEN
        assert incident.severity == IncidentSeverity.CRITICAL

        # Verify database storage
        mock_db_manager.create_incident.assert_called_once()

        # Verify audit logging
        mock_audit_service.log_incident_created.assert_called_once()

        # Verify notification for critical incidents
        mock_notification_service.send_alert.assert_called()

    @pytest.mark.asyncio
    async def test_create_incident_auto_classification(self, incident_manager):
        """Test incident creation with automatic classification"""
        # Given
        incident_data = {
            "title": "System Slowness",
            "description": "API response times very slow",
            "reported_by": "user@company.com"
            # No incident_type or severity provided
        }

        # When
        incident = await incident_manager.create_incident_with_classification(**incident_data)

        # Then
        assert incident.incident_type is not None  # Should be auto-classified
        assert incident.severity is not None       # Should be auto-determined
        assert incident.status == IncidentStatus.OPEN

    @pytest.mark.asyncio
    async def test_update_incident_status(self, incident_manager, mock_db_manager, mock_audit_service):
        """Test updating incident status"""
        # Given
        incident = IncidentRecord(
            title="Test Incident",
            description="Test description",
            incident_type=IncidentType.SYSTEM_OUTAGE,
            severity=IncidentSeverity.MEDIUM,
            reported_by="user@company.com"
        )

        mock_db_manager.get_incident.return_value = incident

        # When
        updated_incident = await incident_manager.update_incident_status(
            incident_id="incident_123",
            new_status=IncidentStatus.INVESTIGATING,
            updated_by="analyst@company.com",
            notes="Started investigation"
        )

        # Then
        assert updated_incident.status == IncidentStatus.INVESTIGATING

        # Verify database update
        mock_db_manager.update_incident.assert_called_once()

        # Verify audit logging
        mock_audit_service.log_incident_updated.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_escalation_for_critical_incidents(self, incident_manager, mock_notification_service):
        """Test automatic escalation for critical incidents"""
        # Given
        incident = await incident_manager.create_incident(
            title="Critical Data Breach",
            description="Massive data breach detected",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="system@company.com"
        )

        # Then
        # Verify escalation notifications sent
        assert mock_notification_service.send_alert.call_count >= 2  # Initial + escalation

        # Check escalation calls included appropriate recipients
        escalation_calls = [call for call in mock_notification_service.send_alert.call_args_list
                          if call.kwargs.get('escalation')]
        assert len(escalation_calls) > 0

    @pytest.mark.asyncio
    async def test_gdpr_breach_notification_workflow(self, incident_manager, mock_db_manager, mock_audit_service):
        """Test GDPR breach notification workflow"""
        # Given
        incident = await incident_manager.create_incident(
            title="Personal Data Breach",
            description="Unauthorized access to customer personal data",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="dpo@company.com",
            metadata={"personal_data_affected": True, "data_subjects_count": 10000}
        )

        # Mock database to return the incident
        mock_db_manager.get_incident.return_value = incident

        # When - Trigger GDPR notification workflow
        notification_result = await incident_manager.initiate_gdpr_breach_notification(
            incident_id=incident.incident_id,
            data_subjects_affected=10000,
            data_types_involved=["personal_data", "email_addresses"],
            contact_email="dpo@company.com"
        )

        # Then
        assert notification_result.success is True
        assert notification_result.supervisory_authority_notified is True
        assert notification_result.notification_deadline is not None

        # Verify audit logging of GDPR notification
        mock_audit_service.log_incident_updated.assert_called()

    @pytest.mark.asyncio
    async def test_incident_assignment_workflow(self, incident_manager, mock_db_manager):
        """Test incident assignment workflow"""
        # Given
        incident = await incident_manager.create_incident(
            title="Security Incident",
            description="Suspicious activity detected",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.HIGH,
            reported_by="monitoring@company.com"
        )

        mock_db_manager.get_incident.return_value = incident

        # When
        assigned_incident = await incident_manager.assign_incident(
            incident_id=incident.incident_id,
            assignee="security_expert@company.com",
            assigned_by="manager@company.com",
            reason="Subject matter expert required"
        )

        # Then
        assert assigned_incident.assignee == "security_expert@company.com"
        assert assigned_incident.assigned_by == "manager@company.com"

        # Verify database update
        mock_db_manager.update_incident.assert_called()

    @pytest.mark.asyncio
    async def test_incident_closure_workflow(self, incident_manager, mock_db_manager, mock_audit_service):
        """Test incident closure workflow with validation"""
        # Given
        incident = await incident_manager.create_incident(
            title="System Issue",
            description="Temporary system glitch",
            incident_type=IncidentType.SYSTEM_OUTAGE,
            severity=IncidentSeverity.LOW,
            reported_by="ops@company.com"
        )

        incident.update_status(IncidentStatus.RESOLVED)
        mock_db_manager.get_incident.return_value = incident

        closure_details = {
            "root_cause": "Temporary network connectivity issue",
            "resolution": "Network connectivity restored",
            "prevention_measures": ["Network monitoring enhanced"],
            "lessons_learned": "Network redundancy needs improvement"
        }

        # When
        closed_incident = await incident_manager.close_incident(
            incident_id=incident.incident_id,
            closed_by="engineer@company.com",
            closure_details=closure_details
        )

        # Then
        assert closed_incident.status == IncidentStatus.CLOSED
        assert closed_incident.closed_by == "engineer@company.com"
        assert closed_incident.closure_details == closure_details

        # Verify audit logging
        mock_audit_service.log_incident_closed.assert_called_once()

    @pytest.mark.asyncio
    async def test_incident_search_and_filtering(self, incident_manager, mock_db_manager):
        """Test incident search and filtering capabilities"""
        # Given
        search_criteria = {
            "severity": IncidentSeverity.HIGH,
            "status": IncidentStatus.OPEN,
            "incident_type": IncidentType.SECURITY_INCIDENT,
            "date_range": {
                "start": datetime.now(timezone.utc) - timedelta(days=7),
                "end": datetime.now(timezone.utc)
            }
        }

        mock_incidents = [
            IncidentRecord(
                title="Security Issue 1",
                description="Security incident",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.HIGH,
                reported_by="user@company.com"
            ),
            IncidentRecord(
                title="Security Issue 2",
                description="Another security incident",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.HIGH,
                reported_by="user@company.com"
            )
        ]
        mock_db_manager.list_incidents.return_value = mock_incidents

        # When
        results = await incident_manager.search_incidents(**search_criteria)

        # Then
        assert len(results) == 2
        mock_db_manager.list_incidents.assert_called_once_with(**search_criteria)

    @pytest.mark.asyncio
    async def test_incident_metrics_and_reporting(self, incident_manager, mock_db_manager):
        """Test incident metrics and reporting functionality"""
        # Given
        mock_incidents = [
            IncidentRecord(
                title="Incident 1",
                description="Critical incident",
                incident_type=IncidentType.DATA_BREACH,
                severity=IncidentSeverity.CRITICAL,
                reported_by="user@company.com"
            ),
            IncidentRecord(
                title="Incident 2",
                description="High severity incident",
                incident_type=IncidentType.SECURITY_INCIDENT,
                severity=IncidentSeverity.HIGH,
                reported_by="user@company.com"
            )
        ]
        mock_db_manager.list_incidents.return_value = mock_incidents

        # When
        metrics = await incident_manager.get_incident_metrics(
            start_date=datetime.now(timezone.utc) - timedelta(days=30),
            end_date=datetime.now(timezone.utc)
        )

        # Then
        assert metrics.total_incidents == 2
        assert metrics.by_severity[IncidentSeverity.CRITICAL] == 1
        assert metrics.by_severity[IncidentSeverity.HIGH] == 1
        assert metrics.average_resolution_time is not None
        assert metrics.gdpr_compliance_rate is not None


class TestGDPRCompliance:
    """Test specific GDPR compliance requirements for incident response"""

    @pytest.mark.asyncio
    async def test_72_hour_notification_tracking(self, incident_manager):
        """Test 72-hour notification deadline tracking for data breaches"""
        # Given - Create a data breach incident
        incident = await incident_manager.create_incident(
            title="Personal Data Breach",
            description="Customer data accessed by unauthorized party",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="dpo@company.com"
        )

        # When - Check notification deadline
        deadline_status = await incident_manager.check_gdpr_notification_deadline(
            incident_id=incident.incident_id
        )

        # Then
        assert deadline_status.hours_remaining is not None
        assert deadline_status.hours_remaining <= 72
        assert deadline_status.deadline_passed is False
        assert deadline_status.supervisory_authority_notified is False

    @pytest.mark.asyncio
    async def test_data_subject_notification_requirements(self, incident_manager):
        """Test data subject notification requirements for high-risk breaches"""
        # Given
        incident = await incident_manager.create_incident(
            title="High-Risk Data Breach",
            description="Personal data breach with high risk to rights and freedoms",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="dpo@company.com",
            metadata={
                "high_risk_to_data_subjects": True,
                "data_types_involved": ["special_category_data"],
                "affected_data_subjects": 5000
            }
        )

        # When - Assess notification requirements
        notification_requirements = await incident_manager.assess_data_subject_notification_requirements(
            incident_id=incident.incident_id
        )

        # Then
        assert notification_requirements.requires_notification is True
        assert notification_requirements.notification_timeline is not None
        assert "communication_mechanism" in notification_requirements.requirements

    @pytest.mark.asyncio
    async def test_incident_documentation_requirements(self, incident_manager):
        """Test GDPR documentation requirements for incidents"""
        # Given
        incident = await incident_manager.create_incident(
            title="Security Incident",
            description="Security breach requiring documentation",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.HIGH,
            reported_by="security@company.com"
        )

        # When - Generate incident report
        incident_report = await incident_manager.generate_gdpr_incident_report(
            incident_id=incident.incident_id
        )

        # Then
        assert incident_report.incident_details is not None
        assert incident_report.timeline is not None
        assert incident_report.impact_assessment is not None
        assert incident_report.measures_taken is not None
        assert incident_report.documentation_timestamp is not None

    @pytest.mark.asyncio
    async def test_data_protection_officer_notification(self, incident_manager, mock_notification_service):
        """Test automatic notification to Data Protection Officer"""
        # Given - Create a data breach incident
        incident = await incident_manager.create_incident(
            title="Data Breach",
            description="Personal data compromised",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="security@company.com"
        )

        # Then - DPO should be automatically notified
        dpo_notifications = [call for call in mock_notification_service.send_alert.call_args_list
                           if call.kwargs.get('recipient') == 'dpo@company.com']
        assert len(dpo_notifications) > 0

    @pytest.mark.asyncio
    async def test_incident_containment_measures(self, incident_manager):
        """Test automatic incident containment measures"""
        # Given
        incident = await incident_manager.create_incident(
            title="Active Security Attack",
            description="Ongoing unauthorized access attempts",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.CRITICAL,
            reported_by="security_system@company.com",
            metadata={"attack_in_progress": True, "source_ip": "192.168.1.100"}
        )

        # When - Apply automatic containment
        containment_result = await incident_manager.apply_automatic_containment(
            incident_id=incident.incident_id
        )

        # Then
        assert containment_result.success is True
        assert len(containment_result.actions_taken) > 0
        assert ContainmentAction.BLOCK_IP in containment_result.actions_taken
        assert containment_result.timestamp is not None

    @pytest.mark.asyncio
    async def test_incident_communication_protocol(self, incident_manager, mock_notification_service):
        """Test incident communication protocol for stakeholders"""
        # Given - Create a critical incident
        incident = await incident_manager.create_incident(
            title="Critical System Failure",
            description="Complete system outage affecting all services",
            incident_type=IncidentType.SYSTEM_OUTAGE,
            severity=IncidentSeverity.CRITICAL,
            reported_by="monitoring@company.com"
        )

        # Then - Verify proper stakeholder communication
        all_notifications = mock_notification_service.send_alert.call_args_list

        # Should have notified different stakeholder groups
        notification_types = [call.kwargs.get('notification_type') for call in all_notifications]
        assert 'executive_update' in notification_types
        assert 'technical_team' in notification_types
        assert 'customer_communication' in notification_types

    @pytest.mark.asyncio
    async def test_post_incident_review_requirements(self, incident_manager, mock_db_manager):
        """Test post-incident review and lessons learned requirements"""
        # Given
        incident = IncidentRecord(
            title="Security Breach",
            description="Security breach requiring review",
            incident_type=IncidentType.SECURITY_INCIDENT,
            severity=IncidentSeverity.HIGH,
            reported_by="security@company.com"
        )
        incident.update_status(IncidentStatus.RESOLVED)

        mock_db_manager.get_incident.return_value = incident

        # When - Conduct post-incident review
        review_result = await incident_manager.conduct_post_incident_review(
            incident_id=incident.incident_id,
            reviewer="incident_commander@company.com",
            review_findings={
                "root_cause_analysis": "Vulnerability in authentication system",
                "timeline_gaps": ["delay in detection", "slow response time"],
                "process_improvements": ["enhanced monitoring", "faster escalation"],
                "technical_improvements": ["multi-factor authentication", "rate limiting"],
                "training_needs": ["security awareness", "incident response procedures"]
            }
        )

        # Then
        assert review_result.review_completed is True
        assert review_result.lessons_learned_documented is True
        assert review_result.action_items_created is True
        assert review_result.follow_up_required is True