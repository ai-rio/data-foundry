"""
Tests for File Domain Value Objects

TDD tests covering FileMetadata, FileType, ComplexityTier, ValidationResult.
"""

import pytest
from datetime import datetime

from src.domain.file.value_objects import (
    FileMetadata,
    FileType,
    ComplexityTier,
    ValidationResult,
)


class TestFileType:
    """Tests for FileType enum."""

    def test_from_extension_csv(self):
        """CSV extension should map to CSV type."""
        assert FileType.from_extension("csv") == FileType.CSV
        assert FileType.from_extension("CSV") == FileType.CSV
        assert FileType.from_extension(".csv") == FileType.CSV

    def test_from_extension_json(self):
        """JSON extension should map to JSON type."""
        assert FileType.from_extension("json") == FileType.JSON

    def test_from_extension_xlsx(self):
        """XLSX extension should map to XLSX type."""
        assert FileType.from_extension("xlsx") == FileType.XLSX

    def test_from_extension_pdf(self):
        """PDF extension should map to PDF type."""
        assert FileType.from_extension("pdf") == FileType.PDF

    def test_from_extension_unknown(self):
        """Unknown extension should return None."""
        assert FileType.from_extension("exe") is None
        assert FileType.from_extension("unknown") is None
        assert FileType.from_extension("") is None

    def test_from_content_type_csv(self):
        """CSV content type should map correctly."""
        assert FileType.from_content_type("text/csv") == FileType.CSV

    def test_from_content_type_json(self):
        """JSON content type should map correctly."""
        assert FileType.from_content_type("application/json") == FileType.JSON

    def test_from_content_type_unknown(self):
        """Unknown content type should return None."""
        assert FileType.from_content_type("application/octet-stream") is None


class TestComplexityTier:
    """Tests for ComplexityTier enum."""

    def test_simple_tier_cost_multiplier(self):
        """Simple tier should have lowest cost multiplier."""
        assert ComplexityTier.SIMPLE.base_cost_multiplier == 0.0058

    def test_moderate_tier_cost_multiplier(self):
        """Moderate tier should have medium cost multiplier."""
        assert ComplexityTier.MODERATE.base_cost_multiplier == 0.012

    def test_complex_tier_cost_multiplier(self):
        """Complex tier should have highest cost multiplier."""
        assert ComplexityTier.COMPLEX.base_cost_multiplier == 0.025

    def test_estimated_processing_seconds(self):
        """Each tier should have appropriate processing time estimate."""
        assert ComplexityTier.SIMPLE.estimated_processing_seconds == 30
        assert ComplexityTier.MODERATE.estimated_processing_seconds == 120
        assert ComplexityTier.COMPLEX.estimated_processing_seconds == 600


class TestFileMetadata:
    """Tests for FileMetadata value object."""

    def test_create_valid_metadata(self):
        """Should create metadata with valid inputs."""
        metadata = FileMetadata(
            name="test.csv",
            size=1024,
            content_type="text/csv",
        )

        assert metadata.name == "test.csv"
        assert metadata.size == 1024
        assert metadata.content_type == "text/csv"
        assert metadata.uploaded_at is not None

    def test_extension_property(self):
        """Should extract extension from filename."""
        metadata = FileMetadata(name="data.csv", size=100, content_type="text/csv")
        assert metadata.extension == "csv"

        metadata = FileMetadata(name="report.xlsx", size=100, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert metadata.extension == "xlsx"

    def test_extension_no_extension(self):
        """Should return empty string for files without extension."""
        metadata = FileMetadata(name="Makefile", size=100, content_type="text/plain")
        assert metadata.extension == ""

    def test_file_type_property(self):
        """Should return FileType enum from extension."""
        metadata = FileMetadata(name="data.csv", size=100, content_type="text/csv")
        assert metadata.file_type == FileType.CSV

    def test_size_mb_property(self):
        """Should calculate size in MB."""
        metadata = FileMetadata(name="test.csv", size=1024 * 1024, content_type="text/csv")
        assert metadata.size_mb == 1.0

        metadata = FileMetadata(name="test.csv", size=5 * 1024 * 1024, content_type="text/csv")
        assert metadata.size_mb == 5.0

    def test_immutable(self):
        """FileMetadata should be immutable (frozen)."""
        metadata = FileMetadata(name="test.csv", size=1024, content_type="text/csv")

        with pytest.raises(Exception):  # ValidationError for frozen model
            metadata.name = "changed.csv"

    def test_dangerous_filename_rejected(self):
        """Should reject filenames with path traversal."""
        with pytest.raises(ValueError, match="Invalid character"):
            FileMetadata(name="../etc/passwd", size=100, content_type="text/plain")

        with pytest.raises(ValueError, match="Invalid character"):
            FileMetadata(name="..\\windows\\system32", size=100, content_type="text/plain")

    def test_checksum_validation(self):
        """Should validate checksum format."""
        # Valid SHA-256 checksum
        metadata = FileMetadata(
            name="test.csv",
            size=100,
            content_type="text/csv",
            checksum="a" * 64,
        )
        assert metadata.checksum == "a" * 64

        # Invalid checksum (wrong length)
        with pytest.raises(ValueError):
            FileMetadata(
                name="test.csv",
                size=100,
                content_type="text/csv",
                checksum="invalid",
            )


class TestValidationResult:
    """Tests for ValidationResult value object."""

    def test_success_factory(self):
        """Success factory should create valid result."""
        result = ValidationResult.success()
        assert result.valid is True
        assert result.errors == []

    def test_success_with_data(self):
        """Success factory should accept data."""
        result = ValidationResult.success(data={"tier": "simple"})
        assert result.valid is True
        assert result.data == {"tier": "simple"}

    def test_failure_factory(self):
        """Failure factory should create invalid result."""
        result = ValidationResult.failure(errors=["File too large"])
        assert result.valid is False
        assert "File too large" in result.errors

    def test_failure_with_warnings(self):
        """Failure factory should accept warnings."""
        result = ValidationResult.failure(
            errors=["Error"],
            warnings=["Warning"],
        )
        assert result.valid is False
        assert "Error" in result.errors
        assert "Warning" in result.warnings

    def test_merge_both_valid(self):
        """Merging two valid results should produce valid result."""
        r1 = ValidationResult.success(data={"key1": "value1"})
        r2 = ValidationResult.success(data={"key2": "value2"})

        merged = r1.merge(r2)

        assert merged.valid is True
        assert merged.data["key1"] == "value1"
        assert merged.data["key2"] == "value2"

    def test_merge_one_invalid(self):
        """Merging valid with invalid should produce invalid result."""
        r1 = ValidationResult.success()
        r2 = ValidationResult.failure(errors=["Error"])

        merged = r1.merge(r2)

        assert merged.valid is False
        assert "Error" in merged.errors

    def test_merge_combines_errors_and_warnings(self):
        """Merging should combine all errors and warnings."""
        r1 = ValidationResult.failure(errors=["Error1"], warnings=["Warning1"])
        r2 = ValidationResult.failure(errors=["Error2"], warnings=["Warning2"])

        merged = r1.merge(r2)

        assert "Error1" in merged.errors
        assert "Error2" in merged.errors
        assert "Warning1" in merged.warnings
        assert "Warning2" in merged.warnings

    def test_bool_conversion(self):
        """Should convert to boolean based on valid field."""
        assert bool(ValidationResult.success()) is True
        assert bool(ValidationResult.failure(errors=["Error"])) is False

    def test_immutable(self):
        """ValidationResult should be immutable."""
        result = ValidationResult.success()

        with pytest.raises(Exception):
            result.valid = False
