# AML Service - End-to-End Flow

## Overview

This document describes the **actual** end-to-end flow through the Data Foundry AML (Anti-Money Laundering) Service implementation, based on the real codebase. It covers the complete processing pipeline from transaction input to final AML classification and storage.

**Target Users:** Fintech compliance officers, AML analysts, financial crime investigators, developers

**Regulatory Framework:** FATF 40 Recommendations, FinCEN BSA/AML Guidelines, EU 6AMLD

---

## Architecture Summary

The AML Service is implemented as a **Prefect-based workflow** with the following key characteristics:

- **Workflow Engine:** Prefect (orchestrates tasks and flows)
- **Database:** PostgreSQL with async SQLAlchemy ORM
- **AI Service:** LiteLLM-integrated OpenAI completion
- **Processing Model:** Job-based async processing with state tracking
- **Entry Point:** `data_ingestion_flow()` in `/home/carlos/projects/data_foundry/data-foundry/src/tasks/ingestion.py`

**IMPORTANT:** The system is **NOT** REST API-driven in the current implementation. It's a **Prefect workflow** that can be invoked programmatically or via the Prefect UI/server.

---

## Primary Flow: AML Batch Processing

### Entry Point: `data_ingestion_flow()`

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/tasks/ingestion.py:2024`

```python
@flow(name="Data Foundry Ingestion Flow")
async def data_ingestion_flow(
    data_source: str = "sample_data",
    enable_validation: bool = True,
    enable_ai_labeling: bool = True,
    enable_pii_redaction: bool = True,
    enable_human_review: bool = True,
    enable_stripe_billing: bool = False,
    job_id: str | None = None,
    tenant_id: str | None = None,
):
```

### How to Invoke

The flow can be invoked in several ways:

#### 1. Direct Python Invocation (Development)

```python
from src.tasks.ingestion import data_ingestion_flow
import asyncio

# Run locally
result = asyncio.run(
    data_ingestion_flow(
        data_source="sample_data",
        enable_validation=True,
        enable_ai_labeling=True,
        enable_pii_redaction=True,
        job_id="job_abc123",
        tenant_id="tenant_001"
    )
)
```

#### 2. Prefect CLI (Production)

```bash
# Deploy as a Prefect deployment
prefect deploy --name "aml-batch-processing" \
    --param data_source="s3://transactions/batch_001.csv" \
    --param enable_validation=True \
    --param enable_ai_labeling=True \
    --param tenant_id="tenant_001"

# Trigger the deployment
prefect run --name "aml-batch-processing"
```

#### 3. Prefect Server/UI

Access via Prefect UI at `http://localhost:4200` (or configured URL)

---

## Complete Processing Flow

```
START: data_ingestion_flow() invoked
|
| Parameters:
|   - data_source: "sample_data" (or file path, S3 URI, etc.)
|   - enable_validation: True
|   - enable_ai_labeling: True
|   - enable_pii_redaction: True
|   - enable_human_review: True
|   - job_id: Optional UUID for job tracking
|   - tenant_id: Optional tenant identifier
|
v
[Step 1] Extract Data
|
| Function: extract_data(data_source)
| Location: ingestion.py:771
|
| Task Type: @task (synchronous)
|
| Returns: List[dict] - Raw transaction records
|
| Sample Record:
| {
|   "id": 1,
|   "name": "John Doe",
|   "email": "john@example.com",
|   "phone": "555-1234",
|   "tenant_id": "tenant_001",
|   "created_at": "2025-01-31T14:23:16Z"
| }
|
v
[Step 2] Data Validation (if enable_validation=True)
|
+--[2a] Schema Validation
|  |
|  | Function: validate_schema(raw_data)
|  | Location: ingestion.py:812
|  |
|  | Uses: DataQualityValidator from src.core.data_quality
|  |
|  | Validates:
|  |   - Required fields present
|  |   - Data types correct
|  |   - Value ranges valid
|  |
|  | Returns: (valid_records, invalid_records)
|  |
|  | Adds fields to each record:
|  |   - validation_is_valid: bool
|  |   - validation_quality_score: float
|  |   - validation_completeness_score: float
|  |   - validation_validity_score: float
|  |   - validation_errors: list[str]
|  |   - validation_warnings: list[str]
|  |   - validated_at: ISO timestamp
|
+--[2b] Duplicate Detection
|  |
|  | Function: check_duplicates(valid_data)
|  | Location: ingestion.py:1055
|  |
|  | Method: SHA-256 hash of record content
|  |
|  | Returns: (new_records, duplicate_records)
|  |
|  | Adds field:
|  |   - record_hash: str (SHA-256)
|
+--[2c] Quality Scoring
|  |
|  | Function: compute_quality_scores(new_data)
|  | Location: ingestion.py:1122
|  |
|  | Adds fields:
|  |   - data_quality_score: float
|  |   - completeness_score: float
|  |   - validity_score: float
|  |   - quality_scored_at: ISO timestamp
|
+--[2d] Quality Filtering
|  |
|  | Function: filter_low_quality(scored_data)
|  | Location: ingestion.py:1189
|  |
|  | Threshold: MIN_QUALITY_SCORE (from config)
|  |
|  | Returns: (high_quality_records, low_quality_records)
|
v
[Step 3] PII Redaction (if enable_pii_redaction=True)
|
| Function: apply_pii_redaction(data_for_processing)
| Location: ingestion.py:1255
|
| Uses: Microsoft Presidio (if installed)
|
| Fields Redacted:
|   - name
|   - email
|   - phone
|   - ssn
|   - notes
|
| Adds fields for each redacted field:
|   - {field}_redacted: bool
|   - pii_redaction_applied: bool
|
| NOTE: If Presidio not installed, returns data WITHOUT redaction
|       and sets: pii_redaction_skipped: True
|
v
[Step 4] AI Labeling
|
+--[Generic AI Labeling]
|  |
|  | Function: apply_ai_labeling(redacted_data)
|  | Location: ingestion.py:1342
|  |
|  | Task Type: @task (async)
|  |
|  | Uses: AIService from src.services.ai_service
|  |
|  | For each record:
|  |   - Builds prompt using build_safe_prompt() (prevents injection)
|  |   - Creates AIRequest with:
|  |       - prompt: str
|  |       - system_prompt: str
|  |       - temperature: float (from config)
|  |       - max_tokens: int
|  |       - response_format: "json"
|  |       - tenant_id: str
|  |       - use_cache: bool
|  |   - Calls: await ai_service.completion(request)
|  |   - Parses JSON response
|  |
|  | Adds fields to each record:
|  |   - ai_category: str
|  |   - ai_confidence: float
|  |   - ai_reasoning: str
|  |   - ai_model: str
|  |   - ai_processed_at: ISO timestamp
|  |   - ai_request_id: str
|  |   - ai_tokens_used: int
|  |   - ai_cost: str
|  |   - ai_processing_time_ms: int
|  |   - ai_fallback_used: bool
|  |   - ai_from_cache: bool
|  |   - provenance_metadata: str (JSON)
|  |   - processing_history: str (JSON)
|  |   - ai_error: str (if error occurred)
|
+--[AML-Specific Labeling] (ACTUAL IMPLEMENTATION)
|  |
|  | Function: apply_aml_labeling(data)
|  | Location: ingestion.py:140
|  |
|  | Task Type: @task (async)
|  |
|  | Uses: AIService.aml_completion() (or completion() fallback)
|  |
|  | For each record:
|  |   1. Build prompt: build_aml_labeling_prompt(record)
|  |      from src.core.prompts.aml_labeling_prompt
|  |
|  |   2. Create AIRequest:
|  |      - prompt: AML-formatted transaction data
|  |      - system_prompt: AML_SYSTEM_PROMPT (expert analyst role)
|  |      - temperature: 0.3 (lower for consistency)
|  |      - max_tokens: 500
|  |      - response_format: "json"
|  |      - use_cache: True
|  |
|  |   3. Call AI: await ai_service.aml_completion(request)
|  |
|  |   4. Parse JSON response
|  |
|  |   5. Validate response: validate_aml_response(ai_result)
|  |      Location: ingestion.py:64
|  |
|  |      Validates:
|  |      - risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
|  |      - typology in FATF_TYPOLOGIES
|  |      - confidence_score between 0-1
|  |      - reasoning length >= 50 chars
|  |
|  |   6. Determine expert review status:
|  |      IF risk_level == "CRITICAL":
|  |        - expert_review_status = "ESCALATED"
|  |        - requires_expert_review = True
|  |      ELIF confidence_score < 0.6:
|  |        - expert_review_status = "PENDING"
|  |        - requires_expert_review = True
|  |      ELSE:
|  |        - expert_review_status = "AGREED"
|  |        - requires_expert_review = False
|  |
|  |   7. Error handling:
|  |      - asyncio.TimeoutError:
|  |        - aml_error_type = "TIMEOUT"
|  |        - aml_retry_count += 1
|  |        - Max retries: 3
|  |        - After max retries: ESCALATED
|  |
|  |      - JSON parse error:
|  |        - aml_error_type = "PARSING"
|  |        - expert_review_status = "PENDING"
|  |
|  |      - Validation error:
|  |        - aml_error_type = "VALIDATION"
|  |        - expert_review_status = "PENDING"
|  |
|  |      - Other errors:
|  |        - aml_error_type = "SERVICE"
|  |        - expert_review_status = "ESCALATED"
|  |
|  | Adds fields to each record:
|  |   - aml_risk_level: str
|  |   - aml_typology: str
|  |   - aml_confidence_score: float
|  |   - aml_reasoning: str
|  |   - aml_regulatory_flags: list[str]
|  |   - aml_expert_review_status: str
|  |   - aml_requires_expert_review: bool
|  |   - aml_model: str
|  |   - aml_processed_at: ISO timestamp
|  |   - aml_request_id: str
|  |   - aml_tokens_used: int
|  |   - aml_cost: str
|  |   - aml_processing_time_ms: int
|  |   - aml_fallback_used: bool
|  |   - aml_from_cache: bool
|  |   - aml_error: str (if error)
|  |   - aml_error_type: str (if error)
|  |   - aml_retry_count: int (if retry)
|  |   - aml_retry_eligible: bool (if retry)
|
v
[Step 5] Human Review Routing
|
| Function: route_for_human_review(labeled_data)
| Location: ingestion.py:1556
|
| Two routing modes:
|
| 1. AML Mode (if kappa_score provided):
|    IF kappa_score >= 0.70 (threshold):
|      - auto_approved = all records
|    ELSE:
|      - human_review = all records
|
| 2. Legacy Mode (individual confidence):
|    IF confidence >= 0.6:
|      - auto_approved
|    ELSE:
|      - human_review
|
| Returns: (auto_approved_records, human_review_records)
|
v
[Step 6] Label Studio Integration (if enable_human_review=True)
|
| Function: send_to_label_studio(human_review)
| Location: ingestion.py:1653
|
| Condition: Only if human_review records exist AND
|            secure_label_studio_api_key() configured
|
| Uses: label_studio_sdk Client
|
| Creates tasks in Label Studio project:
|   - record_id
|   - original_data
|   - ai_category / ai_confidence / ai_reasoning
|
v
[Step 7] Database Persistence
|
+--[Generic Data Save]
|  |
|  | Function: save_to_database(data, table_name)
|  | Location: ingestion.py:1698
|  |
|  | Uses: dlt (Data Loading Tool) with PostgreSQL
|  |
|  | Tables:
|  |   - auto_approved_data
|  |   - human_review_queue
|
+--[AML Labels Save] (ACTUAL IMPLEMENTATION)
|  |
|  | Function: save_aml_labels_to_database(
|  |              labeled_records,
|  |              tenant_id,
|  |              job_id
|  |          )
|  | Location: ingestion.py:1737
|  |
|  | Task Type: @task (async)
|  |
|  | Uses:
|  |   - AMLLabelValidator (validation layer)
|  |   - AMLTransactionLabel (ORM model)
|  |   - DatabaseErrorHandler (error classification)
|  |   - DuplicateRecordHandler (duplicate handling)
|  |
|  | Process:
|  |   1. Validate each record using AMLLabelValidator
|  |      Location: src.core.aml_label_validator
|  |
|  |   2. Create AMLTransactionLabel ORM instance
|  |
|  |   3. Batch insert (100-500 records per batch)
|  |
|  |   4. Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING
|  |      on unique constraint: (transaction_id, tenant_id)
|  |
|  |   5. Commit per batch with rollback on error
|  |
|  | Returns metrics:
|  |   {
|  |     "total_saved": int,
|  |     "duplicates_skipped": int,
|  |     "validation_errors": int,
|  |     "errors": int,
|  |     "batches_processed": int,
|  |     "processing_time_ms": int,
|  |     "labels_per_second": float,
|  |     "error_details": list[dict]
|  |   }
|
v
[Step 8] Inter-Rater Agreement (Optional)
|
| Function: compute_inter_rater_agreement(
|              ai_labels,
|              expert_reviews
|          )
| Location: ingestion.py:392
|
| Task Type: @task (async)
|
| Uses: CohenKappaCalculator from src.core.agreement_calculator
|
| Calculates: Cohen's Kappa coefficient for AI vs expert agreement
|
| Returns:
| {
|   "kappa": float (0.0 - 1.0),
|   "confidence_level": str ("POOR"/"FAIR"/"MODERATE"/"SUBSTANTIAL"/"PERFECT"),
|   "is_sufficient": bool (kappa >= 0.70),
|   "sample_size": int,
|   "computed_at": ISO timestamp
| }
|
v
[Step 9] Audit Report Generation (Optional)
|
| Function: generate_audit_report(
|              job_id,
|              tenant_id,
|              labeled_data,
|              kappa_score
|          )
| Location: ingestion.py:530
|
| Task Type: @task (async)
|
| Uses: AuditReportGenerator from src.services.audit_report_generator
|
| Returns:
| {
|   "report_id": str,
|   "report_generated_at": ISO timestamp,
|   "job_id": str,
|   "tenant_id": str,
|   "total_transactions": int,
|   "aml_risk_distribution": dict,
|   "typology_distribution": dict,
|   "inter_rater_agreement": {
|     "kappa_score": float | None,
|     "confidence_level": str,
|     "available": bool
|   },
|   "expert_review_queue_size": int,
|   "regulatory_references": list[str],
|   "audit_trail": {
|     "methodology_version": str,
|     "generated_by": str,
|     "compliance_status": str
|   }
| }
|
v
[Step 10] Stripe Billing Reporting (if enable_stripe_billing=True)
|
| Function: report_usage_to_stripe(labeled_data, source)
| Location: ingestion.py:2304
|
| Task Type: @task (async)
|
| Uses:
|   - UsageCalculationService (calculate usage from records)
|   - StripeService (report meter events)
|
| Logic:
|   - Count AI labels (confidence >= 0.85)
|   - Count human audits (confidence < 0.85)
|   - Aggregate by tenant
|   - Report as meter events to Stripe
|
| Returns:
| {
|   "tenants_reported": int,
|   "total_ai_labels": int,
|   "total_human_audits": int,
|   "batch_id": str,
|   "successful_events": int,
|   "failed_events": int,
|   "status": str
| }
|
v
[Step 11] Job Status Update (if job_id provided)
|
+--[On Success]
|  |
|  | Function: _update_job_status_complete(job_id, result_records)
|  | Location: ingestion.py:2215
|  |
|  | Uses:
|  |   - JobTrackingService (application service)
|  |   - JobRepository (infrastructure repository)
|  |   - ProcessingJob (domain aggregate)
|  |
|  | Transition: PROCESSING -> COMPLETE
|  |
|  | Stores in job metadata:
|  |   - result_records: int
|  |   aml_results: {
|  |     risk_level_counts: dict,
|  |     inter_rater_agreement: float,
|  |     expert_review_count: int,
|  |     audit_report_url: str
|  |   }
|
+--[On Failure]
|  |
|  | Function: _update_job_status_failed(job_id, error_message)
|  | Location: ingestion.py:2259
|  |
|  | Transition: PROCESSING -> FAILED
|  |
|  | Stores: error_message in job
|
v
COMPLETE: Flow returns statistics dict
|
| {
|   "total_extracted": int,
|   "valid_records": int,
|   "invalid_records": int,
|   "new_records": int,
|   "duplicate_records": int,
|   "high_quality": int,
|   "low_quality": int,
|   "auto_approved": int,
|   "human_review": int,
|   "success": bool,
|   "stripe_billing": dict
| }
```

---

## Job Tracking System

### Job Lifecycle

```
CREATE
  |
  | JobTrackingService.create_job()
  |
  v
PENDING -> PROCESSING
  |
  | JobTrackingService.start_processing()
  |
  v
PROCESSING -> [COMPLETE / FAILED / CANCELLED]
```

### Job States

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/domain/processing_job/aggregate.py`

```python
class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### Job Repository

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/infrastructure/repositories/job_repository.py`

**ORM Model:** `/home/carlos/projects/data_foundry/data-foundry/src/models/processing_job.py`

**Database Table:** `processing_jobs`

**Key Fields:**
- id: UUID (primary key)
- tenant_id: str (foreign key to tenants table)
- status: JobStatus enum
- file_name: str
- file_size: int
- complexity_tier: str
- estimated_cost: Decimal
- actual_cost: Decimal
- result_records: int
- result_url: str
- retry_count: int
- metadata: JSONB (includes AML-specific results)
- created_at, updated_at, started_at, completed_at: timestamps

---

## AML Constants and Validation

### Risk Levels

**Location:** `ingestion.py:32`

```python
AML_RISK_LEVELS = frozenset([
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL"
])
```

### FATF Typologies

**Location:** `ingestion.py:35`

```python
FATF_TYPOLOGIES = frozenset([
    "ML",  # Money Laundering
    "TF",  # Terrorist Financing
    "PEP",  # Politically Exposed Persons
    "FRAUD",  # Financial Fraud
    "SANCTIONS",  # Sanctions Evasion
    "TAX_EVASION",  # Tax Evasion
    "BRIBERY",  # Bribery and Corruption
    "SMUGGLING",  # Trade-based ML
    "DRUG_TRAFFICKING",  # Drug proceeds
    "HUMAN_TRAFFICKING",  # Human trafficking proceeds
    "PROLIFERATION",  # WMD financing
    "CYBERCRIME",  # Cybercrime proceeds
    "ENVIRONMENTAL"  # Environmental crimes
])
```

### Expert Review Status

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_enums.py`

```python
class AMLExpertReviewStatus(Enum):
    PENDING = "pending"  # Awaiting human review
    AGREED = "agreed"  # AI and expert agree
    DISAGREED = "disagreed"  # AI and expert disagree
    ESCALATED = "escalated"  # Critical/high priority review
```

### Confidence Threshold

**Location:** `ingestion.py:53`

```python
AML_CONFIDENCE_THRESHOLD = 0.6
```

Records below this threshold require human review.

---

## AML Database Schema

### AML Transaction Labels Table

**ORM Model:** `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_transaction_label.py`

**Migration:** `/home/carlos/projects/data_foundry/data-foundry/alembic/versions/004_add_aml_audit_fields.py`

**Key Fields:**

```python
class AMLTransactionLabel(Base):
    __tablename__ = "aml_transaction_labels"

    # Primary keys
    id: UUID  # Primary key
    transaction_id: str  # Business key
    tenant_id: str  # Multi-tenancy

    # Job tracking
    job_id: str  # Reference to processing job
    version_id: int  # Methodology version

    # AML classification
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    typology: str  # FATF typology code
    confidence_score: float  # 0.0 - 1.0

    # Reasoning and audit
    ai_reasoning: str  # Detailed explanation (min 50 chars)
    regulatory_flags: JSONB  # Array of regulatory flags

    # Expert review
    expert_review_status: str  # PENDING, AGREED, DISAGREED, ESCALATED

    # Audit fields
    is_audit_ready: bool
    is_deleted: bool
    deleted_by: str | None
    deleted_at: datetime | None

    # Metadata
    created_at: datetime
    updated_at: datetime
    updated_by: str
```

### Unique Constraint

**Migration:** `004_add_aml_audit_fields.py`

```sql
ALTER TABLE aml_transaction_labels
ADD CONSTRAINT uq_transaction_tenant
UNIQUE (transaction_id, tenant_id);
```

This prevents duplicate labels for the same transaction within a tenant.

---

## Error Handling

### Error Types

**Location:** `ingestion.py:219-238`

```python
# Timeout errors
aml_error_type = "TIMEOUT"
aml_retry_count += 1
aml_retry_eligible = True  # until MAX_RETRIES (3) reached

# Parsing errors
aml_error_type = "PARSING"
expert_review_status = "PENDING"

# Validation errors
aml_error_type = "VALIDATION"
expert_review_status = "PENDING"

# Service errors
aml_error_type = "SERVICE"
expert_review_status = "ESCALATED"
```

### Retry Logic

**Location:** `ingestion.py:208-225`

```python
MAX_RETRIES = 3

if aml_retry_count < MAX_RETRIES:
    # Retry eligible
    aml_retry_eligible = True
else:
    # Escalate to human
    aml_retry_eligible = False
    expert_review_status = "ESCALATED"
```

---

## Inter-Rater Agreement (Cohen's Kappa)

### Calculator

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/core/agreement_calculator.py`

**Usage:**

```python
from src.core.agreement_calculator import CohenKappaCalculator

calculator = CohenKappaCalculator()

# Calculate agreement
kappa = calculator.calculate_agreement(
    ai_decisions=["HIGH", "MEDIUM", "LOW"],
    expert_decisions=["HIGH", "HIGH", "LOW"]
)  # Returns: 0.67

# Get confidence level
confidence = calculator.get_confidence_level(kappa)
# Returns: "SUBSTANTIAL"

# Check if sufficient
is_sufficient = calculator.is_agreement_sufficient(kappa)
# Returns: True if kappa >= 0.70
```

### Confidence Levels

- `kappa >= 0.81`: PERFECT
- `0.61 <= kappa < 0.81`: SUBSTANTIAL
- `0.41 <= kappa < 0.61`: MODERATE
- `0.21 <= kappa < 0.41`: FAIR
- `kappa < 0.21`: POOR

---

## Audit Report Generation

### Generator

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/services/audit_report_generator.py`

**Usage:**

```python
from src.services.audit_report_generator import AuditReportGenerator

generator = AuditReportGenerator()

report = generator.generate_report(
    job_data={"job_id": "job_abc123", "tenant_id": "tenant_001"},
    labels=labeled_transactions,
    kappa_score=0.85
)
```

### Report Structure

```json
{
  "report_id": "aml_report_job_abc123_20250131",
  "report_generated_at": "2025-01-31T14:23:16Z",
  "job_id": "job_abc123",
  "tenant_id": "tenant_001",
  "total_transactions": 150,
  "aml_risk_distribution": {
    "LOW": 80,
    "MEDIUM": 40,
    "HIGH": 25,
    "CRITICAL": 5
  },
  "typology_distribution": {
    "ML": 60,
    "TF": 10,
    "FRAUD": 30,
    "SANCTIONS": 5,
    ...
  },
  "inter_rater_agreement": {
    "kappa_score": 0.85,
    "confidence_level": "PERFECT",
    "available": true
  },
  "expert_review_queue_size": 27,
  "regulatory_references": [
    "FATF R.10 (ML/TF typologies)",
    "FinCEN SAR FAQ Oct 2025",
    "EU 6AMLD Directive 2024/1640"
  ],
  "audit_trail": {
    "methodology_version": "v1.0",
    "generated_by": "system",
    "compliance_status": "ready"
  }
}
```

---

## Configuration

### Environment Variables

**Location:** `/home/carlos/projects/data_foundry/data-foundry/src/core/config.py`

```python
# AI Service
PRIMARY_MODEL = "gpt-4o"
OPENAI_API_KEY = (from env)
OPENAI_TEMPERATURE = 0.3
AML_LABELING_MODEL = "gpt-4o"
AML_AI_CONFIDENCE_THRESHOLD = 0.6

# AML thresholds
AML_KAPPA_THRESHOLD = 0.70  # Cohen's Kappa for routing

# Data validation
ENABLE_DATA_VALIDATION = True
MIN_QUALITY_SCORE = 0.5

# PII redaction
ENABLE_PII_REDACTION = True

# A/B testing
ENABLE_AB_TESTING = False
AB_TEST_RATIO = 0.3

# Batch processing
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 500

# Label Studio
LABEL_STUDIO_URL = (from env)
LABEL_STUDIO_API_KEY = (from env)
LABEL_STUDIO_PROJECT_ID = (from env)

# Stripe billing
STRIPE_API_KEY = (from env)
STRIPE_SECRET_KEY = (from env)
```

---

## Testing

### Test Files

**Location:** `/home/carlos/projects/data_foundry/data-foundry/tests/tasks/`

- `test_ingestion.py` - Generic ingestion flow tests
- `test_ingestion_flow_p01_006.py` - AML-specific flow tests
- `test_ingestion_p01_006_integration.py` - Integration tests
- `test_save_aml_labels.py` - Database persistence tests

### Example Test

**Location:** `tests/tasks/test_ingestion_p01_006_integration.py`

```python
@pytest.mark.asyncio
async def test_aml_batch_processing():
    """Test complete AML batch processing flow"""

    # Arrange
    transactions = [
        {
            "transaction_id": "TXN-001",
            "amount": 50000.00,
            "sender_country": "KY",
            "receiver_country": "PA",
            "tenant_id": "tenant_001"
        },
        # ... more transactions
    ]

    # Act
    result = await data_ingestion_flow(
        data_source="test_data",
        enable_validation=True,
        enable_ai_labeling=True,
        enable_pii_redaction=True,
        job_id="test_job_001",
        tenant_id="tenant_001"
    )

    # Assert
    assert result["success"] is True
    assert result["total_extracted"] > 0
    assert result["auto_approved"] >= 0
    assert result["human_review"] >= 0
```

---

## Deployment

### Prefect Deployment

```bash
# Create deployment
prefect deploy src/tasks/ingestion.py:data_ingestion_flow \
    --name "aml-batch-processing" \
    --pool "aml-processing-pool" \
    --parameter default_enable_validation=True \
    --parameter default_enable_ai_labeling=True \
    --parameter default_enable_pii_redaction=True

# Schedule deployment (cron)
prefect deployment set-schedule \
    --name "aml-batch-processing" \
    --interval "3600"  # Every hour
```

### Worker Pool

```bash
# Start worker
prefect worker start --pool "aml-processing-pool" \
    --limit 10  # Max concurrent flows
```

---

## Monitoring

### Prefect UI

Access at: `http://localhost:4200`

**View:**
- Flow runs
- Task runs
- State transitions
- Logs
- Parameters
- Artifacts

### Job Tracking Queries

```python
from src.application.job_tracking_service import JobTrackingService
from src.infrastructure.repositories.job_repository import JobRepository
from src.database.connection import db_connection

async with db_connection.get_session() as session:
    job_repo = JobRepository(session)
    job_service = JobTrackingService(repo=job_repo)

    # Get job status
    job = await job_service.get_job("job_abc123")
    print(f"Status: {job.status}")
    print(f"Progress: {job.result_records} records")

    # Get AML metrics
    metrics = await job_service.get_aml_job_metrics("job_abc123")
    print(f"Risk distribution: {metrics['risk_distribution']}")
    print(f"Inter-rater agreement: {metrics['inter_rater_agreement']}")
```

---

## Key Differences from Documentation

### What DOES NOT Exist (Fictional in Original Doc):

1. **REST API Endpoints**
   - ❌ POST /api/v1/aml/classify (does not exist)
   - ❌ POST /api/v1/aml/classify-batch (does not exist)
   - ❌ GET /api/v1/aml/jobs/{job_id}/status (does not exist)
   - ❌ POST /api/v1/aml/query (does not exist)

2. **Direct CSV Upload via API**
   - ❌ File upload via multipart/form-data (does not exist)
   - ❌ Immediate HTTP 202 response (does not exist)

3. **Webhook Notifications**
   - ❌ Webhook URL parameter (does not exist)
   - ❌ POST to customer webhook (does not exist)

### What ACTUALLY Exists:

1. **Prefect Flow Entry Point**
   - ✅ `data_ingestion_flow()` function
   - ✅ Invoked via Python code or Prefect CLI/UI
   - ✅ Async flow with job tracking

2. **Job-Based Processing**
   - ✅ ProcessingJob aggregate with state machine
   - ✅ JobTrackingService for lifecycle management
   - ✅ PostgreSQL job repository

3. **AML-Specific Tasks**
   - ✅ `apply_aml_labeling()` - AML classification
   - ✅ `save_aml_labels_to_database()` - ORM persistence
   - ✅ `compute_inter_rater_agreement()` - Cohen's Kappa
   - ✅ `generate_audit_report()` - Regulatory reporting

4. **Data Pipeline**
   - ✅ Validation, duplicate detection, quality scoring
   - ✅ PII redaction (via Presidio)
   - ✅ Human review routing
   - ✅ Label Studio integration (optional)

---

## Summary

The AML Service is a **Prefect-based data processing pipeline**, NOT a REST API service.

**To Process Transactions:**
1. Prepare data (CSV, JSON, database query, etc.)
2. Invoke `data_ingestion_flow()` with parameters
3. Flow executes through defined tasks
4. Results stored in PostgreSQL
5. Job status tracked in `processing_jobs` table

**For Production:**
- Deploy as Prefect deployment
- Schedule via Prefect server
- Monitor via Prefect UI
- Scale via worker pools

---

**Document Version:** 2.0
**Created:** January 31, 2025
**Status:** Aligned with actual codebase
**Last Updated:** January 31, 2025
