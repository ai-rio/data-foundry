"""
UsageCalculationService - P02-005: Integration with ingestion pipeline

This service provides:
- Usage calculation from AI labeling results (confidence threshold-based)
- Tenant isolation enforcement (no cross-tenant data leakage)
- Input validation for confidence scores
- Batch aggregation for efficient Stripe meter event reporting
- Edge case handling (null values, missing confidence, out-of-range values)

Security Features:
- Tenant isolation enforcement
- Input validation for confidence scores
- Conservative error handling (treats ambiguous cases as human audits)

Meter Types (from StripeService):
- METER_AI_LABELS: AI-powered data labeling usage
- METER_HUMAN_AUDITS: Human review workflow usage
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


# ============================================================================
# Exception Classes
# ============================================================================

class UsageCalculationError(Exception):
    """Base exception for usage calculation errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class UsageValidationError(UsageCalculationError):
    """Raised when input validation fails."""

    def __init__(self, message: str, validation_errors: Optional[List[str]] = None):
        self.validation_errors = validation_errors or []
        super().__init__(message)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class UsageAggregation:
    """
    Usage aggregation for a single tenant.

    Attributes:
        tenant_id: Tenant identifier
        ai_labels_count: Count of AI labels (confidence >= threshold)
        human_audits_count: Count of human audits (confidence < threshold)
        meter_events: List of meter event dictionaries for Stripe reporting
    """
    tenant_id: str
    ai_labels_count: int
    human_audits_count: int
    meter_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BatchPreparation:
    """
    Prepared batch of meter events for Stripe reporting.

    Attributes:
        batch_id: Unique batch identifier
        events: List of meter event dictionaries
        total_ai_labels: Total AI labels across all tenants
        total_human_audits: Total human audits across all tenants
        tenant_count: Number of tenants in batch
        prepared_at: ISO timestamp of preparation
    """
    batch_id: str
    events: List[Dict[str, Any]]
    total_ai_labels: int
    total_human_audits: int
    tenant_count: int
    prepared_at: str


# ============================================================================
# UsageCalculationService
# ============================================================================

class UsageCalculationService:
    """
    Service for calculating usage from AI labeling results.

    Calculates AI_LABELS and HUMAN_AUDITS based on confidence threshold:
    - AI_LABELS: Count of records where confidence >= threshold
    - HUMAN_AUDITS: Count of records where confidence < threshold

    Threshold Configuration (from requirements):
    - Default: 0.85 (85%)
    - Configurable per deployment

    Security Features:
    - Tenant isolation: Each tenant's usage calculated separately
    - Input validation: Validates confidence scores and tenant IDs
    - Conservative approach: Treats ambiguous cases as human audits
    """

    # Default confidence threshold (from requirements)
    DEFAULT_CONFIDENCE_THRESHOLD = 0.85

    # Meter event names (must match StripeService)
    METER_AI_LABELS = "ai_labels"
    METER_HUMAN_AUDITS = "human_audits"

    def __init__(self):
        """Initialize UsageCalculationService."""
        self._calculation_count = 0
        self._tenant_isolation_violations = 0

    def calculate_usage_from_records(
        self,
        records: List[Dict[str, Any]],
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    ) -> Dict[str, Dict[str, int]]:
        """
        Calculate usage from a list of processed records.

        Calculates AI_LABELS and HUMAN_AUDITS based on confidence threshold:
        - AI_LABELS: Count of records where confidence >= threshold
        - HUMAN_AUDITS: Count of records where confidence < threshold

        Args:
            records: List of processed records with ai_confidence and tenant_id
            confidence_threshold: Confidence threshold for classification (0.0-1.0)

        Returns:
            Dictionary mapping tenant_id to usage counts:
            {
                "tenant_001": {"ai_labels": 10, "human_audits": 5},
                "tenant_002": {"ai_labels": 8, "human_audits": 3}
            }

        Raises:
            UsageValidationError: If input validation fails

        Example:
            >>> service = UsageCalculationService()
            >>> usage = service.calculate_usage_from_records(records, threshold=0.85)
            >>> print(usage["tenant_001"])
            {'ai_labels': 10, 'human_audits': 5}
        """
        # Validate inputs
        self._validate_inputs(records, confidence_threshold)

        # Initialize tenant aggregations
        tenant_usage: Dict[str, Dict[str, int]] = {}

        # Process each record
        for record in records:
            try:
                # Extract tenant_id (required)
                tenant_id = record.get("tenant_id")
                if not tenant_id:
                    raise UsageValidationError(
                        "Missing required field: tenant_id"
                    )

                # Initialize tenant if not exists
                if tenant_id not in tenant_usage:
                    tenant_usage[tenant_id] = {
                        "ai_labels": 0,
                        "human_audits": 0
                    }

                # Extract and validate confidence score
                confidence = record.get("ai_confidence")

                # Classify based on confidence
                classification = self._classify_confidence(
                    confidence, confidence_threshold
                )

                # Increment appropriate counter
                if classification == "ai_label":
                    tenant_usage[tenant_id]["ai_labels"] += 1
                else:
                    tenant_usage[tenant_id]["human_audits"] += 1

            except UsageValidationError:
                # Re-raise validation errors
                raise
            except Exception as e:
                logger.warning(f"Error processing record: {e}. Skipping.")
                continue

        # Track calculation
        self._calculation_count += 1

        logger.info(
            f"Usage calculation complete: {len(tenant_usage)} tenants, "
            f"{sum(t['ai_labels'] + t['human_audits'] for t in tenant_usage.values())} total records"
        )

        return tenant_usage

    def calculate_usage_for_batch_reporting(
        self,
        records: List[Dict[str, Any]],
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    ) -> Dict[str, Any]:
        """
        Calculate usage and prepare aggregation for batch reporting.

        Extends calculate_usage_from_records to include meter event preparation
        for efficient Stripe API batch reporting.

        Args:
            records: List of processed records with ai_confidence and tenant_id
            confidence_threshold: Confidence threshold for classification (0.0-1.0)

        Returns:
            Dictionary with:
            {
                "aggregations": [
                    {
                        "tenant_id": "tenant_001",
                        "ai_labels_count": 10,
                        "human_audits_count": 5,
                        "meter_events": [...]
                    }
                ],
                "total_tenants": 2,
                "total_records": 15
            }

        Example:
            >>> service = UsageCalculationService()
            >>> batch = service.calculate_usage_for_batch_reporting(records)
            >>> print(batch["aggregations"][0]["meter_events"])
        """
        # Calculate base usage
        usage_by_tenant = self.calculate_usage_from_records(
            records=records,
            confidence_threshold=confidence_threshold
        )

        # Prepare aggregations with meter events
        aggregations = []
        total_records = 0

        for tenant_id, usage in usage_by_tenant.items():
            # Create meter events for this tenant
            meter_events = self._create_meter_events_for_tenant(
                tenant_id=tenant_id,
                ai_labels=usage["ai_labels"],
                human_audits=usage["human_audits"]
            )

            aggregation = UsageAggregation(
                tenant_id=tenant_id,
                ai_labels_count=usage["ai_labels"],
                human_audits_count=usage["human_audits"],
                meter_events=meter_events
            )

            aggregations.append({
                "tenant_id": aggregation.tenant_id,
                "ai_labels_count": aggregation.ai_labels_count,
                "human_audits_count": aggregation.human_audits_count,
                "meter_events": aggregation.meter_events
            })

            total_records += usage["ai_labels"] + usage["human_audits"]

        return {
            "aggregations": aggregations,
            "total_tenants": len(aggregations),
            "total_records": total_records
        }

    def prepare_meter_events_batch(
        self,
        usage_calculation: Dict[str, Dict[str, int]],
        batch_id: str,
        source: str = "pipeline",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Prepare meter events batch for Stripe reporting.

        Converts usage calculation results into properly formatted meter events
        for StripeService.report_usage_batch().

        Args:
            usage_calculation: Result from calculate_usage_from_records()
            batch_id: Unique batch identifier
            source: Source of the usage (e.g., "ingestion_pipeline", "approval_workflow")
            metadata: Optional additional metadata

        Returns:
            Dictionary with:
            {
                "batch_id": "batch_001",
                "events": [
                    {"meter_event": "ai_labels", "value": 10, "tenant_id": "tenant_001", ...},
                    {"meter_event": "human_audits", "value": 5, "tenant_id": "tenant_001", ...}
                ],
                "total_ai_labels": 10,
                "total_human_audits": 5,
                "tenant_count": 2,
                "prepared_at": "2024-12-25T10:30:00Z"
            }

        Example:
            >>> service = UsageCalculationService()
            >>> usage = service.calculate_usage_from_records(records)
            >>> batch = service.prepare_meter_events_batch(usage, "batch_001")
        """
        events = []
        total_ai_labels = 0
        total_human_audits = 0

        for tenant_id, usage in usage_calculation.items():
            ai_labels = usage["ai_labels"]
            human_audits = usage["human_audits"]

            # Skip zero-value events (Stripe doesn't need them)
            if ai_labels > 0:
                events.append({
                    "meter_event": self.METER_AI_LABELS,
                    "value": ai_labels,
                    "tenant_id": tenant_id,
                    "metadata": {
                        "source": source,
                        "batch_id": batch_id,
                        "calculated_at": datetime.now(timezone.utc).isoformat(),
                        **(metadata or {})
                    }
                })
                total_ai_labels += ai_labels

            if human_audits > 0:
                events.append({
                    "meter_event": self.METER_HUMAN_AUDITS,
                    "value": human_audits,
                    "tenant_id": tenant_id,
                    "metadata": {
                        "source": source,
                        "batch_id": batch_id,
                        "calculated_at": datetime.now(timezone.utc).isoformat(),
                        **(metadata or {})
                    }
                })
                total_human_audits += human_audits

        return {
            "batch_id": batch_id,
            "events": events,
            "total_ai_labels": total_ai_labels,
            "total_human_audits": total_human_audits,
            "tenant_count": len(usage_calculation),
            "prepared_at": datetime.now(timezone.utc).isoformat()
        }

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _validate_inputs(
        self,
        records: List[Dict[str, Any]],
        confidence_threshold: float
    ) -> None:
        """
        Validate input parameters for usage calculation.

        Args:
            records: List of records to validate
            confidence_threshold: Confidence threshold to validate

        Raises:
            UsageValidationError: If validation fails
        """
        errors = []

        # Validate records is a list
        if not isinstance(records, list):
            errors.append(f"records must be a list, got {type(records).__name__}")

        # Validate confidence threshold
        if not isinstance(confidence_threshold, (int, float)):
            errors.append(
                f"confidence_threshold must be numeric, got {type(confidence_threshold).__name__}"
            )
        elif confidence_threshold < 0.0 or confidence_threshold > 1.0:
            errors.append(
                f"confidence_threshold must be between 0.0 and 1.0, got {confidence_threshold}"
            )

        if errors:
            raise UsageValidationError(
                f"Input validation failed: {'; '.join(errors)}",
                validation_errors=errors
            )

    def _classify_confidence(
        self,
        confidence: Any,
        threshold: float
    ) -> str:
        """
        Classify a confidence score as AI_LABEL or HUMAN_AUDIT.

        Args:
            confidence: Confidence score (can be None, int, float)
            threshold: Classification threshold

        Returns:
            "ai_label" if confidence >= threshold, "human_audit" otherwise
        """
        # Handle missing or None confidence
        if confidence is None:
            logger.debug("Missing confidence score, treating as human audit")
            return "human_audit"

        # Validate type
        if not isinstance(confidence, (int, float)):
            logger.warning(
                f"Invalid confidence type {type(confidence).__name__}, "
                "treating as human audit"
            )
            return "human_audit"

        # Validate range
        if confidence < 0.0 or confidence > 1.0:
            logger.warning(
                f"Confidence {confidence} out of range [0, 1], "
                "treating as human audit"
            )
            return "human_audit"

        # Classify based on threshold
        if confidence >= threshold:
            return "ai_label"
        else:
            return "human_audit"

    def _create_meter_events_for_tenant(
        self,
        tenant_id: str,
        ai_labels: int,
        human_audits: int
    ) -> List[Dict[str, Any]]:
        """
        Create meter events for a single tenant.

        Args:
            tenant_id: Tenant identifier
            ai_labels: Count of AI labels
            human_audits: Count of human audits

        Returns:
            List of meter event dictionaries (non-zero values only)
        """
        events = []

        if ai_labels > 0:
            events.append({
                "meter_event": self.METER_AI_LABELS,
                "value": ai_labels,
                "tenant_id": tenant_id
            })

        if human_audits > 0:
            events.append({
                "meter_event": self.METER_HUMAN_AUDITS,
                "value": human_audits,
                "tenant_id": tenant_id
            })

        return events

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get service metrics.

        Returns:
            Dictionary with service metrics
        """
        return {
            "calculation_count": self._calculation_count,
            "tenant_isolation_violations": self._tenant_isolation_violations
        }
