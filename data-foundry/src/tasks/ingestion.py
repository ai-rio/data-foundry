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


# PII Redaction Support - Track Presidio availability
PRESIDIO_AVAILABLE: bool = False
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    logger.warning(
        "Presidio not installed - PII redaction will be skipped. "
        "Install with: pip install presidio-analyzer presidio-anonymizer"
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

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    redacted_data = []
    for record in data:
        # Analyze and anonymize PII
        text_fields = ["name", "email", "phone"]
        redacted_record = record.copy()

        for field in text_fields:
            if field in record:
                try:
                    # Analyze the text
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
def route_for_human_review(data: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """
    Route records based on confidence scores.
    Low confidence records go to Label Studio.
    """
    logger = get_run_logger()
    logger.info("Routing records for human review")

    auto_approved = []
    human_review = []

    for record in data:
        confidence = record.get("ai_confidence", 1.0)

        if confidence < settings.CONFIDENCE_THRESHOLD:
            human_review.append(record)
            logger.info(
                f"Record {record['id']} routed for human review (confidence: {confidence})"
            )
        else:
            auto_approved.append(record)
            logger.info(
                f"Record {record['id']} auto-approved (confidence: {confidence})"
            )

    logger.info(
        f"Auto-approved: {len(auto_approved)}, Human review: {len(human_review)}"
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


@flow(name="Data Foundry Ingestion Flow")
async def data_ingestion_flow(
    data_source: str = "sample_data",
    enable_validation: bool = True,
    enable_ai_labeling: bool = True,
    enable_pii_redaction: bool = True,
    enable_human_review: bool = True,
):
    """
    Main ingestion flow that orchestrates the entire data processing pipeline.

    Args:
        data_source: Source of data to process
        enable_validation: Whether to apply data validation (schema, duplicates, quality)
        enable_ai_labeling: Whether to apply AI labeling
        enable_pii_redaction: Whether to apply PII redaction
        enable_human_review: Whether to route low confidence for human review
    """
    logger = get_run_logger()
    logger.info("Starting Data Foundry Ingestion Flow")

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

        logger.info("Data Ingestion Flow completed successfully")
        return {
            **stats,
            "success": True,
            "total_records": stats["total_extracted"],  # Alias for backward compatibility
        }

    except Exception as e:
        logger.error(f"Data Ingestion Flow failed: {str(e)}")
        raise


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
