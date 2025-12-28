"""
File Domain Value Objects

Value Objects are immutable domain primitives that describe characteristics
of domain entities. They have no identity and are defined by their attributes.

SOLID Principles:
- Single Responsibility: Each value object represents one concept
- Open/Closed: New file types can be added without modifying existing code
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FileType(str, Enum):
    """
    Enumeration of supported file types.

    Open/Closed Principle: New file types can be added here without
    modifying existing validators or services.
    """
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"
    PDF = "pdf"
    PARQUET = "parquet"

    @classmethod
    def from_extension(cls, extension: str) -> Optional["FileType"]:
        """
        Create FileType from file extension.

        Args:
            extension: File extension without dot (e.g., 'csv')

        Returns:
            FileType if valid, None otherwise
        """
        ext_lower = extension.lower().lstrip(".")
        try:
            return cls(ext_lower)
        except ValueError:
            return None

    @classmethod
    def from_content_type(cls, content_type: str) -> Optional["FileType"]:
        """
        Create FileType from MIME content type.

        Args:
            content_type: MIME type (e.g., 'text/csv')

        Returns:
            FileType if valid, None otherwise
        """
        content_type_map = {
            "text/csv": cls.CSV,
            "application/json": cls.JSON,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": cls.XLSX,
            "application/vnd.ms-excel": cls.XLSX,
            "application/pdf": cls.PDF,
            "application/x-parquet": cls.PARQUET,
            "application/octet-stream": None,  # Unknown type
        }
        return content_type_map.get(content_type.lower())


class ComplexityTier(str, Enum):
    """
    File complexity tiers for processing cost estimation.

    The tier determines:
    - Processing time estimates
    - Resource allocation
    - Cost multipliers
    - Queue priority
    """
    SIMPLE = "simple"       # <5MB, structured, known schema
    MODERATE = "moderate"   # 5-50MB, mixed structured/unstructured
    COMPLEX = "complex"     # >50MB, unstructured, OCR needed

    @property
    def base_cost_multiplier(self) -> float:
        """Get base cost multiplier for this tier."""
        multipliers = {
            ComplexityTier.SIMPLE: 0.0058,
            ComplexityTier.MODERATE: 0.012,
            ComplexityTier.COMPLEX: 0.025,
        }
        return multipliers[self]

    @property
    def estimated_processing_seconds(self) -> int:
        """Get estimated processing time in seconds."""
        estimates = {
            ComplexityTier.SIMPLE: 30,
            ComplexityTier.MODERATE: 120,
            ComplexityTier.COMPLEX: 600,
        }
        return estimates[self]


class FileMetadata(BaseModel):
    """
    Value Object: Immutable file metadata.

    Encapsulates all information about an uploaded file.
    This is a Value Object - it has no identity, only attributes.

    Attributes:
        name: Original filename
        size: File size in bytes
        content_type: MIME type or FileType enum
        uploaded_at: Timestamp of upload
        checksum: Optional SHA-256 hash for integrity
    """
    name: str = Field(..., min_length=1, max_length=255)
    size: int = Field(..., ge=0)
    content_type: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    checksum: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    model_config = {"frozen": True}  # Make immutable

    @field_validator("name")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename doesn't contain dangerous characters."""
        dangerous_chars = ["../", "..\\", "\x00"]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Invalid character in filename: {char!r}")
        return v

    @property
    def extension(self) -> str:
        """Extract file extension from name."""
        if "." in self.name:
            return self.name.rsplit(".", 1)[-1].lower()
        return ""

    @property
    def file_type(self) -> Optional[FileType]:
        """Get FileType enum from extension."""
        return FileType.from_extension(self.extension)

    @property
    def size_mb(self) -> float:
        """Get file size in megabytes."""
        return self.size / (1024 * 1024)

    def __str__(self) -> str:
        return f"FileMetadata(name={self.name}, size={self.size_mb:.2f}MB)"


class ValidationResult(BaseModel):
    """
    Value Object: Result of a validation operation.

    Encapsulates the outcome of any validation, including:
    - Whether validation passed
    - Any error messages
    - Any warning messages
    - Additional data from validation (e.g., detected complexity tier)

    This is immutable and can be composed (multiple results merged).
    """
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    data: Optional[Dict[str, Any]] = Field(default=None)

    model_config = {"frozen": True}  # Make immutable

    @classmethod
    def success(
        cls,
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
    ) -> "ValidationResult":
        """Factory method for successful validation."""
        return cls(valid=True, data=data, warnings=warnings or [])

    @classmethod
    def failure(cls, errors: List[str], warnings: Optional[List[str]] = None) -> "ValidationResult":
        """Factory method for failed validation."""
        return cls(valid=False, errors=errors, warnings=warnings or [])

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """
        Merge two validation results.

        The merged result is:
        - valid only if BOTH are valid
        - contains errors from both
        - contains warnings from both
        - merges data dictionaries
        """
        merged_data = {}
        if self.data:
            merged_data.update(self.data)
        if other.data:
            merged_data.update(other.data)

        return ValidationResult(
            valid=self.valid and other.valid,
            errors=list(self.errors) + list(other.errors),
            warnings=list(self.warnings) + list(other.warnings),
            data=merged_data if merged_data else None,
        )

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.valid
