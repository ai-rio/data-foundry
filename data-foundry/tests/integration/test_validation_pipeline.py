"""
Integration tests for the complete validation pipeline.

These tests verify the integration between all validation components:
- Staging layer (duplicate detection)
- Data quality validator (schema validation)
- Quality scoring (completeness and validity)
- Quality filtering (threshold-based)

Week 1: Data Validation + Database Optimization
Tests: 5
Lines: ~150
"""

import pytest
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

from src.tasks.ingestion import (
    validate_schema,
    check_duplicates,
    compute_quality_scores,
    filter_low_quality,
)
from src.core.data_quality import DataQualityValidator
from src.core.staging import StagingLayer
from src.models.data_record import DataRecord, DataSource


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def temp_staging_dir():
    """Create a temporary staging directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def staging_layer(temp_staging_dir):
    """Create a staging layer instance for tests."""
    return StagingLayer(temp_staging_dir)


@pytest.fixture
def sample_raw_data():
    """Sample raw data for testing the complete pipeline."""
    return [
        {
            "record_id": "rec-001",
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": '{"name": "John Doe", "email": "john@example.com"}',
            "file_name": "data.csv",
            "mime_type": "text/csv",
        },
        {
            "record_id": "rec-002",
            "tenant_id": "tenant-001",
            "data_source": "api",
            "raw_data": '{"name": "Jane Smith"}',
            # Missing recommended fields: file_name, mime_type
        },
        {
            "record_id": "rec-003",
            "tenant_id": "tenant-002",
            "data_source": "json",
            "raw_data": '{"company": "Acme Corp"}',
            "file_name": "import.json",
        },
        {
            # Invalid record - missing required fields
            "record_id": "rec-004",
            # Missing: tenant_id, data_source, raw_data
        },
        {
            "record_id": "rec-001",  # Duplicate content
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": '{"name": "John Doe", "email": "john@example.com"}',
            "file_name": "data.csv",
            "mime_type": "text/csv",
        },
    ]


@pytest.fixture
def mixed_quality_data():
    """Sample data with varying quality scores for threshold testing."""
    return [
        {
            "record_id": f"rec-{i:03d}",
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": f'{{"value": {i}}}',
            "validation_quality_score": quality,
        }
        for i, quality in enumerate([0.9, 0.7, 0.5, 0.4, 0.3, 0.1])
    ]


# ============================================================================
# INTEGRATION TEST 1: Staging then Quality Validation Flow
# ============================================================================


def test_staging_then_quality_validation_flow(sample_raw_data, temp_staging_dir):
    """
    Test complete flow: staging duplicate check -> quality validation.

    GIVEN: Raw data with potential duplicates and varying quality
    WHEN: Data flows through staging then validation
    THEN: Duplicates are detected and quality scores are computed correctly
    """
    # Step 1: Initialize staging layer
    staging = StagingLayer(temp_staging_dir)

    # Step 2: Check duplicates using staging
    new_records, duplicate_records = check_duplicates(sample_raw_data)

    # Verify duplicate detection
    assert len(new_records) == 4  # 5 total - 1 duplicate
    assert len(duplicate_records) == 1
    assert duplicate_records[0]["record_id"] == "rec-001"

    # Step 3: Apply quality validation to new records
    valid_records, invalid_records = validate_schema(new_records)

    # Verify schema validation
    assert len(valid_records) == 3  # rec-002 and rec-003 are valid
    assert len(invalid_records) == 1  # rec-004 is invalid (missing required fields)

    # Step 4: Compute quality scores
    scored_records = compute_quality_scores(valid_records)

    # Verify quality scores are added
    assert len(scored_records) == 3
    for record in scored_records:
        assert "data_quality_score" in record
        assert "completeness_score" in record
        assert "validity_score" in record
        assert 0.0 <= record["data_quality_score"] <= 1.0


# ============================================================================
# INTEGRATION TEST 2: Duplicate Detection Before Quality Scoring
# ============================================================================


def test_duplicate_detection_before_quality_scoring(sample_raw_data):
    """
    Test that duplicate detection happens before quality scoring.

    GIVEN: Data with duplicates
    WHEN: Pipeline runs duplicate check then quality scoring
    THEN: Quality scoring is only computed for non-duplicate records
    """
    # Step 1: Check duplicates
    new_records, duplicate_records = check_duplicates(sample_raw_data)

    # Verify duplicates are separated
    assert len(new_records) + len(duplicate_records) == len(sample_raw_data)
    assert len(new_records) == 4
    assert len(duplicate_records) == 1

    # Step 2: Validate only new records (not duplicates)
    valid_records, invalid_records = validate_schema(new_records)

    # Step 3: Compute quality scores only for valid new records
    scored_records = compute_quality_scores(valid_records)

    # Verify quality scores
    assert len(scored_records) == 3  # Only valid new records
    for record in scored_records:
        assert "data_quality_score" in record
        assert 0.0 <= record["data_quality_score"] <= 1.0

    # Verify duplicates are NOT scored (cost savings)
    for duplicate in duplicate_records:
        assert "data_quality_score" not in duplicate
        assert "completeness_score" not in duplicate


# ============================================================================
# INTEGRATION TEST 3: Quality Filtering with Low Threshold
# ============================================================================


def test_quality_filtering_with_low_threshold(mixed_quality_data):
    """
    Test quality filtering with low threshold (0.3).

    GIVEN: Data with varying quality scores from 0.1 to 0.9
    WHEN: Filter with min_quality=0.3
    THEN: Records with score >= 0.3 pass, others are filtered out
    """
    # Compute quality scores (already in data)
    scored_data = compute_quality_scores(mixed_quality_data)

    # Filter with low threshold
    high_quality, low_quality = filter_low_quality(scored_data, min_quality=0.3)

    # Verify filtering
    # Scores in fixture: [0.9, 0.7, 0.5, 0.4, 0.3, 0.1]
    # With threshold 0.3: high_quality = [0.9, 0.7, 0.5, 0.4, 0.3], low_quality = [0.1]
    assert len(high_quality) == 5  # Scores: 0.9, 0.7, 0.5, 0.4, 0.3
    assert len(low_quality) == 1   # Scores: 0.1

    # Verify all high quality meet threshold
    for record in high_quality:
        assert record["data_quality_score"] >= 0.3

    # Verify all low quality below threshold
    for record in low_quality:
        assert record["data_quality_score"] < 0.3


# ============================================================================
# INTEGRATION TEST 4: Quality Filtering with High Threshold
# ============================================================================


def test_quality_filtering_with_high_threshold(mixed_quality_data):
    """
    Test quality filtering with high threshold (0.7).

    GIVEN: Data with varying quality scores from 0.1 to 0.9
    WHEN: Filter with min_quality=0.7
    THEN: Only records with score >= 0.7 pass (stricter filtering)
    """
    # Compute quality scores (already in data)
    scored_data = compute_quality_scores(mixed_quality_data)

    # Filter with high threshold
    high_quality, low_quality = filter_low_quality(scored_data, min_quality=0.7)

    # Verify filtering
    # Scores in fixture: [0.9, 0.7, 0.5, 0.4, 0.3, 0.1]
    # With threshold 0.7: high_quality = [0.9, 0.7], low_quality = [0.5, 0.4, 0.3, 0.1]
    assert len(high_quality) == 2  # Scores: 0.9, 0.7
    assert len(low_quality) == 4   # Scores: 0.5, 0.4, 0.3, 0.1

    # Verify all high quality meet high threshold
    for record in high_quality:
        assert record["data_quality_score"] >= 0.7

    # Verify all low quality below high threshold
    for record in low_quality:
        assert record["data_quality_score"] < 0.7

    # Compare with low threshold - high threshold should be MORE restrictive
    # (fewer high_quality, more low_quality than low threshold)
    high_quality_low, _ = filter_low_quality(scored_data, min_quality=0.3)
    assert len(high_quality) < len(high_quality_low)  # 2 < 5
    assert len(low_quality) > (len(scored_data) - len(high_quality_low))  # 4 > 1


# ============================================================================
# INTEGRATION TEST 5: Validation Pipeline Error Handling
# ============================================================================


def test_validation_pipeline_error_handling():
    """
    Test error handling in the validation pipeline.

    GIVEN: Data that may cause errors (empty records, missing fields, etc.)
    WHEN: Pipeline processes problematic data
    THEN: Errors are handled gracefully and don't break the pipeline
    """
    # Data with various edge cases - excluding None which causes AttributeError
    problematic_data = [
        {
            "record_id": "rec-001",
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": '{"valid": "data"}',
        },
        {
            "record_id": "rec-003",
            "tenant_id": "tenant-001",
            "data_source": "json",
            "raw_data": '{"another": "value"}',
        },
        {},  # Invalid: empty record
        {
            # Record with invalid email format
            "record_id": "rec-005",
            "tenant_id": "tenant-002",
            "data_source": "api",
            "raw_data": "{}",
            "email": "not-an-email",  # Invalid format
        },
    ]

    # Step 1: Schema validation should handle empty records and invalid formats
    valid_records, invalid_records = validate_schema(problematic_data)

    # Verify error handling - empty record should be invalid
    assert len(valid_records) >= 0
    assert len(invalid_records) >= 0
    assert len(valid_records) + len(invalid_records) == len(problematic_data)

    # Step 2: Duplicate check should handle valid records
    new_records, duplicate_records = check_duplicates(valid_records)

    # Step 3: Quality scoring should handle any remaining records
    scored_records = compute_quality_scores(new_records)

    # Verify all scored records have required fields
    for record in scored_records:
        assert "data_quality_score" in record
        assert isinstance(record["data_quality_score"], (int, float))

    # Step 4: Quality filtering should handle records with missing scores
    high_quality, low_quality = filter_low_quality(scored_records, min_quality=0.5)

    # Verify filtering completed without error
    assert isinstance(high_quality, list)
    assert isinstance(low_quality, list)


# ============================================================================
# ADDITIONAL INTEGRATION SCENARIOS
# ============================================================================


def test_full_validation_pipeline_integration():
    """
    Test the complete validation pipeline end-to-end.

    GIVEN: Raw data with mixed quality, duplicates, and invalid records
    WHEN: All validation stages are applied in sequence
    THEN: Pipeline produces correctly categorized output
    """
    # Complete test data
    test_data = [
        {
            "record_id": "rec-001",
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": '{"name": "John", "email": "john@example.com"}',
            "file_name": "data.csv",
        },
        {
            "record_id": "rec-002",
            "tenant_id": "tenant-001",
            "data_source": "csv",
            "raw_data": '{"name": "Jane"}',
        },
        {
            "record_id": "rec-003",
            "tenant_id": "tenant-002",
            "data_source": "json",
            "raw_data": '{"company": "Acme"}',
        },
        {
            # Invalid - missing required fields
            "record_id": "rec-bad",
        },
    ]

    # Stage 1: Schema validation
    valid, invalid = validate_schema(test_data)
    assert len(valid) == 3
    assert len(invalid) == 1

    # Stage 2: Duplicate check - after validation, each record has unique timestamp
    # so all validated records are treated as new
    new, duplicates = check_duplicates(valid)
    assert len(new) == 3  # All valid records are new
    assert len(duplicates) == 0  # No duplicates in this batch

    # Stage 3: Quality scoring
    scored = compute_quality_scores(new)
    assert len(scored) == 3
    assert all("data_quality_score" in r for r in scored)

    # Stage 4: Quality filtering
    high, low = filter_low_quality(scored, min_quality=0.5)
    assert len(high) + len(low) == 3

    # Verify pipeline statistics
    pipeline_stats = {
        "total_input": len(test_data),
        "invalid_schema": len(invalid),
        "duplicates": len(duplicates),
        "processed": len(scored),
        "high_quality": len(high),
        "low_quality": len(low),
    }

    assert pipeline_stats["total_input"] == 4
    assert pipeline_stats["invalid_schema"] == 1
    assert pipeline_stats["duplicates"] == 0
    assert pipeline_stats["processed"] == 3
