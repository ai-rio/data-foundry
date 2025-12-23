RedditHarbor Pipeline-v4 → Data Foundry: Comprehensive Extraction Plan

 Executive Summary

 After deep analysis of both plans and codebases, this refined plan combines the strengths of both approaches:

 - Partner Plan: Staged extraction (Week 1-3), Data Quality Validator, A/B Testing Framework, comprehensive testing
 - My Plan: Signal Detection cost analysis, Database Performance Patterns, customer value propositions

 Result: 3-week staged extraction with ~72-96.5% total AI cost reduction potential

 ---
 Plan Comparison Summary

 | Component              | My Plan        | Partner Plan | Combined Plan    |
 |------------------------|----------------|--------------|------------------|
 | Data Quality Validator | ❌ Missed      | ✅ Week 1    | ✅ Week 1        |
 | Staging Layer          | ⭐ LOW         | ✅ Week 1    | ✅ Week 1        |
 | Database Patterns      | ✅ MEDIUM      | ❌ Missed    | ✅ Week 1        |
 | A/B Testing Framework  | ❌ Missed      | ✅ Week 2    | ✅ Week 2        |
 | Signal Detection       | ✅ HIGH        | ✅ Week 3    | ✅ Week 3        |
 | Testing Strategy       | ⚠️ Minimal     | ✅ 25+ tests | ✅ Full coverage |
 | Staged Approach        | ❌ All-at-once | ✅ 3 weeks   | ✅ 3 weeks       |

 My Gaps Identified:
 1. Data Quality Validator - data_foundry has quality score fields with NO logic
 2. A/B Testing Framework - Complete production-tested framework exists
 3. Testing Strategy - pipeline-v4 has 20 test files to learn from
 4. Staged extraction - More practical than all-at-once

 Partner Plan Gaps (Filled by My Plan):
 1. Database Performance Patterns - Pre-compiled queries, session pooling
 2. Detailed cost analysis examples
 3. Customer value propositions by persona

 ---
 WEEK 1: Data Validation + Database Optimization (2-3 days)

 Components to Extract/Implement

 1. Staging Layer (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/core/staging.py (161 lines)

 What it does:
 - JSON-based deduplication with O(1) lookups
 - State persistence survives restarts
 - Checkpoint mechanism for progress tracking

 Integration in Data Foundry:
 - Adapt RedditSubmission → DataRecord
 - Use record_hash field for deduplication
 - Create at src/core/staging.py

 Cost Savings: Prevents duplicate AI processing (~5-10% of records)

 2. Data Quality Validator (NEW - Inspired by pipeline-v4 Pydantic patterns)

 Source Patterns: /home/carlos/projects/pipeline-v4/models/reddit.py (223 lines of validation)

 Why NEW: Data Foundry has quality score fields (data_quality_score, completeness_score, validity_score) but NO logic to populate them!

 Implementation:
 # src/core/data_quality.py (NEW - ~350 lines)

 class ValidationResult(BaseModel):
     is_valid: bool
     completeness_score: float  # 0-1
     validity_score: float      # 0-1
     quality_score: float       # Weighted average
     errors: List[str]
     warnings: List[str]

 class DataQualityValidator:
     REQUIRED_FIELDS = ["record_id", "tenant_id", "data_source", "raw_data"]
     RECOMMENDED_FIELDS = ["file_name", "mime_type", "record_hash"]

     def validate_record(self, record: Dict) -> ValidationResult:
         # 1. Required field validation
         # 2. Recommended field validation
         # 3. Field-specific validation (email, phone, timestamps)
         # 4. Compute scores
         return ValidationResult(...)

 Cost Savings: 30% reduction by filtering invalid/bad data before AI

 3. Database Performance Patterns (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/database.py (227 lines) + load/loader.py (586 lines)

 What to extract:
 - Pre-compiled query patterns for hot paths
 - pool_pre_ping=True for connection validation
 - Bulk operation patterns

 Integration: Enhance src/database/connection.py

 Performance Gain: 5-15% faster queries, 10-100x faster bulk operations

 4. Prefect Validation Tasks (NEW)

 Integration Point: src/tasks/ingestion.py

 Add 4 new tasks between extract_data and apply_pii_redaction:
 @task
 def validate_schema(data: list[dict]) -> tuple[list[dict], list[dict]]:
     """Validate schema, return (valid, invalid)"""

 @task
 def check_duplicates(data: list[dict]) -> tuple[list[dict], list[dict]]:
     """Check duplicates via staging, return (new, duplicates)"""

 @task
 def compute_quality_scores(data: list[dict]) -> list[dict]:
     """Add quality scores to records"""

 @task
 def filter_low_quality(data: list[dict], min_quality: float = 0.5) -> tuple[list[dict], list[dict]]:
     """Filter by quality, return (high_quality, low_quality)"""

 5. Comprehensive Testing (EXTRACT patterns from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/tests/test_staging.py (191 lines)

 Tests to create:
 - tests/unit/test_staging.py - 11 tests (adapt from pipeline-v4)
 - tests/unit/test_data_quality.py - 10 tests (NEW)
 - tests/integration/test_validation_pipeline.py - 5 tests (NEW)
 - tests/test_validation_flow_e2e.py - 3 tests (NEW)

 Total: 25+ tests ensuring reliability

 ---
 Week 1 Implementation Details

 Files to Create (6 files)

 src/core/staging.py               # 161 lines (from pipeline-v4)
 src/core/data_quality.py          # 350 lines (NEW, inspired by Pydantic patterns)
 tests/unit/test_staging.py        # 200 lines (adapt from pipeline-v4)
 tests/unit/test_data_quality.py   # 200 lines (NEW)
 tests/integration/test_validation_pipeline.py  # 150 lines (NEW)
 tests/test_validation_flow_e2e.py # 100 lines (NEW)

 Files to Modify (3 files)

 src/tasks/ingestion.py             # Add 4 validation tasks
 src/core/validators.py             # Add helper functions
 src/database/connection.py         # Add pre-compiled queries

 Configuration (NEW)

 # src/core/config.py - ADD:
 ENABLE_DATA_VALIDATION: bool = True
 MIN_QUALITY_SCORE: float = 0.5
 STAGING_DIRECTORY: str = "data_foundry_staging"

 # .env - ADD:
 ENABLE_DATA_VALIDATION=true
 MIN_QUALITY_SCORE=0.5

 Dependencies

 Week 1 & Week 2:
 - Pydantic (already installed)
 - Standard library: json, hashlib, re, pathlib, datetime

 Week 3 (ML capabilities - optional):
 - scikit-learn>=1.5.0  # Random Forest, TF-IDF vectorization
 - joblib>=1.4.0        # Model serialization/deserialization
 - numpy>=1.26.0        # Feature arrays and numerical operations

 ---
 Week 1 Success Criteria

 Functional:
 - Staging layer detects duplicates with >95% accuracy
 - Quality validator catches invalid records with >90% accuracy
 - All 25+ tests pass
 - Backwards compatible (works with enable_validation=False)

 Performance:
 - Processing time increase <10%
 - Database query improvement 5-15% on hot paths
 - Memory usage stable

 Cost Impact:
 - 30% reduction in AI costs from filtering invalid data
 - Additional 5-10% from duplicate detection

 ---
 WEEK 2: A/B Testing Framework (2-3 days)

 Components to Extract

 1. ABTestingController (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/core/ab_testing_controller.py

 Features:
 - Deterministic assignment (same ID gets same treatment)
 - Configurable traffic distribution (ml_ratio parameter)
 - Treatment routing (ml vs baseline)

 Use Case in Data Foundry:
 - Test different validation strategies
 - Compare AI model performance
 - Test new features safely

 2. BasicMetricsCollector (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/core/basic_metrics.py (334 lines)

 Features:
 - Per-treatment precision/recall/F1
 - Confusion matrix tracking
 - Treatment distribution stats
 - JSON export functionality

 3. Testing Wrapper (NEW)

 Implementation:
 # src/core/ab_testing_wrapper.py
 class ValidationABWrapper:
     """Wrap validation logic for A/B testing"""

     def validate_with_ab_info(self, record: dict) -> ABValidationResult:
         # Route to control or variant
         # Collect metrics
         # Return result with treatment info

 4. Validation Script (EXTRACT)

 Source: /home/carlos/projects/pipeline-v4/scripts/validate_ab_framework.py (261 lines)

 Tests:
 - Deterministic assignment
 - Traffic distribution
 - Metrics collection
 - Wrapper interface

 ---
 Week 2 Implementation Details

 Files to Create (4 files)

 src/core/ab_testing_controller.py  # ~200 lines (from pipeline-v4)
 src/core/basic_metrics.py          # 334 lines (from pipeline-v4)
 src/core/ab_testing_wrapper.py     # ~150 lines (NEW)
 scripts/validate_ab_framework.py   # 261 lines (from pipeline-v4)

 Files to Modify (1 file)

 src/tasks/ingestion.py  # Add A/B testing support

 Configuration

 # src/core/config.py - ADD:
 ENABLE_AB_TESTING: bool = False
 AB_TEST_RATIO: float = 0.5  # 50% to treatment
 AB_TEST_NAME: str = "validation_strategy_v1"

 ---
 Week 2 Success Criteria

 - A/B framework correctly assigns treatments
 - Metrics collection works (precision, recall, F1)
 - Can compare control vs variant performance
 - All validation tests pass

 ---
 WEEK 3: Signal Detection - Rule-Based + ML Infrastructure (3-4 days)

 **NEW: ML Capabilities Added**
 - Week 3 now includes ML infrastructure extraction (ml_signal_detector.py, feature_extractor.py)
 - Random Forest classifier with 92.8% ROC-AUC performance
 - Feature engineering pipeline with 114 features (TF-IDF + signals + metadata)
 - A/B testing framework to compare rule-based vs ML approaches
 - Model retraining pipeline for Data Foundry-specific labels

 Components to Extract

 1. Rule-Based SignalDetector (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/transform/signal_detector.py (252 lines)

 What it does:
 - Pattern-based pre-filtering using compiled regex
 - 5 signal types: TOOL_REQUEST, PAIN_COMPLAINT, PRICE_MENTION, PROBLEM_SOLUTION, COMPARISON
 - Signal strength scoring (0-100)
 - Evidence extraction

 Integration: After data quality validation, before AI labeling

 2. ML Signal Detector Infrastructure (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/core/ml_signal_detector.py (329 lines)

 What it provides:
 - Production ML inference wrapper (lazy loading)
 - Feature validation and error handling
 - Batch and single sample prediction
 - Trained Random Forest: 92.8% ROC-AUC, 59.3% PR-AUC

 **CRITICAL**: Model file (random_forest_v1.joblib) trained on Reddit data - NOT directly usable
 **Action Required**: Retrain on Data Foundry data (labels: auto-approved vs human-reviewed)

 3. Feature Extraction Infrastructure (EXTRACT from pipeline-v4)

 Source: /home/carlos/projects/pipeline-v4/transform/feature_extractor.py (~250 lines)

 What it provides:
 - TF-IDF vectorization patterns (100 text features)
 - Categorical encoding utilities
 - Log transformations for engagement metrics
 - Feature validation framework
 - 114-feature pipeline (100 TF-IDF + 8 signals + 6 metadata)

 **Adaptation**: Retrain TF-IDF on Data Foundry text content (raw_data, data_preview fields)

 4. A/B Test: Rule-Based vs ML (NEW - Uses Week 2 A/B Framework)

 Purpose: Compare rule-based signal detection vs ML-based quality prediction

 Setup:
 - Control: Rule-based SignalDetector (proven 60-95% reduction)
 - Treatment: ML-based quality predictor (retrained on Data Foundry data)
 - Metrics: Precision, recall, F1, cost savings, processing time
 - Duration: 2-4 weeks data collection post-deployment

 Signal Types Detected:

 | Signal Type      | Pattern Example                  | Business Use Case          |
 |------------------|----------------------------------|----------------------------|
 | TOOL_REQUEST     | "is there a tool", "looking for" | Identify product requests  |
 | PAIN_COMPLAINT   | "i hate when", "frustrated with" | Identify customer pain     |
 | PRICE_MENTION    | "$\d+", "willing to pay"         | Identify purchase intent   |
 | PROBLEM_SOLUTION | "how do i", "need help with"     | Identify support needs     |
 | COMPARISON       | "vs", "alternative to"           | Identify competitive intel |

 ---
 Practical Examples

 Example 1: Lead Scoring for Sales

 # Input: Customer inquiry
 inquiry = "We urgently need a solution for data processing, our current tool is terrible"

 # Signal detection output
 {
     "signal_type": "PAIN_COMPLAINT",
     "signal_strength": 78,
     "evidence_snippets": ["need a solution", "current tool is terrible"],
     "should_analyze": True  # Above threshold of 70
 }

 # Business action: Route to sales team immediately

 Example 2: Product Feedback Analysis

 # Input: User feedback
 feedback = "I hate when the app crashes vs the stable version we had before"

 # Signal detection output
 {
     "signal_type": "COMPARISON",
     "signal_strength": 72,
     "evidence_snippets": ["hate when", "vs", "stable version"],
     "should_analyze": True
 }

 # Business action: Prioritize for product team review

 ---
 Week 3 Implementation Details

 Files to Create (8 files)

 src/core/signal_detector.py          # 252 lines (from pipeline-v4)
 src/core/signal_patterns.py          # Configurable patterns (NEW)
 src/ml/quality_predictor.py          # ~300 lines (adapt ml_signal_detector.py)
 src/ml/feature_engineering.py        # ~250 lines (adapt feature_extractor.py)
 src/ml/model_training.py              # ~200 lines (NEW - retraining pipeline)
 scripts/train_quality_model.py        # ~150 lines (NEW - training script)
 tests/unit/test_signal_detector.py    # Adapt from pipeline-v4
 tests/unit/test_ml_quality_predictor.py # NEW

 Files to Modify (3 files)

 src/tasks/ingestion.py     # Add detect_signals task + ML quality prediction
 src/services/ai_service.py  # Signal-aware processing
 src/models/data_record.py   # Add signal metadata + ML prediction fields

 Configuration

 # src/core/config.py - ADD:
 ENABLE_SIGNAL_DETECTION: bool = True
 SIGNAL_DETECTION_THRESHOLD: float = 70.0
 SIGNAL_PATTERNS_CONFIG: dict = {...}  # Customizable patterns

 # ML Quality Prediction (NEW)
 ENABLE_ML_QUALITY_PREDICTION: bool = False  # Enable after training
 ML_MODEL_PATH: str = "models/quality_predictor_v1.joblib"
 ML_FEATURE_ARTIFACTS_PATH: str = "models/feature_artifacts.pkl"
 ML_PREDICTION_THRESHOLD: float = 0.5

 ---
 Week 3 Success Criteria

 **Rule-Based Signal Detection:**
 - Signal detection achieves >80% precision, >70% recall
 - 60-95% reduction in AI processing costs
 - High-signal records prioritized
 - All tests pass

 **ML Infrastructure:**
 - ML inference wrapper successfully loads models
 - Feature extraction pipeline validates 114-feature format
 - A/B test framework routes traffic correctly (50/50 split)
 - Model retraining documentation complete

 **A/B Test Results (Post-deployment):**
 - Collect 2-4 weeks of comparison data
 - Determine which approach (rule-based vs ML) performs better
 - Document precision, recall, F1 for both
 - Calculate actual cost savings for both approaches

 ---
 Combined Cost Analysis

 Cost Savings Breakdown

 Scenario: 100,000 customer feedback records/month

 | Week     | Component               | Records Filtered  | Monthly Savings | Annual Savings |
 |----------|-------------------------|-------------------|-----------------|----------------|
 | 1        | Data Quality Validation | 30% invalid       | $9.00           | $108.00        |
 | 1        | Duplicate Detection     | 10% duplicates    | $3.00           | $36.00         |
 | 3        | Signal Detection        | 60-95% low-signal | $18-57          | $216-684       |
 | Combined | All Together            | ~72-97%           | $30-69          | $360-828       |

 Calculation:
 - Base cost (all records): 100,000 × $0.0003 = $30/month
 - After Week 1: 60,000 valid records × $0.0003 = $18/month (40% savings)
 - After Week 3: 3,000-24,000 high-signal records × $0.0003 = $0.90-7.20/month (76-97% total savings)

 Per-Tenant (100 tenants): $3.60-8.28/year savings per tenant
 Enterprise scale (10M records): $3,600-8,280/month savings

 **ML Impact Note:**
 ML-based quality prediction (92.8% ROC-AUC) may improve precision over rule-based detection,
 potentially pushing savings toward the higher end of the range. A/B testing will determine
 actual performance difference between rule-based and ML approaches.

 ---
 Customer Value Proposition

 For Enterprise Customers

 - Cost Savings: 72-97% reduction in AI processing costs
 - Faster Turnaround: Priority processing for high-value records
 - Better Insights: Focus analysis on actionable data

 For Product Teams

 - Lead Scoring: Automatically identify high-intent prospects
 - Pain Point Detection: Find customer problems at scale
 - Competitive Intelligence: Track comparison mentions

 For Support Teams

 - Triage: Automatically route urgent issues
 - Prioritization: Identify frustrated customers
 - Resource Allocation: Focus on high-impact cases

 For Engineering Teams

 - A/B Testing: Safely test new validation approaches
 - Performance: 5-15% database performance improvements
 - Reliability: Comprehensive test coverage (25+ tests)

 ---
 Files Reference

 Pipeline-v4 Files to Extract

 /home/carlos/projects/pipeline-v4/
 ├── core/staging.py                     # ⭐ Week 1 - Deduplication
 ├── models/reddit.py                    # ⭐ Week 1 - Pydantic validation patterns
 ├── models/analysis.py                  # ⭐ Week 1 - Model validation patterns
 ├── database.py                         # ⭐ Week 1 - Connection pooling
 ├── load/loader.py                      # ⭐ Week 1 - Pre-compiled queries
 ├── core/ab_testing_controller.py      # ⭐ Week 2 - A/B testing
 ├── core/basic_metrics.py               # ⭐ Week 2 - Metrics collection
 ├── transform/signal_detector.py        # ⭐ Week 3 - Signal detection (rule-based)
 ├── core/ml_signal_detector.py          # ⭐ Week 3 - ML infrastructure (329 lines)
 ├── transform/feature_extractor.py      # ⭐ Week 3 - Feature engineering (~250 lines)
 ├── models/random_forest_v1_metadata.json # 📊 Week 3 - Model metadata (reference only)
 ├── scripts/validate_ab_framework.py    # ⭐ Week 2 - A/B validation
 ├── tests/test_staging.py               # ⭐ Week 1 - Test patterns
 └── data/validation_metrics.py          # ⭐ Reference - Validation framework

 Data Foundry Files to Modify

 src/
 ├── core/
 │   ├── staging.py                    # NEW - Week 1
 │   ├── data_quality.py               # NEW - Week 1
 │   ├── ab_testing_controller.py      # NEW - Week 2
 │   ├── basic_metrics.py              # NEW - Week 2
 │   ├── ab_testing_wrapper.py         # NEW - Week 2
 │   ├── signal_detector.py            # NEW - Week 3 (rule-based)
 │   └── signal_patterns.py            # NEW - Week 3
 ├── ml/
 │   ├── quality_predictor.py          # NEW - Week 3 (adapt ml_signal_detector.py)
 │   ├── feature_engineering.py        # NEW - Week 3 (adapt feature_extractor.py)
 │   └── model_training.py             # NEW - Week 3 (retraining pipeline)
 ├── scripts/
 │   └── train_quality_model.py        # NEW - Week 3 (training script)
 ├── models/
 │   ├── quality_predictor_v1.joblib   # FUTURE - Week 3+ (after training)
 │   └── feature_artifacts.pkl         # FUTURE - Week 3+ (after training)
 ├── tasks/ingestion.py                # MODIFY - All weeks
 ├── services/ai_service.py            # MODIFY - Week 3
 ├── database/connection.py            # MODIFY - Week 1
 └── models/data_record.py             # MODIFY - Week 3

 ---
 Risk Assessment & Mitigation

 | Risk                             | Probability | Impact | Mitigation                             |
 |----------------------------------|-------------|--------|----------------------------------------|
 | Signal detection false positives | Medium      | Medium | Configurable thresholds, tuning period |
 | Performance overhead             | Low         | Low    | All validation is <10% overhead target |
 | Backwards compatibility          | Low         | High   | All features are optional, can disable |
 | Staging state corruption         | Low         | Low    | Auto-recovery from errors              |
 | A/B testing complexity           | Medium      | Low    | Proven framework from pipeline-v4      |
| Data migration issues            | Medium      | Medium | New validation only applies to new data |
| Dependency conflicts             | Low         | Medium | Verify versions in preflight check     |
| Test environment parity          | Low         | Low    | Adapt tests to Data Foundry structure   |
| Integration test failures        | Medium      | Medium | Feature flags allow isolated testing    |
| Rollback complexity              | Low         | High   | Documented procedures in docs/ROLLBACK.md |

---
Week 0: Preflight Check (1 day)

**Purpose:** Address critical QA audit issues before Week 1

Preflight Checklist:

| Task | Status | Evidence |
|------|--------|----------|
| Create test directory structure | ✅ Complete | tests/unit/ and tests/integration/ created |
| Verify validate_ab_framework.py | ✅ Complete | Found at /home/carlos/projects/pipeline-v4/scripts/ |
| Create baseline measurement script | ✅ Complete | docs/baseline-measurement.md created |
| Document rollback procedures | ✅ Complete | docs/ROLLBACK.md created |
| Update risk assessment | ✅ Complete | 5 new risks added to migration plan |

**Preflight Output Documents:**
- `docs/baseline-measurement.md` - Measurement procedures for pre/post comparison
- `docs/ROLLBACK.md` - Week-by-week rollback procedures
- `tests/unit/` - Directory for unit tests
- `tests/integration/` - Directory for integration tests

**Preflight Success Criteria:**
- All 5 QA HIGH priority issues resolved
- Baseline measurement methodology defined
- Rollback procedures documented
- Ready to start Week 1 implementation

 ---
 Final Recommendation

 Adopt the Combined 3-Week Staged Approach

 Why:
 1. Week 1: Foundation - Data validation + database optimization (30% cost savings)
 2. Week 2: Testing Infrastructure - A/B framework for safe experimentation
 3. Week 3: Advanced Filtering - Signal detection for maximum savings (72-97% total)

 Total Effort: 6-9 days across 3 weeks
 Total Impact: 72-97% AI cost reduction + 5-15% database performance improvement + comprehensive testing

---
TDD Approach Decision

**Recommended: Hybrid TDD (Modified Pragmatic Approach)**

Decision Rationale:
- **EXTRACTED components** (staging.py, ab_testing_controller, signal_detector): Adapt existing tests from pipeline-v4
- **NEW components** (DataQualityValidator, ABTestingWrapper): Full TDD (Red-Green-Refactor)
- **MODIFIED components** (ingestion.py, ai_service.py): Test-after regression guard

This balances speed (3-week timeline) with safety (production-tested patterns).

| Component Type          | TDD Approach         | Rationale                           |
|-------------------------|----------------------|-------------------------------------|
| Extracted from v4       | Adapt existing tests | Leverage 20 proven test files       |
| New validation logic    | Full TDD             | New code = test-first discipline    |
| Integration points      | Test-after           | Regression guard for modifications  |
| Database optimizations  | Performance tests    | Verify 5-15% improvement claim      |

Week-by-Week Test Order:

**Week 1: Data Validation + Database Optimization**
1. Copy `test_staging.py` from pipeline-v4 → adapt to Data Foundry
2. Write `test_data_quality.py` FIRST (Full TDD for new validator)
3. Implement `src/core/staging.py` to pass adapted tests
4. Implement `src/core/data_quality.py` to pass new tests
5. Write integration tests for validation pipeline
6. Performance test database improvements

**Week 2: A/B Testing Framework**
1. Copy `test_ab_testing_controller.py` from pipeline-v4 → adapt
2. Write `test_ab_testing_wrapper.py` FIRST (Full TDD)
3. Implement A/B components to pass tests
4. Validate framework with `scripts/validate_ab_framework.py`

**Week 3: Signal Detection**
1. Copy `test_signal_detector.py` (613 lines) from pipeline-v4 → adapt
2. Implement signal detector to pass tests
3. Performance test (target: >80% precision, >70% recall)
4. Cost validation test (verify 60-95% reduction claim)

**TDD Governance:**
- Each task: tdd-orchestrator agent reviews test-first compliance
- Each completion: code-reviewer agent validates test coverage
- Weekly: test-automator agent runs full suite
- Final acceptance: Full test suite + performance benchmarks must pass