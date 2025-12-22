"""
Comprehensive Test Suite for Advanced Breach Notification Workflow

Following TDD principles, these tests are written first to define the expected behavior
of the breach notification system. All tests will fail initially until the implementation
is complete.

Test Coverage:
- BreachNotificationWorkflow core functionality
- RegulatoryComplianceEngine multi-jurisdiction support
- NotificationTemplateManager template system
- ApprovalWorkflowEngine approval workflows
- Multi-channel notification delivery
- Deadline monitoring and escalation
- Audit trail and compliance reporting
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List
import json

from src.models.incident import IncidentRecord, IncidentTimelineEntry
from src.models.enums import IncidentType, IncidentSeverity, NotificationChannel
from src.core.notification_service import NotificationService, NotificationResult


class TestBreachNotificationWorkflow:
    """Test suite for BreachNotificationWorkflow core functionality"""

    @pytest.fixture
    def mock_incident(self):
        """Create a mock data breach incident for testing"""
        return IncidentRecord(
            title="Customer Data Breach",
            description="Unauthorized access to customer PII data",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.HIGH,
            reported_by="security@company.com",
            affected_systems=["customer_database", "api_gateway"],
            metadata={
                "data_types_involved": ["name", "email", "address", "phone"],
                "estimated_records_affected": 50000,
                "breach_discovery_date": datetime.now().isoformat(),
                "breach_origin": "external_attack"
            }
        )

    @pytest.fixture
    def mock_notification_service(self):
        """Create a mock notification service"""
        service = Mock(spec=NotificationService)
        service.send_alert = AsyncMock(return_value=NotificationResult(
            success=True,
            channel=NotificationChannel.EMAIL,
            message_id="test_msg_123",
            delivery_confirmed=True,
            delivery_timestamp=datetime.now()
        ))
        service.send_bulk_alert = AsyncMock(return_value=[
            NotificationResult(success=True, channel=NotificationChannel.EMAIL)
        ])
        return service

    def test_workflow_initialization(self):
        """Test that BreachNotificationWorkflow initializes correctly"""
        # This test will fail until implementation
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow()

        assert workflow is not None
        assert hasattr(workflow, 'regulatory_engine')
        assert hasattr(workflow, 'template_manager')
        assert hasattr(workflow, 'approval_engine')
        assert hasattr(workflow, 'notification_service')

    @pytest.mark.asyncio
    async def test initiate_breach_notification_workflow(self, mock_incident, mock_notification_service):
        """Test initiating breach notification workflow for a data breach"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        # Test workflow initiation
        result = await workflow.initiate_breach_notification(
            incident=mock_incident,
            initiator_email="dpo@company.com",
            jurisdictions=["GDPR", "CCPA"],
            auto_assess=True
        )

        # Expected behavior - these will fail until implementation
        assert result["success"] is True
        assert result["workflow_id"] is not None
        assert result["regulatory_assessments"] is not None
        assert len(result["regulatory_assessments"]) > 0
        assert "GDPR" in result["regulatory_assessments"]
        assert "CCPA" in result["regulatory_assessments"]
        assert result["next_steps"] is not None
        assert result["deadlines"] is not None

    @pytest.mark.asyncio
    async def test_gdpr_72_hour_deadline_monitoring(self, mock_incident, mock_notification_service):
        """Test GDPR 72-hour deadline monitoring and alerts"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        # Create incident that's approaching deadline
        mock_incident.created_at = datetime.now() - timedelta(hours=70)

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        # Check deadline status
        deadline_status = await workflow.check_gdpr_deadline_status(mock_incident)

        # Expected behavior
        assert deadline_status is not None
        assert deadline_status["hours_remaining"] is not None
        assert deadline_status["hours_remaining"] <= 2
        assert deadline_status["deadline_passed"] is False
        assert deadline_status["alert_required"] is True
        assert deadline_status["escalation_level"] is not None

    @pytest.mark.asyncio
    async def test_multi_jurisdiction_compliance_check(self, mock_incident, mock_notification_service):
        """Test compliance checking across multiple jurisdictions"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        jurisdictions = ["GDPR_FR", "GDPR_DE", "CCPA", "PIPEDA", "LGPD", "PDPA"]

        compliance_result = await workflow.check_multi_jurisdiction_compliance(
            incident=mock_incident,
            jurisdictions=jurisdictions
        )

        # Expected behavior
        assert compliance_result["success"] is True
        assert len(compliance_result["jurisdiction_assessments"]) == len(jurisdictions)

        for jurisdiction in jurisdictions:
            assert jurisdiction in compliance_result["jurisdiction_assessments"]
            assessment = compliance_result["jurisdiction_assessments"][jurisdiction]
            assert "requires_notification" in assessment
            assert "deadline_hours" in assessment
            assert "local_requirements" in assessment

    @pytest.mark.asyncio
    async def test_approval_workflow_for_sensitive_notifications(self, mock_incident, mock_notification_service):
        """Test approval workflow for sensitive breach notifications"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        # Initiate approval workflow for sensitive notification
        approval_result = await workflow.initiate_approval_workflow(
            incident=mock_incident,
            notification_type="supervisory_authority",
            content="Test notification content",
            approvers=["dpo@company.com", "legal@company.com", "ceo@company.com"],
            approval_required=True
        )

        # Expected behavior
        assert approval_result["success"] is True
        assert approval_result["approval_id"] is not None
        assert approval_result["status"] in ["pending", "in_review"]
        assert approval_result["approvers"] is not None
        assert len(approval_result["approvers"]) >= 2
        assert approval_result["deadline"] is not None

    @pytest.mark.asyncio
    async def test_multilingual_notification_generation(self, mock_incident, mock_notification_service):
        """Test generation of multilingual notifications for data subjects"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        languages = ["en", "fr", "de", "es", "pt"]

        notification_result = await workflow.generate_multilingual_notifications(
            incident=mock_incident,
            template_name="data_subject_breach_notification",
            languages=languages,
            personalization_data={
                "company_name": "Test Company",
                "contact_email": "privacy@company.com",
                "breach_date": datetime.now().strftime("%Y-%m-%d"),
                "data_types": ["name", "email", "address"]
            }
        )

        # Expected behavior
        assert notification_result["success"] is True
        assert len(notification_result["translations"]) == len(languages)

        for lang in languages:
            assert lang in notification_result["translations"]
            translation = notification_result["translations"][lang]
            assert "subject" in translation
            assert "body" in translation
            assert "html_body" in translation
            assert len(translation["subject"]) > 0
            assert len(translation["body"]) > 0

    @pytest.mark.asyncio
    async def test_notification_delivery_with_retry_logic(self, mock_incident):
        """Test notification delivery with retry logic and escalation"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        # Mock notification service with initial failure
        mock_notification_service = Mock(spec=NotificationService)
        failing_result = NotificationResult(success=False, error_message="Service unavailable")
        success_result = NotificationResult(
            success=True,
            channel=NotificationChannel.EMAIL,
            message_id="msg_123",
            delivery_confirmed=True
        )

        # First call fails, second succeeds
        mock_notification_service.send_alert = AsyncMock(side_effect=[failing_result, success_result])

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        delivery_result = await workflow.send_notification_with_retry(
            recipient="test@example.com",
            subject="Test Breach Notification",
            message="Test message",
            notification_type="data_subject_notification",
            max_retries=3,
            retry_delay_seconds=1
        )

        # Expected behavior
        assert delivery_result["success"] is True
        assert delivery_result["retry_count"] >= 1
        assert delivery_result["final_status"] == "delivered"
        assert delivery_result["delivery_timestamp"] is not None

    @pytest.mark.asyncio
    async def test_audit_trail_maintenance(self, mock_incident, mock_notification_service):
        """Test comprehensive audit trail maintenance for compliance"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        # Perform various workflow actions
        await workflow.initiate_breach_notification(mock_incident, "test@company.com")

        # Generate audit trail
        audit_trail = await workflow.generate_audit_trail(mock_incident.incident_id)

        # Expected behavior
        assert audit_trail is not None
        assert audit_trail["incident_id"] == mock_incident.incident_id
        assert len(audit_trail["entries"]) > 0
        assert all("timestamp" in entry for entry in audit_trail["entries"])
        assert all("action" in entry for entry in audit_trail["entries"])
        assert all("performed_by" in entry for entry in audit_trail["entries"])

    @pytest.mark.asyncio
    async def test_regulatory_reporting_generation(self, mock_incident, mock_notification_service):
        """Test generation of regulatory reports for different authorities"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        # Generate reports for different regulatory bodies
        reports = await workflow.generate_regulatory_reports(
            incident=mock_incident,
            jurisdictions=["GDPR_FR", "CCPA", "PIPEDA"],
            report_format="json"
        )

        # Expected behavior
        assert reports["success"] is True
        assert len(reports["reports"]) == 3

        for jurisdiction in ["GDPR_FR", "CCPA", "PIPEDA"]:
            assert jurisdiction in reports["reports"]
            report = reports["reports"][jurisdiction]
            assert "content" in report
            assert "metadata" in report
            assert "required_fields" in report["metadata"]
            assert report["metadata"]["compliant"] is True

    @pytest.mark.asyncio
    async def test_escalation_procedures(self, mock_incident, mock_notification_service):
        """Test escalation procedures for missed deadlines"""
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        # Create incident past deadline
        mock_incident.created_at = datetime.now() - timedelta(hours=75)

        workflow = BreachNotificationWorkflow(notification_service=mock_notification_service)

        escalation_result = await workflow.handle_missed_deadline_escalation(
            incident=mock_incident,
            escalation_level=1
        )

        # Expected behavior
        assert escalation_result["success"] is True
        assert escalation_result["escalation_triggered"] is True
        assert escalation_result["escalation_level"] == 1
        assert escalation_result["notified_parties"] is not None
        assert len(escalation_result["notified_parties"]) > 0
        assert escalation_result["next_escalation_time"] is not None


class TestRegulatoryComplianceEngine:
    """Test suite for RegulatoryComplianceEngine"""

    @pytest.mark.asyncio
    async def test_gdpr_compliance_assessment(self):
        """Test GDPR compliance assessment"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        incident_data = {
            "data_types": ["name", "email", "address", "health_data"],
            "subjects_affected": 5000,
            "breach_type": "unauthorized_access",
            "encryption_present": False,
            "measures_taken": ["account_lockout", "investigation"]
        }

        assessment = await engine.assess_gdpr_compliance(incident_data)

        # Expected behavior - will fail until implementation
        assert assessment["jurisdiction"] == "GDPR"
        assert "risk_level" in assessment
        assert assessment["risk_level"] in ["low", "medium", "high"]
        assert "requires_notification" in assessment
        assert "deadline_hours" in assessment
        assert assessment["deadline_hours"] == 72
        assert "supervisory_authority_required" in assessment
        assert "data_subject_notification_required" in assessment
        assert "recommended_actions" in assessment
        assert len(assessment["recommended_actions"]) > 0

    @pytest.mark.asyncio
    async def test_ccpa_compliance_assessment(self):
        """Test CCPA/CPRA compliance assessment"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        incident_data = {
            "data_types": ["name", "email", "address", "ssn", "driver_license"],
            "residents_affected": 1000,
            "breach_type": "ransomware",
            "encryption_present": False
        }

        assessment = await engine.assess_ccpa_compliance(incident_data)

        # Expected behavior
        assert assessment["jurisdiction"] == "CCPA"
        assert "risk_level" in assessment
        assert "requires_notification" in assessment
        assert "deadline_hours" in assessment
        assert assessment["deadline_hours"] <= 72  # CCPA requires "reasonable time"
        assert "consumer_notification_required" in assessment
        assert "attorney_general_required" in assessment

    @pytest.mark.asyncio
    async def test_pipeda_compliance_assessment(self):
        """Test PIPEDA compliance assessment"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        incident_data = {
            "data_types": ["name", "email", "financial_info"],
            "individuals_affected": 500,
            "breach_type": "unauthorized_access",
            "harm_realization": True
        }

        assessment = await engine.assess_pipeda_compliance(incident_data)

        # Expected behavior
        assert assessment["jurisdiction"] == "PIPEDA"
        assert "requires_notification" in assessment
        assert "harm_assessment" in assessment
        assert "timeline_requirements" in assessment
        assert "privacy_commissioner_guidance" in assessment

    @pytest.mark.asyncio
    async def test_lgpd_compliance_assessment(self):
        """Test LGPD (Brazil) compliance assessment"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        incident_data = {
            "data_types": ["name", "cpf", "email", "phone"],
            "data_subjects_affected": 10000,
            "breach_type": "data_exfiltration",
            "risk_to_rights": True
        }

        assessment = await engine.assess_lgpd_compliance(incident_data)

        # Expected behavior
        assert assessment["jurisdiction"] == "LGPD"
        assert "requires_notification" in assessment
        assert "deadline_hours" in assessment
        assert "anpd_notification_required" in assessment
        assert "data_subject_notification_required" in assessment

    @pytest.mark.asyncio
    async def test_pdpa_compliance_assessment(self):
        """Test PDPA (Singapore) compliance assessment"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        incident_data = {
            "data_types": ["name", "nric", "email", "mobile"],
            "individuals_affected": 2000,
            "breach_type": "unauthorized_disclosure",
            "significant_harm_likelihood": True
        }

        assessment = await engine.assess_pdpa_compliance(incident_data)

        # Expected behavior
        assert assessment["jurisdiction"] == "PDPA"
        assert "requires_notification" in assessment
        assert "pdpc_notification_required" in assessment
        assert "assessment_timeline" in assessment
        assert "obligations_under_act" in assessment


class TestNotificationTemplateManager:
    """Test suite for NotificationTemplateManager"""

    @pytest.mark.asyncio
    async def test_template_rendering_with_multilingual_support(self):
        """Test template rendering with multilingual support"""
        from src.core.notification_template_manager import NotificationTemplateManager

        manager = NotificationTemplateManager()

        template_data = {
            "incident_id": "INC-2024-001",
            "company_name": "Test Company",
            "breach_date": "2024-01-15",
            "data_types": ["name", "email", "address"],
            "contact_email": "privacy@company.com"
        }

        # Render template in multiple languages
        languages = ["en", "fr", "de", "es"]
        rendered_templates = await manager.render_template_multilingual(
            template_name="data_subject_breach_notification",
            template_data=template_data,
            languages=languages
        )

        # Expected behavior - will fail until implementation
        assert rendered_templates["success"] is True
        assert len(rendered_templates["templates"]) == len(languages)

        for lang in languages:
            assert lang in rendered_templates["templates"]
            template = rendered_templates["templates"][lang]
            assert "subject" in template
            assert "body" in template
            assert "html_body" in template
            assert template["subject"] != ""
            assert template["body"] != ""

    @pytest.mark.asyncio
    async def test_supervisory_authority_template_generation(self):
        """Test generation of supervisory authority notification templates"""
        from src.core.notification_template_manager import NotificationTemplateManager

        manager = NotificationTemplateManager()

        template_data = {
            "incident_id": "INC-2024-001",
            "organization_name": "Test Organization",
            "dpo_contact": "dpo@company.com",
            "breach_description": "Unauthorized access to customer database",
            "data_categories": ["personal_data", "contact_info"],
            "subjects_affected": 5000,
            "measures_taken": ["immediate_containment", "investigation"],
            "potential_consequences": ["identity_theft", "fraud"]
        }

        # Generate GDPR supervisory authority notification
        notification = await manager.render_template(
            template_name="gdpr_supervisory_authority_notification",
            template_data=template_data,
            jurisdiction="GDPR",
            language="en"
        )

        # Expected behavior
        assert notification["success"] is True
        assert notification["subject"] is not None
        assert notification["body"] is not None
        assert notification["html_body"] is not None
        assert len(notification["body"]) > 500  # Should be comprehensive
        assert "Article 33" in notification["body"]  # GDPR reference

    @pytest.mark.asyncio
    async def test_template_customization_and_branding(self):
        """Test template customization with company branding"""
        from src.core.notification_template_manager import NotificationTemplateManager

        manager = NotificationTemplateManager()

        branding_config = {
            "company_name": "Acme Corp",
            "logo_url": "https://acme.com/logo.png",
            "primary_color": "#0066cc",
            "secondary_color": "#f0f0f0",
            "font_family": "Arial, sans-serif",
            "footer_text": "© 2024 Acme Corp. All rights reserved."
        }

        template_data = {
            "incident_id": "INC-2024-001",
            "breach_summary": "Brief breach description"
        }

        # Render with branding
        branded_template = await manager.render_template_with_branding(
            template_name="base_notification",
            template_data=template_data,
            branding=branding_config
        )

        # Expected behavior
        assert branded_template["success"] is True
        assert branding_config["company_name"] in branded_template["html_body"]
        assert branding_config["primary_color"] in branded_template["html_body"]
        assert branding_config["footer_text"] in branded_template["html_body"]

    @pytest.mark.asyncio
    async def test_template_validation_and_compliance(self):
        """Test template validation for regulatory compliance"""
        from src.core.notification_template_manager import NotificationTemplateManager

        manager = NotificationTemplateManager()

        # Test GDPR-compliant template
        gdpr_template = await manager.validate_template_compliance(
            template_name="data_subject_notification_gdpr",
            jurisdiction="GDPR",
            required_elements=[
                "incident_description",
                "data_categories",
                "rights_explanation",
                "contact_information",
                "remediation_steps"
            ]
        )

        # Expected behavior
        assert gdpr_template["compliant"] is True
        assert gdpr_template["missing_elements"] == []
        assert gdpr_template["compliance_score"] >= 0.9


class TestApprovalWorkflowEngine:
    """Test suite for ApprovalWorkflowEngine"""

    @pytest.mark.asyncio
    async def test_approval_workflow_initiation(self):
        """Test initiation of approval workflow"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        approval_request = {
            "request_type": "supervisory_authority_notification",
            "incident_id": "INC-2024-001",
            "content": "Test notification content",
            "jurisdiction": "GDPR",
            "urgency": "high",
            "requester": "dpo@company.com"
        }

        approvers = ["legal@company.com", "security@company.com", "ceo@company.com"]

        workflow_result = await engine.initiate_approval_workflow(
            request=approval_request,
            approvers=approvers,
            approval_required=True,
            deadline_hours=24
        )

        # Expected behavior - will fail until implementation
        assert workflow_result["success"] is True
        assert workflow_result["workflow_id"] is not None
        assert workflow_result["status"] == "pending"
        assert len(workflow_result["approvers"]) == len(approvers)
        assert workflow_result["deadline"] is not None
        assert workflow_result["approval_threshold"] is not None

    @pytest.mark.asyncio
    async def test_approval_processing_with_majority_vote(self):
        """Test approval processing with majority voting mechanism"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        # Simulate approval responses
        approval_responses = [
            {"approver": "legal@company.com", "decision": "approved", "comments": "Content is compliant"},
            {"approver": "security@company.com", "decision": "approved", "comments": "Technical details verified"},
            {"approver": "ceo@company.com", "decision": "approved", "comments": "Approved for sending"}
        ]

        processing_result = await engine.process_approval_responses(
            workflow_id="WF-001",
            responses=approval_responses,
            approval_threshold=0.67  # 2/3 majority
        )

        # Expected behavior
        assert processing_result["success"] is True
        assert processing_result["final_decision"] == "approved"
        assert processing_result["approval_count"] == 3
        assert processing_result["rejection_count"] == 0
        assert processing_result["approval_percentage"] == 1.0
        assert processing_result["threshold_met"] is True

    @pytest.mark.asyncio
    async def test_approval_denial_and_escalation(self):
        """Test approval denial and escalation procedures"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        # Simulate approval responses with denial
        approval_responses = [
            {"approver": "legal@company.com", "decision": "rejected", "comments": "Legal issues identified"},
            {"approver": "security@company.com", "decision": "approved", "comments": "Technical aspects OK"}
        ]

        processing_result = await engine.process_approval_responses(
            workflow_id="WF-002",
            responses=approval_responses,
            approval_threshold=1.0  # Unanimous approval required
        )

        # Expected behavior
        assert processing_result["success"] is True
        assert processing_result["final_decision"] == "rejected"
        assert processing_result["escalation_required"] is True
        assert processing_result["escalation_level"] is not None
        assert processing_result["next_reviewer"] is not None

    @pytest.mark.asyncio
    async def test_approval_deadline_monitoring(self):
        """Test approval deadline monitoring and reminders"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        # Check pending approvals approaching deadline
        deadline_status = await engine.check_approval_deadlines()

        # Expected behavior
        assert deadline_status["success"] is True
        assert "pending_approvals" in deadline_status
        assert "overdue_approvals" in deadline_status
        assert "reminders_sent" in deadline_status
        assert isinstance(deadline_status["pending_approvals"], list)

    @pytest.mark.asyncio
    async def test_conditional_approval_logic(self):
        """Test conditional approval logic based on incident severity"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        # Test different severity levels
        test_cases = [
            {
                "severity": "critical",
                "expected_approvers": ["dpo", "legal", "ceo", "board"],
                "expected_threshold": 1.0
            },
            {
                "severity": "high",
                "expected_approvers": ["dpo", "legal", "security_lead"],
                "expected_threshold": 0.67
            },
            {
                "severity": "medium",
                "expected_approvers": ["dpo", "security_lead"],
                "expected_threshold": 0.5
            }
        ]

        for case in test_cases:
            approval_config = engine.get_approval_config_for_severity(case["severity"])

            assert approval_config["required_approvers"] == case["expected_approvers"]
            assert approval_config["approval_threshold"] == case["expected_threshold"]
            assert approval_config["deadline_hours"] is not None


class TestIntegrationBreachNotificationWorkflow:
    """Integration tests for complete breach notification workflow"""

    @pytest.mark.asyncio
    async def test_end_to_end_breach_notification_workflow(self):
        """Test complete end-to-end breach notification workflow"""
        # This test will verify the complete integration of all components

        # 1. Create incident
        incident = IncidentRecord(
            title="Major Data Breach",
            description="Unauthorized access to customer database",
            incident_type=IncidentType.DATA_BREACH,
            severity=IncidentSeverity.CRITICAL,
            reported_by="security@company.com"
        )

        # 2. Initialize complete workflow (will fail until implementation)
        from src.core.breach_notification_workflow import BreachNotificationWorkflow

        workflow = BreachNotificationWorkflow()

        # 3. Initiate breach notification process
        initiation_result = await workflow.initiate_breach_notification(
            incident=incident,
            initiator_email="dpo@company.com",
            jurisdictions=["GDPR", "CCPA", "PIPEDA"],
            auto_assess=True
        )

        assert initiation_result["success"] is True
        assert initiation_result["workflow_id"] is not None

        # 4. Check regulatory compliance
        compliance_result = await workflow.check_multi_jurisdiction_compliance(
            incident=incident,
            jurisdictions=["GDPR", "CCPA", "PIPEDA"]
        )

        assert compliance_result["success"] is True
        assert len(compliance_result["jurisdiction_assessments"]) == 3

        # 5. Generate templates
        template_result = await workflow.generate_notification_templates(
            incident=incident,
            notification_types=["supervisory_authority", "data_subject"],
            languages=["en", "fr", "es"]
        )

        assert template_result["success"] is True
        assert len(template_result["templates"]) > 0

        # 6. Initiate approval workflow
        approval_result = await workflow.initiate_approval_workflow(
            incident=incident,
            notification_type="supervisory_authority",
            content=template_result["templates"]["supervisory_authority"]["en"]["body"],
            approvers=["dpo@company.com", "legal@company.com"]
        )

        assert approval_result["success"] is True
        assert approval_result["approval_id"] is not None

        # 7. Process approval (simulate)
        process_result = await workflow.simulate_approval_completion(
            approval_id=approval_result["approval_id"],
            decision="approved",
            approver="legal@company.com"
        )

        assert process_result["success"] is True

        # 8. Send notifications
        notification_result = await workflow.send_approved_notifications(
            workflow_id=initiation_result["workflow_id"]
        )

        assert notification_result["success"] is True
        assert len(notification_result["sent_notifications"]) > 0

        # 9. Generate audit trail
        audit_result = await workflow.generate_audit_trail(incident.incident_id)

        assert audit_result["success"] is True
        assert len(audit_result["entries"]) > 0

        # 10. Verify compliance reporting
        reporting_result = await workflow.generate_compliance_report(
            incident_id=incident.incident_id,
            jurisdictions=["GDPR", "CCPA", "PIPEDA"]
        )

        assert reporting_result["success"] is True
        assert "compliance_summary" in reporting_result


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])