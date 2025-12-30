# AML Service Implementation Plan - Structured Subtasks

**Phase:** P01 - AML Service MLP Implementation
**Date:** December 29, 2025
**Duration:** 2-3 weeks
**Objective:** Build Minimum Lovable Product for fintech AML transaction labeling service

---

## Executive Summary

This document breaks down the AML Service MLP into structured, executable subtasks with clear dependencies, effort estimates, and execution sequencing.

**Total Subtasks:** 28
**Sequential Effort:** 65-80 hours
**Parallel Execution:** 25-35 hours (63% time savings)
**Critical Path:** P01-001 → P01-002 → P01-003 → P01-010 → P01-014 → P01-020 → P01-025 → P01-028

---

## Part 1: Subtask Inventory with Dependencies

### WEEK 1: Core Infrastructure & Labeling

#### P01-001: AML Database Schema Design
**Category:** Database & Data Model
**Effort:** 4 hours
**Dependencies:** None
**Blocks:** P01-002, P01-003, P01-015

**Description:**
Design PostgreSQL schema for AML transaction labeling service with focus on regulatory defensibility and multi-reviewer support.

**Deliverables:**
1. Entity-Relationship Diagram (ERD) showing:
   - `aml_transaction_labels` table
   - `audit_reports` table
   - `expert_reviews` table
   - `labeling_methodology_versions` table

2. Table specifications:
   - Column names, data types, constraints
   - Primary/foreign keys, indexes
   - Audit trail fields (created_at, updated_at, reviewed_by, reviewed_at)
   - Tenant isolation (tenant_id on all tables)
   - Compliance fields (regulatory_standard_version, methodology_version)

3. Design rationale document explaining:
   - Why Cohen's Kappa score is stored (for audit defensibility)
   - Why multiple reviewers are tracked (for inter-rater agreement)
   - Indexing strategy for query performance
   - How data structure supports "audit-ready" output

**Acceptance Criteria:**
- ERD is clear and normalized (3NF)
- All regulatory/audit fields documented
- Schema supports multi-reviewer consensus tracking
- Indexes planned for high-query fields (tenant_id, job_id, aml_risk_level)

---

#### P01-002: Create Alembic Migration for AML Tables
**Category:** Database & Migrations
**Effort:** 3 hours
**Dependencies:** P01-001 (need schema design)
**Blocks:** P01-003, P01-015

**Description:**
Implement Alembic migration that creates AML-specific tables in PostgreSQL.

**Deliverables:**
1. Migration file: `alembic/versions/001_add_aml_transaction_labels_table.py`
   - Create `aml_transaction_labels` table (from P01-001 design)
   - Create `audit_reports` table
   - Create `expert_reviews` table
   - Create indexes
   - Include migration rollback

2. Migration file: `alembic/versions/002_add_aml_audit_trail_table.py`
   - Create `labeling_methodology_versions` table
   - Track methodology changes for regulatory compliance

3. Testing:
   - Migration creates tables successfully
   - Rollback removes tables without errors
   - Schema matches ERD from P01-001

**Acceptance Criteria:**
- Migrations run successfully against test database
- All tables and indexes created
- Rollback works without errors
- Migration files are idempotent

---

#### P01-003: Implement AML ORM Models (SQLAlchemy)
**Category:** Code & Data Models
**Effort:** 4 hours
**Dependencies:** P01-001, P01-002 (schema must exist)
**Blocks:** P01-004, P01-005, P01-010, P01-015

**Description:**
Create SQLAlchemy ORM models for AML domain entities to replace generic data models.

**Deliverables:**
1. New file: `src/models/aml_transaction_label.py`
   ```python
   class AMLTransactionLabel(Base):
       __tablename__ = "aml_transaction_labels"

       id: int
       job_id: UUID (FK to processing_jobs)
       tenant_id: UUID (FK to tenants)
       transaction_id: str (original customer ID)

       # AML-specific fields
       aml_risk_level: int (1-5, FATF-aligned)
       aml_typology: str (structuring, mule_activity, etc.)
       regulatory_flag: str (SARable, COAF_reportable, AMLA_compliant)
       expert_reasoning: str (why this label was applied)

       # Quality/Audit fields
       confidence_score: float (Cohen's Kappa ≥ 0.70)
       reviewed_by_experts: list[str] (names of reviewers)
       reviewed_at: datetime
       methodology_version: str (FATF_2022_v2.1, etc.)

       # Audit trail
       created_at: datetime
       updated_at: datetime

       # Methods
       def is_audit_ready(self) -> bool
       def get_regulatory_references(self) -> list[str]
       def to_csv_row(self) -> dict
   ```

2. New file: `src/models/audit_report.py`
   ```python
   class AuditReport(Base):
       __tablename__ = "audit_reports"

       id: int
       job_id: UUID (FK)
       tenant_id: UUID (FK)
       report_content: str (JSON or PDF)
       methodology_used: str
       regulatory_standards_applied: list[str]
       created_at: datetime

       # Methods
       def to_pdf(self) -> bytes
       def to_json(self) -> dict
   ```

3. New file: `src/models/expert_review.py`
   ```python
   class ExpertReview(Base):
       __tablename__ = "expert_reviews"

       id: int
       label_id: UUID (FK to aml_transaction_label)
       reviewer_name: str
       reviewed_at: datetime
       agreement_score: float
   ```

4. Enums for AML values:
   - Update `src/models/enums.py`:
     - `AMLRiskLevel` (1=minimal, 2=low, 3=medium, 4=high, 5=critical)
     - `AMLTypology` (structuring, mule_activity, trade_based_ml, sanctions_evasion, pep_exposure, value_transfer)
     - `RegulatoryFlag` (fin_cen_sars, coaf_reportable, amla_relevant)

**Acceptance Criteria:**
- All models match schema from P01-001
- Models have validation (risk_level must be 1-5, etc.)
- Relationships defined (job → labels → reviews)
- Methods for audit defensibility implemented
- Tests verify model creation and validation

---

#### P01-004: Rewrite AI Labeling Task for AML (CRITICAL)
**Category:** Core Processing Logic
**Effort:** 6 hours
**Dependencies:** P01-003 (need ORM models)
**Blocks:** P01-005, P01-006, P01-009

**Description:**
Replace generic labeling in `src/tasks/ingestion.py:apply_ai_labeling()` with AML-specific prompt and response parsing.

**Current Code (Lines 729-850 in ingestion.py):**
```python
@task
def apply_ai_labeling(extracted_data, ai_service):
    # Generic prompt - NEEDS REPLACEMENT
    prompt = f"""
    Analyze the following data record and classify it:
    {sanitize_prompt_input(str(record_data))}
    Return JSON with: category, confidence (0-1), reasoning
    """
    # Returns: ai_category, ai_confidence, ai_reasoning
```

**New Implementation:**
1. AML-specific prompt design (250+ tokens):
   - Instructs GPT-4o to extract FATF typologies
   - Asks for AML risk level (1-5)
   - Requests regulatory flag determination
   - Requires explicit reasoning

2. Response structure:
   ```python
   {
       "aml_risk_level": 4,
       "aml_typology": "structuring",
       "regulatory_flag": "fin_cen_sars",
       "expert_reasoning": "High-risk pattern: 8 transfers <$10k from same sender to high-risk jurisdiction within 2 hours, then consolidated by single recipient. FATF R.10 structuring indicator.",
       "confidence_score": 0.92,
       "regulatory_references": ["FATF_R10", "FinCEN_SAR_FAQ_Oct2025"]
   }
   ```

3. Error handling:
   - Validate response has all required fields
   - Handle AI hallucinations (confidence < 0.6)
   - Log failures for manual review
   - Fallback: confidence < 0.6 → route to expert immediately

4. New file: `src/core/prompts/aml_labeling_prompt.py`
   - Centralize AML prompt template
   - Version control prompt updates (when regulations change)
   - Easy to iterate on prompt quality

**Deliverables:**
1. Updated `apply_ai_labeling()` in `src/tasks/ingestion.py`
   - Input: extracted transaction data (sender_id, recipient_country, amount, timestamp)
   - Output: AMLLabel(risk_level, typology, regulatory_flag, reasoning, confidence)

2. New file: `src/core/prompts/aml_labeling_prompt.py`
   - Prompt template with FATF typologies
   - System prompt explaining regulator perspective
   - Example formatting

3. Response validation function:
   - Ensure all required fields present
   - Validate risk_level is 1-5
   - Validate typology matches enum
   - Validate regulatory_flag matches enum

4. Test cases:
   - Structuring pattern detection
   - Mule activity detection
   - Sanctions evasion flags
   - Trade-based ML red flags
   - PEP exposure detection
   - Edge cases (ambiguous transactions)

**Acceptance Criteria:**
- Prompt produces valid FATF-aligned labels
- Response parsing robust (handles AI variations)
- Confidence scoring accurate (reflects model certainty)
- Reasoning is explainable to regulators
- Test cases pass with expected labels

---

#### P01-005: Implement Cohen's Kappa Inter-Rater Agreement Calculation
**Category:** Data Quality & Validation
**Effort:** 4 hours
**Dependencies:** P01-003 (need ORM models), P01-004 (need AML labels)
**Blocks:** P01-006, P01-009, P01-010

**Description:**
Implement Cohen's Kappa coefficient calculation to measure inter-rater agreement and determine when expert review is needed.

**Background:**
- Cohen's Kappa measures agreement between two raters on categorical data
- Formula: κ = (p_o - p_e) / (1 - p_e)
  - p_o = observed agreement
  - p_e = expected agreement by chance
- Interpretation: κ ≥ 0.80 = strong agreement, κ < 0.70 = need review

**Deliverables:**
1. New file: `src/core/agreement_calculator.py`
   ```python
   class CohenKappaCalculator:
       def calculate_agreement(
           self,
           ai_labels: list[AMLLabel],
           expert_labels: list[AMLLabel],
           agreement_type: str = "strict"  # strict or partial
       ) -> float:
           """
           Calculate Cohen's Kappa agreement between AI and expert labels.

           Args:
               ai_labels: Labels from GPT-4o AI model
               expert_labels: Labels from expert reviewers
               agreement_type: "strict" (exact match) or "partial" (similar typology)

           Returns:
               Cohen's Kappa score (0-1)
           """
           # Implementation using scikit-learn's cohen_kappa_score

       def is_agreement_sufficient(self, kappa_score: float) -> bool:
           """Return True if Kappa >= 0.70 (good agreement)."""
           return kappa_score >= 0.70

       def get_confidence_level(self, kappa_score: float) -> str:
           """Return confidence level based on Kappa score."""
           # 0.90+ → Very High
           # 0.80-0.90 → High
           # 0.70-0.80 → Acceptable
           # 0.60-0.70 → Fair (needs expert review)
           # <0.60 → Poor (needs investigation)
   ```

2. Integration point:
   - Call after AI labels generated
   - If only 1 reviewer: use AI confidence as proxy
   - If multiple reviewers: calculate Kappa across all reviewers
   - Store Kappa score in `aml_transaction_label.confidence_score`

3. Test cases:
   - Perfect agreement (Kappa = 1.0)
   - Partial agreement (Kappa = 0.75)
   - Poor agreement (Kappa = 0.40)
   - No agreement (Kappa = 0)

4. Dependencies:
   - `scikit-learn` (for cohen_kappa_score function)

**Acceptance Criteria:**
- Cohen's Kappa calculation is mathematically correct
- Score correctly identifies when expert review needed
- Handles edge cases (perfect agreement, no agreement)
- Performance acceptable for 1000s of transactions

---

#### P01-006: Modify Data Ingestion Flow for AML Labeling
**Category:** Task Orchestration
**Effort:** 5 hours
**Dependencies:** P01-004, P01-005 (need labeling and agreement tasks)
**Blocks:** P01-007, P01-010, P01-014

**Description:**
Update Prefect flow in `src/tasks/ingestion.py:data_ingestion_flow()` to orchestrate AML-specific tasks in correct sequence.

**Current Flow (Lines 1054-1150):**
```
extract_data
  → validate_schema
  → check_duplicates
  → apply_pii_redaction
  → apply_ai_labeling (GENERIC - NEEDS REPLACEMENT)
  → route_for_human_review
  → save_to_database
  → _update_job_status_complete
```

**New Flow:**
```
extract_data
  → validate_schema (modified for AML fields)
  → check_duplicates
  → apply_pii_redaction (modified to keep transaction_id)

  → apply_aml_labeling (REPLACES generic labeling)

  → compute_inter_rater_agreement (NEW)

  → route_for_human_review (modified: check if Kappa < 0.70)
    ├─ High confidence (Kappa ≥ 0.70) → save_to_database
    └─ Low confidence (Kappa < 0.70) → send_to_label_studio

  → save_aml_labels_to_database (NEW - replaces save_to_database)

  → generate_audit_report (NEW)

  → _update_job_status_complete
```

**Deliverables:**
1. Update `data_ingestion_flow()` in `src/tasks/ingestion.py`:
   - Replace `apply_ai_labeling` with `apply_aml_labeling`
   - Add `compute_inter_rater_agreement` task after labeling
   - Modify `route_for_human_review` to use Cohen's Kappa threshold
   - Add `generate_audit_report` task before completion
   - Update result collection to include audit_report_url

2. Task modifications:
   - `validate_schema()`: Expect AML fields (amount > 0, country is ISO-3166)
   - `apply_pii_redaction()`: Redact names but keep transaction_id, amounts, countries
   - `route_for_human_review()`: Use `confidence_score >= 0.70` threshold

3. New tasks:
   - `save_aml_labels_to_database()`: Persist AMLTransactionLabel records
   - `generate_audit_report()`: Create compliance documentation

4. Error handling:
   - If any task fails, mark job as FAILED with error details
   - Log all decisions for audit trail

**Acceptance Criteria:**
- Flow orchestrates all tasks in correct sequence
- AML labels flow through to database
- Audit report generated before job completion
- All errors caught and logged
- Performance acceptable (10,000 transactions in <30 mins)

---

#### P01-007: Implement Save AML Labels to Database Task
**Category:** Database Integration
**Effort:** 3 hours
**Dependencies:** P01-003, P01-006 (need models and flow)
**Blocks:** P01-010

**Description:**
Implement Prefect task that persists AML transaction labels to database with full audit trail.

**Deliverables:**
1. New task in `src/tasks/ingestion.py`: `save_aml_labels_to_database()`
   ```python
   @task
   def save_aml_labels_to_database(
       aml_labels: list[AMLLabel],
       job_id: UUID,
       tenant_id: UUID,
       db_session: AsyncSession
   ) -> int:
       """
       Persist AML labels to aml_transaction_labels table.

       Returns:
           Number of labels saved
       """
       # For each label:
       # 1. Create AMLTransactionLabel ORM object
       # 2. Set: job_id, tenant_id, risk_level, typology, flag, reasoning, confidence
       # 3. Set audit fields: created_at, methodology_version
       # 4. Bulk insert to database
       # 5. Return count
   ```

2. Features:
   - Batch insert for performance (1000s of records)
   - Commit transaction only if all labels saved successfully
   - Rollback on failure (no partial saves)
   - Log insertion metrics (count, duration, records/sec)

3. Error handling:
   - Duplicate transaction_id in same job → skip (no double-labeling)
   - Database constraint violations → log and raise
   - Connection failures → retry up to 3 times

4. Test cases:
   - Save 100 labels successfully
   - Save 10,000 labels in batch
   - Handle duplicate transaction_ids
   - Rollback on database error

**Acceptance Criteria:**
- Labels persist to database
- Audit fields populated correctly
- No data loss or corruption
- Performance: >1000 labels/second

---

### WEEK 1 CONTINUED: Configuration, API, and Human Review

#### P01-008: Add AML-Specific Configuration to settings
**Category:** Configuration Management
**Effort:** 2 hours
**Dependencies:** None (standalone)
**Blocks:** P01-004, P01-009, P01-016

**Description:**
Extend `src/core/config.py` with AML-specific environment variables and defaults.

**Current Config (src/core/config.py):**
```python
class Settings:
    DATABASE_URL: str
    STRIPE_API_KEY: str
    OPENAI_API_KEY: str
    # ... other settings
```

**New Config:**
```python
class Settings:
    # ... existing

    # AML Service Configuration
    AML_LABELING_MODEL: str = "gpt-4o"  # Model for AML labeling
    AML_LABELING_TEMPERATURE: float = 0.2  # Lower = more consistent
    AML_CONFIDENCE_THRESHOLD: float = 0.70  # Cohen's Kappa threshold for expert review

    # Expert Review Configuration
    EXPERT_REVIEWER_IDS: list[str] = ["expert1", "expert2", "expert3"]
    EXPERT_REVIEW_TIMEOUT_HOURS: int = 24

    # Regulatory Standards
    REGULATORY_STANDARD_VERSION: str = "FATF_2022_v2.1"
    LABELING_METHODOLOGY_VERSION: str = "DF_AML_v1.0"

    # Audit Configuration
    AUDIT_REPORT_FORMAT: str = "json"  # json or pdf
    AUDIT_REPORT_INCLUDE_REASONING: bool = True
    AUDIT_REPORT_INCLUDE_REFERENCES: bool = True

    # Stripe Billing (AML-specific)
    STRIPE_METER_ID_AML: str = "aml_transactions"
    AML_PRICE_PER_TRANSACTION: float = 0.012

    # Prefect Configuration
    PREFECT_AML_FLOW_NAME: str = "aml_labeling_flow"
    PREFECT_WORKER_CONCURRENCY: int = 5
```

**Deliverables:**
1. Update `src/core/config.py`:
   - Add all AML configuration variables with defaults
   - Add validation (price must be > 0, threshold must be 0-1, etc.)
   - Add docstrings explaining each setting

2. Update `.env.example`:
   - Document all new AML environment variables
   - Provide example values

3. Add to deployment documentation:
   - How to configure for different regulatory standards
   - How to adjust confidence threshold
   - How to add/remove expert reviewers

**Acceptance Criteria:**
- All settings have sensible defaults
- Settings load from environment variables
- Validation catches invalid values
- Documentation clear for operations team

---

#### P01-009: Extend AI Service for Structured AML Output
**Category:** Service Enhancement
**Effort:** 3 hours
**Dependencies:** P01-008 (need AML config)
**Blocks:** P01-004 (needed before use)

**Description:**
Extend `src/services/ai_service.py` to support structured output parsing for AML labels.

**Current AI Service:**
```python
class AIService:
    def completion(prompt, model, temperature, max_tokens):
        # Returns: AIResponse(content, usage, model, cost)
        # content is raw text - caller parses JSON
```

**Enhancements:**
1. Add structured output support:
   ```python
   def aml_completion(
       self,
       transaction_data: dict,
       model: str = None,
       temperature: float = None
   ) -> AMLLabel:
       """
       Call AI service with AML-specific prompt.

       Returns:
           AMLLabel with: risk_level, typology, regulatory_flag, reasoning, confidence
       """
       # 1. Build AML prompt from template
       # 2. Call completion()
       # 3. Parse JSON response
       # 4. Validate response structure
       # 5. Handle errors (AI returns invalid JSON, missing fields)
       # 6. Return AMLLabel object
   ```

2. Response validation:
   - Ensure all required fields present
   - Validate risk_level is 1-5
   - Validate typology is valid enum
   - Return validation errors for debugging

3. Error handling:
   - Parse errors → log and retry once
   - Invalid typology → log warning, use "unknown"
   - Missing fields → raise exception (escalate to expert)
   - Confidence < 0.5 → mark as low_confidence for review

4. Cost tracking:
   - Track cost per AML completion
   - Aggregate for job billing

**Deliverables:**
1. Add `aml_completion()` method to `AIService` in `src/services/ai_service.py`
2. Add response validation in `src/core/validation.py`
3. Update `src/services/ai_service.py` to handle structured output
4. Test with sample transactions

**Acceptance Criteria:**
- AML completions return valid AMLLabel objects
- Response validation catches malformed responses
- Cost tracking works for billing
- Error handling is robust

---

#### P01-010: Update Job Tracking Service for AML Results
**Category:** API & Service Layer
**Effort:** 3 hours
**Dependencies:** P01-003, P01-006, P01-007 (need models, flow, database)
**Blocks:** P01-011, P01-014

**Description:**
Extend `src/application/job_tracking_service.py` to handle AML-specific job completion with audit report storage.

**Current Service:**
```python
class JobTrackingService:
    def mark_complete(job_id, results_url):
        # Updates job status to COMPLETE
        # Stores results_url
```

**Enhancements:**
1. Add AML result fields:
   ```python
   def mark_complete(
       self,
       job_id: UUID,
       results_url: str,
       audit_report_url: str,  # NEW
       aml_labels_count: int,  # NEW (for reporting)
       high_risk_count: int,   # NEW
       methodology_version: str  # NEW
   ) -> ProcessingJob:
       """Mark job as complete with AML-specific metadata."""
   ```

2. Database updates:
   - Add columns to `processing_jobs` table:
     - `audit_report_url`
     - `aml_labels_count`
     - `high_risk_count`
     - `methodology_version`
   - (Migration: P01-002 should include these)

3. Reporting metrics:
   - Total labels created
   - High-risk (level 4-5) count
   - Risk distribution (counts by level)
   - Top flagged typologies
   - Average confidence score

4. Methods:
   ```python
   def get_aml_job_metrics(job_id: UUID) -> dict:
       """Get AML-specific metrics for completed job."""
       # Returns: {
       #     "total_labels": 1340,
       #     "high_risk_count": 42,
       #     "risk_distribution": {1: 400, 2: 600, 3: 200, 4: 120, 5: 20},
       #     "top_typologies": {"structuring": 45, "mule_activity": 30, ...},
       #     "avg_confidence": 0.88
       # }
   ```

**Deliverables:**
1. Update `src/application/job_tracking_service.py`:
   - Extend `mark_complete()` with AML fields
   - Add `get_aml_job_metrics()` method
   - Add validation (counts must be >= 0)

2. Update domain model in `src/domain/processing_job/aggregate.py`:
   - Add AML-specific fields to Job entity

3. Test cases:
   - Complete job with AML metadata
   - Retrieve AML metrics
   - Validate counts

**Acceptance Criteria:**
- Job completion includes AML metadata
- Metrics calculated correctly
- Data persists and retrieves correctly

---

#### P01-011: Update Job API Contracts for AML
**Category:** API Models
**Effort:** 2 hours
**Dependencies:** P01-010 (need updated job fields)
**Blocks:** P01-012, P01-013

**Description:**
Update Pydantic contracts in `src/api/v1/jobs/contracts.py` to include AML-specific response fields.

**Current Contract:**
```python
class JobStatusContract(BaseModel):
    job_id: UUID
    tenant_id: UUID
    status: str
    file_name: str
    file_size: int
    estimated_cost: float
    actual_cost: float
    result_records: int
    result_url: str
    error_message: str = ""
```

**Updated Contract:**
```python
class JobStatusContract(BaseModel):
    # ... existing fields

    # NEW AML-specific fields
    audit_report_url: str = None
    aml_labels_count: int = 0
    high_risk_count: int = 0
    methodology_version: str = ""

    # AML metrics (optional, only if job complete)
    aml_metrics: AMLMetricsContract = None

class AMLMetricsContract(BaseModel):
    total_labels: int
    high_risk_count: int
    risk_distribution: dict[int, int]  # {1: count, 2: count, ...}
    top_typologies: dict[str, int]  # {typology: count, ...}
    avg_confidence: float

class AMLTransactionLabelContract(BaseModel):
    transaction_id: str
    aml_risk_level: int
    aml_typology: str
    regulatory_flag: str
    expert_reasoning: str
    confidence_score: float
    reviewed_by: list[str]
    reviewed_at: datetime = None
```

**Deliverables:**
1. Update `src/api/v1/jobs/contracts.py`:
   - Add AML-specific fields to JobStatusContract
   - Add AMLMetricsContract
   - Add AMLTransactionLabelContract

2. Update serialization:
   - Job → JobStatusContract (include AML fields if present)
   - AMLLabel → AMLTransactionLabelContract

3. API documentation:
   - Document new fields
   - Explain what each field means
   - Provide example responses

**Acceptance Criteria:**
- Contracts validate properly
- Serialization works for all field combinations
- API documentation updated

---

#### P01-012: Update Job Tracking API Endpoint to Return AML Data
**Category:** API Endpoint
**Effort:** 2 hours
**Dependencies:** P01-011 (need updated contracts)
**Blocks:** P01-013

**Description:**
Update `src/api/v1/jobs/router.py:get_job_status()` endpoint to include AML-specific response data.

**Current Endpoint:**
```python
@router.get("/jobs/{job_id}")
async def get_job_status(job_id: UUID, current_tenant: Tenant = Depends(get_current_tenant)):
    job = job_service.get_job(job_id)
    return job_to_contract(job)  # Returns JobStatusContract
```

**Updates:**
1. Modify `job_to_contract()` helper function:
   - If job.status == COMPLETE, populate AML fields
   - Call `job_service.get_aml_job_metrics(job_id)` for metrics
   - Include audit_report_url from job record

2. Test cases:
   - GET /api/v1/jobs/{non_aml_job} → returns standard fields
   - GET /api/v1/jobs/{aml_job} → returns AML fields populated
   - GET /api/v1/jobs/{pending_job} → returns partial data

**Deliverables:**
1. Update `src/api/v1/jobs/router.py`:
   - Modify `job_to_contract()` helper
   - Handle AML-specific response building

2. Test cases for API responses

**Acceptance Criteria:**
- API returns correct response structure
- All AML fields populated for complete jobs
- API documentation accurate

---

#### P01-013: Create Results Download Endpoint (Fix Current Issue)
**Category:** API Endpoint
**Effort:** 3 hours
**Dependencies:** P01-003, P01-007, P01-011 (need models, saved labels, contracts)
**Blocks:** None (but needed for customer experience)

**Description:**
Fix the current issue where `GET /api/v1/jobs/{job_id}/results` returns 0 records. Implement proper CSV download for AML labels.

**Current Issue (from test_results_final2.log):**
```
📥 Stage 4: Results Download
   📥 Downloading results via GET /api/v1/jobs/{job_id}/results
      ✓ Downloaded 0 records
```

**Root Cause:**
- `save_to_database()` in ingestion.py doesn't return results
- Results endpoint queries database but finds nothing (or can't deserialize)

**Solution:**

1. Update `download_results()` endpoint in `src/api/v1/jobs/router.py`:
   ```python
   @router.get("/jobs/{job_id}/results")
   async def download_results(
       job_id: UUID,
       current_tenant: Tenant = Depends(get_current_tenant)
   ):
       job = job_service.get_job_or_fail(job_id)

       # NEW: Query AML labels from database
       labels = db_session.query(AMLTransactionLabel).filter(
           AMLTransactionLabel.job_id == job_id,
           AMLTransactionLabel.tenant_id == current_tenant.id
       ).all()

       if not labels:
           raise HTTPException(status_code=404, detail="No results found")

       # Convert to CSV format
       csv_content = self._labels_to_csv(labels)

       # Return as downloadable file
       return StreamingResponse(
           BytesIO(csv_content.encode()),
           media_type="text/csv",
           headers={"Content-Disposition": f"attachment; filename=aml_labels_{job_id}.csv"}
       )
   ```

2. Implement CSV conversion:
   ```python
   def _labels_to_csv(self, labels: list[AMLTransactionLabel]) -> str:
       """Convert AML labels to CSV format."""
       output = StringIO()
       writer = csv.DictWriter(output, fieldnames=[
           'transaction_id',
           'aml_risk_level',
           'aml_typology',
           'regulatory_flag',
           'expert_reasoning',
           'confidence_score',
           'reviewed_by',
           'reviewed_at'
       ])

       writer.writeheader()
       for label in labels:
           writer.writerow(label.to_csv_row())

       return output.getvalue()
   ```

3. Test cases:
   - Download 0 labels → 404 error
   - Download 100 labels → valid CSV returned
   - CSV has correct columns and data
   - CSV can be imported to Excel/pandas

4. Add to audit trail:
   - Log when results downloaded
   - Track download timestamp, user, IP

**Deliverables:**
1. Fix `download_results()` in `src/api/v1/jobs/router.py`
2. Implement CSV conversion method
3. Add tests for various download scenarios
4. Update API documentation

**Acceptance Criteria:**
- Results endpoint returns CSV with labeled transactions
- CSV format matches specification
- Test harness shows >0 records downloaded
- API documentation updated

---

### WEEK 2: Human Review, Audit Reports, and Testing

#### P01-014: Implement Label Studio Integration for Expert Review (Optional MVP)
**Category:** External Integration
**Effort:** 6 hours (or 2 hours if skipped for MVP)
**Dependencies:** P01-006, P01-007 (need flow and labeled data)
**Blocks:** P01-015

**Status:** OPTIONAL FOR MVP
- If included: Enables expert annotation of low-confidence labels
- If skipped: Use simple database flag for manual expert review

**Description:**
Integrate with Label Studio (open-source annotation platform) to support expert review of low-confidence transaction labels.

**MVP Alternative (2 hours):**
- Skip Label Studio integration
- Create simple dashboard table to show low-confidence labels
- Expert reviews labels via web UI
- Store review results back to database

**Full Implementation (6 hours):**
1. Label Studio project setup:
   - Create project template for AML transaction review
   - Configure labeling interface to show:
     - AI-suggested label
     - AI reasoning
     - Customer data (sanitized)
   - Allow expert to:
     - Approve AI label
     - Change label + provide new reasoning
     - Mark as ambiguous (needs more data)

2. Integration code:
   - New file: `src/services/label_studio_service.py`
   - Send low-confidence labels to Label Studio
   - Webhook to receive expert reviews
   - Update labels with expert feedback

3. Workflow:
   - During ingestion: Labels with confidence < 0.70 marked for review
   - Send to Label Studio: Create task in project
   - Expert reviews: Updates label, provides feedback
   - Webhook receives: Updates aml_transaction_label with expert decision
   - Recalculate: Cohen's Kappa with expert + AI agreement

**Deliverables (if included):**
1. Label Studio project configuration
2. Label Studio service integration
3. Webhook handler for expert reviews
4. Database update logic from expert feedback

**Decision Point:**
- **For MVP:** Skip (2 hours saved, use database flag instead)
- **For V1.1:** Implement full Label Studio integration

---

#### P01-015: Generate Audit Report (Compliance Documentation)
**Category:** Reporting & Compliance
**Effort:** 5 hours
**Dependencies:** P01-003, P01-006, P01-007 (need models, flow, labels)
**Blocks:** P01-020

**Description:**
Implement audit report generation that produces compliance documentation customers can defend to regulators.

**Report Contents:**

1. **Executive Summary**
   - Number of transactions reviewed
   - Date range
   - Regulatory standards applied (FATF, FinCEN, COAF, AMLA)
   - Methodology version
   - Overall risk distribution

2. **Methodology**
   - How labels were generated (AI + expert review)
   - Which FATF typologies were assessed
   - Cohen's Kappa threshold for human review (0.70)
   - Regulatory standards cited

3. **Results Summary**
   - Total transactions: 1,340
   - High-risk (level 4-5): 42 (3.1%)
   - Risk distribution chart
   - Top flagged typologies
   - Average confidence score

4. **Regulatory Alignment**
   - Compliance with FATF R.10 (ML/TF typologies)
   - FinCEN SAR guidance reference
   - COAF 24-hour reporting timeline
   - AMLA readiness

5. **Quality Metrics**
   - Inter-rater agreement (Cohen's Kappa): 0.88 average
   - AI confidence: 0.92 average
   - Expert review rate: 5.2% (70 transactions)
   - Consensus rate: 94.3% (experts agreed with AI)

6. **Data Integrity**
   - Hash verification of results file
   - Timestamp of generation
   - Signed by Data Foundry (optional - future: digital signatures)

7. **Appendix**
   - Detailed regulatory references (links to FinCEN, COAF, AMLA, FATF docs)
   - Glossary of AML terms
   - Sample labeled records (with customer data redacted)

**Deliverables:**

1. New file: `src/core/audit_report_generator.py`
   ```python
   class AuditReportGenerator:
       def generate_report(
           self,
           job_id: UUID,
           labels: list[AMLTransactionLabel],
           format: str = "json"  # json or pdf
       ) -> dict | bytes:
           """Generate audit report in requested format."""

       def _calculate_metrics(labels) -> dict:
           """Calculate quality metrics from labels."""

       def _build_regulatory_section(labels) -> str:
           """Build regulatory compliance section."""

       def _to_json(self) -> dict:
           """Convert report to JSON."""

       def _to_pdf(self) -> bytes:
           """Convert report to PDF (using reportlab)."""
   ```

2. New file: `src/tasks/audit_report_task.py`
   ```python
   @task
   def generate_audit_report(
       job_id: UUID,
       labels: list[AMLTransactionLabel],
       format: str = "json"
   ) -> tuple[str, str]:  # (report_url, report_hash)
       """Prefect task to generate audit report."""
       generator = AuditReportGenerator()
       report = generator.generate_report(job_id, labels, format)

       # Save to storage
       url = storage_service.upload(f"audit_{job_id}.{format}", report)

       # Calculate hash for integrity verification
       hash = hashlib.sha256(report).hexdigest()

       return url, hash
   ```

3. Integration into `data_ingestion_flow()`:
   - Add `generate_audit_report()` task before job completion
   - Pass report_url to `job_service.mark_complete()`

4. Dependencies:
   - `reportlab` (for PDF generation)
   - `plotly` (for charts if included)

5. Test cases:
   - Generate JSON report
   - Generate PDF report
   - Verify all sections present
   - Verify metrics calculated correctly
   - Hash verification works

**Acceptance Criteria:**
- Report includes all required sections
- Metrics are accurate
- Report is professionally formatted
- Hash verification works
- Test harness shows report generated

---

#### P01-016: Create Regulatory Reference API Endpoint
**Category:** API Endpoint
**Effort:** 2 hours
**Dependencies:** P01-008 (need config), and REGULATORY_REFERENCE_AML_SERVICE.md
**Blocks:** None (informational endpoint)

**Description:**
Create API endpoint that returns regulatory guidance and references relevant to AML labeling.

**Endpoint Design:**

```python
@router.get("/api/v1/regulatory-context/{context_type}")
async def get_regulatory_context(context_type: str):
    """
    Get regulatory guidance context for AML labeling.

    context_type options:
    - "fatf" → FATF R.10 typologies and definitions
    - "fincen" → FinCEN SAR requirements and FAQs
    - "coaf" → Brazil COAF requirements
    - "amla" → EU AMLA requirements
    - "full" → All regulatory standards
    """
    # Returns: {
    #     "standard": "FATF",
    #     "version": "2022",
    #     "typologies": [{
    #         "name": "Structuring",
    #         "description": "Breaking down funds to avoid reporting...",
    #         "indicators": ["Multiple small transfers", "Below reporting threshold"],
    #         "references": ["FATF R.10", "FinCEN SAR FAQ Oct 2025"]
    #     }],
    #     "reporting_timelines": {...},
    #     "penalties": {...},
    #     "last_updated": "2025-12-29"
    # }
```

**Deliverables:**

1. New file: `src/api/v1/regulatory/router.py`
   - Endpoints for regulatory guidance
   - Load regulatory data from REGULATORY_REFERENCE_AML_SERVICE.md
   - Cache responses (regulatory data changes rarely)

2. New file: `src/core/regulatory_context.py`
   - Data structures for regulatory standards
   - Helper functions to format regulatory info
   - Caching layer

3. Integration:
   - Include regulatory context in audit reports
   - Reference in AML labeling prompts
   - Available to frontend for customer education

4. Test cases:
   - GET /api/v1/regulatory-context/fatf → returns FATF guidance
   - GET /api/v1/regulatory-context/full → returns all standards
   - Cache works properly

**Acceptance Criteria:**
- Endpoint returns valid regulatory context
- Data matches REGULATORY_REFERENCE_AML_SERVICE.md
- Caching works
- Documentation complete

---

#### P01-017: Implement Edge Case Consultation Workflow (Optional for MVP)
**Category:** User Workflow
**Effort:** 4 hours (or skip for MVP)
**Dependencies:** P01-003, P01-011 (need models and contracts)
**Blocks:** None

**Status:** OPTIONAL FOR MVP
- If included: Customers can ask questions about specific labels
- If skipped: Built into V1.1

**Description:**
Implement workflow for customers to request expert consultation on ambiguous/edge case transactions.

**MVP Alternative (Skip):**
- Defer to V1.1
- Focus on core labeling and audit reports

**Full Implementation:**

1. API Endpoint:
   ```python
   @router.post("/api/v1/jobs/{job_id}/consultation-request")
   async def request_consultation(
       job_id: UUID,
       request: ConsultationRequest  # {transaction_id, question, context}
   ):
       """Request expert consultation on a specific transaction."""
       # Create consultation task
       # Expert reviews and responds
       # Response includes regulatory guidance
   ```

2. Consultation workflow:
   - Customer submits question about transaction
   - Assigned to expert
   - Expert provides guidance (2-hour SLA)
   - Response includes regulatory reasoning
   - Consultation logged in audit trail

3. Database:
   - New table: `expert_consultations`
   - Fields: job_id, transaction_id, question, expert_response, created_at, resolved_at

**Decision Point:**
- **For MVP:** Skip (save 4 hours)
- **For V1.1:** Implement consultation workflow

---

#### P01-018: Write Unit Tests for AML Labeling
**Category:** Testing
**Effort:** 6 hours
**Dependencies:** P01-004, P01-005 (need labeling and agreement code)
**Blocks:** P01-021

**Description:**
Comprehensive unit tests for AML-specific processing logic.

**Test Scope:**

1. **AML Labeling Tests** (2 hours):
   - Test with structuring pattern transaction → expect risk_level=4, typology="structuring"
   - Test with mule activity pattern → expect typology="mule_activity"
   - Test with sanctions evasion → expect flag="fin_cen_sars"
   - Test with normal transaction → expect risk_level=1
   - Test with ambiguous transaction → expect confidence < 0.70
   - Edge cases: negative amount, invalid country, missing fields

2. **Cohen's Kappa Tests** (1.5 hours):
   - Perfect agreement (Kappa = 1.0)
   - Good agreement (Kappa = 0.85)
   - Acceptable agreement (Kappa = 0.75)
   - Poor agreement (Kappa = 0.40)
   - No agreement (Kappa = 0)
   - Handling edge cases

3. **ORM Model Tests** (1 hour):
   - Create AMLTransactionLabel record
   - Validate constraints (risk_level 1-5)
   - Serialize to CSV row
   - Retrieve from database

4. **Integration Tests** (1.5 hours):
   - End-to-end: extract → validate → label → save
   - Verify flow orchestration
   - Verify database persistence
   - Performance: 1000 transactions in acceptable time

**Deliverables:**

1. New file: `tests/test_aml_labeling.py`
   - Unit tests for labeling logic

2. New file: `tests/test_cohen_kappa.py`
   - Tests for inter-rater agreement calculation

3. New file: `tests/test_aml_models.py`
   - Tests for ORM models

4. Update `tests/test_tasks_integration.py`
   - Add AML flow integration tests

**Acceptance Criteria:**
- Test coverage >90% for AML code
- All tests pass
- Performance tests pass (1000+ transactions)

---

#### P01-019: Write Integration Tests for Full AML Pipeline
**Category:** Testing
**Effort:** 5 hours
**Dependencies:** P01-006, P01-010, P01-013 (need full pipeline)
**Blocks:** P01-021

**Description:**
Integration tests validating the entire AML labeling pipeline from upload to results download.

**Test Scenarios:**

1. **Full Pipeline Test** (2 hours):
   - Upload CSV with 100 test transactions
   - Poll job status (PENDING → PROCESSING → COMPLETE)
   - Verify processing time < 5 minutes
   - Download results → verify 100 records with labels
   - Verify audit report generated

2. **Multi-Vertical Test** (1 hour):
   - Test with fintech-specific transaction types
   - Test with varying transaction sizes
   - Test with mixed risk levels

3. **Error Handling Test** (1 hour):
   - Invalid CSV format → appropriate error
   - Missing required columns → appropriate error
   - Database error → retry and recover
   - Timeout → graceful degradation

4. **Regulatory Compliance Test** (1 hour):
   - Audit report includes FATF references
   - Labels align with FinCEN guidance
   - COAF reporting timeline compliance
   - AMLA readiness verification

**Deliverables:**

1. Update `test_harness_phase2_api.py`:
   - Add AML-specific assertions
   - Verify labels present in results
   - Verify confidence scores present
   - Verify audit report generated
   - Verify Cohen's Kappa calculation

2. New file: `tests/test_aml_end_to_end.py`:
   - Full pipeline tests
   - Multiple transaction types
   - Error scenarios

3. Test data files:
   - `tests/fixtures/aml_test_transactions.csv`
   - Multiple scenarios: structuring, mule activity, normal transactions

**Acceptance Criteria:**
- Full pipeline tests pass
- Test harness shows >0 records downloaded
- Audit report present in results
- All error scenarios handled

---

#### P01-020: Create Audit & Compliance Dashboard (Optional for MVP)
**Category:** Frontend & Visualization
**Effort:** 6 hours (or skip for MVP)
**Dependencies:** P01-015, P01-010 (need reports and metrics)
**Blocks:** None

**Status:** OPTIONAL FOR MVP
- If included: Beautiful dashboard showing AML results
- If skipped: CLI or API-only in MVP, UI in V1.1

**Description:**
Create web-based dashboard to visualize AML labeling results and compliance metrics.

**MVP Alternative (Skip):**
- Focus on API and CSV output
- Dashboard in V1.1

**Full Implementation:**

Dashboard Pages:

1. **Job Results Overview**
   - Total transactions processed
   - Risk level distribution (pie chart)
   - High-risk transactions count
   - Average confidence score
   - Processing time

2. **Risk Analysis**
   - Risk distribution (1-5 scale)
   - Top flagged typologies
   - Geographic risk heat map
   - Timeline of suspicious activity

3. **Compliance Status**
   - FATF alignment
   - FinCEN SAR readiness
   - COAF reporting status
   - AMLA compliance
   - Audit trail

4. **Quality Metrics**
   - Cohen's Kappa scores
   - AI confidence distribution
   - Expert review rate
   - Agreement rate

**Deliverables (if included):**

1. New frontend route: `/dashboard/{job_id}`
2. Chart components (using Plotly or Chart.js)
3. API integration (consume AML metrics endpoint)
4. Styling (match existing Data Foundry branding)

**Decision Point:**
- **For MVP:** Skip (save 6 hours)
- **For V1.1:** Implement dashboard

---

### WEEK 2 CONTINUED: Deployment & Go-to-Market

#### P01-021: Update Test Harness to Validate AML Service
**Category:** Testing Infrastructure
**Effort:** 4 hours
**Dependencies:** P01-013, P01-018, P01-019 (need results endpoint and tests)
**Blocks:** P01-025

**Description:**
Update test harness to validate AML-specific behavior and generate AML-focused test reports.

**Current Test Harness Status (from test_results_final2.log):**
- ✅ Uploads files
- ✅ Tracks job status
- ⚠️ Downloads 0 records (needs fix)
- ⚠️ No AML-specific assertions

**Updates:**

1. AML-Specific Validations:
   ```python
   def test_aml_service():
       # Upload fintech transaction data
       job_id = upload_aml_transactions("fintech_test_data.csv")

       # Track processing
       assert poll_job_status(job_id) == "complete"

       # Validate results
       results = download_results(job_id)

       # NEW: AML assertions
       assert len(results) > 0, "Should have labeled records"
       assert all(r['aml_risk_level'] in [1,2,3,4,5] for r in results)
       assert all(r['confidence_score'] >= 0 and r['confidence_score'] <= 1 for r in results)
       assert all(r['aml_typology'] in VALID_TYPOLOGIES for r in results)

       # Verify audit report
       audit_report = get_audit_report(job_id)
       assert audit_report is not None
       assert "FATF" in audit_report
       assert "methodology" in audit_report
   ```

2. New metrics:
   - Records downloaded (should match uploaded)
   - Confidence score distribution
   - Risk level distribution
   - Typology distribution
   - Processing time per 1000 transactions

3. Report improvements:
   - Generate AML-specific test report
   - Include labeling accuracy if test labels available
   - Performance metrics
   - Recommendation for production deployment

**Deliverables:**

1. Update `test_harness_phase2_api.py`:
   - Add AML test scenarios
   - Add AML assertions
   - Generate AML-specific report

2. New test data:
   - Fintech transactions: structuring patterns, normal transfers, suspicious activity
   - Expected labels for validation

3. Test report enhancements:
   - AML-specific metrics section
   - Pass/fail criteria for AML service
   - Performance benchmarks

**Acceptance Criteria:**
- Test harness validates AML labeling
- Results show >0 records downloaded
- Audit report present and valid
- Test report clearly indicates readiness

---

#### P01-022: Deploy AML Service to Staging Environment
**Category:** DevOps & Deployment
**Effort:** 3 hours
**Dependencies:** P01-001-P01-020 (need complete code)
**Blocks:** P01-023, P01-024

**Description:**
Deploy AML service to staging environment and validate all infrastructure.

**Deployment Checklist:**

1. **Database Setup:**
   - ✓ Run migrations (P01-002)
   - ✓ Verify tables created
   - ✓ Verify indexes created

2. **Application Setup:**
   - ✓ Build Docker image
   - ✓ Start FastAPI server
   - ✓ Start background worker
   - ✓ Connect to database
   - ✓ Verify environment variables loaded

3. **Service Validation:**
   - ✓ Health check endpoint responds
   - ✓ Upload endpoint accepts CSV files
   - ✓ Job tracking works
   - ✓ Background worker polls and processes jobs
   - ✓ Results download works

4. **External Services:**
   - ✓ OpenAI API connectivity
   - ✓ Stripe API connectivity
   - ✓ Redis connectivity (if used for caching)
   - ✓ Storage (R2 or local)

5. **Monitoring:**
   - ✓ Application logs visible
   - ✓ Error tracking configured
   - ✓ Performance metrics available
   - ✓ Database query logs available

**Deliverables:**

1. Staging deployment scripts:
   - Docker Compose configuration for staging
   - Environment variables file (.env.staging)
   - Migration runner script

2. Deployment documentation:
   - Step-by-step deployment guide
   - Rollback procedures
   - Troubleshooting guide

3. Health check script:
   - Validates all components working
   - Provides deployment readiness report

**Acceptance Criteria:**
- Service deploys without errors
- All endpoints respond correctly
- Database migrations run successfully
- Background worker processes jobs
- No critical errors in logs

---

#### P01-023: Run Full Integration Testing on Staging
**Category:** Quality Assurance
**Effort:** 4 hours
**Dependencies:** P01-021, P01-022 (need tests and staging deployment)
**Blocks:** P01-024

**Description:**
Execute comprehensive integration testing on staging environment to validate AML service before production.

**Test Execution Plan:**

1. **API Tests** (1 hour):
   - Test all endpoints
   - Test error handling
   - Test rate limiting
   - Test authentication

2. **AML Pipeline Tests** (2 hours):
   - Upload multiple test datasets
   - Verify processing completes
   - Validate result quality
   - Verify audit reports generated
   - Check performance (process 10,000 transactions)

3. **Data Integrity Tests** (1 hour):
   - Verify data persists correctly
   - Verify no data loss
   - Verify tenant isolation (cross-tenant data not visible)
   - Verify audit trail complete

**Deliverables:**

1. Test execution results:
   - PASS/FAIL for each test
   - Performance metrics
   - Issues/blockers identified

2. Go/No-Go decision document:
   - Readiness assessment
   - Known limitations
   - Recommendation for production

**Acceptance Criteria:**
- All critical tests pass
- No data loss or corruption
- Performance acceptable
- Audit trail complete

---

#### P01-024: Security & Compliance Review
**Category:** Security & Compliance
**Effort:** 3 hours
**Dependencies:** P01-022, P01-023 (need staging and tests)
**Blocks:** P01-025

**Description:**
Security audit of AML service code and infrastructure focusing on regulatory compliance.

**Security Review Checklist:**

1. **Data Security:**
   - ✓ Customer data encrypted at rest
   - ✓ Data encrypted in transit (HTTPS)
   - ✓ PII properly redacted
   - ✓ No customer data in logs

2. **Authentication & Authorization:**
   - ✓ JWT validation works
   - ✓ Tenant isolation enforced
   - ✓ API keys secured
   - ✓ Role-based access control (if applicable)

3. **Regulatory Compliance:**
   - ✓ FATF R.10 requirements met
   - ✓ FinCEN guidance followed
   - ✓ COAF 24-hour reporting compatible (infrastructure ready)
   - ✓ AMLA compliance documented
   - ✓ GDPR compliance for EU data

4. **Code Quality:**
   - ✓ No SQL injection vulnerabilities
   - ✓ No XSS vulnerabilities
   - ✓ No hardcoded secrets
   - ✓ Proper input validation

5. **Audit Trail:**
   - ✓ All actions logged
   - ✓ Audit trail immutable
   - ✓ Timestamp accuracy
   - ✓ User attribution correct

**Deliverables:**

1. Security audit report:
   - Findings and recommendations
   - Risk assessment
   - Remediation plan (if issues found)

2. Compliance documentation:
   - How service meets regulatory requirements
   - Audit-ready documentation
   - Customer-facing compliance summary

**Acceptance Criteria:**
- No critical security issues
- Regulatory requirements met
- Audit trail complete and accurate
- Ready for compliance review

---

#### P01-025: Create Production Deployment Plan
**Category:** Operations & Deployment
**Effort:** 2 hours
**Dependencies:** P01-024 (need security review)
**Blocks:** P01-026

**Description:**
Develop detailed plan for production deployment with rollback procedures.

**Deployment Plan Contents:**

1. **Pre-Deployment Checklist:**
   - Database backups created
   - Staging testing complete
   - Security review passed
   - Performance validated
   - Documentation complete

2. **Deployment Sequence:**
   - Step 1: Backup production database
   - Step 2: Run migrations
   - Step 3: Deploy application
   - Step 4: Start background worker
   - Step 5: Run health checks
   - Step 6: Monitor for 1 hour

3. **Rollback Plan:**
   - Rollback database migrations
   - Redeploy previous application version
   - Restart worker
   - Verify rollback successful

4. **Monitoring Plan:**
   - What metrics to watch
   - Error thresholds
   - Escalation procedures
   - Who to contact if issues

**Deliverables:**

1. Production deployment checklist
2. Step-by-step deployment guide
3. Rollback procedures
4. Monitoring and alerting setup
5. On-call runbook for incidents

**Acceptance Criteria:**
- Plan covers all critical steps
- Rollback procedure tested
- Monitoring configured
- Team trained on procedures

---

#### P01-026: Initial Production Deployment (or Soft Launch)
**Category:** Deployment
**Effort:** 2 hours
**Dependencies:** P01-025 (need deployment plan)
**Blocks:** P01-027

**Status:** Can do staged rollout:
- **Option A:** Full production deploy (2 hours)
- **Option B:** Soft launch to 1-2 early adopters (3 hours, more validation)

**Description:**
Deploy AML service to production using approved deployment plan.

**Deployment Execution:**

1. Pre-deployment (30 min):
   - Backup database
   - Verify staging tests passing
   - Security review complete
   - Get sign-off

2. Deployment (1 hour):
   - Execute deployment steps
   - Run health checks
   - Monitor metrics
   - Verify no errors in logs

3. Post-deployment (30 min):
   - Monitor for issues
   - Alert team if problems
   - Document actual vs planned times
   - Celebrate! 🎉

**Deliverables:**

1. Deployment execution log:
   - When each step completed
   - Any issues and resolutions
   - Performance metrics
   - Final status

2. Post-deployment report:
   - What went well
   - What could be improved
   - Recommendations for next deployment

**Acceptance Criteria:**
- Service deployed to production
- All endpoints responding
- No critical errors
- Performance acceptable

---

#### P01-027: Customer Onboarding Materials
**Category:** Marketing & Documentation
**Effort:** 4 hours
**Dependencies:** P01-026 (need working service)
**Blocks:** P01-028

**Description:**
Create customer-facing documentation for early adopters.

**Deliverables:**

1. **Getting Started Guide** (1 hour):
   - What is Data Foundry AML Service?
   - How to sign up
   - How to upload first dataset
   - How to interpret results
   - FAQ

2. **API Documentation** (1 hour):
   - Upload endpoint
   - Job tracking endpoint
   - Results download endpoint
   - Error codes and responses
   - Code examples (Python, cURL, JavaScript)

3. **Case Study Template** (1 hour):
   - Problem statement (customer had)
   - How AML service solved it
   - Results (improved AML compliance, faster labeling, etc.)
   - Testimonial
   - Metrics achieved

4. **Regulatory Compliance Guide** (1 hour):
   - How labels are generated
   - FATF alignment
   - FinCEN SAR readiness
   - Audit defensibility
   - Regulatory references

**Deliverables:**

1. Getting Started Guide (markdown)
2. API Documentation (generated from OpenAPI/Swagger)
3. Case Study Template (markdown or Notion)
4. Compliance Guide (markdown)
5. Email template for outreach

**Acceptance Criteria:**
- Documentation is clear and customer-ready
- API docs are accurate
- Case study template is compelling
- Compliance guide satisfies regulatory concerns

---

#### P01-028: Early Adopter Outreach & Pilot Program Launch
**Category:** Go-to-Market
**Effort:** 3 hours
**Dependencies:** P01-027 (need documentation)
**Blocks:** None (final task)

**Description:**
Reach out to identified early adopters and launch pilot program.

**Pilot Program Design:**

1. **Target Customers:**
   - Fintech companies with 100k-5M monthly transactions
   - Series A+ funding
   - Moving to ML-based AML
   - Geographic: US, Brazil, EU focus

2. **Pilot Terms:**
   - Duration: 30-60 days
   - Volume: 10,000-100,000 transactions labeled
   - Pricing: 50% discount or free (build relationship)
   - Support: Direct access to team for questions
   - Feedback: Weekly check-ins, monthly review

3. **Success Criteria:**
   - Customer labels training data successfully
   - Uses labels to train ML model
   - Achieves regulatory defensibility
   - Willing to become reference customer

**Deliverables:**

1. **Outreach List** (1 hour):
   - 15-20 target fintech companies
   - Contact info, decision-maker, company size
   - Personalized pitch for each

2. **Pilot Program Agreement** (1 hour):
   - Terms and conditions
   - Service level expectations
   - Feedback requirements
   - Reference customer option

3. **Launch Communications** (1 hour):
   - Outreach email sequence
   - One-pager describing service
   - Pricing/pilot terms
   - Case study from internal validation

**Acceptance Criteria:**
- Outreach list finalized
- Pilot agreements prepared
- First 3-5 customers recruited
- Pilots scheduled to start

---

## Part 2: Dependency Matrix

```
P01-001 (Schema Design)
  ↓
P01-002 (Migrations) ←─────┬────────────────────────────┐
  ↓                        │                            │
P01-003 (ORM Models)       │                            │
  ↓                        ↓                            ↓
P01-004 (AML Labeling) ← P01-008 (Config) ← P01-009 (AI Service)
  ↓
P01-005 (Cohen's Kappa)
  ↓
P01-006 (Ingestion Flow)
  ↓
P01-007 (Save Labels)
  ↓
P01-010 (Job Tracking Service)
  ↓
P01-011 (API Contracts)
  ↓
P01-012 (Job Status Endpoint)
  ↓
P01-013 (Results Download) ← P01-015 (Audit Reports)
  ↓                         ↓
P01-016 (Regulatory API)    P01-014 (Label Studio - OPTIONAL)
  ↓
P01-018 (Unit Tests)
  ↓
P01-019 (Integration Tests)
  ↓
P01-021 (Test Harness Update)
  ↓
P01-022 (Staging Deployment)
  ↓
P01-023 (Integration Testing)
  ↓
P01-024 (Security Review)
  ↓
P01-025 (Production Plan)
  ↓
P01-026 (Production Deployment)
  ↓
P01-027 (Onboarding Materials)
  ↓
P01-028 (Early Adopter Outreach)
```

---

## Part 3: Execution Groups for Parallel Processing

### GROUP 1 - Foundation (No Dependencies)
Can execute immediately, in parallel:

1. **P01-001: AML Database Schema Design** (4h)
2. **P01-008: AML Configuration** (2h)

**Rationale:** Schema and config don't depend on any code; they're foundational.

### GROUP 2 - Infrastructure (Depends on GROUP 1)
Can execute after GROUP 1, in parallel:

1. **P01-002: Alembic Migrations** (3h) - depends on P01-001
2. **P01-003: ORM Models** (4h) - depends on P01-001, P01-002

**Rationale:** Migrations and models depend on schema design.

### GROUP 3 - Core Services (Depends on GROUP 2)
Can execute after GROUP 2, in parallel:

1. **P01-004: AML Labeling Task** (6h) - depends on P01-003, P01-008
2. **P01-009: AI Service Extension** (3h) - depends on P01-008
3. **P01-005: Cohen's Kappa Calculation** (4h) - depends on P01-003

**Rationale:** Labeling, AI service, and agreement calculation are independent.

### GROUP 4 - Orchestration (Depends on GROUP 3)
Can execute after GROUP 3, in parallel:

1. **P01-006: Ingestion Flow** (5h) - depends on P01-004, P01-005
2. **P01-007: Save Labels Task** (3h) - depends on P01-003, P01-006
3. **P01-010: Job Tracking Service** (3h) - depends on P01-003, P01-006, P01-007

**Rationale:** Flow, save task, and job service are independent after orchestration.

### GROUP 5 - API Layer (Depends on GROUP 4)
Can execute after GROUP 4, in parallel:

1. **P01-011: API Contracts** (2h) - depends on P01-010
2. **P01-012: Job Status Endpoint** (2h) - depends on P01-011
3. **P01-013: Results Download Endpoint** (3h) - depends on P01-003, P01-007, P01-011

**Rationale:** All three API modifications are independent.

### GROUP 6 - Reporting & Features (Depends on GROUP 5)
Can execute after GROUP 5, in parallel:

1. **P01-015: Audit Report Generation** (5h) - depends on P01-003, P01-006, P01-007
2. **P01-016: Regulatory API Endpoint** (2h) - depends on P01-008
3. **P01-014: Label Studio Integration** (6h - OPTIONAL) - depends on P01-006, P01-007

**Rationale:** Audit reports, regulatory API, and Label Studio are independent.

### GROUP 7 - Testing (Depends on GROUP 6)
Can execute after GROUP 6, in parallel:

1. **P01-018: Unit Tests** (6h) - depends on P01-004, P01-005
2. **P01-019: Integration Tests** (5h) - depends on P01-006, P01-010, P01-013
3. **P01-017: Edge Case Consultation** (4h - OPTIONAL) - depends on P01-003, P01-011

**Rationale:** Different test types are independent.

### GROUP 8 - Test Infrastructure (Depends on GROUP 7)
Can execute after GROUP 7:

1. **P01-021: Update Test Harness** (4h) - depends on P01-013, P01-018, P01-019

**Rationale:** Must wait for tests to exist before updating harness.

### GROUP 9 - Staging (Depends on GROUP 8)
Can execute after GROUP 8:

1. **P01-022: Deploy to Staging** (3h) - depends on P01-001-P01-020
2. **P01-023: Integration Testing on Staging** (4h) - depends on P01-021, P01-022
3. **P01-024: Security & Compliance Review** (3h) - depends on P01-022, P01-023

Can be parallel after all code/tests complete.

### GROUP 10 - Production (Depends on GROUP 9)
Sequential (critical path):

1. **P01-025: Production Deployment Plan** (2h) - depends on P01-024
2. **P01-026: Production Deployment** (2h) - depends on P01-025
3. **P01-027: Onboarding Materials** (4h) - depends on P01-026
4. **P01-028: Early Adopter Outreach** (3h) - depends on P01-027

---

## Part 4: Critical Path Analysis

**Shortest Path (Sequential):**
P01-001 → P01-002 → P01-003 → P01-004 → P01-005 → P01-006 → P01-007 → P01-010 → P01-011 → P01-012 → P01-013 → P01-015 → P01-021 → P01-022 → P01-023 → P01-024 → P01-025 → P01-026 → P01-027 → P01-028

**Critical Path Duration:**
- Estimated hours on critical path: 60-70 hours (sequential)
- Actual duration with parallelization: 25-35 hours (60% time savings)

---

## Part 5: Effort Summary by Category

| Category | Tasks | Hours | Notes |
|----------|-------|-------|-------|
| **Database & Migrations** | P01-001, P01-002 | 7h | Foundation work |
| **Core Processing Logic** | P01-003, P01-004, P01-005, P01-006, P01-007 | 22h | Most complex tasks |
| **Configuration** | P01-008 | 2h | Quick parallel work |
| **Services & APIs** | P01-009, P01-010, P01-011, P01-012, P01-013 | 13h | API integration |
| **Reporting & Features** | P01-015, P01-016, P01-014, P01-017 | 15h | 4 optional, 2 required |
| **Testing** | P01-018, P01-019, P01-021 | 15h | Critical for quality |
| **Deployment** | P01-022, P01-023, P01-024, P01-025, P01-026 | 14h | Critical path to production |
| **Go-to-Market** | P01-027, P01-028 | 7h | Final steps |
| **TOTAL (MVP)** | 22 required tasks | **65-70h** | Core AML service |
| **TOTAL (Full)** | 28 all tasks | **95-105h** | With all optional features |

---

## Part 6: Optional Tasks (Save Time if Needed)

| Task | Hours | Impact if Skipped |
|------|-------|-------------------|
| **P01-014: Label Studio** | 6h (4h for MVP) | No expert review UI; use database flag instead |
| **P01-017: Consultation** | 4h | Customers can't ask about edge cases; add in V1.1 |
| **P01-020: Dashboard** | 6h | No web visualization; API and CSV only for MVP |

**MVP Timeline:** 65-70 hours (skip optional tasks)
**Full Feature Timeline:** 95-105 hours (include all tasks)

---

**Document Version:** 1.0
**Created:** December 29, 2025
**Status:** Ready for execution assessment and task scheduling

