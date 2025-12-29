"""
Processing Job Value Objects

Immutable value objects for job-related concepts.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class JobCost(BaseModel):
    """
    Value Object: Cost information for a processing job.

    Tracks both estimated and actual costs, with breakdown by type.
    """
    estimated_total: Decimal = Field(..., ge=0)
    actual_total: Optional[Decimal] = Field(default=None, ge=0)

    # Cost breakdown
    ai_processing_cost: Optional[Decimal] = Field(default=None, ge=0)
    storage_cost: Optional[Decimal] = Field(default=None, ge=0)
    human_review_cost: Optional[Decimal] = Field(default=None, ge=0)

    currency: str = "USD"

    model_config = {"frozen": True}  # Immutable

    @classmethod
    def estimate(
        cls,
        tier: str,
        size_bytes: int,
    ) -> "JobCost":
        """
        Factory method to create cost estimate based on tier and size.

        Cost formula: base_cost_per_mb * size_mb
        """
        tier_costs = {
            "simple": Decimal("0.0058"),
            "moderate": Decimal("0.012"),
            "complex": Decimal("0.025"),
        }

        base_cost = tier_costs.get(tier.lower(), Decimal("0.012"))
        size_mb = Decimal(size_bytes) / Decimal(1024 * 1024)
        estimated = base_cost * size_mb

        return cls(estimated_total=estimated.quantize(Decimal("0.000001")))

    @property
    def cost_variance(self) -> Optional[Decimal]:
        """Calculate variance between estimated and actual cost."""
        if self.actual_total is None:
            return None
        return self.actual_total - self.estimated_total

    @property
    def cost_variance_percent(self) -> Optional[float]:
        """Calculate percentage variance."""
        if self.actual_total is None or self.estimated_total == 0:
            return None
        variance = self.cost_variance
        return float(variance / self.estimated_total * 100)


class JobMetrics(BaseModel):
    """
    Value Object: Metrics about job execution.

    Captures timing, record counts, and processing statistics.
    """
    total_records: int = Field(default=0, ge=0)
    processed_records: int = Field(default=0, ge=0)
    failed_records: int = Field(default=0, ge=0)

    # Timing
    queue_time_seconds: Optional[float] = Field(default=None, ge=0)
    processing_time_seconds: Optional[float] = Field(default=None, ge=0)
    total_time_seconds: Optional[float] = Field(default=None, ge=0)

    # Quality metrics
    average_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    human_review_count: int = Field(default=0, ge=0)

    model_config = {"frozen": True}  # Immutable

    @property
    def success_rate(self) -> Optional[float]:
        """Calculate processing success rate."""
        if self.total_records == 0:
            return None
        return self.processed_records / self.total_records

    @property
    def failure_rate(self) -> Optional[float]:
        """Calculate processing failure rate."""
        if self.total_records == 0:
            return None
        return self.failed_records / self.total_records


class JobProgress(BaseModel):
    """
    Value Object: Current progress of a job.

    Used for progress reporting and UI updates.
    """
    current_step: str
    total_steps: int = Field(ge=1)
    current_step_number: int = Field(ge=0)
    percent_complete: float = Field(ge=0, le=100)
    current_record: int = Field(default=0, ge=0)
    total_records: int = Field(default=0, ge=0)
    estimated_seconds_remaining: Optional[int] = Field(default=None, ge=0)

    model_config = {"frozen": True}  # Immutable

    @property
    def is_complete(self) -> bool:
        """Check if job is complete."""
        return self.percent_complete >= 100
