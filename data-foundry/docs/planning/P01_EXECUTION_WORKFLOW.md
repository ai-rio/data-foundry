# P01 AML Service MLP Implementation - Execution Workflow
**Date:** December 29, 2025
**Phase:** P01 - AML Service Minimum Lovable Product
**Execution Model:** Custom 6-Step Agent-Driven Workflow
**Status:** Ready for Execution

---

## Executive Overview

This document defines the execution workflow for P01 (AML Service MLP Implementation) using a custom 6-step per-task cycle with specialized agent assignments.

**Key Characteristics:**
- **28 subtasks** organized into **10 execution groups**
- **6-step per-task workflow**: Implementation → QA Audit → Fixes (loop) → Commit
- **Parallel execution**: ~63% time savings via grouping (25-35h vs 65-70h sequential)
- **Specialized agents**: Dedicated agent for each task type (TDD orchestrator, code reviewer, API specialist, etc.)
- **Quality gates**: Measured at each phase to ensure production-ready code
- **Architecture principles**: SOLID → Encapsulation → DDD → Composability → SoC → High Cohesion/Low Coupling → Pragmatic Adaptation

---

## Section 1: Execution Groups with Task Organization

### GROUP 1 - Foundation (Parallel, No Dependencies)
**Duration:** 4-6 hours
**Can start:** Immediately
**Agent Approach:** test-later (simple configuration/design tasks)

#### Task P01-001: AML Database Schema Design
**Effort:** 4 hours
**Method:** test-later (design-first, validate with tests in GROUP 2)
**Agent:** No specific agent needed (design documentation)

**Workflow:**

1. **Implementation** (2h)
   - Design PostgreSQL schema ERD
   - Define table structures (aml_transaction_labels, audit_reports, expert_reviews, labeling_methodology_versions)
   - Plan indexing strategy
   - Document audit trail fields and compliance fields
   - **Deliverable:** ERD diagram + schema design document

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Review ERD for correctness and normalization (3NF)
   - Verify audit fields complete
   - Check tenant isolation implemented
   - Validate index strategy
   - **Gate:** ERD approved, no normalization issues, all audit fields present

3. **Fixes if needed** (1h)
   - Adjust ERD based on review findings
   - Add missing fields/relationships
   - Reaudit if changes made
   - **Loop back to step 2 until gates met**

4. **Commit** (0.5h)
   - Document final schema design
   - Create SCHEMA_DESIGN.md artifact
   - Ready for P01-002 (migrations)

---

#### Task P01-008: AML Configuration Management
**Effort:** 2 hours
**Method:** test-later (straightforward configuration addition)
**Agent:** No specific agent needed (configuration setup)

**Workflow:**

1. **Implementation** (1h)
   - Add all AML settings to src/core/config.py
   - Create .env.example with new variables
   - Add validation for settings (price > 0, threshold 0-1, etc.)
   - **Deliverable:** Updated config.py, updated .env.example

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Verify all settings have defaults
   - Check environment variables load correctly
   - Validate validation logic
   - Ensure documentation clear
   - **Gate:** All settings loadable, validation works, no hardcoded secrets

3. **Fixes if needed** (0.5h)
   - Fix validation logic
   - Add missing docstrings
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize config.py
   - Ready for P01-004 and P01-009 (AML labeling tasks)

---

### GROUP 2 - Infrastructure Setup (Sequential then Parallel)
**Duration:** 6-8 hours
**Depends on:** GROUP 1 completion
**Agent Approach:** hybrid (database tasks need testing)

#### Task P01-002: Create Alembic Migrations
**Effort:** 3 hours
**Method:** hybrid (schema validation needed)
**Agent:** `data-engineering:data-engineer` (database specialist)

**Workflow:**

1. **Implementation** (1.5h) - `data-engineering:data-engineer`
   - Create migration file: 001_add_aml_transaction_labels_table.py
   - Create migration file: 002_add_aml_audit_trail_table.py
   - Implement rollback logic
   - Test migration creates correct schema
   - **Deliverable:** Two working migration files

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify migrations match P01-001 schema design
   - Check rollback works correctly
   - Validate idempotency
   - Verify no data loss on rollback
   - **Gate:** Migrations run successfully, rollback works, matches schema

3. **Fixes if needed** (0.5h) - `data-engineering:data-engineer`
   - Adjust migration SQL if needed
   - Fix rollback issues
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize migrations
   - Ready for P01-003 (ORM models)

---

#### Task P01-003: Implement AML ORM Models
**Effort:** 4 hours
**Method:** full-tdd (models are critical, need comprehensive tests)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2h) - `tdd-workflows:tdd-orchestrator`
   - Create AMLTransactionLabel model
   - Create AuditReport model
   - Create ExpertReview model
   - Create enums (AMLRiskLevel, AMLTypology, RegulatoryFlag)
   - Implement methods (is_audit_ready, to_csv_row, etc.)
   - **Deliverable:** Four model files with full implementation

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify models match schema (P01-001, P01-002)
   - Check relationships correct
   - Validate enum values
   - Review method implementations
   - **Gate:** Models match schema, relationships correct, all methods implemented

3. **Fixes if needed** (1h) - `tdd-workflows:tdd-orchestrator`
   - Add missing relationships
   - Fix validation logic
   - Implement missing methods
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize ORM models
   - Ready for P01-004, P01-005, P01-007, P01-010

---

### GROUP 3 - Core Services (Parallel)
**Duration:** 10-13 hours
**Depends on:** GROUP 2 completion
**Agent Approach:** hybrid/full-tdd (core business logic needs thorough testing)

#### Task P01-004: AML Labeling Task Implementation
**Effort:** 6 hours
**Method:** full-tdd (critical business logic)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (3h) - `tdd-workflows:tdd-orchestrator`
   - Rewrite apply_ai_labeling() in src/tasks/ingestion.py
   - Create AML-specific prompt in src/core/prompts/aml_labeling_prompt.py
   - Implement response validation
   - Implement error handling (confidence < 0.6 routing)
   - **Deliverable:** Updated ingestion.py + new prompt file

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Verify prompt produces FATF-aligned labels
   - Check response parsing handles edge cases
   - Validate confidence scoring
   - Check reasoning is explainable
   - **Gate:** Prompt valid, parsing robust, confidence accurate, reasoning clear

3. **Fixes if needed** (1.5h) - `python-development:fastapi-pro`
   - Adjust prompt if labels incorrect
   - Fix response parsing errors
   - Improve error handling
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize AML labeling
   - Ready for P01-005, P01-006, P01-009

---

#### Task P01-005: Cohen's Kappa Implementation
**Effort:** 4 hours
**Method:** full-tdd (agreement calculation is measurable)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2h) - `tdd-workflows:tdd-orchestrator`
   - Create CohenKappaCalculator class in src/core/agreement_calculator.py
   - Implement calculate_agreement() method
   - Implement is_agreement_sufficient()
   - Implement get_confidence_level()
   - **Deliverable:** agreement_calculator.py with full implementation

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify calculation mathematically correct
   - Check threshold logic (>= 0.70 for sufficient)
   - Validate edge cases (perfect agreement, no agreement)
   - Test performance with 1000+ records
   - **Gate:** Math correct, thresholds accurate, edge cases handled

3. **Fixes if needed** (1h) - `unit-testing:debugger`
   - Debug calculation if results incorrect
   - Optimize performance if needed
   - Fix edge case handling
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize Cohen's Kappa
   - Ready for P01-006

---

#### Task P01-009: AI Service Extension for AML
**Effort:** 3 hours
**Method:** hybrid (service extension with structured output)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1.5h) - `python-development:fastapi-pro`
   - Add aml_completion() method to AIService
   - Implement response validation
   - Implement error handling
   - Integrate with AML prompt (P01-004)
   - **Deliverable:** Updated ai_service.py

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify method signature correct
   - Check response validation catches malformed responses
   - Validate cost tracking works
   - Check error handling comprehensive
   - **Gate:** Method works, validation robust, cost tracking accurate

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Fix response parsing issues
   - Improve validation logic
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize AI service extension
   - Ready for P01-004 (uses this service)

---

### GROUP 4 - Orchestration Layer (Parallel)
**Duration:** 9-11 hours
**Depends on:** GROUP 3 completion
**Agent Approach:** hybrid/full-tdd (workflow orchestration critical)

#### Task P01-006: Modify Data Ingestion Flow
**Effort:** 5 hours
**Method:** full-tdd (Prefect flow orchestration)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2.5h) - `tdd-workflows:tdd-orchestrator`
   - Update data_ingestion_flow() in src/tasks/ingestion.py
   - Replace generic labeling with AML labeling
   - Add compute_inter_rater_agreement task
   - Modify route_for_human_review with Cohen's Kappa threshold
   - Add generate_audit_report task
   - **Deliverable:** Updated ingestion.py with new flow

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Verify flow orchestrates tasks in correct sequence
   - Check AML labels flow through correctly
   - Validate confidence threshold logic
   - Verify audit report generation integrated
   - **Gate:** Flow sequence correct, all tasks executed, error handling complete

3. **Fixes if needed** (1h) - `python-development:fastapi-pro`
   - Fix task sequencing if incorrect
   - Adjust threshold logic
   - Improve error handling
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize ingestion flow
   - Ready for P01-007, P01-010, P01-014

---

#### Task P01-007: Save AML Labels to Database
**Effort:** 3 hours
**Method:** hybrid (database persistence with batch optimization)
**Agent:** `data-engineering:data-engineer`

**Workflow:**

1. **Implementation** (1.5h) - `data-engineering:data-engineer`
   - Implement save_aml_labels_to_database() task
   - Create batch insert logic
   - Implement transaction handling
   - Add duplicate handling
   - **Deliverable:** Updated ingestion.py with new task

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify batch insert works
   - Check transaction handling (commit/rollback)
   - Validate duplicate prevention
   - Test performance (1000+ labels/sec)
   - **Gate:** Batch insert works, no data loss, duplicates handled, performance good

3. **Fixes if needed** (0.5h) - `data-engineering:data-engineer`
   - Optimize batch insert if slow
   - Fix transaction issues
   - Improve error logging
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize label saving
   - Ready for P01-010, P01-013

---

#### Task P01-010: Update Job Tracking Service
**Effort:** 3 hours
**Method:** hybrid (service layer with AML-specific fields)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1.5h) - `python-development:fastapi-pro`
   - Extend mark_complete() method with AML fields
   - Add get_aml_job_metrics() method
   - Implement metric calculation logic
   - **Deliverable:** Updated job_tracking_service.py

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify method signature correct
   - Check metric calculation accurate
   - Validate data persistence
   - Test metric retrieval
   - **Gate:** Methods work, metrics accurate, data persists

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Fix metric calculation errors
   - Improve data retrieval logic
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize job tracking service
   - Ready for P01-011, P01-012

---

### GROUP 5 - API Layer (Parallel)
**Duration:** 6-7 hours
**Depends on:** GROUP 4 completion
**Agent Approach:** hybrid (API endpoints with validation)

#### Task P01-011: Update Job API Contracts
**Effort:** 2 hours
**Method:** test-later (contract definitions)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1h) - `python-development:fastapi-pro`
   - Add AML-specific fields to JobStatusContract
   - Create AMLMetricsContract
   - Create AMLTransactionLabelContract
   - Implement serialization methods
   - **Deliverable:** Updated contracts.py

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Verify contracts match API spec
   - Check serialization logic
   - Validate all fields present
   - **Gate:** Contracts complete, serialization works, all fields valid

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Add missing fields
   - Fix serialization logic
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize API contracts
   - Ready for P01-012, P01-013

---

#### Task P01-012: Update Job Status Endpoint
**Effort:** 2 hours
**Method:** hybrid (endpoint with AML data)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1h) - `python-development:fastapi-pro`
   - Update job_to_contract() helper function
   - Integrate AML metrics retrieval
   - Include audit_report_url in response
   - **Deliverable:** Updated jobs/router.py

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Test endpoint returns correct response structure
   - Verify AML fields populated for complete jobs
   - Check partial jobs handled correctly
   - **Gate:** Endpoint works, AML fields present, response structure correct

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Fix response building logic
   - Add missing fields
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize status endpoint
   - Ready for tests and integration

---

#### Task P01-013: Results Download Endpoint (FIXES CURRENT ISSUE)
**Effort:** 3 hours
**Method:** hybrid (critical fix for pipeline)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1.5h) - `python-development:fastapi-pro`
   - Fix download_results() endpoint in jobs/router.py
   - Query AML labels from database
   - Implement CSV conversion method
   - Add error handling (404 if no results)
   - **Deliverable:** Fixed router.py with download endpoint

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Test endpoint with various record counts (0, 100, 10000)
   - Verify CSV format correct
   - Check downloadable file works
   - Validate audit trail logged
   - **Gate:** Endpoint works, CSV valid, test harness shows >0 records

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Debug query issues if no results returned
   - Fix CSV format if incorrect
   - Improve error messages
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize download endpoint
   - **CRITICAL:** This fixes test harness "0 records downloaded" issue

---

### GROUP 6 - Reporting & Optional Features (Parallel)
**Duration:** 9-13 hours (5-7h if Label Studio skipped)
**Depends on:** GROUP 5 completion
**Agent Approach:** hybrid/test-later (reporting features)

#### Task P01-015: Audit Report Generation
**Effort:** 5 hours
**Method:** hybrid (reporting with quality validation)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2.5h) - `tdd-workflows:tdd-orchestrator`
   - Create AuditReportGenerator class
   - Implement report generation (JSON + PDF)
   - Create generate_audit_report() Prefect task
   - Integrate into data_ingestion_flow()
   - **Deliverable:** Two new files + updated ingestion.py

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Verify report includes all required sections
   - Check metrics calculated correctly
   - Validate regulatory references present
   - Test JSON and PDF generation
   - **Gate:** Report complete, sections valid, metrics accurate, both formats work

3. **Fixes if needed** (1h) - `unit-testing:debugger`
   - Debug report generation if sections missing
   - Fix metric calculation errors
   - Improve formatting
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize audit report generation
   - Ready for tests and deployment

---

#### Task P01-016: Regulatory Reference API
**Effort:** 2 hours
**Method:** test-later (informational endpoint)
**Agent:** `python-development:fastapi-pro`

**Workflow:**

1. **Implementation** (1h) - `python-development:fastapi-pro`
   - Create regulatory/router.py
   - Implement get_regulatory_context() endpoint
   - Load regulatory data from REGULATORY_REFERENCE_AML_SERVICE.md
   - Add caching layer
   - **Deliverable:** New router file + regulatory_context.py

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Verify endpoint returns valid regulatory context
   - Check data matches reference document
   - Validate caching works
   - **Gate:** Endpoint works, data correct, caching functional

3. **Fixes if needed** (0.5h) - `python-development:fastapi-pro`
   - Fix data loading issues
   - Improve caching strategy
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize regulatory endpoint
   - Ready for deployment

---

#### Task P01-014: Label Studio Integration (OPTIONAL FOR MVP)
**Effort:** 6 hours (or skip for MVP)
**Method:** hybrid (external integration)
**Agent:** `python-development:fastapi-pro`
**Status:** SKIP for MVP (save 6 hours, use simple dashboard flag instead)

**Decision:** For MVP, skip Label Studio. Implement in V1.1.

**If including in full release:**

1. **Implementation** (3h) - `python-development:fastapi-pro`
   - Create label_studio_service.py
   - Implement webhook handler for expert reviews
   - Implement label sending logic
   - Integrate into workflow

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Test Label Studio connectivity
   - Verify webhook handler works
   - Check label synchronization

3. **Fixes if needed** (1h) - `unit-testing:debugger`
   - Debug integration issues

4. **Commit** (0.5h)

---

### GROUP 7 - Testing (Parallel)
**Duration:** 12-15 hours
**Depends on:** GROUP 6 completion
**Agent Approach:** full-tdd (comprehensive test coverage)

#### Task P01-018: Unit Tests for AML Labeling
**Effort:** 6 hours
**Method:** full-tdd (test-driven from start)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (3h) - `tdd-workflows:tdd-orchestrator`
   - Create tests/test_aml_labeling.py
   - Create tests/test_cohen_kappa.py
   - Create tests/test_aml_models.py
   - Implement all test cases from P01-004, P01-005 specs
   - **Deliverable:** Three comprehensive test files

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Verify test coverage >90% for AML code
   - Check all test cases present
   - Validate edge case coverage
   - **Gate:** Coverage >90%, all scenarios tested, edge cases covered

3. **Fixes if needed** (1.5h) - `unit-testing:debugger`
   - Add missing test cases
   - Debug failing tests
   - Improve coverage
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize unit tests
   - Ready for integration tests

---

#### Task P01-019: Integration Tests for Full Pipeline
**Effort:** 5 hours
**Method:** full-tdd (end-to-end validation)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2.5h) - `tdd-workflows:tdd-orchestrator`
   - Create tests/test_aml_end_to_end.py
   - Implement full pipeline tests
   - Create test fixtures with real transaction data
   - **Deliverable:** Comprehensive integration test file

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Test complete pipeline (upload → label → download)
   - Verify audit report generation
   - Check multi-vertical scenarios
   - Validate error handling
   - **Gate:** Pipeline works end-to-end, audit report present, errors handled

3. **Fixes if needed** (1h) - `unit-testing:debugger`
   - Debug pipeline failures
   - Fix test data issues
   - Improve error scenarios
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize integration tests
   - Ready for test harness update

---

#### Task P01-017: Edge Case Consultation (OPTIONAL)
**Effort:** 4 hours (SKIP for MVP)
**Status:** DEFER to V1.1 (save 4 hours)

---

### GROUP 8 - Test Infrastructure
**Duration:** 4 hours
**Depends on:** GROUP 7 completion
**Agent Approach:** hybrid (test harness update)

#### Task P01-021: Update Test Harness
**Effort:** 4 hours
**Method:** hybrid (infrastructure validation)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2h) - `tdd-workflows:tdd-orchestrator`
   - Update test_harness_phase2_api.py
   - Add AML-specific assertions
   - Verify labels present in results
   - Verify confidence scores present
   - Verify audit report generated
   - **Deliverable:** Updated test harness

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Run test harness against staging
   - Verify >0 records downloaded (CRITICAL FIX)
   - Check AML assertions pass
   - Validate report metrics
   - **Gate:** Test harness shows >0 records, all AML assertions pass

3. **Fixes if needed** (1h) - `unit-testing:debugger`
   - Debug test failures
   - Fix assertion logic
   - Improve metrics reporting
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Finalize test harness
   - Ready for staging deployment

---

### GROUP 9 - Staging & Validation (Sequential)
**Duration:** 10-11 hours
**Depends on:** GROUP 8 completion
**Agent Approach:** hybrid/full-tdd (deployment and validation)

#### Task P01-022: Deploy to Staging
**Effort:** 3 hours
**Method:** test-later (deployment checklist)
**Agent:** No specific agent (deployment operations)

**Workflow:**

1. **Implementation** (1.5h)
   - Create Docker image with AML service
   - Run migrations on staging database
   - Start FastAPI server and background worker
   - Verify all services connected
   - **Deliverable:** Staging environment running

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Run health check endpoint
   - Verify upload endpoint works
   - Test job tracking
   - Check background worker processes jobs
   - Verify results download works
   - **Gate:** All endpoints respond, background worker active, no critical errors

3. **Fixes if needed** (0.5h)
   - Debug connectivity issues
   - Fix configuration errors
   - Restart services if needed
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Staging ready for integration testing

---

#### Task P01-023: Integration Testing on Staging
**Effort:** 4 hours
**Method:** full-tdd (comprehensive validation)
**Agent:** `tdd-workflows:tdd-orchestrator`

**Workflow:**

1. **Implementation** (2h) - `tdd-workflows:tdd-orchestrator`
   - Run all unit tests on staging
   - Run all integration tests on staging
   - Execute full test harness
   - Validate performance (10,000 transactions in acceptable time)
   - **Deliverable:** Test results report

2. **QA Audit** (1.5h) - `tdd-workflows:code-reviewer`
   - Review all test results
   - Verify performance metrics acceptable
   - Check data integrity preserved
   - Validate multi-vertical scenarios
   - **Gate:** All tests pass, performance acceptable, data integrity confirmed

3. **Fixes if needed** (0.5h) - `unit-testing:debugger`
   - Debug failing tests
   - Optimize performance if needed
   - Fix any regressions
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Staging validation complete
   - Ready for security review

---

#### Task P01-024: Security & Compliance Review
**Effort:** 3 hours
**Method:** hybrid (security audit)
**Agent:** `tdd-workflows:code-reviewer`

**Workflow:**

1. **Implementation** (1.5h) - `tdd-workflows:code-reviewer`
   - Review code for security vulnerabilities
   - Check data encryption (at rest, in transit)
   - Verify authentication/authorization
   - Validate audit trail implementation
   - **Deliverable:** Security audit report

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Verify no hardcoded secrets
   - Check HIPAA/GDPR compliance
   - Validate PII redaction
   - Confirm regulatory requirements met
   - **Gate:** No critical security issues, compliance documented, audit trail complete

3. **Fixes if needed** (0.5h)
   - Fix security issues found
   - Add missing compliance controls
   - Improve audit trail
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Security review complete
   - Ready for production deployment planning

---

### GROUP 10 - Production & Go-to-Market (Sequential)
**Duration:** 11 hours
**Depends on:** GROUP 9 completion
**Agent Approach:** test-later (deployment and marketing)

#### Task P01-025: Production Deployment Plan
**Effort:** 2 hours
**Method:** test-later (planning documentation)

**Workflow:**

1. **Implementation** (1h)
   - Create deployment checklist
   - Document deployment sequence
   - Create rollback procedures
   - Define monitoring plan
   - **Deliverable:** PRODUCTION_DEPLOYMENT_PLAN.md

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Review plan for completeness
   - Verify rollback procedures work
   - Check monitoring thresholds
   - **Gate:** Plan complete, rollback tested, monitoring defined

3. **Fixes if needed** (0.5h)
   - Improve procedures
   - Add missing steps
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Plan approved
   - Ready for production deployment

---

#### Task P01-026: Production Deployment
**Effort:** 2 hours
**Method:** test-later (execution checklist)

**Workflow:**

1. **Implementation** (1h)
   - Execute deployment plan
   - Backup production database
   - Deploy new code
   - Run migrations
   - Start services
   - **Deliverable:** Production environment running

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Verify all endpoints working
   - Check database integrity
   - Monitor error logs
   - Run health checks
   - **Gate:** All endpoints respond, no critical errors, services healthy

3. **Fixes if needed** (0.5h)
   - Address any deployment issues
   - Rollback if critical issues
   - Debug and reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Production deployment complete
   - Monitor for 1 hour post-deployment

---

#### Task P01-027: Customer Onboarding Materials
**Effort:** 4 hours
**Method:** test-later (content creation)

**Workflow:**

1. **Implementation** (2h)
   - Create Getting Started Guide
   - Generate API Documentation
   - Create Regulatory Compliance Guide
   - Create Case Study Template
   - **Deliverable:** Four documentation files

2. **QA Audit** (1h) - `tdd-workflows:code-reviewer`
   - Review clarity and accuracy
   - Verify API docs match implementation
   - Check compliance guide is customer-ready
   - **Gate:** Documentation clear, accurate, customer-ready

3. **Fixes if needed** (1h)
   - Improve clarity where needed
   - Fix inaccuracies
   - Add missing examples
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Documentation ready for distribution

---

#### Task P01-028: Early Adopter Outreach
**Effort:** 3 hours
**Method:** test-later (go-to-market execution)

**Workflow:**

1. **Implementation** (1.5h)
   - Identify 15-20 target customers
   - Create outreach list with decision-makers
   - Draft personalized pitches
   - Create pilot program terms
   - **Deliverable:** Outreach list + pilot agreement

2. **QA Audit** (0.5h) - `tdd-workflows:code-reviewer`
   - Review target list quality
   - Verify pilot terms clear
   - Check messaging compelling
   - **Gate:** List qualified, terms clear, messaging ready

3. **Fixes if needed** (0.5h)
   - Refine target list
   - Improve messaging
   - Clarify pilot terms
   - Reaudit
   - **Loop until gates met**

4. **Commit** (0.5h)
   - Outreach materials ready
   - Begin customer acquisition

---

## Section 2: Agent Assignments Summary

| Agent | Responsible Tasks | When Used |
|-------|-------------------|-----------|
| **`tdd-workflows:tdd-orchestrator`** | P01-003, P01-004, P01-005, P01-006, P01-015, P01-018, P01-019, P01-021, P01-023 | Full TDD + Hybrid (core business logic) |
| **`tdd-workflows:code-reviewer`** | QA Audit phase for ALL tasks | Every task after implementation |
| **`python-development:fastapi-pro`** | P01-009, P01-010, P01-011, P01-012, P01-013, P01-016, P01-014 | API, service, and endpoint work |
| **`data-engineering:data-engineer`** | P01-002, P01-007 | Database migrations and persistence |
| **`unit-testing:debugger`** | Fixes & debug phase for failing tests | When test failures occur |
| **No specific agent** | P01-001, P01-008, P01-017, P01-025, P01-026, P01-027, P01-028 | test-later tasks (design, config, docs) |

---

## Section 3: Quality Gates by Phase

### Phase 1: Implementation Quality Gates
**Agent:** Implementation-specific
**Acceptance Criteria:**
- Code follows SOLID principles
- High cohesion, low coupling maintained
- Domain-driven design patterns used
- All required functionality present
- Error handling comprehensive

### Phase 2: Code Review Quality Gates
**Agent:** `tdd-workflows:code-reviewer`
**Acceptance Criteria:**
- No hardcoded secrets or credentials
- No SQL injection vulnerabilities
- No XSS vulnerabilities
- Proper input validation
- Audit trails logged where needed
- Documentation complete
- Architecture follows DDD principles
- Composability maintained

### Phase 3: Test Execution Quality Gates
**Agent:** `unit-testing:debugger` (on failures)
**Acceptance Criteria:**
- All unit tests pass
- All integration tests pass
- Code coverage >90%
- Performance benchmarks met
- Edge cases covered
- Error scenarios handled

### Phase 4: Deployment Quality Gates
**Agent:** `tdd-workflows:code-reviewer`
**Acceptance Criteria:**
- All migrations run successfully
- No data loss or corruption
- Services start without errors
- All endpoints respond correctly
- Tenant isolation enforced
- No critical security issues
- Monitoring configured

---

## Section 4: Parallelization Strategy

### Can Run in Parallel

**GROUP 1 (Foundation):**
- P01-001 (Schema) — 4h
- P01-008 (Config) — 2h
- **Parallel time: 4h** (both start together)

**GROUP 3 (Core Services):**
- P01-004 (Labeling) — 6h
- P01-005 (Kappa) — 4h
- P01-009 (AI Service) — 3h
- **Parallel time: 6h** (longest task determines)

**GROUP 4 (Orchestration):**
- P01-006 (Flow) — 5h
- P01-007 (Save) — 3h
- P01-010 (Tracking) — 3h
- **Parallel time: 5h**

**GROUP 5 (API):**
- P01-011 (Contracts) — 2h
- P01-012 (Status) — 2h
- P01-013 (Download) — 3h
- **Parallel time: 3h**

**GROUP 6 (Reporting):**
- P01-015 (Reports) — 5h
- P01-016 (Regulatory) — 2h
- P01-014 (Label Studio) — SKIP for MVP
- **Parallel time: 5h**

**GROUP 7 (Testing):**
- P01-018 (Unit Tests) — 6h
- P01-019 (Integration) — 5h
- **Parallel time: 6h**

**Total Parallel Execution Time:**
- Foundation: 4h
- Groups 2-7: ~26h (as each group completes, next starts)
- **Total: ~30h** (vs 65-70h sequential)
- **Savings: 57% time reduction**

---

## Section 5: Execution Timeline

### Recommended Schedule

**Day 1-2: Foundation (GROUP 1)**
- P01-001 + P01-008 in parallel
- Time: 6h actual (4h + 2h parallel)

**Day 2-3: Infrastructure (GROUP 2)**
- P01-002 + P01-003 (sequential, P01-002 first)
- Time: 7h actual (3h + 4h sequential)

**Day 3-5: Core Services (GROUP 3)**
- P01-004, P01-005, P01-009 in parallel
- Time: 13h actual (6h longest task + 7h QA/fixes)

**Day 5-6: Orchestration (GROUP 4)**
- P01-006, P01-007, P01-010 in parallel
- Time: 11h actual

**Day 6-7: API Layer (GROUP 5)**
- P01-011, P01-012, P01-013 in parallel
- Time: 7h actual

**Day 7-8: Reporting (GROUP 6)**
- P01-015, P01-016 in parallel
- P01-014 skipped for MVP
- Time: 7h actual

**Day 8-9: Testing (GROUP 7)**
- P01-018, P01-019 in parallel
- Time: 15h actual (includes debugging)

**Day 9: Test Infrastructure (GROUP 8)**
- P01-021
- Time: 4h

**Day 10-11: Staging (GROUP 9)**
- P01-022, P01-023, P01-024 sequential
- Time: 11h actual

**Day 11-12: Production (GROUP 10)**
- P01-025, P01-026, P01-027, P01-028 sequential
- Time: 11h actual

**Total Wall-Clock Time: ~12 calendar days (at 8h/day)**

---

## Section 6: Architectural Principles Guide

### SOLID Principles
- **S** (Single Responsibility): Each class/function has one job
  - AMLTransactionLabel handles label data
  - CohenKappaCalculator handles agreement calculation
  - AuditReportGenerator handles report generation

- **O** (Open/Closed): Open for extension, closed for modification
  - AIService can be extended with new aml_completion() without changing existing completion()
  - ORM models can be extended with new validators

- **L** (Liskov Substitution): Subtypes can replace base types
  - AMLTransactionLabel must be fully substitutable where DataRecord was
  - All model types must implement audit_ready() consistently

- **I** (Interface Segregation): Clients shouldn't depend on unused interfaces
  - JobTrackingService only needs methods for AML jobs
  - AIService only exposes needed completion methods

- **D** (Dependency Inversion): Depend on abstractions, not concretions
  - Tasks depend on abstract AIService interface
  - Not directly on OpenAI API client

### Encapsulation & Information Hiding
- Hide internal implementation details (e.g., Cohen's Kappa calculation algorithm)
- Expose only necessary public methods
- Use private/protected methods for helpers
- Validate inputs at boundaries

### Domain-Driven Design (DDD)
- **Bounded Context:** AML Service is distinct context with own language/models
- **Entities:** AMLTransactionLabel (has identity across transactions)
- **Value Objects:** AMLRiskLevel, AMLTypology, RegulatoryFlag (immutable)
- **Aggregates:** Job containing multiple Labels (transactional boundary)
- **Repository:** JobRepository handles persistence concerns

### Composability
- Each task independently composable in Prefect flows
- Services can be composed (JobTrackingService uses AIService)
- Models compose into aggregate roots

### Separation of Concerns (SoC)
- **Labeling concern:** Handled by apply_aml_labeling + AIService
- **Agreement concern:** Handled by CohenKappaCalculator
- **Persistence concern:** Handled by save_aml_labels_to_database + ORM
- **Reporting concern:** Handled by AuditReportGenerator

### High Cohesion, Low Coupling
- **High Cohesion:** Related methods grouped in single class
- **Low Coupling:** Services don't import each other; depend on interfaces

### Pragmatic Adaptation
- Use what works from Phase 2 (API routing, job worker, etc.)
- Only rewrite what needs AML-specific logic
- Don't over-engineer for hypothetical futures

### Flexible Modularization
- Configuration drives behavior (no hardcoded values)
- ORM models extensible for new fields
- Services injectable and mockable for testing

---

## Section 7: Critical Success Factors

### Must Succeed
1. ✅ **P01-004 (AML Labeling)** — Core business logic
   - If fails: Entire service non-functional
   - Quality gate: FATF-aligned labels

2. ✅ **P01-005 (Cohen's Kappa)** — Quality assurance
   - If fails: Can't determine when expert review needed
   - Quality gate: Correct agreement calculation

3. ✅ **P01-013 (Results Download)** — Customer deliverable
   - If fails: Test harness shows "0 records"
   - Quality gate: >0 records downloaded

4. ✅ **P01-015 (Audit Reports)** — Regulatory defensibility
   - If fails: Can't sell to compliance-sensitive customers
   - Quality gate: Report includes all sections

5. ✅ **P01-023 (Staging Tests)** — Production readiness
   - If fails: Production deployment blocked
   - Quality gate: All tests pass on staging

---

## Section 8: Risk Mitigation

### Risk: AI Service Produces Invalid Labels
**Mitigation:** P01-004 includes robust response validation + P01-018 has test cases for invalid responses

### Risk: Database Performance Degrades
**Mitigation:** P01-007 includes batch insert + P01-019 validates 10k transaction performance

### Risk: Tenant Isolation Broken
**Mitigation:** P01-023 tests cross-tenant data visibility

### Risk: Deployment Breaks Production
**Mitigation:** P01-025 includes rollback procedures, P01-026 monitors post-deployment

---

## Section 9: Success Metrics

| Metric | Target | Validated By |
|--------|--------|--------------|
| Unit test coverage | >90% | P01-018 |
| Integration tests | All pass | P01-019, P01-023 |
| Results download | >0 records | P01-021 (test harness) |
| Audit reports | Generated | P01-015, P01-023 |
| Deployment success | No rollback needed | P01-026 |
| Customer onboarding | Materials ready | P01-027 |
| Early adopter pipeline | 3-5 signed up | P01-028 |

---

## Section 10: Post-Execution Checklist

After completing all 28 subtasks:

- ✅ All 28 tasks committed to main branch
- ✅ All 28 tasks pass QA audit
- ✅ All tests pass on production
- ✅ Security review passed
- ✅ Production deployment successful
- ✅ Customer onboarding materials delivered
- ✅ 3-5 early adopters signed up for pilot

---

**Document Version:** 1.0
**Created:** December 29, 2025
**Status:** Ready for Execution
**Last Updated:** December 29, 2025
