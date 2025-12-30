"""
AML Label Validator - Data validation layer for AML transaction labels

This module implements the Single Responsibility Principle by separating
data validation logic from persistence logic.

SOLID Principles Applied:
- S (Single Responsibility): Only validates AML label data, doesn't handle persistence
- O (Open/Closed): Extensible through subclassing, closed for modification
- L (Liskov Substitution): Follows standard validator interface
- I (Interface Segregation): Focused interface with clear validation methods
- D (Dependency Inversion): Depends on abstractions (validation rules), not concrete implementations

Reference: P01-023 - Proper data validation before database insertion
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from decimal import Decimal, InvalidOperation
from datetime import datetime

from src.models.aml_enums import AMLRiskLevel, AMLExpertReviewStatus


@dataclass
class ValidationError:
    """
    Represents a single validation error.

    Attributes:
        field: The field that failed validation
        message: Human-readable error message
        error_code: Machine-readable error code for programmatic handling
        severity: Error severity (ERROR, WARNING)
    """
    field: str
    message: str
    error_code: str
    severity: str = "ERROR"


@dataclass
class ValidationResult:
    """
    Result of AML label validation.

    Attributes:
        is_valid: Whether all validations passed
        errors: List of validation errors
        warnings: List of validation warnings
        validated_data: Cleaned and normalized data (if valid)
    """
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    validated_data: Optional[Dict[str, Any]] = None


class AMLLabelValidator:
    """
    Validates AML transaction label data before database insertion.

    This validator ensures:
    - Required fields are present
    - Data types are correct
    - Values are within acceptable ranges
    - Enums are valid
    - Business rules are satisfied

    Example:
        >>> validator = AMLLabelValidator()
        >>> result = validator.validate(label_data)
        >>> if result.is_valid:
        ...     # Safe to insert into database
        ...     save_to_db(result.validated_data)
        >>> else:
        ...     # Handle validation errors
        ...     for error in result.errors:
        ...         logger.error(f"{error.field}: {error.message}")
    """

    # Required fields for AML labels
    REQUIRED_FIELDS = {
        "transaction_id": str,
        "tenant_id": str,
        "job_id": str,
        "risk_level": str,
        "typology": str,
        "confidence_score": (float, Decimal, int),
        "ai_reasoning": str,
    }

    # Optional fields with expected types
    OPTIONAL_FIELDS = {
        "expert_review_status": str,
        "regulatory_flags": (list, dict),
        "version_id": str,
        "is_audit_ready": bool,
        "is_deleted": bool,
    }

    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """
        Validate AML label data.

        Args:
            data: Dictionary containing AML label fields

        Returns:
            ValidationResult with validation status and cleaned data
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []
        validated_data: Dict[str, Any] = {}

        # Validate required fields
        errors.extend(self._validate_required_fields(data))

        # If required fields are missing, return early
        if errors:
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                validated_data=None
            )

        # Validate and normalize each field
        transaction_id_result = self._validate_transaction_id(data.get("transaction_id"))
        if transaction_id_result.errors:
            errors.extend(transaction_id_result.errors)
        else:
            validated_data["transaction_id"] = transaction_id_result.validated_data

        tenant_id_result = self._validate_tenant_id(data.get("tenant_id"))
        if tenant_id_result.errors:
            errors.extend(tenant_id_result.errors)
        else:
            validated_data["tenant_id"] = tenant_id_result.validated_data

        job_id_result = self._validate_job_id(data.get("job_id"))
        if job_id_result.errors:
            errors.extend(job_id_result.errors)
        else:
            validated_data["job_id"] = job_id_result.validated_data

        risk_level_result = self._validate_risk_level(data.get("risk_level"))
        if risk_level_result.errors:
            errors.extend(risk_level_result.errors)
        else:
            validated_data["risk_level"] = risk_level_result.validated_data

        typology_result = self._validate_typology(data.get("typology"))
        if typology_result.errors:
            errors.extend(typology_result.errors)
        else:
            validated_data["typology"] = typology_result.validated_data

        confidence_result = self._validate_confidence_score(data.get("confidence_score"))
        if confidence_result.errors:
            errors.extend(confidence_result.errors)
        else:
            validated_data["confidence_score"] = confidence_result.validated_data

        reasoning_result = self._validate_reasoning(data.get("ai_reasoning"))
        if reasoning_result.errors:
            errors.extend(reasoning_result.errors)
        else:
            validated_data["ai_reasoning"] = reasoning_result.validated_data

        # Validate optional fields
        review_status_result = self._validate_review_status(
            data.get("expert_review_status", AMLExpertReviewStatus.PENDING.value)
        )
        if review_status_result.errors:
            errors.extend(review_status_result.errors)
        else:
            validated_data["expert_review_status"] = review_status_result.validated_data

        regulatory_flags_result = self._validate_regulatory_flags(
            data.get("regulatory_flags", [])
        )
        if regulatory_flags_result.errors:
            errors.extend(regulatory_flags_result.errors)
        elif regulatory_flags_result.warnings:
            warnings.extend(regulatory_flags_result.warnings)
        validated_data["regulatory_flags"] = regulatory_flags_result.validated_data

        # Add metadata fields with defaults
        validated_data["version_id"] = data.get("version_id")
        validated_data["is_audit_ready"] = data.get("is_audit_ready", False)
        validated_data["is_deleted"] = data.get("is_deleted", False)
        validated_data["created_at"] = datetime.utcnow()
        validated_data["updated_at"] = datetime.utcnow()

        # Determine final validation result
        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            validated_data=validated_data if is_valid else None
        )

    def _validate_required_fields(self, data: Dict[str, Any]) -> List[ValidationError]:
        """Check that all required fields are present."""
        errors = []

        for field, expected_type in self.REQUIRED_FIELDS.items():
            if field not in data or data[field] is None:
                errors.append(ValidationError(
                    field=field,
                    message=f"Required field '{field}' is missing",
                    error_code="MISSING_REQUIRED_FIELD",
                    severity="ERROR"
                ))
            elif not isinstance(data[field], expected_type):
                errors.append(ValidationError(
                    field=field,
                    message=f"Field '{field}' must be of type {expected_type}",
                    error_code="INVALID_FIELD_TYPE",
                    severity="ERROR"
                ))

        return errors

    def _validate_transaction_id(self, value: Any) -> ValidationResult:
        """Validate transaction_id field."""
        errors = []

        if not value or not str(value).strip():
            errors.append(ValidationError(
                field="transaction_id",
                message="Transaction ID cannot be empty",
                error_code="EMPTY_TRANSACTION_ID"
            ))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            validated_data=str(value).strip() if value else None
        )

    def _validate_tenant_id(self, value: Any) -> ValidationResult:
        """Validate tenant_id field."""
        errors = []

        if not value or not str(value).strip():
            errors.append(ValidationError(
                field="tenant_id",
                message="Tenant ID cannot be empty",
                error_code="EMPTY_TENANT_ID"
            ))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            validated_data=str(value).strip() if value else None
        )

    def _validate_job_id(self, value: Any) -> ValidationResult:
        """Validate job_id field."""
        errors = []

        if not value or not str(value).strip():
            errors.append(ValidationError(
                field="job_id",
                message="Job ID cannot be empty",
                error_code="EMPTY_JOB_ID"
            ))

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[],
            validated_data=str(value).strip() if value else None
        )

    def _validate_risk_level(self, value: Any) -> ValidationResult:
        """Validate risk_level is a valid AML risk level."""
        errors = []

        try:
            # Try to convert to AMLRiskLevel enum
            risk_level = AMLRiskLevel(value)
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                validated_data=risk_level
            )
        except (ValueError, KeyError):
            valid_levels = [level.value for level in AMLRiskLevel]
            errors.append(ValidationError(
                field="risk_level",
                message=f"Invalid risk_level '{value}'. Must be one of: {', '.join(valid_levels)}",
                error_code="INVALID_RISK_LEVEL"
            ))
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=[],
                validated_data=None
            )

    def _validate_typology(self, value: Any) -> ValidationResult:
        """Validate typology field."""
        errors = []
        warnings = []

        if not value or not str(value).strip():
            errors.append(ValidationError(
                field="typology",
                message="Typology cannot be empty",
                error_code="EMPTY_TYPOLOGY"
            ))
            return ValidationResult(is_valid=False, errors=errors, warnings=[], validated_data=None)

        typology = str(value).strip().upper()

        # Define valid FATF typologies
        VALID_TYPOLOGIES = {
            "ML", "TF", "PEP", "FRAUD", "SANCTIONS", "TAX_EVASION",
            "BRIBERY", "SMUGGLING", "DRUG_TRAFFICKING", "HUMAN_TRAFFICKING",
            "PROLIFERATION", "CYBERCRIME", "ENVIRONMENTAL"
        }

        if typology not in VALID_TYPOLOGIES:
            warnings.append(ValidationError(
                field="typology",
                message=f"Typology '{typology}' is not a standard FATF typology",
                error_code="NON_STANDARD_TYPOLOGY",
                severity="WARNING"
            ))

        return ValidationResult(
            is_valid=True,
            errors=[],
            warnings=warnings,
            validated_data=typology
        )

    def _validate_confidence_score(self, value: Any) -> ValidationResult:
        """Validate confidence_score is between 0 and 1."""
        errors = []

        try:
            # Convert to Decimal for precise validation
            score = Decimal(str(value))

            if score < Decimal("0.0") or score > Decimal("1.0"):
                errors.append(ValidationError(
                    field="confidence_score",
                    message=f"Confidence score {score} must be between 0.0 and 1.0",
                    error_code="CONFIDENCE_OUT_OF_RANGE"
                ))

            return ValidationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=[],
                validated_data=score if len(errors) == 0 else None
            )

        except (ValueError, InvalidOperation, TypeError):
            errors.append(ValidationError(
                field="confidence_score",
                message=f"Invalid confidence_score '{value}'. Must be a number between 0 and 1",
                error_code="INVALID_CONFIDENCE_SCORE"
            ))
            return ValidationResult(is_valid=False, errors=errors, warnings=[], validated_data=None)

    def _validate_reasoning(self, value: Any) -> ValidationResult:
        """Validate ai_reasoning field."""
        errors = []
        warnings = []

        if not value or not str(value).strip():
            errors.append(ValidationError(
                field="ai_reasoning",
                message="AI reasoning cannot be empty",
                error_code="EMPTY_REASONING"
            ))
            return ValidationResult(is_valid=False, errors=errors, warnings=[], validated_data=None)

        reasoning = str(value).strip()

        # Check minimum length for audit trail
        MIN_REASONING_LENGTH = 20
        if len(reasoning) < MIN_REASONING_LENGTH:
            warnings.append(ValidationError(
                field="ai_reasoning",
                message=f"AI reasoning is short ({len(reasoning)} chars). Minimum {MIN_REASONING_LENGTH} recommended for audit trail.",
                error_code="SHORT_REASONING",
                severity="WARNING"
            ))

        return ValidationResult(
            is_valid=True,
            errors=[],
            warnings=warnings,
            validated_data=reasoning
        )

    def _validate_review_status(self, value: Any) -> ValidationResult:
        """Validate expert_review_status is a valid enum value."""
        errors = []

        try:
            # Try to convert to AMLExpertReviewStatus enum
            review_status = AMLExpertReviewStatus(value)
            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                validated_data=review_status
            )
        except (ValueError, KeyError):
            valid_statuses = [status.value for status in AMLExpertReviewStatus]
            errors.append(ValidationError(
                field="expert_review_status",
                message=f"Invalid review status '{value}'. Must be one of: {', '.join(valid_statuses)}",
                error_code="INVALID_REVIEW_STATUS"
            ))
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=[],
                validated_data=None
            )

    def _validate_regulatory_flags(self, value: Any) -> ValidationResult:
        """Validate regulatory_flags field."""
        warnings = []

        # regulatory_flags can be a list or dict, default to empty list
        if value is None:
            return ValidationResult(is_valid=True, errors=[], warnings=[], validated_data=[])

        if isinstance(value, dict):
            return ValidationResult(is_valid=True, errors=[], warnings=[], validated_data=value)

        if isinstance(value, list):
            return ValidationResult(is_valid=True, errors=[], warnings=[], validated_data=value)

        # Try to convert to list
        try:
            flags = list(value)
            return ValidationResult(is_valid=True, errors=[], warnings=[], validated_data=flags)
        except (TypeError, ValueError):
            warnings.append(ValidationError(
                field="regulatory_flags",
                message=f"Regulatory flags '{value}' could not be converted to list/dict, using empty list",
                error_code="INVALID_REGULATORY_FLAGS",
                severity="WARNING"
            ))
            return ValidationResult(is_valid=True, errors=[], warnings=warnings, validated_data=[])
