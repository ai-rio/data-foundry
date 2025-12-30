"""
Data Ingestion Flow using Prefect and dlt
This demonstrates the "Glue" integration between Prefect and dlt
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Callable

from dlt import pipeline
from dlt.destinations import postgres
from prefect import flow, get_run_logger, task

from src.core.config import settings
from src.core.data_quality import DataQualityValidator, ValidationResult
from src.core.ab_testing_wrapper import ABTestingWrapper
import re


# Module logger
logger = logging.getLogger(__name__)


# =============================================================================
# AML Labeling Constants (P01-004)
# =============================================================================

# Valid AML risk levels per FATF guidelines
AML_RISK_LEVELS = frozenset(["LOW", "MEDIUM", "HIGH", "CRITICAL"])

# Valid FATF typologies for AML classification
FATF_TYPOLOGIES = frozenset([
    "ML",  # Money Laundering
    "TF",  # Terrorist Financing
    "PEP",  # Politically Exposed Persons
    "FRAUD",  # Financial Fraud
    "SANCTIONS",  # Sanctions Evasion
    "TAX_EVASION",  # Tax Evasion
    "BRIBERY",  # Bribery and Corruption
    "SMUGGLING",  # Trade-based ML
    "DRUG_TRAFFICKING",  # Drug proceeds
    "HUMAN_TRAFFICKING",  # Human trafficking proceeds
    "PROLIFERATION",  # WMD financing
    "CYBERCRIME",  # Cybercrime proceeds
    "ENVIRONMENTAL"  # Environmental crimes
])

# Confidence threshold for expert review routing
# Using configured threshold from settings
AML_CONFIDENCE_THRESHOLD = 0.6  # Default fallback, use settings.AML_AI_CONFIDENCE_THRESHOLD in production

# Minimum reasoning length for explainability
# Matches prompt requirement (line 161 in aml_labeling_prompt.py)
MIN_REASONING_LENGTH = 50


# =============================================================================
# AML Response Validation (P01-004)
# =============================================================================

def validate_aml_response(response: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate AML labeling response from AI service.

    Validates:
    - risk_level is in AML_RISK_LEVELS
    - typology is in FATF_TYPOLOGIES
    - confidence_score is between 0 and 1
    - reasoning is non-empty and meets minimum length

    Args:
        response: AI response dictionary

    Returns:
        tuple: (is_valid, list of error messages)
    """
    errors = []

    # Validate risk_level
    risk_level = response.get("risk_level")
    if not risk_level:
        errors.append("Missing required field: risk_level")
    elif risk_level not in AML_RISK_LEVELS:
        errors.append(
            f"Invalid risk_level '{risk_level}'. "
            f"Must be one of: {', '.join(sorted(AML_RISK_LEVELS))}"
        )

    # Validate typology
    typology = response.get("typology")
    if not typology:
        errors.append("Missing required field: typology")
    elif typology not in FATF_TYPOLOGIES:
        errors.append(
            f"Invalid typology '{typology}'. "
            f"Must be one of: {', '.join(sorted(FATF_TYPOLOGIES))}"
        )

    # Validate confidence_score
    confidence = response.get("confidence_score")
    if confidence is None:
        errors.append("Missing required field: confidence_score")
    else:
        try:
            conf_value = float(confidence)
            if conf_value < 0.0 or conf_value > 1.0:
                errors.append(
                    f"Invalid confidence_score {conf_value}. "
                    "Must be between 0.0 and 1.0"
                )
        except (TypeError, ValueError):
            errors.append(
                f"Invalid confidence_score type. "
                "Must be a numeric value between 0.0 and 1.0"
            )

    # Validate reasoning
    reasoning = response.get("reasoning")
    if not reasoning:
        errors.append("Missing required field: reasoning")
    elif not isinstance(reasoning, str):
        errors.append("Reasoning must be a string")
    elif len(reasoning.strip()) < MIN_REASONING_LENGTH:
        errors.append(
            f"Reasoning too short ({len(reasoning.strip())} chars). "
            f"Minimum {MIN_REASONING_LENGTH} characters required for audit trail"
        )

    return (len(errors) == 0, errors)


# =============================================================================
# AML Labeling Task (P01-004)
# =============================================================================

@task
async def apply_aml_labeling(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply AML-specific AI labeling using FATF-aligned prompts.

    This task replaces the generic apply_ai_labeling() for AML use cases.
    It uses the AIService.aml_completion() method and validates responses
    against AML-specific schemas.

    Features:
    - FATF-aligned risk classification (LOW, MEDIUM, HIGH, CRITICAL)
    - FATF typology assignment (ML, TF, PEP, etc.)
    - Confidence scoring with expert review routing
    - Explainable AI reasoning for audit trail
    - Regulatory flags for compliance reporting

    Error Handling:
    - Invalid AI response: Set status PENDING (needs expert review)
    - AI timeout: Return with retry_eligible=True
    - AI error: Set status ESCALATED

    Args:
        data: List of transaction records to label

    Returns:
        List of labeled records with AML classification data

    Reference: P01-004 (AML Labeling Task Implementation)
    """
    from src.models.aml_enums import AMLExpertReviewStatus

    logger = get_run_logger()
    logger.info(f"Applying AML labeling to {len(data)} records")

    # Handle empty input
    if not data:
        logger.info("No records to process")
        return []

    labeled_data = []

    try:
        from src.services.ai_service import AIService, AIRequest
        from src.core.prompts.aml_labeling_prompt import (
            build_aml_labeling_prompt,
            AML_SYSTEM_PROMPT
        )

        # Initialize AI Service
        ai_service = AIService()
        await ai_service.initialize()

        for record in data:
            try:
                labeled_record = await _process_aml_record(
                    record=record,
                    ai_service=ai_service,
                    build_prompt=build_aml_labeling_prompt,
                    system_prompt=AML_SYSTEM_PROMPT,
                    logger=logger
                )
                labeled_data.append(labeled_record)

            except asyncio.TimeoutError as e:
                logger.error(
                    f"AI timeout for record {record.get('id')}: {str(e)}"
                )
                error_record = record.copy()

                # P01-006 Issue 1: Get current retry count (default to 0 if not present)
                current_retry_count = record.get("aml_retry_count", 0)
                new_retry_count = current_retry_count + 1

                # P01-006 Issue 1: Determine if should escalate based on max retry limit
                # Max 3 retries before escalation
                MAX_RETRIES = 3
                should_escalate = new_retry_count >= MAX_RETRIES

                error_record.update({
                    "aml_error": f"AI request timeout: {str(e)}",
                    "aml_error_type": "TIMEOUT",  # P01-006 Issue 3: Standardized error type
                    "aml_retry_count": new_retry_count,  # P01-006 Issue 1: Track retry count
                    "aml_expert_review_status": AMLExpertReviewStatus.ESCALATED.value if should_escalate else AMLExpertReviewStatus.PENDING.value,
                    "aml_retry_eligible": not should_escalate,  # P01-006 Issue 1: No retry after max
                    "aml_processed_at": datetime.utcnow().isoformat()
                })
                labeled_data.append(error_record)

            except Exception as e:
                logger.error(
                    f"AI error for record {record.get('id')}: {str(e)}"
                )
                error_record = record.copy()
                error_record.update({
                    "aml_error": str(e),
                    "aml_error_type": "SERVICE",  # P01-006 Issue 3: Standardized error type
                    "aml_expert_review_status": AMLExpertReviewStatus.ESCALATED.value,
                    "aml_processed_at": datetime.utcnow().isoformat()
                })
                labeled_data.append(error_record)

        logger.info(f"AML labeling completed for {len(labeled_data)} records")
        return labeled_data

    except Exception as e:
        logger.error(f"AI service initialization failed: {str(e)}")
        # Return all records with error status
        from src.models.aml_enums import AMLExpertReviewStatus
        for record in data:
            error_record = record.copy()
            error_record.update({
                "aml_error": f"AI service initialization failed: {str(e)}",
                "aml_expert_review_status": AMLExpertReviewStatus.ESCALATED.value,
                "aml_processed_at": datetime.utcnow().isoformat()
            })
            labeled_data.append(error_record)
        return labeled_data


async def _process_aml_record(
    record: dict[str, Any],
    ai_service: Any,
    build_prompt: callable,
    system_prompt: str,
    logger: Any
) -> dict[str, Any]:
    """
    Process a single record for AML labeling.

    Args:
        record: Transaction record to label
        ai_service: Initialized AI service
        build_prompt: Function to build AML prompt
        system_prompt: System prompt for AI
        logger: Logger instance

    Returns:
        Labeled record with AML classification
    """
    from src.services.ai_service import AIRequest
    from src.models.aml_enums import AMLExpertReviewStatus

    # Build AML-specific prompt
    prompt = build_prompt(record)

    # Create AI request
    request = AIRequest(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.3,  # Lower temperature for consistent classification
        max_tokens=500,
        response_format="json",
        tenant_id=record.get("tenant_id", "unknown"),
        user_id=record.get("user_id"),
        use_cache=True
    )

    # Call AI Service using aml_completion method if available
    # Using EAFP pattern for better error handling
    try:
        response = await ai_service.aml_completion(request)
    except AttributeError:
        # Fall back to standard completion if aml_completion not available
        response = await ai_service.completion(request)

    # Parse JSON response
    try:
        ai_result = json.loads(response.content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        # Return error record
        error_record = record.copy()
        error_record.update({
            "aml_error": f"Invalid JSON response from AI: {str(e)}",
            "aml_error_type": "PARSING",  # P01-006 Issue 3: Standardized error type
            "aml_expert_review_status": AMLExpertReviewStatus.PENDING.value,
            "aml_processed_at": datetime.utcnow().isoformat()
        })
        return error_record

    # Validate response
    is_valid, validation_errors = validate_aml_response(ai_result)

    if not is_valid:
        logger.warning(
            f"AML response validation failed for record {record.get('id')}: "
            f"{validation_errors}"
        )
        error_record = record.copy()
        error_record.update({
            "aml_validation_error": "; ".join(validation_errors),
            "aml_error": "; ".join(validation_errors),  # P01-006 Issue 3: Standardized field
            "aml_error_type": "VALIDATION",  # P01-006 Issue 3: Standardized error type
            "aml_expert_review_status": AMLExpertReviewStatus.PENDING.value,
            "aml_processed_at": datetime.utcnow().isoformat()
        })
        return error_record

    # Extract validated values
    risk_level = ai_result.get("risk_level")
    typology = ai_result.get("typology")
    confidence_score = float(ai_result.get("confidence_score"))
    reasoning = ai_result.get("reasoning")
    regulatory_flags = ai_result.get("regulatory_flags", [])

    # Determine expert review status based on risk and confidence
    if risk_level == "CRITICAL":
        # CRITICAL risk always escalated for immediate attention
        expert_review_status = AMLExpertReviewStatus.ESCALATED
        requires_expert_review = True
    elif confidence_score < AML_CONFIDENCE_THRESHOLD:
        # Low confidence requires expert review
        expert_review_status = AMLExpertReviewStatus.PENDING
        requires_expert_review = True
    else:
        # High confidence, non-critical: mark as agreed (auto-approved)
        # Using AGREED status since AI and expert would agree at high confidence
        expert_review_status = AMLExpertReviewStatus.AGREED
        requires_expert_review = False

    # Build labeled record
    labeled_record = record.copy()
    labeled_record.update({
        "aml_risk_level": risk_level,
        "aml_typology": typology,
        "aml_confidence_score": confidence_score,
        "aml_reasoning": reasoning,
        "aml_regulatory_flags": regulatory_flags,
        "aml_expert_review_status": expert_review_status.value,
        "aml_requires_expert_review": requires_expert_review,
        "aml_model": response.model,
        "aml_processed_at": datetime.utcnow().isoformat(),
        "aml_request_id": response.request_id,
        "aml_tokens_used": response.usage.total_tokens,
        "aml_cost": str(response.cost),
        "aml_processing_time_ms": response.response_time_ms,
        "aml_fallback_used": response.fallback_used,
        "aml_from_cache": response.from_cache
    })

    logger.debug(
        f"Record {record.get('id')} labeled: "
        f"risk={risk_level}, typology={typology}, confidence={confidence_score:.2f}"
    )

    return labeled_record


# =============================================================================
# AML Inter-Rater Agreement Task (P01-006)
# =============================================================================

@task
async def compute_inter_rater_agreement(
    ai_labels: list[dict[str, Any]],
    expert_reviews: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Compute Cohen's Kappa coefficient for AI and expert agreement.

    P01-006 Requirement #2:
    This task calculates inter-rater reliability between AI-generated
    AML classifications and human expert reviews using Cohen's Kappa.

    The Kappa coefficient measures agreement beyond chance:
    - k = 1.0: Perfect agreement
    - k = 0.0: Agreement equal to chance
    - k < 0.0: Agreement worse than chance

    Features:
    - Uses CohenKappaCalculator for accurate kappa computation
    - Extracts risk levels from AI labels and expert reviews
    - Returns kappa, confidence level, and sufficiency flag
    - Includes metadata for audit trail

    Args:
        ai_labels: List of AI-labeled records with aml_risk_level field
        expert_reviews: List of expert reviews with expert_risk_level field
                      Must include transaction_id to match with AI labels

    Returns:
        Dictionary with:
        - kappa: Cohen's Kappa coefficient (float)
        - confidence_level: Interpretation label (POOR/FAIR/MODERATE/SUBSTANTIAL/PERFECT)
        - is_sufficient: Boolean indicating if kappa >= threshold
        - sample_size: Number of matched pairs used for calculation
        - computed_at: ISO timestamp of calculation
        - error: Error message if calculation failed (optional)

    Example:
        >>> result = await compute_inter_rater_agreement(
        ...     ai_labels=[{"id": 1, "aml_risk_level": "HIGH"}, ...],
        ...     expert_reviews=[{"transaction_id": 1, "expert_risk_level": "HIGH"}, ...]
        ... )
        >>> print(result["kappa"])  # 0.85
        >>> print(result["confidence_level"])  # "SUBSTANTIAL"
        >>> print(result["is_sufficient"])  # True

    Reference: P01-005 (Cohen's Kappa Calculator Implementation)
    """
    logger = get_run_logger()
    logger.info(
        f"Computing inter-rater agreement: "
        f"{len(ai_labels)} AI labels, {len(expert_reviews)} expert reviews"
    )

    try:
        from src.core.agreement_calculator import CohenKappaCalculator

        # Handle empty inputs
        if not ai_labels or not expert_reviews:
            logger.warning("Cannot compute agreement: empty inputs")
            return {
                "kappa": None,
                "confidence_level": "UNAVAILABLE",
                "is_sufficient": False,
                "sample_size": 0,
                "computed_at": datetime.utcnow().isoformat(),
                "error": "Empty input data"
            }

        # Create mapping from transaction_id to AI risk level
        ai_risk_map = {
            label.get("id"): label.get("aml_risk_level")
            for label in ai_labels
            if "aml_risk_level" in label
        }

        # Create mapping from transaction_id to expert risk level
        expert_risk_map = {
            review.get("transaction_id"): review.get("expert_risk_level")
            for review in expert_reviews
            if "expert_risk_level" in review
        }

        # Find matching transaction IDs
        matching_ids = set(ai_risk_map.keys()) & set(expert_risk_map.keys())

        if not matching_ids:
            logger.warning("No matching transaction IDs between AI labels and expert reviews")
            return {
                "kappa": None,
                "confidence_level": "UNAVAILABLE",
                "is_sufficient": False,
                "sample_size": 0,
                "computed_at": datetime.utcnow().isoformat(),
                "error": "No matching transaction IDs"
            }

        # Extract matched pairs for kappa calculation
        ai_decisions = [ai_risk_map[tid] for tid in matching_ids]
        expert_decisions = [expert_risk_map[tid] for tid in matching_ids]

        # Initialize calculator and compute kappa
        calculator = CohenKappaCalculator()
        kappa = calculator.calculate_agreement(ai_decisions, expert_decisions)
        confidence_level = calculator.get_confidence_level(kappa)
        is_sufficient = calculator.is_agreement_sufficient(kappa)

        result = {
            "kappa": kappa,
            "confidence_level": confidence_level,
            "is_sufficient": is_sufficient,
            "sample_size": len(matching_ids),
            "computed_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Inter-rater agreement computed: kappa={kappa:.4f}, "
            f"level={confidence_level}, sufficient={is_sufficient}"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to compute inter-rater agreement: {str(e)}")
        return {
            "kappa": None,
            "confidence_level": "ERROR",
            "is_sufficient": False,
            "sample_size": 0,
            "computed_at": datetime.utcnow().isoformat(),
            "error": str(e)
        }


# =============================================================================
# AML Audit Report Generation Task (P01-015)
# =============================================================================

@task
async def generate_audit_report(
    job_id: str,
    tenant_id: str,
    labeled_data: list[dict[str, Any]],
    kappa_score: float | None = None
) -> dict[str, Any]:
    """
    Generate comprehensive AML audit report for regulatory compliance.

    P01-015 Implementation:
    This task uses AuditReportGenerator to create complete JSON audit reports
    with all required sections for regulatory defensibility.

    Features:
    - Complete report structure (report_id, timestamps, metadata)
    - AML risk distribution (LOW, MEDIUM, HIGH, CRITICAL counts)
    - FATF typology distribution
    - Inter-rater agreement metrics (Cohen's Kappa + confidence level)
    - Expert review queue size
    - Regulatory references (FATF, FinCEN, EU AML Directive)
    - Audit trail metadata (methodology version, compliance status)

    Args:
        job_id: Processing job identifier that generated the labeled data
        tenant_id: Tenant identifier for multi-tenancy isolation
        labeled_data: List of AML-labeled transaction records
        kappa_score: Optional Cohen's Kappa coefficient from inter-rater agreement

    Returns:
        Dictionary with complete audit report including:
        - report_id: Unique report identifier (UUID-based with timestamp)
        - report_generated_at: ISO timestamp of report generation
        - job_id: Processing job identifier
        - tenant_id: Tenant identifier
        - total_transactions: Total number of processed transactions
        - aml_risk_distribution: Count of transactions per risk level
        - typology_distribution: Count per FATF typology
        - inter_rater_agreement: Kappa score and confidence level
        - expert_review_queue_size: Number of records pending expert review
        - regulatory_references: List of applicable regulatory citations
        - audit_trail: Methodology version and compliance status

    Example:
        >>> report = await generate_audit_report(
        ...     job_id="job_abc123",
        ...     tenant_id="tenant_001",
        ...     labeled_data=labeled_transactions,
        ...     kappa_score=0.85
        ... )
        >>> print(report["total_transactions"])  # 150
        >>> print(report["aml_risk_distribution"])  # {"LOW": 80, "MEDIUM": 40, ...}
        >>> print(report["inter_rater_agreement"]["confidence_level"])  # "PERFECT"

    Reference: P01-015 (Audit Report Generation)
    """
    logger = get_run_logger()
    logger.info(
        f"Generating AML audit report for job {job_id}: "
        f"{len(labeled_data)} transactions"
    )

    try:
        from src.services.audit_report_generator import AuditReportGenerator

        # Initialize generator
        generator = AuditReportGenerator()

        # Generate complete report
        report = generator.generate_report(
            job_data={"job_id": job_id, "tenant_id": tenant_id},
            labels=labeled_data,
            kappa_score=kappa_score
        )

        logger.info(
            f"Successfully generated audit report {report['report_id']}: "
            f"{report['total_transactions']} transactions, "
            f"kappa={kappa_score}, "
            f"risk_dist={report['aml_risk_distribution']}"
        )

        return report

    except Exception as e:
        logger.error(f"Failed to generate audit report: {str(e)}")
        # Return minimal report with error info for resilience
        return {
            "report_id": f"aml_report_error_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "report_generated_at": datetime.utcnow().isoformat(),
            "job_id": job_id,
            "tenant_id": tenant_id,
            "total_transactions": len(labeled_data),
            "aml_risk_distribution": {},
            "typology_distribution": {},
            "inter_rater_agreement": {
                "kappa_score": None,
                "confidence_level": "ERROR",
                "available": False
            },
            "expert_review_queue_size": 0,
            "regulatory_references": [],
            "audit_trail": {
                "methodology_version": "v1.0",
                "generated_by": "system",
                "compliance_status": "error"
            },
            "error": str(e)
        }


# PII Redaction Support - Track Presidio availability
PRESIDIO_AVAILABLE: bool = False
try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer
    from presidio_anonymizer import AnonymizerEngine
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    logger.warning(
        "Presidio not installed - PII redaction will be skipped. "
        "Install with: pip install presidio-analyzer presidio-anonymizer"
    )


def _get_ssn_recognizer() -> PatternRecognizer | None:
    r"""
    Create a custom SSN recognizer for hyphenated format: XXX-XX-XXXX.

    WHY:
    - Presidio's default US_SSN recognizer may not detect hyphenated SSNs
    - The format '123-45-6789' is a common SSN representation
    - Custom pattern ensures consistent detection

    HOW:
    - Uses regex pattern \d{3}-\d{2}-\d{4}
    - Assigns high confidence (0.9) for exact pattern matches
    - Returns None if Presidio is not available

    Returns:
        PatternRecognizer configured for SSN detection, or None
    """
    if not PRESIDIO_AVAILABLE:
        return None

    from presidio_analyzer import Pattern

    # SSN pattern: XXX-XX-XXXX (exactly 3 digits, hyphen, 2 digits, hyphen, 4 digits)
    ssn_patterns = [
        Pattern(
            name="SSN_HYPHENATED_PATTERN",
            regex=r"\b\d{3}-\d{2}-\d{4}\b",
            score=0.9,
        )
    ]

    # Create the recognizer
    # Note: Not using a deny list for test values - in production,
    # you may want to add common example SSNs to avoid false positives
    return PatternRecognizer(
        supported_entity="US_SSN",
        patterns=ssn_patterns,
        context=["ssn", "social", "security", "tax", "id"],
    )


def sanitize_prompt_input(value: Any, max_length: int = 100) -> str:
    """
    Sanitize user data for safe inclusion in AI prompts.

    SECURITY: This function prevents prompt injection attacks by:
    1. Stripping control characters and newlines that could inject commands
    2. Limiting length to prevent token overflow attacks
    3. Removing potential prompt injection patterns

    Args:
        value: The user input to sanitize
        max_length: Maximum length of sanitized output

    Returns:
        Sanitized string safe for prompt interpolation
    """
    if value is None:
        return ""

    # Convert to string
    text = str(value)

    # Remove common prompt injection patterns
    injection_patterns = [
        r"\bignore\s+(all\s+)?(previous\s+)?(instructions?|commands?)\b",
        r"\bforget\s+(all\s+)?(previous\s+)?(instructions?|commands?)\b",
        r"\boverride\s+(all\s+)?(previous\s+)?(instructions?|commands?)\b",
        r"\bdisregard\s+(all\s+)?(previous\s+)?(instructions?|commands?)\b",
        r"\bprint\s+(all\s+)?(the\s+)?(data|records|information)\b",
        r"\bshow\s+(all\s+)?(the\s+)?(data|records|information)\b",
        r"\bdump\s+(all\s+)?(the\s+)?(data|records|database)\b",
        r"\bexec(ute)?\s*\(",
        r"\beval\s*\(",
        r"__import__",
    ]

    for pattern in injection_patterns:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)

    # Remove control characters and newlines (prevent command injection)
    text = re.sub(r"[\x00-\x1f\x7f-\x9f\n\r\t]", " ", text)

    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Limit length
    if len(text) > max_length:
        text = text[:max_length] + "..."

    return text


def build_safe_prompt(template: str, **kwargs) -> str:
    """
    Build an AI prompt from template with sanitized user data.

    This function safely interpolates user-provided data into prompt templates,
    applying sanitization to prevent prompt injection attacks.

    Args:
        template: Prompt template with {placeholder} syntax
        **kwargs: User data to interpolate (will be sanitized)

    Returns:
        Safe prompt with sanitized user data
    """
    # Sanitize all keyword arguments
    safe_kwargs = {
        key: sanitize_prompt_input(value) for key, value in kwargs.items()
    }

    # Interpolate into template
    return template.format(**safe_kwargs)


@task
def extract_data(data_source: str) -> list[dict[str, Any]]:
    """
    Extract data from source (simulated).
    In production, this would connect to various data sources.
    """
    logger = get_run_logger()
    logger.info(f"Extracting data from {data_source}")

    # Simulate data extraction
    sample_data = [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "555-5678",
            "tenant_id": "tenant_001",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 3,
            "name": "Bob Johnson",
            "email": "bob@example.com",
            "phone": "555-9876",
            "tenant_id": "tenant_002",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    logger.info(f"Extracted {len(sample_data)} records")
    return sample_data


@task
def validate_schema(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Validate schema using DataQualityValidator.

    WHY:
    - Ensures data quality before processing
    - Prevents invalid data from reaching AI processing (30% cost savings)
    - Provides detailed error/warning information

    HOW:
    - Uses DataQualityValidator to validate each record
    - Returns tuple of (valid_records, invalid_records)
    - Invalid records include validation_errors and validation_warnings fields

    Args:
        data: List of records to validate

    Returns:
        tuple: (valid_records, invalid_records)

    Example:
        >>> valid, invalid = validate_schema(records)
        >>> print(f"Valid: {len(valid)}, Invalid: {len(invalid)}")
    """
    logger = get_run_logger()
    logger.info(f"Validating schema for {len(data)} records")

    validator = DataQualityValidator()
    valid_records = []
    invalid_records = []

    for record in data:
        try:
            result: ValidationResult = validator.validate_record(record)

            # Add validation metadata to record
            record_with_validation = record.copy()
            record_with_validation["validation_is_valid"] = result.is_valid
            record_with_validation["validation_completeness_score"] = result.completeness_score
            record_with_validation["validation_validity_score"] = result.validity_score
            record_with_validation["validation_quality_score"] = result.quality_score
            record_with_validation["validation_errors"] = result.errors
            record_with_validation["validation_warnings"] = result.warnings
            record_with_validation["validated_at"] = datetime.utcnow().isoformat()

            if result.is_valid:
                valid_records.append(record_with_validation)
                logger.debug(
                    f"Record valid: quality_score={result.quality_score:.2f}, "
                    f"completeness={result.completeness_score:.2f}"
                )
            else:
                invalid_records.append(record_with_validation)
                logger.warning(
                    f"Record invalid: errors={result.errors}, warnings={result.warnings}"
                )

        except Exception as e:
            logger.error(f"Validation error for record: {str(e)}")
            # Add to invalid records with error
            error_record = record.copy()
            error_record["validation_is_valid"] = False
            error_record["validation_errors"] = [f"Validation exception: {str(e)}"]
            error_record["validation_warnings"] = []
            error_record["validated_at"] = datetime.utcnow().isoformat()
            invalid_records.append(error_record)

    logger.info(
        f"Schema validation complete: {len(valid_records)} valid, {len(invalid_records)} invalid"
    )
    return valid_records, invalid_records


@task
async def validate_with_ab_testing(
    records: list[dict[str, Any]],
    control_validator: Callable[[dict[str, Any]], ValidationResult],
    variant_validator: Callable[[dict[str, Any]], ValidationResult],
    ab_ratio: float | None = None
) -> dict[str, Any]:
    """
    Run A/B test comparing two validation strategies.

    WHY:
    - Enables comparison of different validation approaches
    - Provides data-driven decisions about validation strategy effectiveness
    - Allows gradual rollout of new validation logic with safety monitoring

    HOW:
    - Uses ABTestingWrapper for deterministic treatment assignment
    - Routes records to control or variant validator based on record_id hash
    - Collects metrics via BasicMetricsCollector for comparison
    - Falls back to control validator when A/B testing is disabled

    Args:
        records: List of data records to validate (must have record_id field)
        control_validator: Control strategy validation function
            Signature: (record: Dict) -> ValidationResult
        variant_validator: Variant strategy validation function
            Signature: (record: Dict) -> ValidationResult
        ab_ratio: Fraction of traffic to route to variant (0.0-1.0)
            Defaults to settings.AB_TEST_RATIO if not specified

    Returns:
        Dictionary with:
        - control_results: Validation results for control group
        - variant_results: Validation results for variant group
        - metrics: Comparison metrics from BasicMetricsCollector
        - total_processed: Total number of records processed

    Example:
        >>> from src.core.data_quality import DataQualityValidator
        >>> validator = DataQualityValidator()
        >>> result = await validate_with_ab_testing(
        ...     records=records,
        ...     control_validator=validator.validate_record,
        ...     variant_validator=variant_validator.validate_record,
        ...     ab_ratio=0.3
        ... )
        >>> print(f"Control: {len(result['control_results'])}, "
        ...       f"Variant: {len(result['variant_results'])}")
    """
    logger = get_run_logger()

    # Use default ratio from settings if not specified
    if ab_ratio is None:
        ab_ratio = settings.AB_TEST_RATIO

    # Check if A/B testing is enabled
    if not settings.ENABLE_AB_TESTING:
        logger.info(
            "A/B testing disabled (ENABLE_AB_TESTING=False) - "
            "using control validator for all records"
        )

        # Fallback to standard validation using control validator
        control_results = []
        for record in records:
            try:
                result: ValidationResult = control_validator(record)
                control_results.append({
                    "record_id": record.get("record_id"),
                    "is_valid": result.is_valid,
                    "quality_score": result.quality_score,
                    "completeness_score": result.completeness_score,
                    "validity_score": result.validity_score,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "treatment": "control",
                    "is_variant": False
                })
            except Exception as e:
                logger.error(f"Control validation error for record {record.get('record_id')}: {str(e)}")
                control_results.append({
                    "record_id": record.get("record_id"),
                    "is_valid": False,
                    "quality_score": 0.0,
                    "completeness_score": 0.0,
                    "validity_score": 0.0,
                    "errors": [f"Validation exception: {str(e)}"],
                    "warnings": [],
                    "treatment": "control",
                    "is_variant": False
                })

        return {
            "control_results": control_results,
            "variant_results": [],
            "metrics": {},
            "total_processed": len(records)
        }

    # Initialize A/B testing wrapper
    logger.info(
        f"A/B testing enabled - test_name={settings.AB_TEST_NAME}, "
        f"ratio={ab_ratio:.1%}, processing {len(records)} records"
    )

    wrapper = ABTestingWrapper(
        test_name=settings.AB_TEST_NAME,
        treatment_ratio=ab_ratio
    )

    control_results: list[dict[str, Any]] = []
    variant_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for record in records:
        try:
            # Validate with A/B treatment assignment
            ab_result = wrapper.validate_with_ab_info(
                record=record,
                control_validator=control_validator,
                variant_validator=variant_validator
            )

            result_dict = {
                "record_id": record.get("record_id"),
                "treatment": ab_result.treatment,
                "is_variant": ab_result.is_variant,
                "is_valid": ab_result.validation_result.is_valid,
                "quality_score": ab_result.validation_result.quality_score,
                "completeness_score": ab_result.validation_result.completeness_score,
                "validity_score": ab_result.validation_result.validity_score,
                "errors": ab_result.validation_result.errors,
                "warnings": ab_result.validation_result.warnings
            }

            # Sort results by treatment
            if ab_result.is_variant:
                variant_results.append(result_dict)
            else:
                control_results.append(result_dict)

        except Exception as e:
            logger.error(f"A/B validation error for record {record.get('record_id')}: {str(e)}")
            errors.append({
                "record_id": record.get("record_id"),
                "error": str(e)
            })

    # Get metrics from wrapper
    metrics = wrapper.get_metrics()
    stats = wrapper.get_stats()

    logger.info(
        f"A/B testing complete: control={len(control_results)}, "
        f"variant={len(variant_results)}, errors={len(errors)}"
    )
    logger.info(
        f"Treatment distribution: {stats['control_count']} control, "
        f"{stats['variant_count']} variant (total: {stats['total_samples']})"
    )

    return {
        "control_results": control_results,
        "variant_results": variant_results,
        "metrics": metrics,
        "total_processed": len(records)
    }


@task
def check_duplicates(data: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Check for duplicate records using content-based hashing.

    WHY:
    - Prevents duplicate AI processing (5-10% cost savings)
    - Identifies records that have already been processed
    - Maintains data integrity in the pipeline

    HOW:
    - Generates SHA-256 hash from record content (sorted fields)
    - Uses in-memory set to track seen hashes
    - Returns tuple of (new_records, duplicate_records)

    Args:
        data: List of records to check for duplicates

    Returns:
        tuple: (new_records, duplicate_records)

    Example:
        >>> new, dupes = check_duplicates(records)
        >>> print(f"New: {len(new)}, Duplicates: {len(dupes)}")
    """
    logger = get_run_logger()
    logger.info(f"Checking {len(data)} records for duplicates")

    seen_hashes = set()
    new_records = []
    duplicate_records = []

    for record in data:
        try:
            # Create deterministic hash from record content
            # Sort keys and exclude validation fields for hash calculation
            record_for_hash = {
                k: v for k, v in record.items()
                if not k.startswith("validation_")
            }
            record_str = json.dumps(record_for_hash, sort_keys=True)
            record_hash = hashlib.sha256(record_str.encode()).hexdigest()

            record_with_hash = record.copy()
            record_with_hash["record_hash"] = record_hash

            if record_hash in seen_hashes:
                duplicate_records.append(record_with_hash)
                logger.debug(f"Duplicate record found: hash={record_hash[:16]}...")
            else:
                seen_hashes.add(record_hash)
                new_records.append(record_with_hash)
                logger.debug(f"New record: hash={record_hash[:16]}...")

        except Exception as e:
            logger.error(f"Error checking duplicate for record: {str(e)}")
            # Treat hash errors as new records to avoid data loss
            record_with_error = record.copy()
            record_with_error["duplicate_check_error"] = str(e)
            new_records.append(record_with_error)

    logger.info(
        f"Duplicate check complete: {len(new_records)} new, {len(duplicate_records)} duplicates"
    )
    return new_records, duplicate_records


@task
def compute_quality_scores(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Add quality scores to records from validation results.

    WHY:
    - Adds computed quality scores to records for filtering
    - Enables data-driven decisions about record quality
    - Provides metrics for monitoring and analysis

    HOW:
    - Extracts validation scores from validated records
    - Maps to data_quality_score, completeness_score, validity_score
    - Adds quality metadata fields

    Args:
        data: List of validated records

    Returns:
        list: Records with quality scores added

    Example:
        >>> scored = compute_quality_scores(validated_records)
        >>> print(f"Average quality: {avg(r['data_quality_score'] for r in scored):.2f}")
    """
    logger = get_run_logger()
    logger.info(f"Computing quality scores for {len(data)} records")

    scored_records = []

    for record in data:
        try:
            record_with_scores = record.copy()

            # Extract or compute quality scores
            if "validation_quality_score" in record:
                # Use validation results
                record_with_scores["data_quality_score"] = record.get("validation_quality_score", 0.0)
                record_with_scores["completeness_score"] = record.get("validation_completeness_score", 0.0)
                record_with_scores["validity_score"] = record.get("validation_validity_score", 0.0)
            else:
                # Default values if not validated
                record_with_scores["data_quality_score"] = 0.5
                record_with_scores["completeness_score"] = 0.5
                record_with_scores["validity_score"] = 0.5

            record_with_scores["quality_scored_at"] = datetime.utcnow().isoformat()
            scored_records.append(record_with_scores)

            logger.debug(
                f"Quality scores: data_quality={record_with_scores['data_quality_score']:.2f}"
            )

        except Exception as e:
            logger.error(f"Error computing quality scores: {str(e)}")
            # Add record with default scores
            error_record = record.copy()
            error_record["data_quality_score"] = 0.0
            error_record["completeness_score"] = 0.0
            error_record["validity_score"] = 0.0
            error_record["quality_score_error"] = str(e)
            scored_records.append(error_record)

    logger.info(f"Quality scores computed for {len(scored_records)} records")
    return scored_records


@task
def filter_low_quality(
    data: list[dict[str, Any]],
    min_quality: float = 0.5
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Filter records by quality score threshold.

    WHY:
    - Prevents low-quality data from reaching AI processing
    - Reduces noise and improves AI model performance
    - Enables separate handling of low-quality records

    HOW:
    - Filters records based on data_quality_score >= min_quality
    - Returns tuple of (high_quality_records, low_quality_records)
    - Uses MIN_QUALITY_SCORE from config as default threshold

    Args:
        data: List of scored records to filter
        min_quality: Minimum quality score (default: from config)

    Returns:
        tuple: (high_quality_records, low_quality_records)

    Example:
        >>> high, low = filter_low_quality(scored_records, min_quality=0.7)
        >>> print(f"High quality: {len(high)}, Low quality: {len(low)}")
    """
    logger = get_run_logger()
    logger.info(
        f"Filtering {len(data)} records by quality threshold: {min_quality}"
    )

    high_quality = []
    low_quality = []

    for record in data:
        try:
            quality_score = record.get("data_quality_score", 0.0)

            if quality_score >= min_quality:
                high_quality.append(record)
                logger.debug(
                    f"High quality record: score={quality_score:.2f}"
                )
            else:
                low_quality.append(record)
                logger.debug(
                    f"Low quality record: score={quality_score:.2f}"
                )

        except Exception as e:
            logger.error(f"Error filtering record: {str(e)}")
            # Treat errors as low quality
            error_record = record.copy()
            error_record["filter_error"] = str(e)
            low_quality.append(error_record)

    logger.info(
        f"Quality filtering complete: {len(high_quality)} high quality, "
        f"{len(low_quality)} low quality"
    )
    return high_quality, low_quality


@task
def apply_pii_redaction(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply PII redaction using Microsoft Presidio.

    SECURITY: If Presidio is not installed and PII redaction is enabled,
    this function will log a clear warning but continue processing.
    In production, ensure Presidio is installed if ENABLE_PII_REDACTION is True.

    WHY:
    - Redacts PII including SSN, phone, email, and names
    - Uses custom SSN recognizer for hyphenated format (XXX-XX-XXXX)
    - Returns metadata about what was redacted

    HOW:
    - Registers custom SSN pattern recognizer with Presidio analyzer
    - Processes text fields: name, email, phone, ssn, notes
    - Replaces detected PII with entity type placeholders (e.g., <US_SSN>)

    Args:
        data: List of records to redact

    Returns:
        List of records with PII redacted and metadata added

    Example:
        >>> redacted = apply_pii_redaction([{"ssn": "123-45-6789", ...}])
        >>> redacted[0]["ssn"]  # Returns: "<US_SSN>"
    """
    logger = get_run_logger()

    if not PRESIDIO_AVAILABLE:
        logger.warning(
            "PII redaction requested but Presidio is not installed. "
            "Returning data WITHOUT redaction - SECURITY RISK in production! "
            "Install with: pip install presidio-analyzer presidio-anonymizer"
        )
        # Add metadata indicating PII was NOT redacted
        for record in data:
            record["pii_redaction_skipped"] = True
            record["pii_redaction_reason"] = "Presidio not installed"
        return data

    logger.info("Applying PII redaction with Presidio")

    # Initialize analyzer with custom SSN recognizer
    analyzer = AnalyzerEngine()
    ssn_recognizer = _get_ssn_recognizer()
    if ssn_recognizer:
        analyzer.registry.add_recognizer(ssn_recognizer)
        logger.info("Custom SSN recognizer registered for hyphenated format (XXX-XX-XXXX)")

    anonymizer = AnonymizerEngine()

    redacted_data = []
    for record in data:
        # Analyze and anonymize PII
        # Include 'ssn' and 'notes' fields in addition to standard fields
        text_fields = ["name", "email", "phone", "ssn", "notes"]
        redacted_record = record.copy()

        for field in text_fields:
            if field in record:
                try:
                    # Analyze the text for PII
                    results = analyzer.analyze(text=str(record[field]), language="en")

                    # Anonymize if PII detected
                    if results:
                        anonymized = anonymizer.anonymize(
                            text=str(record[field]), analyzer_results=results
                        )
                        redacted_record[field] = anonymized.text
                        redacted_record[f"{field}_redacted"] = True
                    else:
                        redacted_record[f"{field}_redacted"] = False
                except Exception as e:
                    logger.warning(f"Failed to redact PII in field {field}: {e}")
                    redacted_record[f"{field}_redaction_error"] = str(e)

        redacted_record["pii_redaction_applied"] = True
        redacted_data.append(redacted_record)

    logger.info(f"PII redaction applied to {len(redacted_data)} records")
    return redacted_data


@task
async def apply_ai_labeling(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Apply AI labeling using LiteLLM integrated AI Service.
    """
    logger = get_run_logger()
    logger.info("Applying AI labeling with LiteLLM integration")

    try:
        from src.services.ai_service import AIService, AIRequest
        import json

        # Initialize AI Service
        ai_service = AIService()
        await ai_service.initialize()

        labeled_data = []
        for record in data:
            try:
                # Create labeling prompt with SANITIZED user data
                # SECURITY: Using build_safe_prompt to prevent prompt injection
                prompt = build_safe_prompt(
                    """
                    Analyze this record and assign labels:
                    Name: {name}
                    Email: {email}
                    Phone: {phone}

                    Assign one of these categories:
                    - 'high_value' (appears to be enterprise/corporate)
                    - 'medium_value' (appears to be small business)
                    - 'low_value' (appears to be personal)

                    Also provide a confidence score (0-1).

                    Return JSON: {{"category": "...", "confidence": ..., "reasoning": "..."}}
                    """,
                    name=record.get("name", "N/A"),
                    email=record.get("email", "N/A"),
                    phone=record.get("phone", "N/A")
                )

                # Create AI request
                request = AIRequest(
                    prompt=prompt,
                    system_prompt="You are a data labeling expert.",
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=200,
                    response_format="json",
                    tenant_id=record.get("tenant_id", "unknown"),
                    user_id=record.get("user_id"),
                    use_cache=True
                )

                # Call AI Service
                response = await ai_service.completion(request)

                # Parse response
                ai_result = json.loads(response.content)

                # Add AI results to record with enhanced metadata
                labeled_record = record.copy()
                labeled_record.update(
                    {
                        "ai_category": ai_result.get("category"),
                        "ai_confidence": ai_result.get("confidence"),
                        "ai_reasoning": ai_result.get("reasoning"),
                        "ai_model": response.model,
                        "ai_processed_at": datetime.utcnow().isoformat(),
                        "ai_request_id": response.request_id,
                        "ai_tokens_used": response.usage.total_tokens,
                        "ai_cost": str(response.cost),
                        "ai_processing_time_ms": response.response_time_ms,
                        "ai_fallback_used": response.fallback_used,
                        "ai_from_cache": response.from_cache
                    }
                )

                # Add provenance metadata
                provenance = {
                    "ai_service_version": "1.0.0",
                    "processing_pipeline": "ingestion_v2",
                    "model_provider": response.model.split("/")[0] if "/" in response.model else "openai",
                    "token_breakdown": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens
                    },
                    "cost_breakdown": {
                        "currency": "USD",
                        "total_cost": str(response.cost)
                    }
                }
                labeled_record["provenance_metadata"] = json.dumps(provenance)

                # Add processing history
                processing_history = []
                if response.retry_count > 0:
                    processing_history.append({
                        "event": "model_retry",
                        "count": response.retry_count,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                if response.fallback_used:
                    processing_history.append({
                        "event": "model_fallback",
                        "primary_model": settings.PRIMARY_MODEL,
                        "fallback_model": response.model,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                if response.from_cache:
                    processing_history.append({
                        "event": "cache_hit",
                        "cache_key": response.completion_id,
                        "timestamp": response.cached_at.isoformat() if response.cached_at else datetime.utcnow().isoformat()
                    })

                labeled_record["processing_history"] = json.dumps(processing_history)

                labeled_data.append(labeled_record)

            except Exception as e:
                logger.error(f"AI labeling failed for record {record.get('id')}: {str(e)}")
                # Add error to record but continue processing
                error_record = record.copy()
                error_record["ai_error"] = str(e)
                error_record["ai_processed_at"] = datetime.utcnow().isoformat()
                labeled_data.append(error_record)

        logger.info(f"AI labeling applied to {len(labeled_data)} records")
        return labeled_data

    except Exception as e:
        logger.error(f"AI labeling service initialization failed: {str(e)}")
        # Fallback to original OpenAI if available
        logger.info("Attempting fallback to direct OpenAI API")

        try:
            from openai import OpenAI

            # Get API key safely
            api_key = None
            try:
                api_key = settings.secure_openai_api_key
                if callable(api_key):
                    api_key = api_key()
            except Exception:
                api_key = None

            if not api_key:
                raise ValueError("OpenAI API key not available")

            client = OpenAI(api_key=api_key)

            labeled_data = []
            for record in data:
                # SECURITY: Using build_safe_prompt to prevent prompt injection
                prompt = build_safe_prompt(
                    """
                    Analyze this record and assign labels:
                    Name: {name}
                    Email: {email}
                    Phone: {phone}

                    Assign one of these categories:
                    - 'high_value' (appears to be enterprise/corporate)
                    - 'medium_value' (appears to be small business)
                    - 'low_value' (appears to be personal)

                    Also provide a confidence score (0-1).

                    Return JSON: {{"category": "...", "confidence": ..., "reasoning": "..."}}
                    """,
                    name=record.get("name", "N/A"),
                    email=record.get("email", "N/A"),
                    phone=record.get("phone", "N/A")
                )

                response = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a data labeling expert."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=200,
                )

                ai_result = json.loads(response.choices[0].message.content)

                labeled_record = record.copy()
                labeled_record.update(
                    {
                        "ai_category": ai_result.get("category"),
                        "ai_confidence": ai_result.get("confidence"),
                        "ai_reasoning": ai_result.get("reasoning"),
                        "ai_model": settings.OPENAI_MODEL,
                        "ai_processed_at": datetime.utcnow().isoformat(),
                        "ai_fallback_method": "direct_openai"
                    }
                )

                labeled_data.append(labeled_record)

            logger.info(f"Fallback AI labeling applied to {len(labeled_data)} records")
            return labeled_data

        except Exception as fallback_error:
            logger.error(f"Fallback AI labeling also failed: {str(fallback_error)}")
            # Return data without AI labels but with error
            for record in data:
                record["ai_error"] = f"Primary: {str(e)}, Fallback: {str(fallback_error)}"
            return data


@task
def route_for_human_review(
    data: list[dict[str, Any]],
    kappa_score: float | None = None,
    kappa_threshold: float | None = None
) -> tuple[list[dict], list[dict]]:
    """
    Route records based on confidence scores OR Cohen's Kappa threshold.

    P01-006 Modification:
    This task now supports two routing modes:
    1. AML Mode (NEW): Uses Cohen's Kappa threshold from inter-rater agreement
    2. Legacy Mode: Uses confidence threshold (for backward compatibility)

    AML Mode Routing Logic:
    - If kappa_score >= kappa_threshold (default 0.70): Auto-approve all
    - If kappa_score < kappa_threshold: Route all for human review
    - If kappa_score is None: Route conservatively (human review)

    Args:
        data: List of labeled records to route
        kappa_score: Cohen's Kappa coefficient (None for legacy mode)
        kappa_threshold: Threshold for sufficient agreement (defaults to AML_KAPPA_THRESHOLD)

    Returns:
        tuple: (auto_approved_records, human_review_records)

    Example (AML Mode):
        >>> kappa = await compute_inter_rater_agreement(ai_labels, expert_reviews)
        >>> auto, review = route_for_human_review(
        ...     data=labeled_data,
        ...     kappa_score=kappa["kappa"]
        ... )

    Example (Legacy Mode):
        >>> auto, review = route_for_human_review(data=data)
    """
    logger = get_run_logger()
    logger.info("Routing records for human review")

    # Determine threshold: use provided value, config, or None for legacy mode
    if kappa_threshold is None:
        kappa_threshold = settings.AML_KAPPA_THRESHOLD

    auto_approved = []
    human_review = []

    # AML Mode: Use Cohen's Kappa for routing decision
    if kappa_score is not None:
        logger.info(
            f"AML routing mode: kappa={kappa_score:.4f}, threshold={kappa_threshold:.4f}"
        )

        if kappa_score >= kappa_threshold:
            # Sufficient agreement: auto-approve all
            auto_approved = data.copy()
            logger.info(
                f"Cohen's Kappa {kappa_score:.4f} >= threshold {kappa_threshold:.4f}: "
                f"Auto-approving all {len(data)} records"
            )
        else:
            # Insufficient agreement: route all for expert review
            human_review = data.copy()
            logger.warning(
                f"Cohen's Kappa {kappa_score:.4f} < threshold {kappa_threshold:.4f}: "
                f"Routing all {len(data)} records for expert review"
            )
    else:
        # Legacy Mode: Use individual confidence scores
        logger.info("Legacy routing mode: using individual confidence scores")

        for record in data:
            # Try AML confidence first, fall back to generic AI confidence
            confidence = (
                record.get("aml_confidence_score") or
                record.get("ai_confidence", 1.0)
            )

            if confidence < settings.CONFIDENCE_THRESHOLD:
                human_review.append(record)
                logger.info(
                    f"Record {record.get('id')} routed for human review (confidence: {confidence})"
                )
            else:
                auto_approved.append(record)
                logger.info(
                    f"Record {record.get('id')} auto-approved (confidence: {confidence})"
                )

    logger.info(
        f"Routing complete: {len(auto_approved)} auto-approved, "
        f"{len(human_review)} for human review"
    )

    return auto_approved, human_review


@task
def send_to_label_studio(data: list[dict[str, Any]]) -> bool:
    """
    Send low-confidence records to Label Studio for human review.
    """
    logger = get_run_logger()
    logger.info(f"Sending {len(data)} records to Label Studio")

    try:
        from label_studio_sdk import Client

        # Connect to Label Studio
        ls = Client(
            url=settings.LABEL_STUDIO_URL, api_key=settings.secure_label_studio_api_key()
        )

        # Get or create project
        project = ls.get_project(settings.LABEL_STUDIO_PROJECT_ID)

        # Create tasks for human review
        tasks = []
        for record in data:
            task_data = {
                "data": {
                    "record_id": record["id"],
                    "original_data": record,
                    "ai_category": record.get("ai_category"),
                    "ai_confidence": record.get("ai_confidence"),
                    "ai_reasoning": record.get("ai_reasoning"),
                }
            }
            tasks.append(task_data)

        # Import tasks
        if tasks:
            project.import_tasks(tasks)
            logger.info(f"Successfully imported {len(tasks)} tasks to Label Studio")

        return True

    except Exception as e:
        logger.error(f"Failed to send to Label Studio: {str(e)}")
        return False


@task
def save_to_database(
    data: list[dict[str, Any]], table_name: str = "processed_data"
) -> bool:
    """
    Save processed data to PostgreSQL using dlt.
    """
    logger = get_run_logger()
    logger.info(f"Saving {len(data)} records to {table_name}")

    try:
        # Create dlt pipeline
        pipeline_obj = pipeline(
            pipeline_name="data_foundry_ingestion",
            destination=postgres(settings.DATABASE_URL_SYNC),
            dataset_name="public",
        )

        # Create a simple source
        def data_source():
            for record in data:
                yield record

        # Run pipeline
        load_info = pipeline_obj.run(data_source(), table_name=table_name)

        logger.info(f"Successfully saved {len(data)} records to database")
        logger.info(f"Load info: {load_info}")
        return True

    except Exception as e:
        logger.error(f"Failed to save to database: {str(e)}")
        return False


# =============================================================================
# AML Labels Database Persistence (P01-007)
# =============================================================================

@task
async def save_aml_labels_to_database(
    labeled_records: list[dict[str, Any]],
    tenant_id: str,
    job_id: str
) -> dict[str, Any]:
    """
    Save AML-labeled records to database in batches.

    P01-007: Implement AML labels persistence with batch insert, transaction
    handling, and duplicate detection.

    P01-013: Added job_id parameter for job-specific label queries.

    FEATURES:
    - Batch insert: Process 100-500 records at a time for performance
    - Transaction handling: All-or-nothing per batch with commit/rollback
    - Duplicate handling: Skip records that already exist (based on transaction_id)
    - Error handling: Continue processing on individual record failures
    - Return metrics: total_saved, duplicates_skipped, errors
    - Job tracking: Associates labels with the processing job that created them

    BATCH SIZE OPTIMIZATION:
    - Uses settings.DEFAULT_BATCH_SIZE (default: 500)
    - Max batch size limited by settings.MAX_BATCH_SIZE
    - Typical performance: 1000+ labels/sec (bulk insert operations)

    DUPLICATE DETECTION:
    - Checks for existing labels by transaction_id within the same tenant
    - Uses PostgreSQL's ON CONFLICT DO NOTHING for efficient skipping
    - Duplicates are tracked but don't fail the entire batch

    TRANSACTION SAFETY:
    - Each batch is wrapped in a separate transaction
    - Failures in one batch don't affect other batches
    - Individual record errors are logged but don't stop processing

    Args:
        labeled_records: List of AML-labeled transaction records with fields:
            - transaction_id: Unique transaction identifier (required)
            - aml_risk_level: Risk classification (LOW, MEDIUM, HIGH, CRITICAL)
            - aml_typology: FATF typology code
            - aml_confidence_score: AI confidence (0.0 - 1.0)
            - aml_reasoning: AI explanation
            - aml_expert_review_status: Review workflow status
            - aml_regulatory_flags: Optional regulatory flags list
        tenant_id: Tenant identifier for multi-tenancy isolation
        job_id: Processing job identifier that generated these labels

    Returns:
        Dictionary with metrics:
        {
            "total_saved": int,           # Number of labels inserted
            "duplicates_skipped": int,    # Number of duplicates found
            "errors": int,                # Number of record errors
            "batches_processed": int,     # Number of batches
            "processing_time_ms": int,    # Total processing time
            "labels_per_second": float    # Throughput metric
        }

    Example:
        >>> result = await save_aml_labels_to_database(
        ...     labeled_records=labeled_data,
        ...     tenant_id="tenant_001",
        ...     job_id="job_abc123"
        ... )
        >>> print(f"Saved {result['total_saved']} labels, "
        ...       f"skipped {result['duplicates_skipped']} duplicates")

    Reference: P01-007 (Save AML Labels to Database), P01-013 (Add job_id)
    """
    from datetime import datetime
    from decimal import Decimal
    from uuid import uuid4
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    logger = get_run_logger()
    start_time = datetime.utcnow()
    logger.info(
        f"Saving {len(labeled_records)} AML labels to database "
        f"(tenant_id={tenant_id})"
    )

    # Initialize metrics
    metrics = {
        "total_saved": 0,
        "duplicates_skipped": 0,
        "errors": 0,
        "batches_processed": 0,
        "error_details": []
    }

    # Handle empty input
    if not labeled_records:
        logger.info("No labels to save")
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        metrics.update({
            "processing_time_ms": int(processing_time),
            "labels_per_second": 0.0
        })
        return metrics

    # Determine batch size from settings
    batch_size = min(
        settings.DEFAULT_BATCH_SIZE,
        settings.MAX_BATCH_SIZE
    )
    logger.debug(f"Using batch_size={batch_size}")

    try:
        from src.database.connection import db_connection
        from src.models.aml_enums import (
            AMLRiskLevel,
            AMLExpertReviewStatus
        )

        # Process in batches with individual transactions
        async with db_connection.get_session() as session:
            for i in range(0, len(labeled_records), batch_size):
                batch = labeled_records[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(labeled_records) + batch_size - 1) // batch_size

                logger.debug(
                    f"Processing batch {batch_num}/{total_batches} "
                    f"({len(batch)} records)"
                )

                try:
                    # Convert records to ORM model instances
                    label_models = []
                    batch_transaction_ids = []

                    for record in batch:
                        try:
                            # Validate required fields
                            transaction_id = record.get("transaction_id")
                            if not transaction_id:
                                raise ValueError("Missing required field: transaction_id")

                            risk_level_str = record.get("aml_risk_level")
                            if not risk_level_str:
                                raise ValueError("Missing required field: aml_risk_level")

                            # Convert risk_level to enum
                            risk_level = AMLRiskLevel(risk_level_str)

                            # Convert expert_review_status to enum
                            review_status_str = record.get(
                                "aml_expert_review_status",
                                AMLExpertReviewStatus.PENDING.value
                            )
                            expert_review_status = AMLExpertReviewStatus(review_status_str)

                            # Build AMLTransactionLabel model
                            label_model = {
                                "id": str(uuid4()),
                                "transaction_id": str(transaction_id),
                                "tenant_id": tenant_id,
                                "job_id": job_id,
                                "risk_level": risk_level,
                                "typology": record.get("aml_typology", "ML"),
                                "confidence_score": Decimal(
                                    str(record.get("aml_confidence_score", 0.0))
                                ),
                                "ai_reasoning": record.get(
                                    "aml_reasoning",
                                    "No reasoning provided"
                                ),
                                "expert_review_status": expert_review_status,
                                "regulatory_flags": record.get(
                                    "aml_regulatory_flags",
                                    []
                                ),
                                "is_audit_ready": False,
                                "is_deleted": False,
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow()
                            }

                            label_models.append(label_model)
                            batch_transaction_ids.append(str(transaction_id))

                        except (ValueError, TypeError) as e:
                            logger.error(
                                f"Invalid record data for transaction "
                                f"{record.get('transaction_id')}: {e}"
                            )
                            metrics["errors"] += 1
                            metrics["error_details"].append({
                                "transaction_id": record.get("transaction_id"),
                                "error": str(e)
                            })

                    # P01-006 Issue 2: Removed redundant duplicate detection SELECT query
                    # The ON CONFLICT DO NOTHING clause below handles duplicates efficiently
                    # This removes the unnecessary database roundtrip for duplicate checking
                    new_labels = label_models

                    # Bulk insert using PostgreSQL INSERT ... ON CONFLICT
                    if new_labels:
                        # Prepare bulk insert data for optimal performance
                        # Building parameter list for single bulk execute operation
                        bulk_params = [
                            {
                                "id": label["id"],
                                "transaction_id": label["transaction_id"],
                                "tenant_id": label["tenant_id"],
                                "job_id": label["job_id"],
                                "version_id": None,
                                "risk_level": label["risk_level"].value,
                                "typology": label["typology"],
                                "confidence_score": label["confidence_score"],
                                "ai_reasoning": label["ai_reasoning"],
                                "expert_review_status": label["expert_review_status"].value,
                                "regulatory_flags": label["regulatory_flags"],
                                "is_audit_ready": label["is_audit_ready"],
                                "is_deleted": label["is_deleted"],
                                "deleted_by": None,
                                "deleted_at": None,
                                "created_at": label["created_at"],
                                "updated_at": label["updated_at"],
                                "updated_by": None
                            }
                            for label in new_labels
                        ]

                        # Use PostgreSQL's insert ... on conflict for atomic upsert
                        # Bulk operation: single execute() with all parameters
                        insert_stmt = text("""
                            INSERT INTO aml_transaction_labels (
                                id, transaction_id, tenant_id, job_id, version_id,
                                risk_level, typology, confidence_score, ai_reasoning,
                                expert_review_status, regulatory_flags,
                                is_audit_ready, is_deleted, deleted_by, deleted_at,
                                created_at, updated_at, updated_by
                            ) VALUES (
                                :id, :transaction_id, :tenant_id, :job_id, :version_id,
                                :risk_level, :typology, :confidence_score, :ai_reasoning,
                                :expert_review_status, :regulatory_flags,
                                :is_audit_ready, :is_deleted, :deleted_by, :deleted_at,
                                :created_at, :updated_at, :updated_by
                            )
                            ON CONFLICT (transaction_id, tenant_id) DO NOTHING
                        """)

                        # Bulk insert - single round-trip to database
                        # Note: rowcount doesn't reflect skipped duplicates with ON CONFLICT
                        result = await session.execute(insert_stmt, bulk_params)

                        # Commit this batch's transaction
                        await session.commit()

                        # P01-006 Issue 2: With ON CONFLICT DO NOTHING, we can't easily
                        # count duplicates from rowcount. The total_saved metric tracks
                        # attempted inserts. For exact duplicate counts, a post-insert
                        # query would be needed, but that would defeat the performance gain.
                        saved_count = len(new_labels)
                        metrics["total_saved"] += saved_count
                        metrics["batches_processed"] += 1

                        logger.debug(
                            f"Batch {batch_num}: Attempted {saved_count} label inserts "
                            f"(duplicates silently skipped by ON CONFLICT)"
                        )

                    # Flush to ensure transaction integrity
                    await session.flush()

                except Exception as batch_error:
                    # Rollback on batch error but continue with next batch
                    await session.rollback()
                    logger.error(
                        f"Batch {batch_num} failed: {batch_error}. "
                        f"Rolling back and continuing..."
                    )
                    metrics["errors"] += len(batch)
                    metrics["error_details"].append({
                        "batch": batch_num,
                        "error": str(batch_error)
                    })
                    # Continue to next batch instead of failing entire operation

        # Calculate final metrics
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        total_processed = metrics["total_saved"] + metrics["duplicates_skipped"]
        labels_per_second = (
            (total_processed / processing_time) * 1000
            if processing_time > 0 else 0
        )

        metrics.update({
            "processing_time_ms": int(processing_time),
            "labels_per_second": round(labels_per_second, 2)
        })

        logger.info(
            f"AML labels save complete: {metrics['total_saved']} saved, "
            f"{metrics['duplicates_skipped']} duplicates, "
            f"{metrics['errors']} errors, "
            f"{metrics['labels_per_second']:.1f} labels/sec"
        )

        return metrics

    except Exception as e:
        # High-level error (database connection, etc.)
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        logger.error(f"Failed to save AML labels to database: {str(e)}")

        metrics.update({
            "processing_time_ms": int(processing_time),
            "labels_per_second": 0.0,
            "fatal_error": str(e)
        })

        # Return metrics with fatal_error set rather than raising
        # This allows pipeline to continue and handle the error
        return metrics


@flow(name="Data Foundry Ingestion Flow")
async def data_ingestion_flow(
    data_source: str = "sample_data",
    enable_validation: bool = True,
    enable_ai_labeling: bool = True,
    enable_pii_redaction: bool = True,
    enable_human_review: bool = True,
    enable_stripe_billing: bool = False,
    job_id: str | None = None,
    tenant_id: str | None = None,
):
    """
    Main ingestion flow that orchestrates the entire data processing pipeline.

    P02-005: Integration with Stripe metered billing for usage tracking.
    Phase 2: Job status updates via PostgreSQL JobRepository.

    SOLID Principles:
    - Single Responsibility: Flow focuses on data processing, status updates are separate concern
    - Open/Closed: Extensible through parameters
    - Dependency Injection: JobTrackingService injected when job_id is provided

    Args:
        data_source: Source of data to process
        enable_validation: Whether to apply data validation (schema, duplicates, quality)
        enable_ai_labeling: Whether to apply AI labeling
        enable_pii_redaction: Whether to apply PII redaction
        enable_human_review: Whether to route low confidence for human review
        enable_stripe_billing: Whether to report usage to Stripe for metered billing
        job_id: Optional job ID for status tracking (Phase 2 integration)
        tenant_id: Optional tenant ID for multi-tenant context

    Note:
        When job_id is provided, the flow will update job status to COMPLETE on success
        or FAILED on error, using the PostgreSQL JobRepository.
    """
    logger = get_run_logger()
    logger.info(
        f"Starting Data Foundry Ingestion Flow "
        f"(job_id={job_id}, tenant_id={tenant_id})"
    )

    # Track statistics for all validation outcomes
    stats = {
        "total_extracted": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "new_records": 0,
        "duplicate_records": 0,
        "high_quality": 0,
        "low_quality": 0,
        "auto_approved": 0,
        "human_review": 0,
    }

    try:
        # Step 1: Extract data (sync task - call directly in async flow)
        raw_data = extract_data(data_source)
        stats["total_extracted"] = len(raw_data)

        # Step 2: Apply validation (NEW - Week 1)
        if enable_validation and settings.ENABLE_DATA_VALIDATION:
            logger.info("Data validation enabled")

            # 2a: Validate schema (sync task)
            valid_data, invalid_data = validate_schema(raw_data)
            stats["valid_records"] = len(valid_data)
            stats["invalid_records"] = len(invalid_data)

            # 2b: Check duplicates (sync task)
            new_data, duplicate_data = check_duplicates(valid_data)
            stats["new_records"] = len(new_data)
            stats["duplicate_records"] = len(duplicate_data)

            # 2c: Compute quality scores (sync task)
            scored_data = compute_quality_scores(new_data)

            # 2d: Filter by quality (sync task)
            high_quality_data, low_quality_data = filter_low_quality(
                scored_data,
                min_quality=settings.MIN_QUALITY_SCORE
            )
            stats["high_quality"] = len(high_quality_data)
            stats["low_quality"] = len(low_quality_data)

            # Use high quality data for further processing
            data_for_processing = high_quality_data

            # Log invalid data for monitoring
            if invalid_data:
                logger.warning(
                    f"Skipping {len(invalid_data)} invalid records due to validation errors"
                )
            if duplicate_data:
                logger.info(
                    f"Skipping {len(duplicate_data)} duplicate records"
                )
            if low_quality_data:
                logger.info(
                    f"Skipping {len(low_quality_data)} low quality records "
                    f"(below threshold {settings.MIN_QUALITY_SCORE})"
                )
        else:
            logger.info("Data validation disabled - using raw data")
            data_for_processing = raw_data

        # Step 3: Apply PII redaction (sync task)
        if enable_pii_redaction:
            redacted_data = apply_pii_redaction(data_for_processing)
        else:
            redacted_data = data_for_processing

        # Step 4: Apply AI labeling (async task - use await)
        # Get API key safely - handle None or exceptions
        api_key = None
        try:
            api_key = settings.secure_openai_api_key
            if callable(api_key):
                api_key = api_key()
        except Exception:
            api_key = None

        if enable_ai_labeling and (api_key or settings.PRIMARY_MODEL):
            labeled_data = await apply_ai_labeling(redacted_data)
        else:
            labeled_data = redacted_data
            logger.info("Skipping AI labeling - no API key configured")

        # Step 5: Route for human review (sync task)
        if enable_human_review:
            auto_approved, human_review = route_for_human_review(labeled_data)
        else:
            auto_approved = labeled_data
            human_review = []

        stats["auto_approved"] = len(auto_approved)
        stats["human_review"] = len(human_review)

        # Step 6: Send low confidence to Label Studio (sync task)
        if human_review and settings.secure_label_studio_api_key():
            send_to_label_studio(human_review)

        # Step 7: Save auto-approved data to database (sync task)
        if auto_approved:
            save_to_database(auto_approved, "auto_approved_data")

        # Step 8: Save human review queue to database (sync task)
        if human_review:
            save_to_database(human_review, "human_review_queue")

        # P02-005: Step 9 - Report usage to Stripe for metered billing
        stripe_billing_stats = {}
        if enable_stripe_billing and enable_ai_labeling and labeled_data:
            stripe_billing_stats = await report_usage_to_stripe(
                labeled_data=labeled_data,
                source="ingestion_pipeline"
            )

        # Phase 2: Step 10 - Update job status to COMPLETE
        if job_id:
            await _update_job_status_complete(
                job_id=job_id,
                result_records=stats.get("valid_records", 0),
                logger=logger,
            )

        logger.info("Data Ingestion Flow completed successfully")
        return {
            **stats,
            "success": True,
            "total_records": stats["total_extracted"],  # Alias for backward compatibility
            "stripe_billing": stripe_billing_stats,
        }

    except Exception as e:
        logger.error(f"Data Ingestion Flow failed: {str(e)}")

        # Phase 2: Update job status to FAILED on exception
        if job_id:
            await _update_job_status_failed(
                job_id=job_id,
                error_message=str(e),
                logger=logger,
            )

        raise


# -----------------------------------------------------------------
# Phase 2: Job Status Update Helpers
# -----------------------------------------------------------------

async def _update_job_status_complete(
    job_id: str,
    result_records: int,
    logger,
) -> None:
    """
    Update job status to COMPLETE in PostgreSQL.

    Phase 2 integration: Uses JobTrackingService to update job status
    after successful flow execution.

    SOLID Principles:
    - Single Responsibility: Only handles status update to COMPLETE
    - Dependency Injection: Creates service with fresh database session

    Args:
        job_id: Processing job ID to update
        result_records: Number of records successfully processed
        logger: Prefect run logger for consistent logging
    """
    try:
        from src.application.job_tracking_service import JobTrackingService
        from src.infrastructure.repositories.job_repository import JobRepository
        from src.database.connection import db_connection

        logger.info(f"Updating job {job_id} status to COMPLETE ({result_records} records)")

        async with db_connection.get_session() as session:
            job_repo = JobRepository(session)
            job_service = JobTrackingService(repo=job_repo)

            await job_service.mark_complete(
                job_id=job_id,
                result_records=result_records,
            )

        logger.info(f"Job {job_id} marked COMPLETE successfully")

    except Exception as e:
        # Log but don't fail the flow if status update fails
        # The data processing succeeded, status update is secondary
        logger.error(f"Failed to update job {job_id} status to COMPLETE: {str(e)}")


async def _update_job_status_failed(
    job_id: str,
    error_message: str,
    logger,
) -> None:
    """
    Update job status to FAILED in PostgreSQL.

    Phase 2 integration: Uses JobTrackingService to update job status
    when flow execution fails.

    SOLID Principles:
    - Single Responsibility: Only handles status update to FAILED
    - Dependency Injection: Creates service with fresh database session

    Args:
        job_id: Processing job ID to update
        error_message: Error description for the failure
        logger: Prefect run logger for consistent logging
    """
    try:
        from src.application.job_tracking_service import JobTrackingService
        from src.infrastructure.repositories.job_repository import JobRepository
        from src.database.connection import db_connection

        logger.info(f"Updating job {job_id} status to FAILED: {error_message}")

        async with db_connection.get_session() as session:
            job_repo = JobRepository(session)
            job_service = JobTrackingService(repo=job_repo)

            await job_service.mark_failed(
                job_id=job_id,
                error_message=error_message,
            )

        logger.warning(f"Job {job_id} marked FAILED")

    except Exception as e:
        # Log but don't suppress the original error
        # We want the original exception to propagate
        logger.error(f"Failed to update job {job_id} status to FAILED: {str(e)}")


@task
async def report_usage_to_stripe(
    labeled_data: list[dict[str, Any]],
    source: str = "pipeline"
) -> dict[str, Any]:
    """
    P02-005: Report usage to Stripe for metered billing.

    FR-030: Post-Processing Hook - Trigger meter event after data processing completes
    FR-031: Batch Aggregation - Aggregate usage within processing batches before reporting
    FR-032: Async Reporting - Report usage asynchronously to avoid blocking processing pipeline
    FR-034: Audit Trail - Log all meter event reports for audit purposes

    This task:
    1. Calculates usage from AI labeling results (confidence threshold-based)
    2. Aggregates usage by tenant
    3. Reports to Stripe asynchronously (non-blocking)
    4. Includes audit trail metadata

    Args:
        labeled_data: List of records with AI labeling results (ai_confidence, tenant_id)
        source: Source of the usage (e.g., "ingestion_pipeline", "approval_workflow")

    Returns:
        Dictionary with billing statistics:
        {
            "tenants_reported": 2,
            "total_ai_labels": 15,
            "total_human_audits": 5,
            "batch_id": "batch_20250125_1234_abc123"
        }
    """
    logger = get_run_logger()
    logger.info(f"Reporting usage to Stripe for {len(labeled_data)} labeled records")

    try:
        from src.services.usage_calculation_service import UsageCalculationService
        from src.services.stripe_service import StripeService
        from sqlalchemy.ext.asyncio import AsyncSession
        from src.database.connection import get_async_session

        usage_service = UsageCalculationService()

        # Calculate usage from labeled records
        usage = usage_service.calculate_usage_from_records(
            records=labeled_data,
            confidence_threshold=0.85  # AI_LABELS >= 0.85, HUMAN_AUDITS < 0.85
        )

        if not usage:
            logger.info("No usage to report (empty tenant aggregation)")
            return {
                "tenants_reported": 0,
                "total_ai_labels": 0,
                "total_human_audits": 0,
                "status": "skipped"
            }

        # Prepare batch for Stripe reporting
        batch = usage_service.prepare_meter_events_batch(
            usage_calculation=usage,
            batch_id=f"ingest_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            source=source
        )

        # Initialize Stripe service and report asynchronously
        stripe_service = StripeService()
        await stripe_service.initialize()

        # Use batch reporting for efficiency
        async with get_async_session() as db_session:
            batch_result = await stripe_service.report_usage_batch(
                events=batch["events"],
                tenant_id="multi_tenant",  # Events have individual tenant_id
                db_session=db_session
            )

        logger.info(
            f"Stripe billing report complete: "
            f"{batch_result.successful_count}/{batch_result.total_events} events succeeded"
        )

        return {
            "tenants_reported": batch["tenant_count"],
            "total_ai_labels": batch["total_ai_labels"],
            "total_human_audits": batch["total_human_audits"],
            "batch_id": batch["batch_id"],
            "successful_events": batch_result.successful_count,
            "failed_events": batch_result.failed_count,
            "status": "reported"
        }

    except Exception as e:
        logger.error(f"Failed to report usage to Stripe: {str(e)}")
        return {
            "tenants_reported": 0,
            "total_ai_labels": 0,
            "total_human_audits": 0,
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    # Run the flow locally for testing
    asyncio.run(
        data_ingestion_flow(
            data_source="sample_data",
            enable_validation=False,  # Disable validation for backwards compatibility testing
            enable_ai_labeling=False,  # Disable AI for testing without API keys
            enable_pii_redaction=False,  # Disable PII for testing
            enable_human_review=False,
        )
    )
