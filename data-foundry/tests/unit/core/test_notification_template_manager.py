"""
Unit Tests for NotificationTemplateManager

TDD-focused unit tests for multilingual notification template management,
template rendering, and compliance validation.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock
import json

from src.models.enums import NotificationChannel


class TestNotificationTemplateManager:
    """Comprehensive test suite for NotificationTemplateManager"""

    @pytest.fixture
    def template_manager(self):
        """Initialize template manager for testing"""
        from src.core.notification_template_manager import NotificationTemplateManager
        return NotificationTemplateManager()

    @pytest.fixture
    def sample_template_data(self):
        """Sample template data for testing"""
        return {
            "incident_id": "INC-2024-001",
            "company_name": "Acme Corporation",
            "breach_date": "2024-01-15",
            "discovery_date": "2024-01-16",
            "data_types_affected": ["name", "email", "address", "phone"],
            "number_affected": 5000,
            "contact_email": "privacy@acme.com",
            "contact_phone": "+1-555-0123",
            "measures_taken": [
                "Immediate containment of the breach",
                "Forensic investigation initiated",
                "Password reset for all affected users",
                "Enhanced security measures implemented"
            ],
            "recommendations": [
                "Monitor your accounts for suspicious activity",
                "Change your password",
                "Be cautious of phishing attempts"
            ]
        }

    def test_manager_initialization(self):
        """Test that NotificationTemplateManager initializes correctly"""
        from src.core.notification_template_manager import NotificationTemplateManager

        manager = NotificationTemplateManager()

        # Expected attributes and capabilities
        assert manager is not None
        assert hasattr(manager, 'template_store')
        assert hasattr(manager, 'translation_service')
        assert hasattr(manager, 'compliance_validator')
        assert hasattr(manager, 'branding_engine')

        # Check that essential templates are loaded
        available_templates = manager.get_available_templates()
        assert "data_subject_notification_gdpr" in available_templates
        assert "supervisory_authority_notification_gdpr" in available_templates
        assert "data_subject_notification_ccpa" in available_templates
        assert "internal_incident_alert" in available_templates

    @pytest.mark.asyncio
    async def test_template_rendering_basic(self, template_manager, sample_template_data):
        """Test basic template rendering functionality"""
        result = await template_manager.render_template(
            template_name="data_subject_notification_gdpr",
            template_data=sample_template_data,
            language="en"
        )

        # Expected rendering result
        assert result["success"] is True
        assert result["subject"] is not None
        assert result["body"] is not None
        assert result["html_body"] is not None

        # Verify template variables are replaced
        assert sample_template_data["company_name"] in result["subject"]
        assert sample_template_data["incident_id"] in result["body"]
        assert sample_template_data["breach_date"] in result["body"]

        # Verify HTML formatting
        assert "<html>" in result["html_body"]
        assert "</html>" in result["html_body"]
        assert "<head>" in result["html_body"]
        assert "<body>" in result["html_body"]

    @pytest.mark.asyncio
    async def test_multilingual_template_rendering(self, template_manager, sample_template_data):
        """Test multilingual template rendering"""
        languages = ["en", "fr", "de", "es", "pt", "it", "nl", "sv"]

        result = await template_manager.render_template_multilingual(
            template_name="data_subject_notification_gdpr",
            template_data=sample_template_data,
            languages=languages
        )

        # Expected multilingual result
        assert result["success"] is True
        assert len(result["templates"]) == len(languages)

        # Check each language translation
        for lang in languages:
            assert lang in result["templates"]
            translation = result["templates"][lang]
            assert "subject" in translation
            assert "body" in translation
            assert "html_body" in translation
            assert len(translation["subject"]) > 0
            assert len(translation["body"]) > 0

            # Verify language-specific content
            if lang == "fr":
                assert "viol" in translation["body"] or "données" in translation["body"]
            elif lang == "de":
                assert "Verstoß" in translation["body"] or "Daten" in translation["body"]
            elif lang == "es":
                assert "violación" in translation["body"] or "datos" in translation["body"]

    @pytest.mark.asyncio
    async def test_gdpr_supervisory_authority_template(self, template_manager):
        """Test GDPR supervisory authority notification template"""
        gdpr_data = {
            "incident_id": "INC-2024-001",
            "organization_name": "Global Tech Inc",
            "dpo_name": "John Doe",
            "dpo_email": "dpo@globaltech.com",
            "dpo_phone": "+44-20-1234-5678",
            "breach_description": "Unauthorized access to customer database via exploited vulnerability",
            "data_categories": ["personal_identification", "contact_information", "financial_data"],
            "approximate_subjects_affected": 25000,
            "geographic_scope": "EU and UK",
            "discovery_date": "2024-01-15T10:30:00Z",
            "breach_date": "2024-01-14T22:15:00Z",
            "measures_taken": [
                "Immediate system isolation",
                "Security patch deployment",
                "Forensic investigation by third-party experts",
                "Password reset for all users"
            ],
            "potential_consequences": [
                "Identity theft risk",
                "Financial fraud potential",
                "Unauthorized use of personal data"
            ]
        }

        result = await template_manager.render_template(
            template_name="gdpr_supervisory_authority_notification",
            template_data=gdpr_data,
            language="en",
            jurisdiction="GDPR"
        )

        # Expected GDPR supervisory authority notification
        assert result["success"] is True
        assert "Article 33" in result["body"]  # GDPR reference
        assert gdpr_data["organization_name"] in result["body"]
        assert gdpr_data["incident_id"] in result["body"]
        assert gdpr_data["dpo_email"] in result["body"]

        # Check required GDPR elements
        required_elements = [
            "nature of the personal data breach",
            "categories of data subjects concerned",
            "likely consequences",
            "measures taken or proposed",
            "contact details of the DPO"
        ]

        for element in required_elements:
            assert element.lower() in result["body"].lower()

    @pytest.mark.asyncio
    async def test_ccpa_consumer_notification_template(self, template_manager):
        """Test CCPA consumer notification template"""
        ccpa_data = {
            "company_name": "California Business Corp",
            "incident_date": "2024-01-15",
            "incident_description": "Unauthorized access to customer information system",
            "data_types_compromised": ["name", "email", "address", "phone", "social_security_number"],
            "california_residents_affected": 15000,
            "consumer_guidance": [
                "Review your account statements",
                "Monitor your credit reports",
                "Place a fraud alert on your credit file",
                "Consider a credit freeze"
            ],
            "contact_information": {
                "privacy_email": "privacy@calbusiness.com",
                "toll_free": "1-800-123-4567",
                "website": "www.calbusiness.com/privacy"
            }
        }

        result = await template_manager.render_template(
            template_name="ccpa_consumer_notification",
            template_data=ccpa_data,
            language="en",
            jurisdiction="CCPA"
        )

        # Expected CCPA consumer notification
        assert result["success"] is True
        assert "California Consumer Privacy Act" in result["body"]
        assert ccpa_data["company_name"] in result["body"]
        assert len(ccpa_data["data_types_compromised"]) == len([dt for dt in result["body"].split() if dt in ccpa_data["data_types_compromised"]])

        # Check CCPA requirements
        assert "What happened" in result["body"]
        assert "What information was involved" in result["body"]
        assert "What we are doing" in result["body"]
        assert "What you can do" in result["body"]

    @pytest.mark.asyncio
    async def test_template_branding_customization(self, template_manager, sample_template_data):
        """Test template customization with company branding"""
        branding_config = {
            "company_name": "SecureTech Solutions",
            "logo_url": "https://securetech.com/logo.png",
            "primary_color": "#2E86AB",
            "secondary_color": "#A23B72",
            "accent_color": "#F18F01",
            "font_family": "Arial, Helvetica, sans-serif",
            "footer_text": "© 2024 SecureTech Solutions. All rights reserved.",
            "website": "https://securetech.com",
            "social_links": {
                "twitter": "https://twitter.com/securetech",
                "linkedin": "https://linkedin.com/company/securetech"
            }
        }

        result = await template_manager.render_template_with_branding(
            template_name="data_subject_notification_gdpr",
            template_data=sample_template_data,
            branding=branding_config,
            language="en"
        )

        # Expected branded template
        assert result["success"] is True
        assert branding_config["company_name"] in result["html_body"]
        assert branding_config["primary_color"] in result["html_body"]
        assert branding_config["footer_text"] in result["html_body"]
        assert branding_config["logo_url"] in result["html_body"]

        # Verify CSS styling is applied
        assert "style=" in result["html_body"]
        assert branding_config["primary_color"] in result["html_body"]

    @pytest.mark.asyncio
    async def test_template_compliance_validation(self, template_manager):
        """Test template validation for regulatory compliance"""
        # Test GDPR-compliant template
        gdpr_template_content = {
            "subject": "Data Breach Notification - Incident #INC-2024-001",
            "body": """
            We experienced a data breach affecting your personal information.

            What happened: Unauthorized access to our customer database
            What information was affected: Name, email, address, phone
            When it happened: January 15, 2024
            What we are doing: We have secured the system and are investigating
            Your rights: You have the right to access, correct, and delete your data
            Contact us: privacy@company.com, 1-800-555-0123
            """,
            "required_elements": [
                "incident_description",
                "data_categories",
                "rights_information",
                "contact_details",
                "remediation_steps"
            ]
        }

        validation_result = await template_manager.validate_template_compliance(
            content=gdpr_template_content,
            jurisdiction="GDPR",
            notification_type="data_subject"
        )

        # Expected validation result
        assert validation_result["compliant"] is True
        assert validation_result["compliance_score"] >= 0.9
        assert len(validation_result["missing_elements"]) == 0
        assert validation_result["jurisdiction"] == "GDPR"

        # Test non-compliant template
        non_compliant_template = {
            "subject": "Security Issue",
            "body": "We had a security issue. Contact us if you have questions.",
            "required_elements": ["incident_description", "data_categories"]
        }

        non_compliant_validation = await template_manager.validate_template_compliance(
            content=non_compliant_template,
            jurisdiction="GDPR",
            notification_type="data_subject"
        )

        assert non_compliant_validation["compliant"] is False
        assert len(non_compliant_validation["missing_elements"]) > 0
        assert non_compliant_validation["compliance_score"] < 0.5

    @pytest.mark.asyncio
    async def test_template_personalization(self, template_manager):
        """Test template personalization for individual recipients"""
        recipient_data = {
            "recipient_name": "Jane Smith",
            "recipient_email": "jane.smith@email.com",
            "account_number": "ACC-12345-6789",
            "services_affected": ["online_banking", "mobile_app"],
            "last_login": "2024-01-14T15:30:00Z",
            "registration_date": "2020-03-15"
        }

        base_template_data = {
            "incident_id": "INC-2024-001",
            "company_name": "SecureBank",
            "breach_date": "2024-01-15"
        }

        result = await template_manager.render_personalized_template(
            template_name="personalized_breach_notification",
            base_data=base_template_data,
            recipient_data=recipient_data,
            language="en"
        )

        # Expected personalized template
        assert result["success"] is True
        assert recipient_data["recipient_name"] in result["body"]
        assert recipient_data["email"] in result["body"]
        assert len(result["personalization_variables"]) > 0

        # Check that personalization markers are properly replaced
        assert "{{" not in result["body"]  # No unrendered template variables
        assert "}}" not in result["body"]

    @pytest.mark.asyncio
    async def test_template_channel_adaptation(self, template_manager, sample_template_data):
        """Test template adaptation for different notification channels"""
        channels = [NotificationChannel.EMAIL, NotificationChannel.SMS, NotificationChannel.IN_APP]

        results = await template_manager.render_for_multiple_channels(
            template_name="data_subject_brief_notification",
            template_data=sample_template_data,
            channels=channels
        )

        # Expected channel-specific adaptations
        assert results["success"] is True
        assert len(results["channel_versions"]) == len(channels)

        for channel in channels:
            assert channel.value in results["channel_versions"]
            version = results["channel_versions"][channel.value]

            if channel == NotificationChannel.SMS:
                # SMS should be concise
                assert len(version["content"]) <= 160
                assert "DATA BREACH:" in version["content"]
            elif channel == NotificationChannel.EMAIL:
                # Email should be comprehensive
                assert len(version["subject"]) > 0
                assert len(version["body"]) > 200
                assert "<html>" in version["html_body"]
            elif channel == NotificationChannel.IN_APP:
                # In-app should be action-oriented
                assert "view_details" in version["body"].lower() or "learn_more" in version["body"].lower()

    @pytest.mark.asyncio
    async def test_template_a11y_compliance(self, template_manager, sample_template_data):
        """Test template accessibility compliance (WCAG, etc.)"""
        result = await template_manager.render_template_with_accessibility(
            template_name="accessible_notification",
            template_data=sample_template_data,
            language="en",
            accessibility_options={
                "wcag_level": "AA",
                "screen_reader_optimized": True,
                "high_contrast": False,
                "large_font": False
            }
        )

        # Expected accessibility features
        assert result["success"] is True
        assert result["accessibility_compliant"] is True

        html_content = result["html_body"]

        # Check for proper semantic HTML
        assert "<h1>" in html_content or "<h2>" in html_content
        assert "<p>" in html_content
        assert "<ul>" in html_content or "<ol>" in html_content

        # Check for alt text (if images are present)
        if "<img" in html_content:
            assert "alt=" in html_content

        # Check for proper heading structure
        assert result["accessibility_report"]["semantic_structure"] is True
        assert result["accessibility_report"]["color_contrast"] is True
        assert result["accessibility_report"]["screen_reader_compatible"] is True

    @pytest.mark.asyncio
    async def test_template_versioning(self, template_manager, sample_template_data):
        """Test template versioning and rollback capabilities"""
        # Create initial template version
        version_1 = await template_manager.create_template_version(
            template_name="custom_breach_notification",
            template_data=sample_template_data,
            version="1.0",
            language="en"
        )

        assert version_1["success"] is True
        assert version_1["version"] == "1.0"
        assert version_1["template_id"] is not None

        # Create updated version
        updated_data = sample_template_data.copy()
        updated_data["additional_info"] = "Additional security measures have been implemented"

        version_2 = await template_manager.create_template_version(
            template_name="custom_breach_notification",
            template_data=updated_data,
            version="2.0",
            language="en",
            parent_version="1.0"
        )

        assert version_2["success"] is True
        assert version_2["version"] == "2.0"

        # Test version history
        version_history = await template_manager.get_template_version_history(
            template_name="custom_breach_notification",
            language="en"
        )

        assert len(version_history["versions"]) == 2
        assert version_history["versions"][0]["version"] == "1.0"
        assert version_history["versions"][1]["version"] == "2.0"

        # Test rollback to previous version
        rollback_result = await template_manager.rollback_template_version(
            template_name="custom_breach_notification",
            target_version="1.0",
            language="en"
        )

        assert rollback_result["success"] is True
        assert rollback_result["current_version"] == "1.0"

    @pytest.mark.asyncio
    async def test_template_testing_and_preview(self, template_manager, sample_template_data):
        """Test template testing and preview functionality"""
        # Test template with sample data
        test_result = await template_manager.test_template(
            template_name="data_subject_notification_gdpr",
            test_data=sample_template_data,
            language="en"
        )

        # Expected test results
        assert test_result["success"] is True
        assert test_result["rendering_successful"] is True
        assert test_result["missing_variables"] == []
        assert test_result["validation_errors"] == []

        # Check preview generation
        preview_result = await template_manager.generate_preview(
            template_name="data_subject_notification_gdpr",
            sample_data=sample_template_data,
            language="en",
            channels=[NotificationChannel.EMAIL, NotificationChannel.SMS]
        )

        assert preview_result["success"] is True
        assert "email_preview" in preview_result
        assert "sms_preview" in preview_result
        assert preview_result["email_preview"]["subject"] is not None
        assert preview_result["email_preview"]["body"] is not None
        assert preview_result["sms_preview"]["content"] is not None

    @pytest.mark.asyncio
    async def test_template_localization_validation(self, template_manager):
        """Test template localization and cultural adaptation validation"""
        # Test cultural adaptation requirements
        cultural_requirements = {
            "formality_level": "formal",
            "date_format": "%d/%m/%Y",
            "number_format": "comma_decimal",
            "cultural_references": True,
            "legal_phrases": "local_regulation"
        }

        localization_result = await template_manager.validate_localization(
            template_name="data_subject_notification_gdpr",
            target_language="fr",
            cultural_requirements=cultural_requirements,
            jurisdiction="GDPR_FR"
        )

        # Expected localization validation
        assert localization_result["success"] is True
        assert localization_result["culturally_appropriate"] is True
        assert localization_result["legal_terminology_correct"] is True
        assert localization_result["formality_level_matches"] is True

        # Check specific French requirements
        french_validation = localization_result["language_specific_checks"]
        assert "formal_address_used" in french_validation
        assert "legal_terms_translated" in french_validation
        assert "cultural_norms_respected" in french_validation

    @pytest.mark.asyncio
    async def test_template_performance_optimization(self, template_manager, sample_template_data):
        """Test template rendering performance optimization"""
        import time

        # Test batch rendering performance
        start_time = time.time()

        batch_results = await template_manager.render_batch(
            template_name="data_subject_notification_gdpr",
            data_list=[sample_template_data] * 100,  # 100 recipients
            language="en"
        )

        end_time = time.time()
        rendering_time = end_time - start_time

        # Expected performance metrics
        assert batch_results["success"] is True
        assert len(batch_results["rendered_templates"]) == 100
        assert rendering_time < 5.0  # Should complete within 5 seconds
        assert batch_results["performance"]["average_time_per_template"] < 0.05

        # Check rendering quality
        for template in batch_results["rendered_templates"]:
            assert template["success"] is True
            assert template["subject"] is not None
            assert template["body"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])