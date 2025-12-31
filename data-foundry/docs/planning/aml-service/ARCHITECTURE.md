# AML Service - Architecture

## High-Level Overview

The AML (Anti-Money Laundering) Service is a specialized data processing pipeline integrated into the Data Foundry platform. It provides AI-powered transaction labeling for AML compliance through a job-based upload system. The service processes uploaded CSV files containing financial transactions, applies GPT-4 based classification, and generates audit-ready documentation.

**Key Architecture Points:**
- **No dedicated AML API endpoints** - AML processing is triggered through the generic job-based upload system
- **Vertical-specific processing** - AML is one of several "verticals" that can be specified during file upload
- **Job-centric architecture** - All processing is tracked through ProcessingJob entities with status state machine
- **PostgreSQL-backed** - Uses SQLAlchemy ORM with async sessions for persistence
- **Prefect orchestration** - Data ingestion flow orchestrated through Prefect tasks

```
                            EXTERNAL CLIENTS
                  (Fintech Compliance Officers, ML Teams)

                             API (FastAPI)

    +-------------------------------------------------------------+
    |                    Upload API (Single Entry Point)           |
    |                    POST /api/v1/upload                       |
    |                    POST /api/v1/upload/with-processing       |
    +-------------------------------------------------------------+
                             |
    +-------------------------------------------------------------+
    |
    |   Upload Service -> Job Tracking -> Processing Pipeline
    |         |                  |                  |
    |         v                  v                  v
    |   File Storage      Job Repository      Prefect Flow
    |   (Local/S3)        (PostgreSQL)       (Ingestion Tasks)
    |         |                  |                  |
    |         +------------------+------------------+
    |                            |
    |   +--------------------------------------------------------+
    |   |
    |   |---------------+---------------+---------------+---------|
    |   |               |               |               |         |
    | AML Labeling    Data Quality    Validation    Database    Report
    |   (GPT-4)        Scoring          Layer        Persistence Generation
    |   |               |               |               |         |
    |   +---------------+---------------+---------------+---------+
    |                            |
    |   +--------------------------------------------------------+
    |   |
    |   +-------------------+-------------------+-------------------+
    |   |                   |                   |                   |
    | PostgreSQL          OpenAI API          Storage            Jobs API
    | (ORM + Audit)      (GPT-4o)           (Results)       (Status/Download)
    |   |                   |                   |                   |
    | - Tables           - Labeling          - CSV Results     - GET /jobs/{id}
    | - Migrations       - Completion        - Audit Reports   - GET /jobs/{id}/results
    | - Relationships    - Prompts                              - POST /jobs/{id}/retry
    |                                                            - POST /jobs/{id}/cancel
```

---

## Component Breakdown

### 1. Upload API (Single Entry Point)

**Responsibility:** File upload and job creation for all processing types (including AML)

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/api/v1/upload/router.py`

**Endpoints:**

**File Upload:**
- `POST /api/v1/upload` - Upload file for processing
  - Input: `multipart/form-data` with file + metadata
  - Parameters:
    - `file`: CSV file with transactions
    - `vertical`: Processing vertical (e.g., "aml", "general")
    - `auto_start`: Boolean to immediately start processing
  - Output: Job ID for tracking

**Upload and Process:**
- `POST /api/v1/upload/with-processing` - Upload and immediately start processing
  - Triggers the complete pipeline synchronously
  - Returns pipeline result including flow run ID

**Get Supported Types:**
- `GET /api/v1/upload/supported-types` - Get list of supported file types

**Characteristics:**
- Vertical-agnostic (AML is one of many verticals)
- Multi-tenant via `X-Tenant-ID` header (JWT-based in production)
- File validation before storage
- Complexity tier calculation for cost estimation

**Note:** There are NO dedicated AML endpoints like `/api/v1/aml/*`. AML processing is triggered by setting `vertical="aml"` in the upload request.

---

### 2. Jobs API (Job Management)

**Responsibility:** Job status tracking, results download, and job lifecycle management

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/api/v1/jobs/router.py`

**Endpoints:**

**Job Status:**
- `GET /api/v1/jobs/{job_id}` - Get job status and progress
  - Returns job metadata including AML-specific metrics when available:
    - `aml_risk_level_counts`: Distribution of transactions by risk level
    - `aml_inter_rater_agreement`: Cohen's Kappa for AI-expert agreement
    - `aml_expert_review_count`: Number of labels requiring expert review
    - `aml_audit_report_url`: Link to generated audit report

**Job Listing:**
- `GET /api/v1/jobs` - List all jobs for tenant
  - Query parameters: `status`, `limit`, `offset`

**Job Control:**
- `POST /api/v1/jobs/{job_id}/cancel` - Cancel processing job
- `POST /api/v1/jobs/{job_id}/retry` - Retry failed job

**Results Download:**
- `GET /api/v1/jobs/{job_id}/results` - Download AML labels as CSV
  - Returns CSV with all AML transaction labels for the job
  - Filters by `job_id` and `tenant_id` for security
  - Uses `AMLTransactionLabel.to_csv_row()` for CSV generation

- `GET /api/v1/jobs/{job_id}/download` - Get download URL for results

**Characteristics:**
- Tenant isolation enforced at endpoint level
- Returns 404 for jobs owned by other tenants
- AML metrics only populated for completed AML jobs

---

### 3. Job Tracking Service

**Responsibility:** Manage processing job lifecycle through state machine

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/application/job_tracking_service.py`

**Job States:**
```
PENDING -> PROCESSING -> COMPLETE
                 |
                 v
              FAILED
                 |
                 v
              CANCELLED
```

**Key Methods:**

```python
class JobTrackingService:
    # Job Creation
    async def create_job(tenant_id, file_name, file_size, complexity_tier, estimated_cost, metadata) -> ProcessingJob

    # State Transitions
    async def start_processing(job_id) -> ProcessingJob
    async def mark_complete(job_id, result_records, result_url, actual_cost,
                          aml_risk_level_counts, aml_inter_rater_agreement,
                          aml_expert_review_count, aml_audit_report_url) -> ProcessingJob
    async def mark_failed(job_id, error_message) -> ProcessingJob
    async def cancel_job(job_id, reason) -> ProcessingJob
    async def retry_job(job_id) -> ProcessingJob

    # Query Operations
    async def get_job(job_id) -> Optional[ProcessingJob]
    async def list_tenant_jobs(tenant_id, status, limit, offset) -> List[ProcessingJob]
    async def get_pending_jobs(limit) -> List[ProcessingJob]

    # AML-specific Operations
    async def get_aml_job_metrics(job_id, aml_labels) -> Dict[str, Any]
```

**Job Entity:**

The `ProcessingJob` aggregate (from `/home/carlos/projects/data_foundry/data-foundry/src/domain/processing_job/aggregate.py`) contains:

```python
class ProcessingJob:
    id: str  # UUID
    tenant_id: str
    status: JobStatus  # PENDING, PROCESSING, COMPLETE, FAILED, CANCELLED
    file_name: str
    file_size: int
    complexity_tier: str
    estimated_cost: Decimal
    actual_cost: Optional[Decimal]

    # Results
    result_records: Optional[int]  # Number of transactions processed
    result_url: Optional[str]      # Storage location of results

    # AML-specific metadata (stored in metadata JSON field)
    metadata: dict = {
        "aml_results": {
            "risk_level_counts": {"LOW": 100, "MEDIUM": 25, "HIGH": 5, "CRITICAL": 2},
            "inter_rater_agreement": 0.85,
            "expert_review_count": 15,
            "audit_report_url": "s3://bucket/audit_reports/job_123.pdf"
        }
    }

    # Timestamps
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Error handling
    error_message: Optional[str]
    retry_count: int
```

**AML-Specific Features:**
- `mark_complete()` accepts AML-specific parameters and stores them in job metadata
- `get_aml_job_metrics()` calculates AML metrics from labels or retrieves from metadata
- AML results are stored in flexible `metadata` JSON field

---

### 4. Data Ingestion Pipeline (Prefect Flow)

**Responsibility:** Orchestrate AML labeling pipeline with fault tolerance

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/tasks/ingestion.py`

**AML Flow Structure:**

The Prefect flow `data_ingestion_flow()` orchestrates the following tasks:

```
extract_data(job_id, storage_key, file_name)
    |
    v
validate_schema(extracted_data, expected_columns)
    |
    v
check_duplicates(extracted_data, tenant_id)
    |
    v
compute_quality_scores(extracted_data)
    |
    v
filter_low_quality(extracted_data, min_quality_threshold)
    |
    v
apply_pii_redaction(extracted_data)  # Optional: Presidio
    |
    v
apply_aml_labeling(extracted_data, job_id)  # GPT-4o calls
    |
    v
save_aml_labels_to_database(labels, job_id, tenant_id)
    |
    v
generate_audit_report(job_id, labels, tenant_id)
    |
    v
_update_job_status_complete(job_id, metrics)
```

**Key AML Tasks:**

**apply_aml_labeling()** (Lines ~139-256)
- Iterates over extracted transactions
- For each transaction:
  - Builds AML prompt with transaction data
  - Calls AI service (GPT-4o) via `ai_completion()`
  - Validates response against AML schema
  - Returns structured classification:
    - `risk_level`: LOW, MEDIUM, HIGH, CRITICAL
    - `typology`: FATF typology code (ML, TF, PEP, etc.)
    - `confidence_score`: 0.0 - 1.0
    - `reasoning`: Explanation text
    - `regulatory_flags`: List of applicable flags
- Handles timeouts and errors with retry logic
- Routes low-confidence labels for expert review

**save_aml_labels_to_database()** (Lines ~1736-2020)
- Validates records using `AMLLabelValidator`
- Creates `AMLTransactionLabel` ORM instances
- Batch inserts (100-500 records per batch)
- Handles duplicates via unique constraint on `(transaction_id, tenant_id)`
- Returns metrics: saved count, duplicates skipped, errors

**generate_audit_report()** (Lines ~529-637)
- Creates `AMLAuditReport` ORM instance with:
  - Transaction counts
  - Risk distribution
  - Typology distribution
  - Inter-rater agreement metrics
- Stores report metadata in database
- Generates report URL for download

**Characteristics:**
- Fault-tolerant (retry on transient errors)
- Observable (detailed logging at each step)
- Idempotent (safe to re-run)

---

### 5. AI Service Integration (OpenAI GPT-4)

**Responsibility:** Generate AML classifications using GPT-4o

**File:** Referenced in ingestion flow (likely `/home/carlos/projects/data_foundry/data-foundry/src/services/ai_service.py`)

**AML-Specific Method:**
```python
async def aml_completion(request: AIRequest) -> AIResponse:
    """
    Call AI service with AML-specific prompt.

    Returns structured AML classification:
    {
        "risk_level": "HIGH",           # LOW, MEDIUM, HIGH, CRITICAL
        "typology": "ML",               # FATF typology code
        "confidence_score": 0.92,       # 0.0 - 1.0
        "reasoning": "High-risk pattern...",
        "regulatory_flags": ["STRUCTURING", "HIGH_RISK_JURISDICTION"]
    }
    """
```

**AML Prompt:** `/home/carlos/projects/data_foundry/data-foundry/src/core/prompts/aml_labeling_prompt.py`

The prompt defines:
- **System role**: Expert AML Analyst with FATF/FinCEN expertise
- **Risk levels**: LOW, MEDIUM, HIGH, CRITICAL with detailed definitions
- **FATF typologies**: ML, TF, PEP, FRAUD, SANCTIONS, TAX_EVASION, BRIBERY, SMUGGLING, DRUG_TRAFFICKING, HUMAN_TRAFFICKING, PROLIFERATION, CYBERCRIME, ENVIRONMENTAL
- **Regulatory flags**: HIGH_RISK_JURISDICTION, SANCTIONS_MATCH, SUSPICIOUS_PATTERN, SHELL_COMPANY, etc.
- **Few-shot examples**: 4 examples showing high/low confidence assessments
- **Output format**: Structured JSON with validation rules

**Response Validation:** Implemented in ingestion flow
- Checks `risk_level` in valid set
- Validates `typology` against FATF list
- Ensures `confidence_score` in range [0, 1]
- Requires minimum `reasoning` length (50 characters)
- Invalid responses routed to expert review

**Error Handling:**
- Timeout: 3 retries before escalation
- Parsing error: Route to expert review
- Validation error: Route to expert review
- Service error: Escalate immediately

---

### 6. Inter-Rater Agreement Calculator

**Responsibility:** Measure AI-expert agreement for quality assurance

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/core/agreement_calculator.py`

**Cohen's Kappa Calculation:**
```
kappa = (p_o - p_e) / (1 - p_e)

Where:
- p_o = Observed agreement (matching labels / total)
- p_e = Expected agreement by chance
```

**Key Class:**
```python
class CohenKappaCalculator:
    def __init__(self, threshold=0.70, interpretation_ranges=None)
    def calculate_agreement(rater1_decisions, rater2_decisions) -> float
    def is_agreement_sufficient(kappa_value) -> bool
    def get_confidence_level(kappa_value) -> str  # POOR, FAIR, MODERATE, SUBSTANTIAL, PERFECT
    def interpret_landis_koch(kappa_value) -> str
    def calculate_confusion_matrix(rater1_decisions, rater2_decisions) -> dict
```

**Interpretation Scale (Landis & Koch 1977):**
| Kappa Range | Level | Regulatory Sufficiency |
|-------------|-------|------------------------|
| < 0.00 | POOR | Not sufficient |
| 0.00 - 0.20 | SLIGHT | Not sufficient |
| 0.21 - 0.40 | FAIR | Not sufficient |
| 0.41 - 0.60 | MODERATE | Not sufficient |
| 0.61 - 0.80 | SUBSTANTIAL | Sufficient |
| 0.81 - 1.00 | ALMOST PERFECT | Excellent |

**Configuration:**
- `AML_CONFIG["kappa_threshold"]` - Minimum acceptable agreement (default: 0.70)
- `AML_CONFIG["kappa_interpretation"]` - Custom interpretation ranges

**Usage in Pipeline:**
1. AI generates labels with confidence scores
2. Expert reviews sample (or low-confidence items)
3. Calculate kappa between AI and expert decisions
4. Route based on kappa >= threshold

---

### 7. ORM Layer (SQLAlchemy/SQLModel)

**Responsibility:** Database models with type safety and audit trails

**Files:**
- `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_transaction_label.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_audit_report.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_expert_review.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_labeling_methodology.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/models/aml_enums.py`

**Core Models:**

**AMLTransactionLabel**
```python
class AMLTransactionLabel(SQLModel, table=True):
    # Primary keys
    id: str  # UUID

    # Foreign keys (indexed)
    transaction_id: str  # Original customer ID
    tenant_id: str       # Multi-tenant isolation
    job_id: str          # Processing job
    version_id: Optional[str]  # Methodology version

    # Classification
    risk_level: AMLRiskLevel  # LOW, MEDIUM, HIGH, CRITICAL
    typology: str              # FATF code (ML, TF, PEP, etc.)
    confidence_score: Decimal  # 0.00 - 1.00
    ai_reasoning: str          # Explanation (Text)

    # Expert review
    expert_review_status: AMLExpertReviewStatus  # PENDING, AGREED, DISAGREED, ESCALATED
    expert_reviewer_id: Optional[str]
    expert_reviewed_at: Optional[datetime]
    expert_review_comments: Optional[str]

    # Regulatory flags (JSONB)
    regulatory_flags: Dict[str, Any] = {}

    # Audit fields
    is_audit_ready: bool
    is_deleted: bool  # Soft delete
    deleted_by: Optional[str]
    deleted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]

    # Business logic methods
    def requires_expert_review() -> bool
    def to_csv_row() -> Dict[str, Any]
```

**AMLAuditReport**
```python
class AMLAuditReport(SQLModel, table=True):
    id: str
    tenant_id: str
    job_id: str

    # Statistics
    transaction_count: int
    labeled_count: int
    expert_reviewed_count: int

    # Risk distribution (JSON)
    risk_distribution: Dict[str, int]

    # Typology distribution (JSON)
    typology_distribution: Dict[str, int]

    # Agreement metrics
    kappa_coefficient: Decimal
    agreement_level: AMLAgreementLevel

    # Report metadata
    generated_at: datetime
    report_url: str

    # Audit fields
    is_deleted: bool
    deleted_by: Optional[str]
    deleted_at: Optional[datetime]
    created_at: datetime
```

**AMLExpertReview**
```python
class AMLExpertReview(SQLModel, table=True):
    id: str
    tenant_id: str
    transaction_label_id: str  # FK to AMLTransactionLabel

    reviewer_id: str
    reviewed_at: datetime

    # Expert classification
    expert_risk_level: AMLRiskLevel
    expert_typology: str
    expert_comments: Optional[str]

    # Agreement
    agrees_with_ai: bool
    disagreement_reason: Optional[str]

    # Audit
    is_deleted: bool
    created_at: datetime
```

**AMLLabelingMethodology**
```python
class AMLLabelingMethodology(SQLModel, table=True):
    id: str
    tenant_id: str
    version: str
    description: str
    status: AMLMethodologyStatus  # DRAFT, ACTIVE, ARCHIVED

    # Configuration (JSON)
    risk_thresholds: Dict[str, Any]
    typologies: Dict[str, Any]
    regulatory_references: Dict[str, Any]

    # Audit
    is_deleted: bool
    created_at: datetime
    created_by: Optional[str]
```

**Enums:** (`/home/carlos/projects/data_foundry/data-foundry/src/models/aml_enums.py`)
- `AMLRiskLevel`: LOW, MEDIUM, HIGH, CRITICAL
- `AMLTypology`: ML, TF, PEP, FRAUD, SANCTIONS, TAX_EVASION, BRIBERY, SMUGGLING, DRUG_TRAFFICKING, HUMAN_TRAFFICKING, PROLIFERATION, CYBERCRIME, ENVIRONMENTAL
- `AMLExpertReviewStatus`: PENDING, AGREED, DISAGREED, ESCALATED
- `AMLAgreementLevel`: POOR, SLIGHT, FAIR, MODERATE, SUBSTANTIAL, ALMOST_PERFECT, PERFECT
- `AMLMethodologyStatus`: DRAFT, ACTIVE, ARCHIVED

**Characteristics:**
- Type-safe enums
- Soft delete support
- Comprehensive audit trail
- Business logic methods
- JSONB for flexible metadata

---

### 8. Database Schema (PostgreSQL)

**Responsibility:** Persistent storage with full audit trail

**Migrations:**
- `/home/carlos/projects/data_foundry/data-foundry/src/database/migrations/003_add_job_id_to_aml_labels.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/database/migrations/add_aml_transaction_labels_table.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/database/migrations/add_aml_audit_trail_tables.py`
- `/home/carlos/projects/data_foundry/data-foundry/src/database/migrations/004_add_unique_constraint_aml_labels.py`

**Tables:**

**aml_transaction_labels**
```sql
CREATE TABLE aml_transaction_labels (
    id UUID PRIMARY KEY,
    transaction_id VARCHAR NOT NULL,
    tenant_id VARCHAR NOT NULL,
    job_id VARCHAR NOT NULL,
    version_id VARCHAR,

    risk_level VARCHAR NOT NULL,  -- LOW, MEDIUM, HIGH, CRITICAL
    typology VARCHAR NOT NULL,    -- FATF typology code
    confidence_score DECIMAL(5,4) NOT NULL,
    ai_reasoning TEXT NOT NULL,

    expert_review_status VARCHAR NOT NULL DEFAULT 'PENDING',
    expert_reviewer_id VARCHAR,
    expert_reviewed_at TIMESTAMP,
    expert_review_comments TEXT,

    regulatory_flags JSONB DEFAULT '{}',

    is_audit_ready BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by VARCHAR,
    deleted_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR,

    UNIQUE (transaction_id, tenant_id)
);

CREATE INDEX idxaml_tenant ON aml_transaction_labels(tenant_id);
CREATE INDEX idxaml_job ON aml_transaction_labels(job_id);
CREATE INDEX idxaml_risk ON aml_transaction_labels(risk_level);
CREATE INDEX idxaml_status ON aml_transaction_labels(expert_review_status);
```

**aml_audit_reports**
```sql
CREATE TABLE aml_audit_reports (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    job_id VARCHAR NOT NULL,

    transaction_count INTEGER NOT NULL,
    labeled_count INTEGER NOT NULL,
    expert_reviewed_count INTEGER NOT NULL,

    risk_distribution JSONB,
    typology_distribution JSONB,

    kappa_coefficient DECIMAL(5,4) NOT NULL,
    agreement_level VARCHAR NOT NULL,

    generated_at TIMESTAMP NOT NULL,
    report_url VARCHAR NOT NULL,

    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by VARCHAR,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**aml_expert_reviews**
```sql
CREATE TABLE aml_expert_reviews (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    transaction_label_id VARCHAR NOT NULL,

    reviewer_id VARCHAR NOT NULL,
    reviewed_at TIMESTAMP NOT NULL,

    expert_risk_level VARCHAR NOT NULL,
    expert_typology VARCHAR NOT NULL,
    expert_comments TEXT,

    agrees_with_ai BOOLEAN NOT NULL,
    disagreement_reason TEXT,

    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**aml_labeling_methodology**
```sql
CREATE TABLE aml_labeling_methodology (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    created_by VARCHAR,

    version VARCHAR NOT NULL,
    description TEXT,

    risk_thresholds JSONB,
    typologies JSONB,
    regulatory_references JSONB,

    status VARCHAR NOT NULL DEFAULT 'DRAFT',

    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by VARCHAR,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Characteristics:**
- JSONB for flexible metadata (regulatory_flags, distributions)
- Unique constraint prevents duplicate labeling per transaction
- Soft delete for data retention compliance
- Indexed for query performance
- Foreign key relationships enforced

---

### 9. AML Label Validator

**Responsibility:** Pre-insertion validation for data quality

**File:** `/home/carlos/projects/data_foundry/data-foundry/src/core/aml_label_validator.py`

**Validation:**
```python
class AMLLabelValidator:
    @staticmethod
    def validate(record: dict) -> ValidationResult:
        """
        Validate AML label record before insertion.

        Checks:
        - Required fields present
        - Risk level in valid set
        - Typology in FATF list
        - Confidence in range [0, 1]
        - Reasoning meets minimum length
        - Regulatory flags is valid JSON
        """
```

**Error Types:**
- `ValidationError`: Invalid data
- `MissingFieldError`: Required field missing
- `InvalidEnumError`: Invalid enum value
- `RangeError`: Value out of range

---

### 10. PII Redaction (Optional)

**Responsibility:** Redact personally identifiable information before AI processing

**File:** Implemented in `/home/carlos/projects/data_foundry/data-foundry/src/tasks/ingestion.py`

**PII Types Detected:**
- SSN (including hyphenated format: XXX-XX-XXXX)
- Email addresses
- Phone numbers
- Names
- Credit card numbers
- Bank account numbers

**Implementation:**
- Microsoft Presidio Analyzer + Anonymizer
- Custom SSN recognizer for hyphenated format
- Replaces detected PII with `<ENTITY_TYPE>` placeholders
- Logs redaction metadata for audit trail

**Security:**
- If Presidio not installed: clear warning + continue without redaction
- Configurable via `ENABLE_PII_REDACTION`

---

## Data Flow Diagram

### Complete AML Pipeline (Actual Implementation)

```
Customer uploads CSV (financial transactions)
    |
    v
POST /api/v1/upload (with vertical="aml" or auto-detected)
    |
    v
UploadService.upload_file()
    ├─ Validate file format (CSV)
    ├─ Calculate complexity tier
    ├─ Estimate cost
    ├─ Store in local/S3 storage
    ├─ Create ProcessingJob (status=PENDING)
    └─ Return job_id
    |
    v
UploadPipeline.execute() or JobWorker polls for PENDING jobs
    |
    v
Claim job (start_processing: status=PROCESSING)
    |
    v
Execute Prefect data_ingestion_flow(job_id, storage_key, file_name)
    |
    +--> extract_data() - Parse CSV rows, return list of dicts
    |
    +--> validate_schema() - Check required columns exist
    |
    +--> check_duplicates() - SHA256 hash comparison against existing labels
    |
    +--> compute_quality_scores() - Data quality metrics (completeness, validity)
    |
    +--> filter_low_quality() - Min quality threshold (default 0.5)
    |
    +--> apply_pii_redaction() - Presidio PII removal (optional)
    |
    +--> apply_aml_labeling() - [GPT-4o via AI service]
    |   |
    |   +-- For each transaction:
    |       +-- Build AML prompt (from aml_labeling_prompt.py)
    |       +-- Call AI service (ai_completion with AML prompt)
    |       +-- Parse JSON response
    |       +-- Validate AML response
    |           - risk_level in {LOW, MEDIUM, HIGH, CRITICAL}
    |           - typology in FATF typologies
    |           - confidence in [0, 1]
    |           - reasoning >= 50 chars
    |       +-- If validation fails: mark expert_review_status = PENDING
    |       +-- If confidence < 0.6: mark expert_review_status = PENDING
    |       +-- Else: mark expert_review_status = AGREED
    |   |
    |   +-- Return list of AMLTransactionLabel objects
    |
    +--> save_aml_labels_to_database()
    |   |
    |   +-- Validate records (AMLLabelValidator)
    |   |
    |   +-- Create ORM instances (AMLTransactionLabel)
    |   |
    |   +-- Batch insert (100-500 records per batch)
    |       |
    |       +-- ON CONFLICT (transaction_id, tenant_id) DO NOTHING
    |       |
    |       +-- Log duplicates skipped
    |   |
    |   +-- Return metrics (saved, dupes, errors)
    |
    +--> generate_audit_report()
    |   |
    |   +-- Calculate statistics
    |       - Total transactions
    |       - Risk distribution (counts per level)
    |       - Typology distribution (counts per type)
    |       - Expert review queue size
    |   |
    |   +-- Create AMLAuditReport ORM instance
    |   |
    |   +-- Store in database
    |
    +--> _update_job_status_complete()
        |
        +-- status = COMPLETE
        |
        +-- result_records = labeled count
        |
        +-- Store AML metrics in metadata:
            {
                "aml_results": {
                    "risk_level_counts": {"LOW": X, "MEDIUM": Y, ...},
                    "inter_rater_agreement": kappa_score,
                    "expert_review_count": count_pending,
                    "audit_report_url": report_path
                }
            }
    |
    v
Customer polls GET /api/v1/jobs/{job_id}
    |
    v
Status = COMPLETE
    |
    v
Download results:
    - GET /api/v1/jobs/{job_id}/results -> CSV with AML labels
      (filtered by job_id and tenant_id for security)
```

---

## Key Architecture Differences from Specification

### What DOES Exist:

1. **Job-Based Upload System**
   - Generic `/api/v1/upload` endpoint handles all verticals
   - AML processing triggered by `vertical` parameter or auto-detection
   - Job tracking through `ProcessingJob` aggregate with state machine

2. **ORM Models**
   - `AMLTransactionLabel` - Main label storage
   - `AMLAuditReport` - Audit report metadata
   - `AMLExpertReview` - Expert review records
   - `AMLLabelingMethodology` - Methodology versioning
   - All enums defined in `aml_enums.py`

3. **Database Schema**
   - Tables created via Alembic migrations
   - Unique constraint on `(transaction_id, tenant_id)`
   - JSONB for flexible metadata
   - Soft delete support

4. **Core Components**
   - AML prompt with FATF alignment
   - Cohen's Kappa calculator
   - AML label validator
   - PII redaction (optional)

5. **Jobs API**
   - Job status retrieval
   - Results download as CSV
   - Job control (retry, cancel)
   - AML metrics in job metadata

### What DOES NOT Exist (Fictional in old doc):

1. **Dedicated AML API endpoints**
   - ~~`GET /api/v1/regulatory-context/{type}`~~ - Not implemented
   - ~~`POST /webhooks/aml-events`~~ - Not implemented
   - AML is processed through generic upload/jobs APIs

2. **Stripe Billing Integration**
   - ~~`src/services/usage_calculation_service.py`~~ - Not found
   - ~~Meter events reporting~~ - Not implemented
   - Usage tracking exists in job metadata but no billing integration

3. **Background Worker**
   - ~~`src/workers/job_worker.py`~~ - Not found
   - Job processing triggered via upload pipeline or Prefect flow

4. **Label Studio Integration**
   - No human review interface implemented
   - Expert review model exists but no UI

5. **Redis Cache**
   - No Redis implementation found
   - Idempotency not implemented (database-based only)

---

## External Dependencies

### Required
- **PostgreSQL 12+**: Persistent storage with JSONB support
- **Python 3.11+**: Runtime environment
- **FastAPI**: Web framework
- **SQLAlchemy/SQLModel**: ORM
- **Prefect**: Workflow orchestration
- **OpenAI API**: GPT-4o for AML labeling

### Optional
- **Presidio**: PII redaction (graceful degradation if missing)
- **S3/R2**: File storage (currently using local storage)
- **Sentry**: Error tracking (referenced but not verified)

### NOT Implemented
- Stripe billing integration
- Redis caching
- Message queue (database queue used)
- Label Studio for human review
- Dedicated AML endpoints

---

## Integration Points

### Inbound (Customers to AML Service)
1. **HTTP API via Upload Endpoint**
   - `POST /api/v1/upload` with `vertical="aml"`
   - Auth: `X-Tenant-ID` header (JWT-based in production)
   - Response: Job ID for tracking

2. **File Upload**
   - CSV files with transaction data
   - Required columns: transaction_id, amount, currency, sender/receiver info
   - Supports 10K-100K transactions per file

### Outbound (AML Service to External Systems)
1. **OpenAI API**
   - Model: GPT-4o (fallback: GPT-4o-mini)
   - Prompt: AML-specific with FATF typologies
   - Response: Structured JSON

2. **Storage (S3/R2/Local)**
   - Input: Original CSV files
   - Output: Labeled CSV results
   - Audit reports: Generated but storage location varies

3. **Database (PostgreSQL)**
   - AML labels persistence
   - Audit report metadata
   - Expert review records

---

## Multi-Tenancy Model

**Isolation Level:** Complete (no data cross-contamination)

**Implementation:**
```
Request with X-Tenant-ID header (or JWT claim)
    |
    v
Extract: tenant_id = "tenant_abc"
    |
    v
All Database Operations:
    - ProcessingJob queries filter by tenant_id
    - AMLTransactionLabel queries filter by tenant_id
    - API endpoints verify tenant ownership
    |
    v
Result: Only this tenant's data
```

**Multi-Tenant Enforcement:**
- API level: All job/label endpoints check tenant ownership
- Database level: Queries include `WHERE tenant_id = :tenant_id`
- Cross-tenant access: Returns 403 Forbidden

**Tenant-Specific Configuration:**
- Risk thresholds (per methodology)
- Confidence thresholds (configurable)
- Pricing tier (job metadata, not enforced)
- Methodology version (can vary by tenant)

---

## Deployment Architecture

### Current Implementation (Single Service)
```
┌────────────────────────────────┐
│   FastAPI Application          │
│  ┌──────────────────────────┐  │
│  │ Upload API Router        │  │
│  │ Jobs API Router          │  │
│  │ Application Services     │  │
│  │ Domain Logic             │  │
│  └──────────────────────────┘  │
└────────┬───────────────────────┘
         │
         ├──────────────────┬──────────────────┬───────────────┐
         │                  │                  │               │
    ┌────▼────┐      ┌─────▼─────┐     ┌────▼────┐    ┌────▼────┐
    │PostgreSQL│      │ OpenAI API│     │ Storage │    │ Prefect │
    │ (Data)   │      │ (GPT-4o)  │     │ (Local) │    │ (Flow)  │
    └──────────┘      └───────────┘     └─────────┘    └─────────┘
```

**Best for:** MVP, single-tenant deployments, development
**Scaling:** Horizontal (load balancer + multiple containers)

### Production Deployment (Future)
```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  API Server │     │Prefect Server│     │ Worker Process │
│  (FastAPI)  │────▶│ (Orchestration)│   │  (Task Runner) │
└─────────────┘     └──────────────┘     └────────────────┘
        │                    │                    │
        └────────┬───────────┴────────┬───────────┘
                 │                    │
    ┌────────────▼────────┐  ┌────────▼─────────┐
    │  PostgreSQL         │  │  Storage (S3/R2) │
    │  (data + audit)     │  │  (files + reports)│
    └─────────────────────┘  └──────────────────┘
                 │
                 └────────┬───────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
    ┌────▼────┐     ┌────▼────┐     ┌────▼────┐
    │ OpenAI  │     │ Storage │     │ Optional│
    │ GPT-4o  │     │ Backup  │     │ Redis   │
    └─────────┘     └─────────┘     └─────────┘
```

---

## Error Handling Strategy

**Validation Errors** (Record-Level)
```
Invalid AML response from AI
    ↓
Validation fails in apply_aml_labeling()
    ↓
Set: expert_review_status = PENDING
    ↓
Log: "AML response validation failed"
    ↓
Result: Record saved but flagged for expert review
```

**System Errors** (Service-Level)
```
OpenAI API timeout
    ↓
apply_aml_labeling() catches asyncio.TimeoutError
    ↓
Retry counter incremented
    ↓
If retry_count < 3:
    Mark: expert_review_status = PENDING (will retry)
Else:
    Mark: expert_review_status = ESCALATED
    ↓
Result: Transaction routed for expert review
```

**Database Errors**
```
ON CONFLICT (transaction_id, tenant_id) DO NOTHING
    ↓
Duplicate detected in batch insert
    ↓
metrics["duplicates_skipped"] += 1
    ↓
Log: "Duplicate transaction_id: abc123 (skipped)"
    ↓
Continue: No error, just skip duplicate
```

**Job-Level Errors**
```
Task failure in Prefect flow
    ↓
Exception caught by flow
    ↓
mark_failed(job_id, error_message)
    ↓
Job status = FAILED
    ↓
Result: Job can be retried via API
```

---

## Monitoring & Observability

**Critical Metrics (Available in Job Metadata):**
- Transactions processed per job
- Risk level distribution (LOW/MEDIUM/HIGH/CRITICAL counts)
- Typology distribution (most common FATF types)
- Expert review count (labels requiring review)
- Inter-rater agreement (Cohen's Kappa, if expert reviews exist)

**Logging:**
- All API requests (method, path, status, tenant_id)
- AML labeling results (risk, typology, confidence)
- Validation errors (field, error type)
- Database operations (inserts, duplicates, errors)
- Prefect flow execution (task start/completion)

**Alerts (Recommended):**
- AML labeling error rate > 5%
- High proportion of labels routed for expert review (>50%)
- Job failure rate > 10%
- Database connection failures
- OpenAI API rate limits reached

---

## Security Considerations

**Data at Rest:**
- PostgreSQL encryption (via cloud provider or self-managed)
- Local storage for development (no encryption by default)
- S3/R2 encryption recommended for production

**Data in Transit:**
- HTTPS only (TLS 1.3+) in production
- HTTP acceptable for local development

**Authentication:**
- Header-based: `X-Tenant-ID` for development
- JWT-based planned for production (not yet implemented)
- No password-based auth

**Authorization:**
- Tenant isolation enforced at:
  - API endpoint level (403 if tenant mismatch)
  - Database query level (filter by tenant_id)
- Cross-tenant access returns 403

**Audit Trail:**
- All AML labels logged with timestamps
- Job state transitions tracked
- Soft delete for retention compliance
- Expert reviews tracked (when implemented)

**PII Handling:**
- Presidio redaction available (optional)
- Configurable per transaction
- Redaction metadata logged
- Original data retained in database (for audit)

---

## Scalability Approach

**Horizontal Scaling:**
- API servers: Stateless, add behind load balancer
- Prefect workers: Multiple instances, shared job queue
- Database: Read replicas for queries, primary for writes

**Performance Optimization:**
- Batch inserts (100-500 records)
- Database indexes on frequently queried fields
- Connection pooling (SQLAlchemy)

**Bottlenecks:**
- OpenAI API rate limits (sequential processing)
- Large file uploads (memory-based, not streamed)
- Database write throughput (batch size tuning needed)

**Capacity Planning (Estimates):**
| Transactions/Job | API Servers | Prefect Workers | DB (CPU) | DB (RAM) |
|-----------------|------------|-----------------|----------|----------|
| 1K | 1 | 1 | 1 core | 1 GB |
| 10K | 1 | 2 | 2 cores | 2 GB |
| 100K | 2 | 4 | 4 cores | 4 GB |
| 1M | 4+ | 8+ | 8+ cores | 8+ GB |

---

## Summary

| Aspect | Details |
|--------|---------|
| **Architecture** | FastAPI + Prefect + PostgreSQL + OpenAI |
| **Core Purpose** | AML transaction labeling via job-based upload system |
| **Entry Point** | `POST /api/v1/upload` with `vertical="aml"` |
| **AI Model** | GPT-4o with FATF-aligned prompts |
| **Quality Assurance** | Confidence-based routing + Cohen's Kappa (when expert reviews exist) |
| **Output** | Labeled CSV (via `GET /api/v1/jobs/{id}/results`) |
| **Authentication** | Header-based (`X-Tenant-ID`) for dev, JWT planned |
| **Multi-Tenancy** | Complete isolation at API and database level |
| **Job Tracking** | ProcessingJob aggregate with state machine |
| **Database** | PostgreSQL with JSONB + audit trails |
| **Compliance** | FATF, FinCEN aligned (via prompts) |

---

## Related Documentation

- **Models:** `/home/carlos/projects/data_foundry/data-foundry/src/models/`
- **Tasks:** `/home/carlos/projects/data_foundry/data-foundry/src/tasks/ingestion.py`
- **API:** `/home/carlos/projects/data_foundry/data-foundry/src/api/v1/`
- **Core Components:** `/home/carlos/projects/data_foundry/data-foundry/src/core/`
- **Tests:** `/home/carlos/projects/data_foundry/data-foundry/tests/tasks/`
- **Migrations:** `/home/carlos/projects/data_foundry/data-foundry/src/database/migrations/`

---

**Document Version:** 2.0
**Created:** December 31, 2025
**Last Updated:** December 31, 2025
**Owner:** Data Foundry AML Service Team
**Changes from v1.0:** Aligned with actual codebase implementation, removed fictional endpoints, corrected architecture to reflect job-based upload system
