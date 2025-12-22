"""
Unit Tests for RegulatoryComplianceEngine

TDD-focused unit tests for multi-jurisdiction regulatory compliance checking.
These tests define the expected behavior of the compliance engine for various
privacy regulations worldwide.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import json

from src.models.enums import IncidentType, IncidentSeverity


class TestRegulatoryComplianceEngine:
    """Comprehensive test suite for RegulatoryComplianceEngine"""

    @pytest.fixture
    def compliance_engine(self):
        """Initialize compliance engine for testing"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine
        return RegulatoryComplianceEngine()

    @pytest.fixture
    def sample_breach_data(self):
        """Sample breach data for testing compliance assessments"""
        return {
            "incident_id": "INC-2024-001",
            "incident_type": "data_breach",
            "discovery_date": datetime.now(),
            "data_types": ["name", "email", "address", "phone", "ssn", "health_records"],
            "subjects_affected": 10000,
            "breach_cause": "external_attack",
            "encryption_present": False,
            "measures_taken": ["immediate_containment", "forensic_investigation", "password_reset"],
            "notification_history": [],
            "risk_factors": ["sensitive_data", "large_scale", "no_encryption"]
        }

    def test_engine_initialization(self):
        """Test that RegulatoryComplianceEngine initializes with all required components"""
        from src.core.regulatory_compliance_engine import RegulatoryComplianceEngine

        engine = RegulatoryComplianceEngine()

        # Expected attributes and capabilities
        assert engine is not None
        assert hasattr(engine, 'jurisdiction_configs')
        assert hasattr(engine, 'compliance_rules')
        assert hasattr(engine, 'notification_requirements')
        assert hasattr(engine, 'deadline_calculators')

        # Check that major jurisdictions are configured
        supported_jurisdictions = engine.get_supported_jurisdictions()
        assert "GDPR" in supported_jurisdictions
        assert "CCPA" in supported_jurisdictions
        assert "PIPEDA" in supported_jurisdictions
        assert "LGPD" in supported_jurisdictions
        assert "PDPA" in supported_jurdictions

    @pytest.mark.asyncio
    async def test_gdpr_compliance_assessment_critical_breach(self, compliance_engine, sample_breach_data):
        """Test GDPR compliance assessment for critical data breach"""
        # Create high-risk scenario
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "subjects_affected": 50000,
            "data_types": ["health_records", "biometric_data", "genetic_data"],
            "special_category_data": True,
            "cross_border_transfer": True
        })

        assessment = await compliance_engine.assess_gdpr_compliance(breach_data)

        # Expected GDPR assessment results
        assert assessment["jurisdiction"] == "GDPR"
        assert assessment["risk_level"] == "high"
        assert assessment["requires_notification"] is True
        assert assessment["supervisory_authority_required"] is True
        assert assessment["data_subject_notification_required"] is True
        assert assessment["deadline_hours"] == 72
        assert assessment["special_categories_involved"] is True

        # Check specific GDPR requirements
        assert "communication_details" in assessment["required_content"]
        assert "likely_consequences" in assessment["required_content"]
        assert "measures_taken" in assessment["required_content"]
        assert "dpo_contact_details" in assessment["required_content"]

        # Check recommendations
        assert "recommended_actions" in assessment
        assert len(assessment["recommended_actions"]) > 0
        assert any("immediate_notification" in action.lower() for action in assessment["recommended_actions"])

    @pytest.mark.asyncio
    async def test_gdpr_compliance_assessment_low_risk_breach(self, compliance_engine, sample_breach_data):
        """Test GDPR compliance assessment for low-risk breach that may not require notification"""
        # Create low-risk scenario
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "subjects_affected": 50,
            "data_types": ["name", "email"],
            "encryption_present": True,
            "encryption_bypassed": False,
            "unlikely_to_risk_rights": True
        })

        assessment = await compliance_engine.assess_gdpr_compliance(breach_data)

        # Expected low-risk assessment
        assert assessment["risk_level"] == "low"
        assert assessment["requires_notification"] is False
        assert assessment["notification_waiver_reasons"] is not None
        assert len(assessment["notification_waiver_reasons"]) > 0

    @pytest.mark.asyncio
    async def test_ccpa_compliance_assessment(self, compliance_engine, sample_breach_data):
        """Test CCPA/CPRA compliance assessment"""
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "california_residents_affected": 5000,
            "data_types": ["name", "email", "ssn", "driver_license", "financial_info"],
            "breach_cause": "ransomware",
            "encryption_present": False
        })

        assessment = await compliance_engine.assess_ccpa_compliance(breach_data)

        # Expected CCPA assessment
        assert assessment["jurisdiction"] == "CCPA"
        assert assessment["requires_notification"] is True
        assert "consumer_notification_required" in assessment
        assert assessment["consumer_notification_required"] is True
        assert "attorney_general_required" in assessment

        # Check deadline calculation (CCPA requires "reasonable time")
        assert assessment["deadline_hours"] is not None
        assert assessment["deadline_hours"] <= 72

        # Check specific CCPA requirements
        assert "breach_description" in assessment["required_content"]
        assert "data_types_compromised" in assessment["required_content"]
        assert "consumer_protection_steps" in assessment["required_content"]

    @pytest.mark.asyncio
    async def test_pipeda_compliance_assessment(self, compliance_engine, sample_breach_data):
        """Test PIPEDA (Canada) compliance assessment"""
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "canadians_affected": 1000,
            "data_types": ["name", "email", "health_info", "financial_data"],
            "harm_realization": True,
            "harm_types": ["identity_theft", "financial_loss", "embarrassment"]
        })

        assessment = await compliance_engine.assess_pipeda_compliance(breach_data)

        # Expected PIPEDA assessment
        assert assessment["jurisdiction"] == "PIPEDA"
        assert assessment["requires_notification"] is True
        assert "harm_assessment" in assessment
        assert assessment["harm_assessment"]["significant_harm"] is True
        assert assessment["privacy_commissioner_required"] is True
        assert assessment["individual_notification_required"] is True

        # Check timeline requirements
        assert "timeline_requirements" in assessment
        assert assessment["timeline_requirements"]["notification_after_breach_discovery"] is not None

    @pytest.mark.asyncio
    async def test_lgpd_compliance_assessment(self, plagiarism_engine, sample_breach_data):
        """Test LGPD (Brazil) compliance assessment"""
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "brazilian_residents_affected": 15000,
            "data_types": ["name", "cpf", "email", "phone", "location_data"],
            "risk_to_rights": True,
            "relevant_data_types": ["personal_data", "sensitive_personal_data"]
        })

        assessment = await plagiarism_engine.assess_lgpd_compliance(breach_data)

        # Expected LGPD assessment
        assert assessment["jurisdiction"] == "LGPD"
        assert assessment["requires_notification"] is True
        assert assessment["anpd_notification_required"] is True  # ANPD = Brazilian National Data Protection Authority
        assert assessment["data_subject_notification_required"] is True
        assert assessment["deadline_hours"] is not None
        assert "communication_plan" in assessment["required_content"]

    @pytest.mark.asyncio
    async def test_pdpa_compliance_assessment(self, compliance_engine, sample_breach_data):
        """Test PDPA (Singapore) compliance assessment"""
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "singapore_residents_affected": 2000,
            "data_types": ["name", "nric", "mobile", "email", "health_data"],
            "significant_harm_likelihood": True,
            "harm_types": ["identity_theft", "fraud", "public embarrassment"]
        })

        assessment = await compliance_engine.assess_pdpa_compliance(breach_data)

        # Expected PDPA assessment
        assert assessment["jurisdiction"] == "PDPA"
        assert assessment["requires_notification"] is True
        assert assessment["pdpc_notification_required"] is True  # PDPC = Personal Data Protection Commission
        assert assessment["assessment_timeline"] is not None
        assert "obligations_under_act" in assessment

    @pytest.mark.asyncio
    async def test_multi_jurisdiction_comprehensive_assessment(self, compliance_engine, sample_breach_data):
        """Test comprehensive assessment across multiple jurisdictions simultaneously"""
        breach_data = sample_breach_data.copy()
        breach_data.update({
            "subjects_affected": {
                "total": 100000,
                "by_country": {
                    "france": 20000,
                    "germany": 15000,
                    "california": 10000,
                    "canada": 8000,
                    "brazil": 12000,
                    "singapore": 3000
                }
            },
            "data_types": ["name", "email", "address", "phone", "ssn", "health_records"],
            "special_category_data": True
        })

        jurisdictions = ["GDPR_FR", "GDPR_DE", "CCPA", "PIPEDA", "LGPD", "PDPA"]

        comprehensive_assessment = await compliance_engine.assess_multi_jurisdiction_compliance(
            breach_data=breach_data,
            jurisdictions=jurisdictions
        )

        # Expected comprehensive assessment
        assert comprehensive_assessment["success"] is True
        assert len(comprehensive_assessment["jurisdiction_assessments"]) == len(jurisdictions)
        assert comprehensive_assessment["overall_risk_level"] is not None
        assert comprehensive_assessment["coordinated_notification_plan"] is not None

        # Check each jurisdiction assessment
        for jurisdiction in jurisdictions:
            assert jurisdiction in comprehensive_assessment["jurisdiction_assessments"]
            assessment = comprehensive_assessment["jurisdiction_assessments"][jurisdiction]
            assert "requires_notification" in assessment
            assert "deadline_hours" in assessment
            assert "local_requirements" in assessment

        # Check coordination requirements
        assert "notification_timing_recommendations" in comprehensive_assessment
        assert "content_localization_requirements" in comprehensive_assessment

    def test_jurisdiction_specific_deadline_calculations(self, compliance_engine):
        """Test deadline calculations for different jurisdictions"""
        test_scenarios = [
            {
                "jurisdiction": "GDPR",
                "discovery_date": datetime.now(),
                "expected_deadline_hours": 72
            },
            {
                "jurisdiction": "CCPA",
                "discovery_date": datetime.now(),
                "expected_deadline_hours": 72  # "Reasonable time" but typically 72 hours
            },
            {
                "jurisdiction": "PIPEDA",
                "discovery_date": datetime.now(),
                "expected_deadline_hours": None  # "As soon as feasible"
            },
            {
                "jurisdiction": "LGPD",
                "discovery_date": datetime.now(),
                "expected_deadline_hours": 72
            }
        ]

        for scenario in test_scenarios:
            deadline_info = compliance_engine.calculate_notification_deadline(
                jurisdiction=scenario["jurisdiction"],
                discovery_date=scenario["discovery_date"]
            )

            if scenario["expected_deadline_hours"]:
                assert deadline_info["deadline_hours"] == scenario["expected_deadline_hours"]
                assert deadline_info["deadline_date"] is not None
            else:
                assert deadline_info["deadline_hours"] is None
                assert deadline_info["guidance"] is not None

    def test_data_type_sensitivity_classification(self, compliance_engine):
        """Test data type sensitivity classification for risk assessment"""
        test_data_types = [
            ("name", "low"),
            ("email", "low"),
            ("ssn", "high"),
            ("health_records", "very_high"),
            ("biometric_data", "very_high"),
            ("genetic_data", "very_high"),
            ("political_opinions", "very_high"),
            ("religious_beliefs", "very_high"),
            ("financial_data", "high"),
            ("location_data", "medium"),
            ("device_id", "low")
        ]

        for data_type, expected_sensitivity in test_data_types:
            sensitivity = compliance_engine.classify_data_sensitivity(data_type)
            assert sensitivity["level"] == expected_sensitivity
            assert sensitivity["special_category"] == (expected_sensitivity == "very_high")

    def test_risk_level_calculation(self, compliance_engine):
        """Test comprehensive risk level calculation"""
        risk_factors = {
            "data_sensitivity": "very_high",
            "volume_affected": 50000,
            "encryption_present": False,
            "external_attack": True,
            "special_categories": True,
            "vulnerable_population": True,
            "cross_border_transfer": True
        }

        risk_assessment = compliance_engine.calculate_risk_level(risk_factors)

        # Expected risk assessment
        assert risk_assessment["overall_risk"] in ["low", "medium", "high", "critical"]
        assert risk_assessment["risk_score"] is not None
        assert 0 <= risk_assessment["risk_score"] <= 100
        assert risk_assessment["mitigating_factors"] is not None
        assert risk_assessment["aggravating_factors"] is not None
        assert len(risk_assessment["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_compliance_rule_validation(self, compliance_engine):
        """Test validation of compliance rules and requirements"""
        test_content = {
            "subject": "Data Breach Notification",
            "body": "We experienced a data breach affecting personal data. We have taken measures to secure the data.",
            "contact_info": "privacy@company.com",
            "measures_taken": ["immediate_containment", "investigation"],
            "data_types": ["name", "email"],
            "rights_explanation": "You have the right to access, correct, and delete your data"
        }

        validation_result = await compliance_engine.validate_notification_content(
            content=test_content,
            jurisdiction="GDPR",
            notification_type="supervisory_authority"
        )

        # Expected validation result
        assert validation_result["compliant"] is True
        assert validation_result["missing_required_elements"] == []
        assert validation_result["compliance_score"] >= 0.9

        # Test with missing elements
        incomplete_content = {
            "subject": "Data Breach",
            "body": "We had a breach."
        }

        incomplete_validation = await compliance_engine.validate_notification_content(
            content=incomplete_content,
            jurisdiction="GDPR",
            notification_type="supervisory_authority"
        )

        assert incomplete_validation["compliant"] is False
        assert len(incomplete_validation["missing_required_elements"]) > 0

    def test_jurisdiction_configuration_loading(self, compliance_engine):
        """Test loading and validation of jurisdiction configurations"""
        # Test that configurations are properly loaded
        jurisdictions = compliance_engine.get_supported_jurisdictions()

        # Check that major jurisdictions are present
        required_jurisdictions = ["GDPR", "CCPA", "PIPEDA", "LGPD", "PDPA"]
        for jurisdiction in required_jurisdictions:
            assert jurisdiction in jurisdictions

        # Test configuration details
        gdpr_config = compliance_engine.get_jurisdiction_config("GDPR")
        assert gdpr_config["notification_deadline_hours"] == 72
        assert gdpr_config["supervisory_authority_required"] is True
        assert "required_content_elements" in gdpr_config

        ccpa_config = compliance_engine.get_jurisdiction_config("CCPA")
        assert ccpa_config["consumer_notification_required"] is True
        assert "required_content_elements" in ccpa_config

    def test_localization_requirements_by_jurisdiction(self, compliance_engine):
        """Test localization requirements for different jurisdictions"""
        jurisdictions = ["GDPR_FR", "GDPR_DE", "GDPR_ES", "CCPA", "LGPD"]

        for jurisdiction in jurisdictions:
            localization_reqs = compliance_engine.get_localization_requirements(jurisdiction)

            assert localization_reqs is not None
            assert "required_languages" in localization_reqs
            assert "translation_requirements" in localization_reqs
            assert "cultural_considerations" in localization_reqs
            assert "legal_phrases" in localization_reqs

            # Check that required languages are appropriate
            if jurisdiction == "GDPR_FR":
                assert "fr" in localization_reqs["required_languages"]
            elif jurisdiction == "GDPR_DE":
                assert "de" in localization_reqs["required_languages"]
            elif jurisdiction == "GDPR_ES":
                assert "es" in localization_reqs["required_languages"]

    @pytest.mark.asyncio
    async def test_compliance_monitoring_automation(self, compliance_engine, sample_breach_data):
        """Test automated compliance monitoring and alerting"""
        # Test monitoring setup
        monitoring_config = {
            "incident_id": "INC-2024-001",
            "jurisdictions": ["GDPR", "CCPA"],
            "alert_thresholds": {
                "deadline_warning_hours": 12,
                "escalation_hours": 6
            }
        }

        monitoring_result = await compliance_engine.setup_compliance_monitoring(
            incident_data=sample_breach_data,
            config=monitoring_config
        )

        assert monitoring_result["success"] is True
        assert monitoring_result["monitoring_id"] is not None
        assert monitoring_result["alert_schedules"] is not None

        # Test deadline checking
        deadline_status = await compliance_engine.check_compliance_deadlines(
            monitoring_id=monitoring_result["monitoring_id"]
        )

        assert deadline_status["active_monitoring"] is True
        assert "upcoming_deadlines" in deadline_status
        assert "overdue_deadlines" in deadline_status
        assert "alerts_generated" in deadline_status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])