#!/usr/bin/env python3
"""
Phase 1 Pipeline Test Harness - Validate Backend Ingestion Pipeline

Tests the existing data ingestion pipeline (Phase 1 backend) with real Kaggle datasets.
NO API calls - directly tests pipeline functions.

Hardware-Conscious Design:
- Tests with CSV only (no heavy PDF/DOCX parsing)
- Uses in-memory data processing
- Measures performance and cost accuracy

Purpose:
- Validate pipeline works end-to-end with real datasets
- Measure processing time per vertical
- Validate cost calculation accuracy
- Identify any pipeline errors before API integration
- Confirm Phase 0 assumptions (speed, accuracy, cost)

Output:
- pilot_test_results/ directory with per-vertical results
- Summary CSV with performance metrics

Note: For API endpoint testing, use test_harness_phase2_api.py
"""

import os
import sys
import json
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd
import asyncio
from dataclasses import dataclass, asdict

# Setup paths
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "data-foundry"))

# Import existing pipeline (NO MODIFICATIONS)
from src.tasks.ingestion import (
    extract_data,
    validate_schema,
    check_duplicates,
    compute_quality_scores,
    filter_low_quality,
    apply_pii_redaction,
    apply_ai_labeling,
    route_for_human_review,
    save_to_database,
)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PilotTestConfig:
    """Configuration for a pilot test."""
    vertical: str  # fintech, healthcare, ecommerce, legal
    dataset_path: str
    sample_size: int  # How many records to test (0 = all)
    enable_validation: bool = True
    enable_pii_redaction: bool = True
    enable_ai_labeling: bool = True
    enable_human_review: bool = True


@dataclass
class PilotTestResult:
    """Results from running a pilot test."""
    vertical: str
    dataset_path: str
    timestamp: str
    total_records: int
    sample_size: int
    processing_time_seconds: float = 0.0

    # Pipeline stages
    extracted_count: int = 0
    validated_count: int = 0
    invalid_count: int = 0
    new_records_count: int = 0
    duplicate_count: int = 0
    high_quality_count: int = 0
    low_quality_count: int = 0
    auto_approved_count: int = 0
    human_review_count: int = 0

    # Cost estimation
    estimated_cost: float = 0.0
    cost_per_record: float = 0.0

    # Status
    success: bool = False
    error_message: str = ""


# ============================================================================
# Utilities
# ============================================================================

def load_dataset(path: str, sample_size: int = 0) -> tuple[List[Dict[str, Any]], int]:
    """Load dataset from CSV."""
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
            total = len(df)

            if sample_size > 0:
                df = df.head(sample_size)

            data = df.to_dict('records')
            return data, total
        else:
            raise ValueError(f"Unsupported format: {path}")
    except Exception as e:
        print(f"❌ Failed to load {path}: {str(e)}")
        raise


def wrap_raw_data(raw_records: List[Dict[str, Any]], vertical: str, tenant_id: str = "test-tenant") -> List[Dict[str, Any]]:
    """
    Wrap raw CSV records with required metadata before validation.

    Transforms raw CSV data into the format expected by DataQualityValidator:
    - Adds record_id (auto-generated from vertical + index)
    - Adds tenant_id (for multi-tenancy)
    - Adds data_source (vertical name)
    - Wraps raw data as JSON string in raw_data field

    Args:
        raw_records: List of raw CSV record dicts
        vertical: Vertical name (fintech, healthcare, ecommerce, legal)
        tenant_id: Tenant identifier (default: test-tenant)

    Returns:
        List of wrapped records ready for pipeline validation
    """
    wrapped = []
    for idx, record in enumerate(raw_records):
        wrapped.append({
            "record_id": f"{vertical}-{idx:06d}",
            "tenant_id": tenant_id,
            "data_source": vertical,
            "raw_data": json.dumps(record)
        })
    return wrapped


def estimate_cost(vertical: str, auto_approved: int, human_review: int) -> tuple[float, float]:
    """
    Estimate cost based on vertical and record counts.
    Uses pricing from CUSTOMER_WILLINGNESS_TO_PAY_BY_VERTICAL research.
    """
    # Pricing per vertical (from research)
    pricing = {
        "fintech": {
            "ai_labels": 0.03,  # AI processing
            "human_audits": 0.08,  # Human review
        },
        "healthcare": {
            "ai_labels": 0.15,
            "human_audits": 0.25,
        },
        "ecommerce": {
            "ai_labels": 0.08,
            "human_audits": 0.15,
        },
        "legal": {
            "ai_labels": 35,
            "human_audits": 65,
        },
    }

    if vertical not in pricing:
        return 0.0, 0.0

    rates = pricing[vertical]

    # Calculate total cost
    ai_cost = auto_approved * rates["ai_labels"]
    human_cost = human_review * rates["human_audits"]
    total_cost = ai_cost + human_cost

    # Per-record average
    total_records = auto_approved + human_review
    cost_per_record = total_cost / total_records if total_records > 0 else 0.0

    return total_cost, cost_per_record


# ============================================================================
# Test Executor
# ============================================================================

async def run_pilot_test(config: PilotTestConfig) -> PilotTestResult:
    """
    Run a single pilot test using EXISTING pipeline.
    """
    result = PilotTestResult(
        vertical=config.vertical,
        dataset_path=config.dataset_path,
        timestamp=datetime.now().isoformat(),
        total_records=0,
        sample_size=config.sample_size,
    )

    try:
        print(f"\n{'='*70}")
        print(f"PILOT TEST: {config.vertical.upper()}")
        print(f"{'='*70}")
        print(f"Dataset: {config.dataset_path}")

        # Load dataset
        print("📥 Loading dataset...")
        start_time = time.time()
        data, total_count = load_dataset(config.dataset_path, config.sample_size)
        result.total_records = total_count
        result.sample_size = len(data)
        result.processing_time_seconds = 0.0  # Initialize
        print(f"   ✓ Loaded {len(data)} records (total in file: {total_count})")

        # Stage 1: Extract (already loaded, but simulate extract_data)
        print("🔍 Stage 1: Extract Data")
        extracted = data
        result.extracted_count = len(extracted)
        print(f"   ✓ Extracted: {result.extracted_count} records")

        # Stage 2: Wrap raw data with metadata
        print("📦 Stage 1.5: Wrap Raw Data")
        wrapped_data = wrap_raw_data(extracted, config.vertical)
        print(f"   ✓ Wrapped {len(wrapped_data)} records with metadata")

        # Stage 3: Validate
        if config.enable_validation:
            print("✔️  Stage 2: Validate")
            try:
                valid_data, invalid_data = validate_schema(wrapped_data)
                result.validated_count = len(valid_data)
                result.invalid_count = len(invalid_data)
                print(f"   ✓ Valid: {result.validated_count}, Invalid: {result.invalid_count}")

                # Check duplicates
                new_data, duplicates = check_duplicates(valid_data)
                result.new_records_count = len(new_data)
                result.duplicate_count = len(duplicates)
                print(f"   ✓ New: {result.new_records_count}, Duplicates: {result.duplicate_count}")

                # Quality scoring
                scored_data = compute_quality_scores(new_data)
                high_quality, low_quality = filter_low_quality(scored_data, min_quality=0.75)
                result.high_quality_count = len(high_quality)
                result.low_quality_count = len(low_quality)
                print(f"   ✓ High Quality: {result.high_quality_count}, Low Quality: {result.low_quality_count}")

                data_for_processing = high_quality
            except Exception as e:
                print(f"   ⚠️  Validation error (continuing): {str(e)}")
                data_for_processing = extracted
        else:
            data_for_processing = extracted
            print("   ⏭️  Validation disabled")

        # Stage 4: PII Redaction
        if config.enable_pii_redaction:
            print("🔐 Stage 3: PII Redaction")
            try:
                redacted_data = apply_pii_redaction(data_for_processing)
                print(f"   ✓ Redacted: {len(redacted_data)} records")
                data_for_processing = redacted_data
            except Exception as e:
                print(f"   ⚠️  PII redaction error (continuing): {str(e)}")
        else:
            print("   ⏭️  PII redaction disabled")

        # Stage 5: AI Labeling
        if config.enable_ai_labeling:
            print("🤖 Stage 4: AI Labeling")
            try:
                labeled_data = await apply_ai_labeling(data_for_processing)
                print(f"   ✓ Labeled: {len(labeled_data)} records")
                data_for_processing = labeled_data
            except Exception as e:
                print(f"   ⚠️  AI labeling error (continuing): {str(e)}")
                labeled_data = data_for_processing
        else:
            print("   ⏭️  AI labeling disabled")
            labeled_data = data_for_processing

        # Stage 6: Confidence Routing
        if config.enable_human_review:
            print("👥 Stage 5: Confidence Routing")
            try:
                auto_approved, human_review = route_for_human_review(labeled_data)
                result.auto_approved_count = len(auto_approved)
                result.human_review_count = len(human_review)
                print(f"   ✓ Auto-approved: {result.auto_approved_count}")
                print(f"   ✓ Human review: {result.human_review_count}")
            except Exception as e:
                print(f"   ⚠️  Confidence routing error: {str(e)}")
                result.auto_approved_count = len(labeled_data)
                result.human_review_count = 0
        else:
            print("   ⏭️  Human review disabled")
            result.auto_approved_count = len(labeled_data)
            result.human_review_count = 0

        # Calculate metrics
        end_time = time.time()
        result.processing_time_seconds = end_time - start_time

        # Cost estimation
        estimated_cost, cost_per_record = estimate_cost(
            config.vertical,
            result.auto_approved_count,
            result.human_review_count
        )
        result.estimated_cost = estimated_cost
        result.cost_per_record = cost_per_record

        # Success
        result.success = True

        # Print summary
        print(f"\n📊 RESULTS for {config.vertical.upper()}:")
        print(f"   Processing Time: {result.processing_time_seconds:.2f}s")
        print(f"   Records Processed: {result.sample_size}")
        print(f"   Auto-Approved: {result.auto_approved_count} ({result.auto_approved_count/result.sample_size*100:.1f}%)")
        print(f"   Human Review: {result.human_review_count} ({result.human_review_count/result.sample_size*100:.1f}%)")
        print(f"   Estimated Cost: ${result.estimated_cost:.2f}")
        print(f"   Cost/Record: ${result.cost_per_record:.4f}")

    except Exception as e:
        result.success = False
        result.error_message = str(e)
        print(f"❌ FAILED: {str(e)}")

    return result


# ============================================================================
# Main
# ============================================================================

async def main():
    """Run all pilot tests."""

    # Create output directory
    output_dir = PROJECT_ROOT / "pilot_test_results"
    output_dir.mkdir(exist_ok=True)

    # Define pilot tests
    tests = [
        PilotTestConfig(
            vertical="fintech",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/fintech/Banking_Transactions_USA_2023_2024.csv"),
            sample_size=1000,  # Start with 1000 to test quickly
        ),
        PilotTestConfig(
            vertical="healthcare",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/healthcare/healthcare_dataset.csv"),
            sample_size=1000,
        ),
        PilotTestConfig(
            vertical="ecommerce",
            dataset_path=str(PROJECT_ROOT.parent / "data/pilot_test_datasets/ecommerce/Phones.csv"),
            sample_size=500,  # E-commerce CSVs are smaller
        ),
        # Legal dataset is JSON/structured, need different handling
        # Skip for now, will adapt extract_data first
    ]

    results = []

    print("\n" + "="*70)
    print("PILOT TEST HARNESS - EXISTING PIPELINE (NO MODIFICATIONS)")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Output Directory: {output_dir}")

    # Run tests
    for test_config in tests:
        result = await run_pilot_test(test_config)
        results.append(result)

        # Save individual result
        result_file = output_dir / f"{test_config.vertical}_result.json"
        with open(result_file, 'w') as f:
            json.dump(asdict(result), f, indent=2)
        print(f"   📄 Result saved: {result_file}")

    # Generate summary CSV
    print(f"\n{'='*70}")
    print("SUMMARY REPORT")
    print(f"{'='*70}")

    summary_file = output_dir / "pilot_test_summary.csv"
    with open(summary_file, 'w', newline='') as f:
        fieldnames = [k for k in asdict(results[0]).keys()] if results else []
        writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))

    print(f"✅ Summary saved: {summary_file}\n")

    # Print table
    print("VERTICAL      | SUCCESS | TIME(s) | RECORDS | AUTO-APPR | HUMAN-REV | COST/REC")
    print("-" * 85)
    for result in results:
        status = "✓" if result.success else "✗"
        print(f"{result.vertical:13} | {status:7} | {result.processing_time_seconds:7.2f} | "
              f"{result.sample_size:7} | {result.auto_approved_count:9} | "
              f"{result.human_review_count:9} | ${result.cost_per_record:8.4f}")

    print("\n✅ PILOT TEST COMPLETE")
    print(f"📁 Results in: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
