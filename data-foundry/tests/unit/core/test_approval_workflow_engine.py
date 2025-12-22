"""
Unit Tests for ApprovalWorkflowEngine

TDD-focused unit tests for approval workflow management, multi-level approvals,
escalation procedures, and compliance validation for sensitive breach notifications.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import json
from typing import Dict, Any, List

from src.models.enums import IncidentSeverity


class TestApprovalWorkflowEngine:
    """Comprehensive test suite for ApprovalWorkflowEngine"""

    @pytest.fixture
    def approval_engine(self):
        """Initialize approval workflow engine for testing"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine
        return ApprovalWorkflowEngine()

    @pytest.fixture
    def sample_approval_request(self):
        """Sample approval request for testing"""
        return {
            "request_type": "supervisory_authority_notification",
            "incident_id": "INC-2024-001",
            "incident_severity": "high",
            "content": {
                "subject": "GDPR Data Breach Notification - Incident INC-2024-001",
                "body": "Formal notification of data breach affecting EU citizens...",
                "attachments": ["risk_assessment.pdf", "timeline.pdf"]
            },
            "jurisdiction": "GDPR",
            "urgency": "high",
            "requester": "dpo@company.com",
            "business_impact": "significant_risk_to_rights",
            "estimated_recipients": 25000,
            "special_categories": True
        }

    def test_engine_initialization(self):
        """Test that ApprovalWorkflowEngine initializes correctly"""
        from src.core.approval_workflow_engine import ApprovalWorkflowEngine

        engine = ApprovalWorkflowEngine()

        # Expected attributes and capabilities
        assert engine is not None
        assert hasattr(engine, 'workflow_store')
        assert hasattr(engine, 'approval_rules')
        assert hasattr(engine, 'escalation_manager')
        assert hasattr(engine, 'notification_service')

        # Check that approval configurations are loaded
        assert len(engine.approval_configs) > 0
        assert "critical" in engine.approval_configs
        assert "high" in engine.approval_configs
        assert "medium" in engine.approval_configs
        assert "low" in engine.approval_configs

    @pytest.mark.asyncio
    async def test_approval_workflow_initiation(self, approval_engine, sample_approval_request):
        """Test initiation of approval workflow"""
        approvers = [
            {"email": "legal@company.com", "role": "legal_counsel", "required": True},
            {"email": "security@company.com", "role": "security_lead", "required": True},
            {"email": "compliance@company.com", "role": "compliance_officer", "required": True},
            {"email": "ceo@company.com", "role": "executive_sponsor", "required": False}
        ]

        result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=approvers,
            approval_required=True,
            deadline_hours=24,
            approval_threshold=0.75  # 75% approval required
        )

        # Expected workflow initiation result
        assert result["success"] is True
        assert result["workflow_id"] is not None
        assert result["status"] == "pending_approval"
        assert len(result["approvers"]) == len(approvers)
        assert result["approval_threshold"] == 0.75
        assert result["deadline"] is not None
        assert result["created_at"] is not None

        # Check approver details
        for approver in result["approvers"]:
            assert "email" in approver
            assert "role" in approver
            assert "required" in approver
            assert "approval_status" in approver
            assert approver["approval_status"] == "pending"

    @pytest.mark.asyncio
    async def test_severity_based_approval_configuration(self, approval_engine):
        """Test that approval requirements change based on incident severity"""
        severity_scenarios = [
            {
                "severity": "critical",
                "expected_approvers": ["dpo", "legal", "ceo", "board_member"],
                "expected_threshold": 1.0,  # 100% unanimous
                "expected_deadline_hours": 6
            },
            {
                "severity": "high",
                "expected_approvers": ["dpo", "legal", "security_lead"],
                "expected_threshold": 0.67,  # 2/3 majority
                "expected_deadline_hours": 12
            },
            {
                "severity": "medium",
                "expected_approvers": ["dpo", "security_lead"],
                "expected_threshold": 0.5,  # Simple majority
                "expected_deadline_hours": 24
            },
            {
                "severity": "low",
                "expected_approvers": ["dpo"],
                "expected_threshold": 0.5,  # Single approver
                "expected_deadline_hours": 48
            }
        ]

        for scenario in severity_scenarios:
            config = approval_engine.get_approval_config_for_severity(scenario["severity"])

            assert config["required_approvers"] == scenario["expected_approvers"]
            assert config["approval_threshold"] == scenario["expected_threshold"]
            assert config["deadline_hours"] == scenario["expected_deadline_hours"]
            assert "escalation_rules" in config

    @pytest.mark.asyncio
    async def test_approval_submission_and_processing(self, approval_engine, sample_approval_request):
        """Test submission and processing of individual approvals"""
        # First initiate workflow
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel", "required": True},
                {"email": "security@company.com", "role": "security_lead", "required": True}
            ],
            approval_threshold=0.5
        )

        workflow_id = workflow_result["workflow_id"]

        # Submit first approval
        approval_response = {
            "approver_email": "legal@company.com",
            "decision": "approved",
            "comments": "Content is legally compliant and meets GDPR requirements.",
            "reviewed_at": datetime.now().isoformat(),
            "confidence_level": "high"
        }

        approval_result = await approval_engine.submit_approval(
            workflow_id=workflow_id,
            approval_response=approval_response
        )

        # Expected approval submission result
        assert approval_result["success"] is True
        assert approval_result["approver"] == "legal@company.com"
        assert approval_result["decision"] == "approved"
        assert approval_result["workflow_status"] == "pending_approval"  # Still waiting for other approvers

        # Check workflow status update
        updated_workflow = await approval_engine.get_workflow_status(workflow_id)
        assert updated_workflow["approvers"][0]["approval_status"] == "approved"
        assert updated_workflow["approvers"][1]["approval_status"] == "pending"

    @pytest.mark.asyncio
    async def test_approval_threshold_evaluation(self, approval_engine, sample_approval_request):
        """Test evaluation of approval thresholds and final decisions"""
        # Initiate workflow with 3 approvers, 2/3 threshold
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel", "required": True},
                {"email": "security@company.com", "role": "security_lead", "required": True},
                {"email": "compliance@company.com", "role": "compliance_officer", "required": False}
            ],
            approval_threshold=0.67  # 2 out of 3 required
        )

        workflow_id = workflow_result["workflow_id"]

        # Submit approvals (2 approve, 1 rejects)
        approvals = [
            {
                "approver_email": "legal@company.com",
                "decision": "approved",
                "comments": "Legally compliant"
            },
            {
                "approver_email": "security@company.com",
                "decision": "approved",
                "comments": "Security measures adequate"
            },
            {
                "approver_email": "compliance@company.com",
                "decision": "rejected",
                "comments": "Need additional compliance documentation"
            }
        ]

        results = []
        for approval in approvals:
            result = await approval_engine.submit_approval(
                workflow_id=workflow_id,
                approval_response=approval
            )
            results.append(result)

        # Expected final decision (threshold met with 2/3 approval)
        final_status = await approval_engine.get_workflow_status(workflow_id)
        assert final_status["final_decision"] == "approved"
        assert final_status["approval_percentage"] == 0.67
        assert final_status["threshold_met"] is True
        assert final_status["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approval_rejection_and_escalation(self, approval_engine, sample_approval_request):
        """Test approval rejection and escalation procedures"""
        # Initiate workflow with unanimous approval required
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel", "required": True},
                {"email": "security@company.com", "role": "security_lead", "required": True}
            ],
            approval_threshold=1.0  # Unanimous approval required
        )

        workflow_id = workflow_result["workflow_id"]

        # Submit conflicting approvals (1 approve, 1 reject)
        approvals = [
            {
                "approver_email": "legal@company.com",
                "decision": "approved",
                "comments": "Content is compliant"
            },
            {
                "approver_email": "security@company.com",
                "decision": "rejected",
                "comments": "Security concerns not fully addressed",
                "blocking_issues": ["insufficient_technical_details", "missing_mitigation_steps"]
            }
        ]

        for approval in approvals:
            await approval_engine.submit_approval(
                workflow_id=workflow_id,
                approval_response=approval
            )

        # Check final status (should be rejected due to threshold not met)
        final_status = await approval_engine.get_workflow_status(workflow_id)
        assert final_status["final_decision"] == "rejected"
        assert final_status["approval_percentage"] == 0.5
        assert final_status["threshold_met"] is False
        assert final_status["escalation_required"] is True

        # Test escalation process
        escalation_result = await approval_engine.initiate_escalation(
            workflow_id=workflow_id,
            escalation_level=1,
            escalation_reason="approval_threshold_not_met",
            escalation_approvers=["ceo@company.com", "board_member@company.com"]
        )

        assert escalation_result["success"] is True
        assert escalation_result["escalation_level"] == 1
        assert len(escalation_result["escalation_approvers"]) == 2
        assert escalation_result["escalation_deadline"] is not None

    @pytest.mark.asyncio
    async def test_conditional_approval_logic(self, approval_engine):
        """Test conditional approval based on content and risk factors"""
        # Test scenarios with different conditions
        conditional_scenarios = [
            {
                "name": "High Risk Special Categories",
                "conditions": {
                    "special_categories": True,
                    "subjects_affected": 50000,
                    "cross_border_transfer": True
                },
                "expected_additional_approvers": ["board_member", "ethics_officer"]
            },
            {
                "name": "Media Attention Likely",
                "conditions": {
                    "media_risk": "high",
                    "brand_reputation_impact": "severe"
                },
                "expected_additional_approvers": ["pr_director", "executive_communications"]
            },
            {
                "name": "Financial Regulatory Impact",
                "conditions": {
                    "financial_data_involved": True,
                    "regulatory_bodies": ["SEC", "FCA"]
                },
                "expected_additional_approvers": ["cfo", "investor_relations"]
            }
        ]

        for scenario in conditional_scenarios:
            conditional_config = await approval_engine.evaluate_conditional_approvals(
                conditions=scenario["conditions"],
                base_severity="high"
            )

            assert conditional_config["additional_approvers_required"] is True
            for approver in scenario["expected_additional_approvers"]:
                assert approver in conditional_config["additional_approvers"]

    @pytest.mark.asyncio
    async def test_approval_deadline_monitoring(self, approval_engine):
        """Test monitoring of approval deadlines and automatic reminders"""
        # Create workflows with different deadlines
        workflows = []
        for hours_deadline in [1, 6, 12, 24, 48]:
            workflow = await approval_engine.initiate_approval_workflow(
                request=sample_approval_request,
                approvers=[{"email": f"approver_{hours_deadline}@company.com", "role": "reviewer"}],
                approval_threshold=0.5,
                deadline_hours=hours_deadline
            )
            workflows.append(workflow)

        # Check deadline status
        deadline_status = await approval_engine.check_approval_deadlines()

        # Expected deadline monitoring results
        assert deadline_status["success"] is True
        assert "pending_approvals" in deadline_status
        assert "approaching_deadlines" in deadline_status
        assert "overdue_approvals" in deadline_status
        assert "reminders_sent" in deadline_status

        # Check that appropriate reminders are sent
        assert len(deadline_status["reminders_sent"]) >= 1
        for reminder in deadline_status["reminders_sent"]:
            assert "workflow_id" in reminder
            assert "approver_email" in reminder
            assert "reminder_type" in reminder

    @pytest.mark.asyncio
    async def test_approval_delegation_and_proxy(self, approval_engine, sample_approval_request):
        """Test approval delegation and proxy approval capabilities"""
        # Initiate workflow
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel", "required": True},
                {"email": "security@company.com", "role": "security_lead", "required": True}
            ],
            approval_threshold=0.5
        )

        workflow_id = workflow_result["workflow_id"]

        # Set up delegation
        delegation_result = await approval_engine.setup_delegation(
            delegator="legal@company.com",
            delegate="legal_deputy@company.com",
            delegation_scope="all_gdpr_notifications",
            delegation_start=datetime.now(),
            delegation_end=datetime.now() + timedelta(days=30),
            reason="legal_counsel_on_vacation"
        )

        assert delegation_result["success"] is True
        assert delegation_result["delegation_id"] is not None

        # Submit approval through delegate
        proxy_approval = {
            "approver_email": "legal_deputy@company.com",
            "decision": "approved",
            "comments": "Approved on behalf of legal@company.com",
            "delegation_id": delegation_result["delegation_id"]
        }

        approval_result = await approval_engine.submit_approval(
            workflow_id=workflow_id,
            approval_response=proxy_approval
        )

        assert approval_result["success"] is True
        assert approval_result["delegation_used"] is True
        assert approval_result["original_approver"] == "legal@company.com"

    @pytest.mark.asyncio
    async def test_approval_workflow_audit_trail(self, approval_engine, sample_approval_request):
        """Test comprehensive audit trail for approval workflows"""
        # Initiate and process complete workflow
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel"},
                {"email": "security@company.com", "role": "security_lead"}
            ],
            approval_threshold=0.5
        )

        workflow_id = workflow_result["workflow_id"]

        # Submit approvals
        await approval_engine.submit_approval(
            workflow_id=workflow_id,
            approval_response={
                "approver_email": "legal@company.com",
                "decision": "approved",
                "comments": "Legally compliant"
            }
        )

        await approval_engine.submit_approval(
            workflow_id=workflow_id,
            approval_response={
                "approver_email": "security@company.com",
                "decision": "approved",
                "comments": "Security verified"
            }
        )

        # Generate audit trail
        audit_trail = await approval_engine.generate_audit_trail(workflow_id)

        # Expected comprehensive audit trail
        assert audit_trail["success"] is True
        assert audit_trail["workflow_id"] == workflow_id
        assert len(audit_trail["events"]) >= 5  # Initiation + 2 approvals + decision

        # Check required audit fields
        for event in audit_trail["events"]:
            assert "timestamp" in event
            assert "event_type" in event
            assert "user_id" in event
            assert "ip_address" in event
            assert "user_agent" in event
            assert "action_details" in event

        # Check workflow completion
        assert audit_trail["workflow_completed"] is True
        assert audit_trail["final_decision"] == "approved"
        assert audit_trail["completion_timestamp"] is not None

    @pytest.mark.asyncio
    async def test_parallel_approval_workflows(self, approval_engine):
        """Test handling of parallel approval workflows for different jurisdictions"""
        # Create parallel workflows for different jurisdictions
        jurisdiction_configs = [
            {
                "jurisdiction": "GDPR",
                "approvers": ["dpo_eu@company.com", "legal_eu@company.com"],
                "deadline_hours": 72
            },
            {
                "jurisdiction": "CCPA",
                "approvers": ["privacy_officer_us@company.com", "legal_us@company.com"],
                "deadline_hours": 48
            },
            {
                "jurisdiction": "PIPEDA",
                "approvers": ["privacy_officer_ca@company.com"],
                "deadline_hours": 24
            }
        ]

        parallel_workflows = []
        for config in jurisdiction_configs:
            request = sample_approval_request.copy()
            request["jurisdiction"] = config["jurisdiction"]

            workflow = await approval_engine.initiate_approval_workflow(
                request=request,
                approvers=[{"email": email, "role": "reviewer"} for email in config["approvers"]],
                deadline_hours=config["deadline_hours"]
            )
            parallel_workflows.append(workflow)

        # Get combined status
        combined_status = await approval_engine.get_parallel_workflow_status(
            [w["workflow_id"] for w in parallel_workflows]
        )

        # Expected parallel workflow status
        assert combined_status["success"] is True
        assert len(combined_status["workflows"]) == len(jurisdiction_configs)
        assert combined_status["overall_status"] == "pending_approval"

        # Check individual workflow statuses
        for workflow in combined_status["workflows"]:
            assert "workflow_id" in workflow
            assert "jurisdiction" in workflow
            assert "status" in workflow
            assert "deadline" in workflow

    @pytest.mark.asyncio
    async def test_approval_workflow_integration_with_notifications(self, approval_engine):
        """Test integration with notification system for approval requests"""
        # Mock notification service
        mock_notification_service = Mock()
        mock_notification_service.send_alert = AsyncMock(return_value={"success": True})

        approval_engine.notification_service = mock_notification_service

        # Initiate workflow and verify notifications are sent
        workflow_result = await approval_engine.initiate_approval_workflow(
            request=sample_approval_request,
            approvers=[
                {"email": "legal@company.com", "role": "legal_counsel"},
                {"email": "security@company.com", "role": "security_lead"}
            ],
            approval_threshold=0.5
        )

        # Verify notification was sent
        assert mock_notification_service.send_alert.called
        call_args = mock_notification_service.send_alert.call_args
        assert "approval_request" in str(call_args)

        # Submit approval and verify notification
        await approval_engine.submit_approval(
            workflow_id=workflow_result["workflow_id"],
            approval_response={
                "approver_email": "legal@company.com",
                "decision": "approved",
                "comments": "Approved"
            }
        )

        # Verify approval notification was sent
        assert mock_notification_service.send_alert.call_count >= 2  # Initial request + approval notification

    @pytest.mark.asyncio
    async def test_approval_workflow_compliance_validation(self, approval_engine):
        """Test compliance validation within approval workflows"""
        # Create compliance-sensitive approval request
        compliance_request = sample_approval_request.copy()
        compliance_request.update({
            "compliance_checks_required": [
                "gdpr_article_33_compliance",
                "data_minimization_principles",
                "retention_policy_compliance",
                "cross_border_transfer_legitimacy"
            ],
            "risk_assessment_document": "risk_assessment_v2.pdf",
            "d Impact_assessment": "required"
        })

        workflow_result = await approval_engine.initiate_approval_workflow(
            request=compliance_request,
            approvers=[
                {"email": "dpo@company.com", "role": "data_protection_officer"},
                {"email": "compliance@company.com", "role": "compliance_officer"}
            ],
            approval_threshold=1.0,  # Unanimous approval for compliance
            compliance_validation_required=True
        )

        # Check that compliance validation is triggered
        workflow_id = workflow_result["workflow_id"]
        compliance_status = await approval_engine.get_compliance_validation_status(workflow_id)

        assert compliance_status["validation_required"] is True
        assert len(compliance_status["compliance_checks"]) == 4
        assert compliance_status["validation_status"] == "in_progress"

        # Submit compliance approval with validation confirmation
        compliance_approval = {
            "approver_email": "dpo@company.com",
            "decision": "approved",
            "comments": "All compliance requirements verified and met",
            "compliance_confirmation": {
                "gdpr_article_33_compliance": True,
                "data_minimization_principles": True,
                "retention_policy_compliance": True,
                "cross_border_transfer_legitimacy": True
            }
        }

        await approval_engine.submit_approval(
            workflow_id=workflow_id,
            approval_response=compliance_approval
        )

        # Verify compliance validation is updated
        updated_compliance_status = await approval_engine.get_compliance_validation_status(workflow_id)
        assert updated_compliance_status["validation_status"] == "passed"
        assert all(updated_compliance_status["compliance_checks"][check] for check in updated_compliance_status["compliance_checks"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])