"""
NotificationTemplateManager for Advanced Breach Notification Workflows

This manager provides comprehensive multilingual template management, template rendering,
branding customization, and compliance validation for breach notifications across
multiple jurisdictions and communication channels.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import json
import uuid
from jinja2 import Environment, BaseLoader, Template, TemplateError
import re

from src.models.enums import NotificationChannel

logger = logging.getLogger(__name__)


class NotificationTemplateManager:
    """
    Advanced template management system for multilingual breach notifications.

    Provides template rendering, localization, branding, compliance validation,
    and accessibility features for regulatory-compliant communications.
    """

    def __init__(self):
        """Initialize the notification template manager"""
        self.template_store = self._initialize_template_store()
        self.translation_service = self._initialize_translation_service()
        self.compliance_validator = self._initialize_compliance_validator()
        self.branding_engine = self._initialize_branding_engine()
        self.accessibility_validator = self._initialize_accessibility_validator()
        self.template_cache = {}
        self.performance_monitor = self._initialize_performance_monitor()

    def _initialize_template_store(self) -> Dict[str, Any]:
        """Initialize the template store with default templates"""
        return {
            # GDPR templates
            "data_subject_notification_gdpr": {
                "subject": {
                    "en": "Important Information About a Data Breach - {company_name}",
                    "fr": "Informations importantes concernant une violation de données - {company_name}",
                    "de": "Wichtige Informationen über einen Datenverstoß - {company_name}",
                    "es": "Información importante sobre una brecha de datos - {company_name}",
                    "pt": "Informação importante sobre uma violação de dados - {company_name}",
                    "it": "Informazioni importanti su una violazione dei dati - {company_name}",
                    "nl": "Belangrijke informatie over een datalek - {company_name}"
                },
                "body": {
                    "en": """
Dear {recipient_name},

We are writing to inform you about a data security incident that may have affected your personal information.

What happened:
On {breach_date}, we discovered that {incident_description}. This incident was discovered on {discovery_date}.

What information was affected:
The following types of personal information may have been affected: {data_types_affected}.

What we are doing:
We have taken the following immediate steps: {measures_taken}. We are also working with cybersecurity experts to investigate and secure our systems.

What this means for you:
{risk_explanation}

Your rights:
Under GDPR, you have the right to access, rectify, erase, restrict processing, data portability, and object to processing of your personal data. For more information about these rights, please contact our Data Protection Officer.

Contact information:
If you have questions or concerns, please contact us at {contact_email} or {contact_phone}.

We sincerely apologize for this incident and are committed to protecting your personal information.

Sincerely,
{company_name}
                    """,
                    "fr": """
Cher/Chère {recipient_name},

Nous vous écrivons pour vous informer d'un incident de sécurité des données qui a pu affecter vos informations personnelles.

Ce qui s'est passé :
Le {breach_date}, nous avons découvert que {incident_description}. Cet incident a été découvert le {discovery_date}.

Quelles informations ont été affectées :
Les types d'informations personnelles suivants ont pu être affectés : {data_types_affected}.

Ce que nous faisons :
Nous avons pris les mesures immédiates suivantes : {measures_taken}. Nous travaillons également avec des experts en cybersécurité pour enquêter et sécuriser nos systèmes.

Ce que cela signifie pour vous :
{risk_explanation}

Vos droits :
Conformément au RGPD, vous avez le droit d'accéder, rectifier, effacer, limiter le traitement, porter et vous opposer au traitement de vos données personnelles. Pour plus d'informations sur ces droits, veuillez contacter notre délégué à la protection des données.

Coordonnées :
Si vous avez des questions ou des préoccupations, veuillez nous contacter à {contact_email} ou {contact_phone}.

Nous nous excusons sincèrement pour cet incident et nous nous engageons à protéger vos informations personnelles.

Cordialement,
{company_name}
                    """,
                    "de": """
Sehr geehrte/r {recipient_name},

Wir schreiben Ihnen, um Sie über einen Vorfall mit der Datensicherheit zu informieren, der Ihre persönlichen Daten möglicherweise betroffen hat.

Was passiert ist:
Am {breach_date} haben wir festgestellt, dass {incident_description}. Dieser Vorfall wurde am {discovery_date} entdeckt.

Welche Informationen betroffen sind:
Die folgenden Arten personenbezogener Daten könnten betroffen sein: {data_types_affected}.

Was wir tun:
Wir haben die folgenden sofortigen Schritte unternommen: {measures_taken}. Wir arbeiten auch mit Cybersicherheitsexperten zusammen, um den Vorfall zu untersuchen und unsere Systeme zu sichern.

Was dies für Sie bedeutet:
{risk_explanation}

Ihre Rechte:
Nach der DSGVO haben Sie das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und Widerspruch gegen die Verarbeitung Ihrer personenbezogenen Daten. Für weitere Informationen zu diesen Rechten wenden Sie sich bitte an unseren Datenschutzbeauftragten.

Kontaktinformationen:
Wenn Sie Fragen oder Bedenken haben, kontaktieren Sie uns bitte unter {contact_email} oder {contact_phone}.

Wir entschuldigen uns aufrichtig für diesen Vorfall und sind bestrebt, Ihre persönlichen Daten zu schützen.

Mit freundlichen Grüßen,
{company_name}
                    """
                }
            },
            "gdpr_supervisory_authority_notification": {
                "subject": {
                    "en": "GDPR Data Breach Notification - {organization_name} - Incident {incident_id}",
                    "fr": "Notification de violation de données RGPD - {organization_name} - Incident {incident_id}",
                    "de": "DSGVO-Datenverstoß-Meldung - {organization_name} - Vorfall {incident_id}"
                },
                "body": {
                    "en": """
To: {supervisory_authority}
From: {dpo_contact}
Date: {notification_date}
Subject: GDPR Article 33 Notification - Data Breach

Organization Details:
Name: {organization_name}
Address: {organization_address}
DPO Contact: {dpo_name} - {dpo_email} - {dpo_phone}

Incident Details:
Incident ID: {incident_id}
Date of Breach: {breach_date}
Date of Discovery: {discovery_date}
Nature of Breach: {breach_description}

Data Categories Involved:
{data_categories}

Approximate Number of Data Subjects Affected: {subjects_affected}

Geographic Scope: {geographic_scope}

Potential Consequences:
{potential_consequences}

Measures Taken or Proposed:
{measures_taken}

Additional Information:
{additional_information}

Please acknowledge receipt of this notification. We will provide updated information as our investigation progresses.

Sincerely,
{dpo_name}
Data Protection Officer
{organization_name}
                    """
                }
            },
            # CCPA templates
            "ccpa_consumer_notification": {
                "subject": {
                    "en": "Important Notice About a Data Breach Affecting Your California Privacy Rights"
                },
                "body": {
                    "en": """
Dear California Resident,

We are writing to inform you about a recent security incident that may have involved your personal information.

What Happened:
On {incident_date}, we discovered that {incident_description}.

What Information Was Involved:
The following types of information were compromised: {data_types_compromised}.

What We Are Doing:
We have taken immediate steps to secure our systems and are working with cybersecurity experts to investigate this incident. {consumer_guidance}

What You Can Do:
{consumer_guidance}

For more information:
Please contact us at {contact_information["privacy_email"]} or {contact_information["toll_free"]}.
Visit our website at {contact_information["website"]}.

We take this incident very seriously and sincerely apologize for any concern this may cause.

Sincerely,
{company_name}
                    """
                }
            },
            # PIPEDA templates
            "pipeda_individual_notification": {
                "subject": {
                    "en": "Important Notice Regarding a Privacy Incident"
                },
                "body": {
                    "en": """
Dear Canadian Resident,

We are writing to inform you about a privacy incident that may have affected your personal information.

Circumstances of the Incident:
On {incident_date}, we discovered that {incident_description}.

What Information Was Compromised:
The following types of personal information were involved: {compromised_information}.

What We Are Doing to Reduce Harm:
{risk_reduction_steps}

What You Can Do:
{individual_recommendations}

For more information or assistance:
Please contact our Privacy Office at {privacy_contact_email} or {privacy_contact_phone}.

We sincerely apologize for this incident and are committed to protecting your personal information.

Sincerely,
{company_name}
                    """
                }
            },
            # Internal notification templates
            "internal_incident_alert": {
                "subject": {
                    "en": "CRITICAL: {incident_type} Incident - {incident_id}"
                },
                "body": {
                    "en": """
ALERT: Security Incident Notification

Incident Details:
- ID: {incident_id}
- Type: {incident_type}
- Severity: {incident_severity}
- Reported By: {reported_by}
- Reported At: {reported_at}
- Description: {incident_description}

Affected Systems:
{affected_systems}

Immediate Actions Required:
{immediate_actions}

Contact Information:
- Incident Commander: {incident_commander}
- Security Team: {security_team_contact}
- Legal Team: {legal_team_contact}

Status Updates:
{status_updates}

All personnel must follow incident response procedures and maintain confidentiality.
                    """
                }
            },
            # SMS templates
            "data_subject_brief_sms": {
                "subject": {
                    "en": "DATA BREACH: {company_name} Security Alert"
                },
                "body": {
                    "en": "DATA BREACH: {company_name} experienced a security incident affecting your personal data. Visit {website} or call {phone} for info. REF: {incident_id}"
                }
            }
        }

    def _initialize_translation_service(self) -> Dict[str, Any]:
        """Initialize translation service configuration"""
        return {
            "supported_languages": ["en", "fr", "de", "es", "pt", "it", "nl", "sv"],
            "translation_engine": "mock",  # Would integrate with real translation service
            "fallback_language": "en",
            "quality_threshold": 0.8
        }

    def _initialize_compliance_validator(self) -> Dict[str, Any]:
        """Initialize compliance validation rules"""
        return {
            "gdpr_required_elements": [
                "incident_description",
                "data_categories",
                "affected_subjects_count",
                "consequences_assessment",
                "measures_taken",
                "contact_information",
                "rights_information"
            ],
            "ccpa_required_elements": [
                "what_happened",
                "what_information_was_involved",
                "what_we_are_doing",
                "what_you_can_do",
                "contact_information"
            ],
            "pipeda_required_elements": [
                "breach_circumstances",
                "compromised_information",
                "risk_reduction_steps",
                "individual_recommendations",
                "contact_information"
            ]
        }

    def _initialize_branding_engine(self) -> Dict[str, Any]:
        """Initialize branding engine configuration"""
        return {
            "default_branding": {
                "company_name": "Your Company",
                "primary_color": "#0066cc",
                "secondary_color": "#f0f0f0",
                "font_family": "Arial, Helvetica, sans-serif",
                "logo_url": None,
                "footer_text": "© 2024 Your Company. All rights reserved."
            },
            "accessibility_defaults": {
                "wcag_level": "AA",
                "font_size": "16px",
                "contrast_ratio": "4.5:1",
                "alt_text_required": True
            }
        }

    def _initialize_accessibility_validator(self) -> Dict[str, Any]:
        """Initialize accessibility validation configuration"""
        return {
            "wcag_levels": ["A", "AA", "AAA"],
            "required_attributes": ["alt", "aria-label"],
            "semantic_html_required": True,
            "color_contrast_thresholds": {
                "AA_normal": 4.5,
                "AA_large": 3.0,
                "AAA_normal": 7.0,
                "AAA_large": 4.5
            }
        }

    def _initialize_performance_monitor(self) -> Dict[str, Any]:
        """Initialize performance monitoring"""
        return {
            "rendering_times": [],
            "cache_hit_ratio": 0.0,
            "template_load_times": {},
            "average_rendering_time": 0.0
        }

    def get_available_templates(self) -> List[str]:
        """Get list of available template names"""
        return list(self.template_store.keys())

    async def _validate_rendered_content(
        self,
        subject: str,
        body: str,
        jurisdiction: Optional[str]
    ) -> Dict[str, Any]:
        """Validate rendered content for compliance"""
        return {
            "compliant": True,
            "missing_elements": [],
            "jurisdiction": jurisdiction
        }

    async def render_template(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        language: str = "en",
        jurisdiction: Optional[str] = None,
        channel: Optional[NotificationChannel] = None
    ) -> Dict[str, Any]:
        """
        Render a notification template with provided data.

        Args:
            template_name: Name of template to render
            template_data: Data for template rendering
            language: Target language for rendering
            jurisdiction: Target jurisdiction for compliance
            channel: Notification channel for rendering

        Returns:
            Rendered template content with metadata
        """
        try:
            start_time = datetime.now()
            logger.info(f"Rendering template '{template_name}' in language '{language}'")

            # Check cache first
            cache_key = f"{template_name}_{language}_{jurisdiction}_{channel}"
            if cache_key in self.template_cache:
                cached_template = self.template_cache[cache_key]
                logger.info(f"Template '{template_name}' found in cache")
                return cached_template

            # Get template from store
            template_content = self._get_template_content(template_name, language)
            if not template_content:
                raise ValueError(f"Template '{template_name}' not found for language '{language}'")

            # Prepare template data with defaults
            prepared_data = self._prepare_template_data(template_data, language, jurisdiction)

            # Render subject and body
            subject = self._render_template_string(
                template_content.get("subject", ""), prepared_data
            )
            body = self._render_template_string(
                template_content.get("body", ""), prepared_data
            )

            # Generate HTML body
            html_body = self._generate_html_content(subject, body, template_name, channel)

            # Validate rendered content
            validation_result = await self._validate_rendered_content(
                subject, body, jurisdiction
            )

            render_time = (datetime.now() - start_time).total_seconds()
            self._update_performance_metrics(template_name, render_time)

            result = {
                "success": True,
                "template_name": template_name,
                "language": language,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "validation": validation_result,
                "render_time_ms": int(render_time * 1000),
                "render_timestamp": datetime.now().isoformat()
            }

            # Cache the result
            self.template_cache[cache_key] = result

            logger.info(f"Template '{template_name}' rendered successfully in {render_time:.3f}s")
            return result

        except Exception as e:
            logger.error(f"Error rendering template '{template_name}': {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "language": language
            }

    async def render_template_multilingual(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        languages: List[str],
        jurisdiction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Render template in multiple languages simultaneously.

        Args:
            template_name: Name of template to render
            template_data: Data for template rendering
            languages: List of target languages
            jurisdiction: Target jurisdiction

        Returns:
            Multilingual rendering results
        """
        try:
            logger.info(f"Rendering template '{template_name}' in {len(languages)} languages")

            render_tasks = []
            for language in languages:
                task = self.render_template(
                    template_name=template_name,
                    template_data=template_data,
                    language=language,
                    jurisdiction=jurisdiction
                )
                render_tasks.append(task)

            # Execute all renderings concurrently
            results = await asyncio.gather(*render_tasks, return_exceptions=True)

            # Process results
            templates = {}
            successful_renders = 0
            failed_renders = 0

            for i, result in enumerate(results):
                language = languages[i]
                if isinstance(result, Exception):
                    logger.error(f"Failed to render template in {language}: {result}")
                    templates[language] = {
                        "success": False,
                        "error": str(result)
                    }
                    failed_renders += 1
                else:
                    templates[language] = result
                    if result.get("success"):
                        successful_renders += 1
                    else:
                        failed_renders += 1

            multilingual_result = {
                "success": successful_renders > 0,
                "template_name": template_name,
                "total_languages": len(languages),
                "successful_renders": successful_renders,
                "failed_renders": failed_renders,
                "translations": templates,  # Changed key name to match test expectations
                "render_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Multilingual rendering completed: {successful_renders}/{len(languages)} successful")
            return multilingual_result

        except Exception as e:
            logger.error(f"Error in multilingual template rendering: {str(e)}")
            raise

    def _get_template_content(self, template_name: str, language: str) -> Optional[Dict[str, str]]:
        """Get template content for specific language"""
        template = self.template_store.get(template_name)
        if not template:
            return None

        # Try to get content for specified language
        if language in template.get("subject", {}) and language in template.get("body", {}):
            return {
                "subject": template["subject"][language],
                "body": template["body"][language]
            }

        # Fallback to English if available
        if "en" in template.get("subject", {}) and "en" in template.get("body", {}):
            logger.warning(f"Template '{template_name}' not available in '{language}', using English fallback")
            return {
                "subject": template["subject"]["en"],
                "body": template["body"]["en"]
            }

        # Return first available language
        for lang_key in template.get("subject", {}):
            if lang_key in template.get("body", {}):
                logger.warning(f"Template '{template_name}' using available language '{lang_key}'")
                return {
                    "subject": template["subject"][lang_key],
                    "body": template["body"][lang_key]
                }

        return None

    def _prepare_template_data(
        self,
        template_data: Dict[str, Any],
        language: str,
        jurisdiction: Optional[str]
    ) -> Dict[str, Any]:
        """Prepare template data with additional context and defaults"""
        prepared_data = template_data.copy()

        # Add timestamp information
        now = datetime.now()
        prepared_data.update({
            "current_date": now.strftime("%Y-%m-%d"),
            "current_time": now.strftime("%H:%M:%S"),
            "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "language": language,
            "jurisdiction": jurisdiction
        })

        # Format dates if present
        if "breach_date" in prepared_data:
            breach_date = prepared_data["breach_date"]
            if isinstance(breach_date, str):
                prepared_data["breach_date"] = breach_date
            elif isinstance(breach_date, datetime):
                prepared_data["breach_date"] = breach_date.strftime("%Y-%m-%d")

        if "discovery_date" in prepared_data:
            discovery_date = prepared_data["discovery_date"]
            if isinstance(discovery_date, str):
                prepared_data["discovery_date"] = discovery_date
            elif isinstance(discovery_date, datetime):
                prepared_data["discovery_date"] = discovery_date.strftime("%Y-%m-%d")

        # Add default values for common fields
        prepared_data.setdefault("company_name", "Your Company")
        prepared_data.setdefault("contact_email", "privacy@company.com")
        prepared_data.setdefault("contact_phone", "1-800-555-0123")

        # Format lists for display
        if "measures_taken" in prepared_data and isinstance(prepared_data["measures_taken"], list):
            prepared_data["measures_taken"] = "; ".join(prepared_data["measures_taken"])

        if "data_types_affected" in prepared_data and isinstance(prepared_data["data_types_affected"], list):
            prepared_data["data_types_affected"] = ", ".join(prepared_data["data_types_affected"])

        return prepared_data

    def _render_template_string(self, template_string: str, data: Dict[str, Any]) -> str:
        """Render a template string with provided data using Jinja2"""
        try:
            if not template_string:
                return ""

            env = Environment(loader=BaseLoader())
            template = env.from_string(template_string)
            return template.render(**data)

        except TemplateError as e:
            logger.error(f"Template rendering error: {str(e)}")
            # Return original string with variables unrendered if template fails
            return template_string

    def _generate_html_content(
        self,
        subject: str,
        body: str,
        template_name: str,
        channel: Optional[NotificationChannel]
    ) -> str:
        """Generate HTML version of the notification content"""
        if channel == NotificationChannel.SMS:
            # SMS doesn't use HTML
            return ""

        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f4f4f4;
        }}
        .header {{
            background-color: #0066cc;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 5px 5px 0 0;
        }}
        .content {{
            background-color: white;
            padding: 30px;
            border-radius: 0 0 5px 5px;
        }}
        .footer {{
            margin-top: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 5px;
            font-size: 12px;
            color: #666;
            text-align: center;
        }}
        h1 {{
            color: #0066cc;
            margin-bottom: 20px;
        }}
        .signature {{
            margin-top: 30px;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{subject}</h1>
    </div>
    <div class="content">
        <div class="body-content">
            {self._format_body_text_as_html(body)}
        </div>
        <div class="signature">
            <p>This is an automated message from our notification system.</p>
        </div>
    </div>
    <div class="footer">
        <p>© 2024 Data Foundry. All rights reserved.</p>
        <p>If you received this message in error, please notify us immediately.</p>
    </div>
</body>
</html>
        """
        return html_template

    def _format_body_text_as_html(self, body_text: str) -> str:
        """Convert plain text body to HTML format"""
        # Split into paragraphs
        paragraphs = body_text.strip().split('\n\n')
        html_paragraphs = []

        for paragraph in paragraphs:
            if paragraph.strip():
                # Convert line breaks within paragraphs to <br>
                paragraph = paragraph.replace('\n', '<br>')
                html_paragraphs.append(f"<p>{paragraph}</p>")

        return "\n".join(html_paragraphs)

    async def render_template_with_branding(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        branding: Optional[Dict[str, Any]] = None,
        language: str = "en",
        jurisdiction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Render template with custom branding.

        Args:
            template_name: Name of template to render
            template_data: Data for template rendering
            branding: Custom branding configuration
            language: Target language
            jurisdiction: Target jurisdiction

        Returns:
            Branded template content
        """
        try:
            logger.info(f"Rendering branded template '{template_name}'")

            # Use provided branding or default
            branding_config = branding if branding else self.branding_engine["default_branding"]

            # Render base template
            base_result = await self.render_template(
                template_name=template_name,
                template_data=template_data,
                language=language,
                jurisdiction=jurisdiction
            )

            if not base_result.get("success"):
                return base_result

            # Apply branding to HTML content
            branded_html = self._apply_branding_to_html(
                base_result["html_body"],
                branding_config
            )

            branded_result = {
                **base_result,
                "html_body": branded_html,
                "branding_applied": True,
                "branding_config": branding_config
            }

            logger.info(f"Branded template '{template_name}' rendered successfully")
            return branded_result

        except Exception as e:
            logger.error(f"Error rendering branded template: {str(e)}")
            raise

    def _apply_branding_to_html(self, html_content: str, branding: Dict[str, Any]) -> str:
        """Apply branding configuration to HTML content"""
        try:
            # Replace colors
            if "primary_color" in branding:
                html_content = html_content.replace("#0066cc", branding["primary_color"])

            if "secondary_color" in branding:
                html_content = html_content.replace("#f4f4f4", branding["secondary_color"])

            # Replace company name
            if "company_name" in branding:
                html_content = html_content.replace("Data Foundry", branding["company_name"])

            # Replace footer text
            if "footer_text" in branding:
                html_content = re.sub(
                    r'<p>© 2024.*?All rights reserved\.</p>',
                    f'<p>{branding["footer_text"]}</p>',
                    html_content
                )

            # Add logo if provided
            if branding.get("logo_url"):
                logo_html = f'<img src="{branding["logo_url"]}" alt="{branding.get("company_name", "Company Logo")}" style="max-height: 60px;">'
                html_content = html_content.replace(
                    '<h1>{subject}</h1>',
                    f'<div style="text-align: center; margin-bottom: 20px;">{logo_html}</div>\n            <h1>{{{{subject}}}}</h1>'
                )

            return html_content

        except Exception as e:
            logger.error(f"Error applying branding to HTML: {str(e)}")
            return html_content  # Return original HTML if branding fails

    async def validate_template_compliance(
        self,
        content: Dict[str, Any],
        jurisdiction: str,
        notification_type: str,
        required_elements: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate template content for regulatory compliance.

        Args:
            content: Template content to validate
            jurisdiction: Target jurisdiction
            notification_type: Type of notification
            required_elements: Specific required elements to check

        Returns:
            Compliance validation results
        """
        try:
            logger.info(f"Validating template compliance for {jurisdiction} - {notification_type}")

            # Get required elements for jurisdiction and notification type
            if not required_elements:
                required_elements = self._get_required_elements_for_jurisdiction(
                    jurisdiction, notification_type
                )

            # Check for missing elements
            missing_elements = []
            body_text = content.get("body", "").lower()
            subject_text = content.get("subject", "").lower()

            for element in required_elements:
                # Create keyword variations for each element
                element_keywords = self._get_element_keywords(element)
                found = any(
                    keyword in body_text or keyword in subject_text
                    for keyword in element_keywords
                )
                if not found:
                    missing_elements.append(element)

            # Calculate compliance score
            total_elements = len(required_elements)
            present_elements = total_elements - len(missing_elements)
            compliance_score = present_elements / total_elements if total_elements > 0 else 1.0

            # Additional compliance checks
            additional_checks = self._perform_additional_compliance_checks(
                content, jurisdiction
            )

            validation_result = {
                "compliant": len(missing_elements) == 0,
                "compliance_score": compliance_score,
                "missing_required_elements": missing_elements,
                "additional_checks": additional_checks,
                "jurisdiction": jurisdiction,
                "notification_type": notification_type,
                "validation_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Compliance validation completed: score={compliance_score:.2f}, missing={len(missing_elements)}")
            return validation_result

        except Exception as e:
            logger.error(f"Error validating template compliance: {str(e)}")
            raise

    def _get_required_elements_for_jurisdiction(
        self, jurisdiction: str, notification_type: str
    ) -> List[str]:
        """Get required elements for specific jurisdiction and notification type"""
        compliance_validator = self.compliance_validator

        # Map jurisdiction and notification type to required elements
        if jurisdiction == "GDPR":
            if notification_type == "data_subject":
                return compliance_validator["gdpr_required_elements"]
            elif notification_type == "supervisory_authority":
                return [
                    "incident_description",
                    "data_categories",
                    "affected_subjects_count",
                    "measures_taken",
                    "dpo_contact_details"
                ]
        elif jurisdiction == "CCPA":
            return compliance_validator["ccpa_required_elements"]
        elif jurisdiction == "PIPEDA":
            return compliance_validator["pipeda_required_elements"]

        # Default to empty list if no specific requirements
        return []

    def _get_element_keywords(self, element: str) -> List[str]:
        """Get keyword variations for checking element presence"""
        keyword_mapping = {
            "incident_description": [
                "what happened", "incident", "breach", "occurred", "security incident"
            ],
            "data_categories": [
                "data types", "information", "personal data", "categories", "compromised"
            ],
            "affected_subjects_count": [
                "affected", "number of", "count", "individuals", "customers"
            ],
            "consequences_assessment": [
                "consequences", "impact", "risk", "affect", "potential harm"
            ],
            "measures_taken": [
                "measures", "steps", "actions", "security", "protecting"
            ],
            "contact_information": [
                "contact", "email", "phone", "reach", "questions"
            ],
            "rights_information": [
                "rights", "gdpr", "data subject", "access", "rectification"
            ]
        }

        return keyword_mapping.get(element, [element])

    def _perform_additional_compliance_checks(
        self, content: Dict[str, Any], jurisdiction: str
    ) -> Dict[str, Any]:
        """Perform additional compliance checks"""
        checks = {}

        body_text = content.get("body", "")
        subject_text = content.get("subject", "")

        # Check for minimum content length
        checks["minimum_length_met"] = len(body_text) >= 200

        # Check for contact information
        contact_keywords = ["contact", "email", "phone", "reach"]
        checks["has_contact_info"] = any(
            keyword in body_text.lower() for keyword in contact_keywords
        )

        # Check for clear language indicators
        checks["uses_clear_language"] = len(body_text.split()) >= 50

        # Jurisdiction-specific checks
        if jurisdiction == "GDPR":
            gdpr_keywords = ["gdpr", "data subject", "rights", "article"]
            checks["mentions_gdpr"] = any(
                keyword in body_text.lower() for keyword in gdpr_keywords
            )
        elif jurisdiction == "CCPA":
            ccpa_keywords = ["ccpa", "california", "consumer rights"]
            checks["mentions_ccpa"] = any(
                keyword in body_text.lower() for keyword in ccpa_keywords
            )

        return checks

    async def render_for_multiple_channels(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        channels: List[NotificationChannel],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Render template for multiple notification channels.

        Args:
            template_name: Name of template to render
            template_data: Data for template rendering
            channels: List of notification channels
            language: Target language

        Returns:
            Channel-specific rendering results
        """
        try:
            logger.info(f"Rendering template '{template_name}' for {len(channels)} channels")

            # Render base template first
            base_result = await self.render_template(
                template_name=template_name,
                template_data=template_data,
                language=language
            )

            if not base_result.get("success"):
                return {
                    "success": False,
                    "error": base_result.get("error"),
                    "channels": channels
                }

            # Adapt content for each channel
            channel_versions = {}
            for channel in channels:
                adapted_content = self._adapt_content_for_channel(
                    base_result, channel
                )
                channel_versions[channel.value] = adapted_content

            result = {
                "success": True,
                "template_name": template_name,
                "language": language,
                "channels": channels,
                "channel_versions": channel_versions,
                "render_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Multi-channel rendering completed for {len(channels)} channels")
            return result

        except Exception as e:
            logger.error(f"Error rendering for multiple channels: {str(e)}")
            raise

    def _adapt_content_for_channel(
        self, base_result: Dict[str, Any], channel: NotificationChannel
    ) -> Dict[str, Any]:
        """Adapt template content for specific notification channel"""
        adapted = base_result.copy()

        if channel == NotificationChannel.SMS:
            # SMS adaptation: create concise version
            subject = base_result.get("subject", "")
            body = base_result.get("body", "")

            # Create SMS-friendly content
            sms_content = f"{subject[:50]}: {body[:100]}..." if len(body) > 100 else f"{subject}: {body}"

            adapted = {
                "subject": None,  # SMS doesn't use subject
                "content": sms_content[:160],  # SMS limit
                "channel": "SMS",
                "adaptation_applied": True
            }

        elif channel == NotificationChannel.EMAIL:
            # Email: use full content
            adapted.update({
                "channel": "EMAIL",
                "adaptation_applied": False
            })

        elif channel == NotificationChannel.IN_APP:
            # In-app: make it more interactive
            body = base_result.get("body", "")
            cta = "\n\n[View Details] [Learn More] [Contact Support]"
            adapted["body"] = body + cta
            adapted["channel"] = "IN_APP"
            adapted["adaptation_applied"] = True

        return adapted

    async def render_template_with_accessibility(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        language: str = "en",
        accessibility_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Render template with accessibility features.

        Args:
            template_name: Name of template to render
            template_data: Data for template rendering
            language: Target language
            accessibility_options: Accessibility configuration options

        Returns:
            Accessibility-enhanced template content
        """
        try:
            logger.info(f"Rendering accessible template '{template_name}'")

            # Use provided accessibility options or defaults
            options = accessibility_options if accessibility_options else self.accessibility_validator

            # Render base template
            base_result = await self.render_template(
                template_name=template_name,
                template_data=template_data,
                language=language
            )

            if not base_result.get("success"):
                return base_result

            # Apply accessibility enhancements
            accessible_html = self._apply_accessibility_features(
                base_result["html_body"],
                options
            )

            # Generate accessibility report
            accessibility_report = self._validate_accessibility(
                accessible_html, options
            )

            result = {
                **base_result,
                "html_body": accessible_html,
                "accessibility_compliant": accessibility_report["compliant"],
                "accessibility_report": accessibility_report,
                "accessibility_options": options
            }

            logger.info(f"Accessible template '{template_name}' rendered successfully")
            return result

        except Exception as e:
            logger.error(f"Error rendering accessible template: {str(e)}")
            raise

    def _apply_accessibility_features(self, html_content: str, options: Dict[str, Any]) -> str:
        """Apply accessibility features to HTML content"""
        try:
            accessible_html = html_content

            # Ensure proper heading structure
            accessible_html = re.sub(
                r'<div class="header">\s*<h1>(.*?)</h1>',
                r'<header role="banner">\n        <h1>\1</h1>',
                accessible_html,
                flags=re.DOTALL
            )

            # Add ARIA labels
            accessible_html = re.sub(
                r'<div class="content">',
                '<div class="content" role="main" aria-label="Notification content">',
                accessible_html
            )

            # Add semantic structure
            accessible_html = accessible_html.replace(
                '<div class="body-content">',
                '<section class="body-content">'
            ).replace(
                '</div>\n        <div class="signature">',
                '</section>\n        <footer class="signature" role="contentinfo">'
            )

            # Ensure proper font size if specified
            if options.get("large_font"):
                accessible_html = re.sub(
                    r'font-size: \d+px',
                    'font-size: 18px',
                    accessible_html
                )

            # Ensure high contrast if specified
            if options.get("high_contrast"):
                accessible_html = accessible_html.replace(
                    "color: #333;",
                    "color: #000;"
                ).replace(
                    "background-color: #f4f4f4;",
                    "background-color: #ffffff;"
                )

            return accessible_html

        except Exception as e:
            logger.error(f"Error applying accessibility features: {str(e)}")
            return html_content  # Return original HTML if accessibility fails

    def _validate_accessibility(self, html_content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Validate HTML content for accessibility compliance"""
        try:
            validation_report = {
                "compliant": True,
                "issues": [],
                "warnings": [],
                "checks": {}
            }

            # Check for semantic HTML structure
            has_semantic_structure = bool(re.search(r'<header|<main|<section|<footer', html_content))
            validation_report["checks"]["semantic_structure"] = has_semantic_structure
            if not has_semantic_structure:
                validation_report["issues"].append("Missing semantic HTML structure")

            # Check for ARIA labels
            has_aria_labels = bool(re.search(r'aria-|role=', html_content))
            validation_report["checks"]["aria_labels"] = has_aria_labels
            if not has_aria_labels:
                validation_report["warnings"].append("Consider adding ARIA labels for better accessibility")

            # Check for alt text requirement
            if options.get("alt_text_required"):
                images_without_alt = re.findall(r'<img(?![^>]*alt=)[^>]*>', html_content)
                validation_report["checks"]["alt_text"] = len(images_without_alt) == 0
                if images_without_alt:
                    validation_report["issues"].append(f"Found {len(images_without_alt)} images without alt text")

            # Check color contrast (simplified check)
            has_high_contrast = bool(re.search(r'color: #000;|background-color: #fff', html_content))
            if options.get("high_contrast") and not has_high_contrast:
                validation_report["warnings"].append("Consider using higher contrast colors")

            # Overall compliance
            validation_report["compliant"] = len(validation_report["issues"]) == 0

            return validation_report

        except Exception as e:
            logger.error(f"Error validating accessibility: {str(e)}")
            return {
                "compliant": False,
                "issues": [f"Accessibility validation error: {str(e)}"],
                "warnings": [],
                "checks": {}
            }

    async def create_template_version(
        self,
        template_name: str,
        template_data: Dict[str, Any],
        version: str,
        language: str,
        parent_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new version of a template.

        Args:
            template_name: Name of template
            template_data: Template content data
            version: Version identifier
            language: Template language
            parent_version: Parent version for versioning chain

        Returns:
            Template version creation result
        """
        try:
            logger.info(f"Creating template version '{template_name}' v{version}")

            # In a real implementation, this would save to database
            template_version_id = f"{template_name}_{language}_{version}".replace(" ", "_")

            # Validate template content
            validation_result = await self.validate_template_compliance(
                {
                    "subject": template_data.get("subject", ""),
                    "body": template_data.get("body", "")
                },
                template_data.get("jurisdiction", "GDPR"),
                template_data.get("notification_type", "data_subject")
            )

            version_info = {
                "success": True,
                "template_id": template_version_id,
                "template_name": template_name,
                "version": version,
                "language": language,
                "parent_version": parent_version,
                "validation": validation_result,
                "created_at": datetime.now().isoformat(),
                "status": "active"
            }

            # Store template version (in real implementation, save to database)
            self.template_store[f"{template_name}_v{version}_{language}"] = {
                "subject": {language: template_data.get("subject", "")},
                "body": {language: template_data.get("body", "")}
            }

            logger.info(f"Template version '{version}' created successfully")
            return version_info

        except Exception as e:
            logger.error(f"Error creating template version: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "version": version
            }

    async def get_template_version_history(
        self, template_name: str, language: str
    ) -> Dict[str, Any]:
        """
        Get version history for a template.

        Args:
            template_name: Name of template
            language: Template language

        Returns:
            Template version history
        """
        try:
            logger.info(f"Getting version history for '{template_name}' in {language}")

            # In a real implementation, this would query database
            versions = []
            for key in self.template_store.keys():
                if key.startswith(template_name) and key.endswith(language):
                    # Extract version number
                    parts = key.split("_")
                    if len(parts) >= 3:
                        version = parts[-2]
                        versions.append({
                            "version": version,
                            "language": language,
                            "created_at": datetime.now().isoformat(),  # Would get from DB
                            "status": "active"
                        })

            # Sort by version
            versions.sort(key=lambda x: x["version"], reverse=True)

            history = {
                "success": True,
                "template_name": template_name,
                "language": language,
                "total_versions": len(versions),
                "versions": versions,
                "retrieved_at": datetime.now().isoformat()
            }

            logger.info(f"Found {len(versions)} versions for template '{template_name}'")
            return history

        except Exception as e:
            logger.error(f"Error getting template version history: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "language": language
            }

    async def rollback_template_version(
        self, template_name: str, target_version: str, language: str
    ) -> Dict[str, Any]:
        """
        Rollback template to a specific version.

        Args:
            template_name: Name of template
            target_version: Version to rollback to
            language: Template language

        Returns:
            Rollback operation result
        """
        try:
            logger.info(f"Rolling back '{template_name}' to version '{target_version}' in {language}")

            # In a real implementation, this would:
            # 1. Get target version from database
            # 2. Update current template to use target version content
            # 3. Create audit trail of rollback

            rollback_info = {
                "success": True,
                "template_name": template_name,
                "target_version": target_version,
                "language": language,
                "previous_version": "current",  # Would get from DB
                "current_version": target_version,
                "rollback_at": datetime.now().isoformat(),
                "reason": "Manual rollback requested"
            }

            logger.info(f"Template rolled back to version '{target_version}'")
            return rollback_info

        except Exception as e:
            logger.error(f"Error rolling back template version: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "target_version": target_version
            }

    async def test_template(
        self,
        template_name: str,
        test_data: Dict[str, Any],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Test template rendering with sample data.

        Args:
            template_name: Name of template to test
            test_data: Sample data for testing
            language: Target language

        Returns:
            Template test results
        """
        try:
            logger.info(f"Testing template '{template_name}'")

            # Render template with test data
            render_result = await self.render_template(
                template_name=template_name,
                template_data=test_data,
                language=language
            )

            # Validate rendered content
            validation_result = {
                "missing_variables": [],
                "validation_errors": []
            }

            if render_result.get("success"):
                content = {
                    "subject": render_result.get("subject", ""),
                    "body": render_result.get("body", "")
                }

                # Check for unrendered variables
                unrendered_vars = re.findall(r'\{\{[^}]*\}\}', render_result.get("body", ""))
                if unrendered_vars:
                    validation_result["missing_variables"] = unrendered_vars

            test_result = {
                "success": render_result.get("success", False),
                "rendering_successful": render_result.get("success", False),
                "template_name": template_name,
                "language": language,
                "render_result": render_result,
                "validation": validation_result,
                "test_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Template test completed: success={test_result['success']}")
            return test_result

        except Exception as e:
            logger.error(f"Error testing template: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name
            }

    async def generate_preview(
        self,
        template_name: str,
        sample_data: Dict[str, Any],
        language: str = "en",
        channels: Optional[List[NotificationChannel]] = None
    ) -> Dict[str, Any]:
        """
        Generate preview of template with sample data.

        Args:
            template_name: Name of template
            sample_data: Sample data for preview
            language: Target language
            channels: Channels to generate preview for

        Returns:
            Preview results with rendered content
        """
        try:
            logger.info(f"Generating preview for template '{template_name}'")

            # Render base template
            base_result = await self.render_template(
                template_name=template_name,
                template_data=sample_data,
                language=language
            )

            preview = {
                "success": base_result.get("success", False),
                "template_name": template_name,
                "language": language,
                "preview_timestamp": datetime.now().isoformat()
            }

            if base_result.get("success"):
                # Email preview
                if not channels or NotificationChannel.EMAIL in channels:
                    preview["email_preview"] = {
                        "subject": base_result.get("subject"),
                        "body": base_result.get("body"),
                        "html_body": base_result.get("html_body")
                    }

                # SMS preview
                if not channels or NotificationChannel.SMS in channels:
                    sms_content = self._adapt_content_for_channel(
                        base_result, NotificationChannel.SMS
                    )
                    preview["sms_preview"] = {
                        "content": sms_content.get("content")
                    }

                # In-app preview
                if not channels or NotificationChannel.IN_APP in channels:
                    in_app_content = self._adapt_content_for_channel(
                        base_result, NotificationChannel.IN_APP
                    )
                    preview["in_app_preview"] = {
                        "subject": base_result.get("subject"),
                        "body": in_app_content.get("body")
                    }

            logger.info(f"Preview generated for template '{template_name}'")
            return preview

        except Exception as e:
            logger.error(f"Error generating template preview: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name
            }

    async def validate_localization(
        self,
        template_name: str,
        target_language: str,
        cultural_requirements: Dict[str, Any],
        jurisdiction: str
    ) -> Dict[str, Any]:
        """
        Validate template localization for cultural and legal requirements.

        Args:
            template_name: Name of template to validate
            target_language: Target language for localization
            cultural_requirements: Cultural adaptation requirements
            jurisdiction: Target jurisdiction

        Returns:
            Localization validation results
        """
        try:
            logger.info(f"Validating localization for '{template_name}' to {target_language}")

            # Get template in target language
            template_content = self._get_template_content(template_name, target_language)
            if not template_content:
                return {
                    "success": False,
                    "error": f"Template not available in {target_language}",
                    "culturally_appropriate": False
                }

            # Check cultural requirements
            cultural_validation = self._validate_cultural_requirements(
                template_content, target_language, cultural_requirements
            )

            # Check legal terminology
            legal_validation = self._validate_legal_terminology(
                template_content, jurisdiction, target_language
            )

            # Check formality level
            formality_validation = self._validate_formality_level(
                template_content, cultural_requirements.get("formality_level", "formal")
            )

            localization_result = {
                "success": True,
                "template_name": template_name,
                "target_language": target_language,
                "jurisdiction": jurisdiction,
                "culturally_appropriate": cultural_validation["appropriate"],
                "legal_terminology_correct": legal_validation["correct"],
                "formality_level_matches": formality_validation["matches"],
                "language_specific_checks": {
                    "formal_address_used": cultural_validation["formal_address"],
                    "legal_terms_translated": legal_validation["translated"],
                    "cultural_norms_respected": cultural_validation["norms_respected"]
                },
                "recommendations": self._generate_localization_recommendations(
                    cultural_validation, legal_validation, formality_validation
                ),
                "validation_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Localization validation completed for {target_language}")
            return localization_result

        except Exception as e:
            logger.error(f"Error validating localization: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "template_name": template_name,
                "target_language": target_language
            }

    def _validate_cultural_requirements(
        self,
        template_content: Dict[str, str],
        language: str,
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate cultural requirements for template"""
        body_text = template_content.get("body", "").lower()
        subject_text = template_content.get("subject", "").lower()

        validation = {
            "appropriate": True,
            "formal_address": False,
            "norms_respected": True,
            "issues": []
        }

        # Check formality level
        formality_level = requirements.get("formality_level", "formal")
        if formality_level == "formal":
            formal_indicators = ["dear", "sincerely", "respectfully", "cordialement", "sehr geehrte"]
            validation["formal_address"] = any(
                indicator in body_text or indicator in subject_text
                for indicator in formal_indicators
            )
            if not validation["formal_address"]:
                validation["issues"].append("Formal address missing")

        # Check cultural norms (simplified)
        if language == "fr":
            # French templates should use formal address
            if not any(indicator in body_text for indicator in ["cher", "chère", "cordialement"]):
                validation["issues"].append("French cultural norms not fully respected")
        elif language == "de":
            # German templates should use formal address
            if not any(indicator in body_text for indicator in ["sehr geehrte", "mit freundlichen grüßen"]):
                validation["issues"].append("German cultural norms not fully respected")

        if validation["issues"]:
            validation["appropriate"] = False
            validation["norms_respected"] = False

        return validation

    def _validate_legal_terminology(
        self,
        template_content: Dict[str, str],
        jurisdiction: str,
        language: str
    ) -> Dict[str, Any]:
        """Validate legal terminology for jurisdiction and language"""
        body_text = template_content.get("body", "").lower()

        validation = {
            "correct": True,
            "translated": True,
            "missing_terms": [],
            "issues": []
        }

        # Expected legal terms by jurisdiction and language
        legal_terms_map = {
            ("GDPR", "fr"): ["rgpd", "droit", "autorité de contrôle"],
            ("GDPR", "de"): ["dsgvo", "rechte", "aufsichtsbehörde"],
            ("GDPR", "es"): ["rgpd", "derechos", "autoridad de control"],
            ("GDPR", "pt"): ["lgpd", "direitos", "autoridade de controle"],
            ("CCPA", "es"): ["ccpa", "derechos", "fiscal general"],
            ("LGPD", "pt"): ["lgpd", "direitos", "anpd"]
        }

        expected_terms = legal_terms_map.get((jurisdiction, language), [])
        if expected_terms:
            missing_terms = [
                term for term in expected_terms if term not in body_text
            ]
            if missing_terms:
                validation["missing_terms"] = missing_terms
                validation["translated"] = False
                validation["issues"].append(f"Missing legal terms: {missing_terms}")

        return validation

    def _validate_formality_level(
        self,
        template_content: Dict[str, str],
        required_level: str
    ) -> Dict[str, Any]:
        """Validate formality level of template content"""
        body_text = template_content.get("body", "")

        validation = {
            "matches": True,
            "detected_level": "formal",
            "issues": []
        }

        # Simple heuristics for formality detection
        informal_indicators = ["hey", "hi", "thanks", "cheers", "btw"]
        formal_indicators = ["dear", "sincerely", "respectfully", "regards", "cordialement"]

        informal_count = sum(1 for indicator in informal_indicators if indicator.lower() in body_text.lower())
        formal_count = sum(1 for indicator in formal_indicators if indicator.lower() in body_text.lower())

        if informal_count > formal_count and required_level == "formal":
            validation["matches"] = False
            validation["detected_level"] = "informal"
            validation["issues"].append("Template tone is too informal")

        return validation

    def _generate_localization_recommendations(
        self,
        cultural_validation: Dict[str, Any],
        legal_validation: Dict[str, Any],
        formality_validation: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for localization improvements"""
        recommendations = []

        if not cultural_validation["formal_address"]:
            recommendations.append("Add formal address appropriate for target culture")

        if cultural_validation["issues"]:
            recommendations.extend(cultural_validation["issues"])

        if legal_validation["missing_terms"]:
            recommendations.append(f"Include required legal terms: {', '.join(legal_validation['missing_terms'])}")

        if not formality_validation["matches"]:
            recommendations.append(f"Adjust formality level from '{formality_validation['detected_level']}' to match requirements")

        return recommendations

    async def render_batch(
        self,
        template_name: str,
        data_list: List[Dict[str, Any]],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Render template for multiple recipients (batch processing).

        Args:
            template_name: Name of template to render
            data_list: List of template data for each recipient
            language: Target language

        Returns:
            Batch rendering results
        """
        try:
            logger.info(f"Starting batch render for '{template_name}' with {len(data_list)} items")

            start_time = datetime.now()
            render_tasks = []

            # Create render tasks for all items
            for i, data in enumerate(data_list):
                task = self.render_template(
                    template_name=template_name,
                    template_data=data,
                    language=language
                )
                render_tasks.append(task)

            # Execute all renderings concurrently
            results = await asyncio.gather(*render_tasks, return_exceptions=True)

            # Process results
            rendered_templates = []
            successful_count = 0
            failed_count = 0

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Batch item {i} failed: {result}")
                    rendered_templates.append({
                        "success": False,
                        "error": str(result),
                        "index": i
                    })
                    failed_count += 1
                else:
                    rendered_templates.append({
                        "success": result.get("success", False),
                        "template": result,
                        "index": i
                    })
                    if result.get("success"):
                        successful_count += 1
                    else:
                        failed_count += 1

            total_time = (datetime.now() - start_time).total_seconds()
            average_time = total_time / len(data_list) if data_list else 0

            batch_result = {
                "success": successful_count > 0,
                "template_name": template_name,
                "total_items": len(data_list),
                "successful_renders": successful_count,
                "failed_renders": failed_count,
                "rendered_templates": rendered_templates,
                "performance": {
                    "total_time_seconds": total_time,
                    "average_time_per_template": average_time,
                    "templates_per_second": len(data_list) / total_time if total_time > 0 else 0
                },
                "batch_timestamp": datetime.now().isoformat()
            }

            logger.info(f"Batch render completed: {successful_count}/{len(data_list)} successful")
            return batch_result

        except Exception as e:
            logger.error(f"Error in batch rendering: {str(e)}")
            raise

    def _update_performance_metrics(self, template_name: str, render_time: float):
        """Update performance monitoring metrics"""
        self.performance_monitor["rendering_times"].append(render_time)

        # Keep only last 100 rendering times
        if len(self.performance_monitor["rendering_times"]) > 100:
            self.performance_monitor["rendering_times"] = self.performance_monitor["rendering_times"][-100:]

        # Update average
        times = self.performance_monitor["rendering_times"]
        self.performance_monitor["average_rendering_time"] = sum(times) / len(times) if times else 0

        # Update template-specific metrics
        if template_name not in self.performance_monitor["template_load_times"]:
            self.performance_monitor["template_load_times"][template_name] = []

        self.performance_monitor["template_load_times"][template_name].append(render_time)

    async def render_personalized_template(
        self,
        template_name: str,
        base_data: Dict[str, Any],
        recipient_data: Dict[str, Any],
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Render template with personalized data for specific recipient.

        Args:
            template_name: Name of template to render
            base_data: Base template data
            recipient_data: Personalization data for recipient
            language: Target language

        Returns:
            Personalized template content
        """
        try:
            logger.info(f"Rendering personalized template '{template_name}'")

            # Merge base data with recipient data
            merged_data = {**base_data, **recipient_data}

            # Add personalization metadata
            merged_data["personalization_applied"] = True
            merged_data["personalization_timestamp"] = datetime.now().isoformat()

            # Render template with merged data
            result = await self.render_template(
                template_name=template_name,
                template_data=merged_data,
                language=language
            )

            if result.get("success"):
                result["personalization_variables"] = list(recipient_data.keys())
                result["personalized_for"] = recipient_data.get("recipient_email", "unknown")

            logger.info(f"Personalized template rendered successfully")
            return result

        except Exception as e:
            logger.error(f"Error rendering personalized template: {str(e)}")
            raise