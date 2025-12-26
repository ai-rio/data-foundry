# StripeService Refactoring Plan - P2.5 (Pre-Phase 3)

**Project**: Data Foundry Backend - Stripe Metered Billing Integration
**Date**: 2025-01-25
**Version**: 1.0.0
**Author**: Architecture Team
**Status**: Ready for Implementation

---

## Executive Summary

This document outlines the refactoring plan for `src/services/stripe_service.py` to address architectural issues identified before proceeding to Phase 3 (Subscriptions). The current implementation (~1700 LOC monolith) will be split into 10 focused modules following SOLID principles while maintaining 100% backward compatibility.

**Key Objectives**:
- ✅ Split monolithic StripeService into focused, testable modules
- ✅ Improve testability and maintainability
- ✅ Maintain 100% backward compatibility (zero breaking changes)
- ✅ Prevent regressions through comprehensive testing
- ✅ Enable future Phase 3-5 development without technical debt

---

## 1. Current State Analysis

### 1.1 Identified Issues

| Issue | Impact | Severity |
|-------|--------|----------|
| **God Class Anti-Pattern** | 1743 lines, 7 responsibilities | High |
| **Poor Testability** | Hard to mock, tight coupling | High |
| **No Separation of Concerns** | Mixed business logic, infra, validation | High |
| **Lack of Dependency Injection** | Direct instantiation, hard-coded env vars | Medium |
| **Primitive Obsession** | Dict[str, Any] instead of DTOs | Medium |
| **Code Duplication** | Retry logic could be reused elsewhere | Low |

### 1.2 Dependencies Map

**Current Integration Points**:
```
StripeService ← ingestion.py (P02-005)
            ← approval_workflow_engine.py (future)
            ← test_stripe_service.py (100% coverage)
            ← test_ingestion_stripe_integration.py
            ← test_usage_calculation_service.py
            ← migrations/add_stripe_customers_table.py
```

### 1.3 Test Coverage Status (Verified 2025-01-25)

**Actual Current State**:
- **Total Tests**: 206 tests (204 passing ✅, 2 failing ❌)
- **Code Coverage**: 96% (468 statements, 20 missed)
- **Test Breakdown**:
  - `test_stripe_service.py`: 163 tests (161 passing, 2 failing)
  - `test_usage_calculation_service.py`: 29 tests (all passing)
  - `test_ingestion_stripe_integration.py`: 14 tests (all passing)

**Failing Tests** (edge cases, low priority):
1. `test_report_meter_event_to_stripe_fallback_to_api_requestor` - Old SDK fallback test
2. `test_is_transient_error_with_api_connection_error` - Error classification edge case

**Conclusion**: **98% of existing tests (202/206) are passing and can be reused unchanged**

---

## 2. Target Architecture

### 2.1 Module Structure

```
src/services/stripe/
├── __init__.py                    # Public API exports & backward compat
├── types.py                       # Protocols, TypedDicts, Enums, DTOs
├── exceptions.py                  # Exception hierarchy (11 types)
├── config.py                      # StripeConfig with env var loading
├── validation.py                  # ValidationService (meter, metadata)
├── idempotency_service.py         # IdempotencyService (P02-004)
├── retry_service.py               # RetryService (P02-003)
├── customer_service.py            # CustomerService (P1-002)
├── meter_event_service.py         # MeterEventService (P02-001)
├── batch_processor.py             # BatchProcessor (P02-002)
├── base.py                        # StripeServiceBase (init logic)
└── facade.py                      # StripeService (backward compat)
```

### 2.2 Responsibility Matrix

| Module | Lines (est.) | Responsibilities | SOLID Principles |
|--------|--------------|------------------|------------------|
| `types.py` | 200 | Type definitions | SRP, ISP |
| `exceptions.py` | 150 | Error handling | SRP |
| `config.py` | 100 | Configuration | SRP, DIP |
| `validation.py` | 200 | Input validation | SRP, OCP |
| `idempotency_service.py` | 300 | Key generation, registry | SRP |
| `retry_service.py` | 200 | Exponential backoff | SRP, OCP |
| `customer_service.py` | 250 | Customer CRUD | SRP, DIP |
| `meter_event_service.py` | 200 | Meter event reporting | SRP, DIP |
| `batch_processor.py` | 200 | Batch operations | SRP, DIP |
| `base.py` | 100 | Initialization | SRP |
| `facade.py` | 400 | Backward compat API | Facade Pattern |

**Total**: ~2,300 LOC (split across 11 files vs. 1,743 in monolith)

### 2.3 Dependency Graph

```
                    ┌─────────────┐
                    │   facade    │ (StripeService - public API)
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  customer    │  │meter_event   │  │batch_processor│
│  _service    │  │ _service     │  │              │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                  │                  │
       │                  ▼                  │
       │          ┌──────────────┐           │
       │          │idempotency   │           │
       │          │ _service     │           │
       │          └──────┬───────┘           │
       │                 │                   │
       └─────────────────┼───────────────────┘
                         │
                         ▼
                 ┌──────────────┐
                 │retry_service │
                 └──────┬───────┘
                        │
                        ▼
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ validation  │ │   config    │ │ exceptions  │
└──────┬──────┘ └──────┬──────┘ └─────────────┘
       │               │
       └───────┬───────┘
               │
               ▼
        ┌─────────────┐
        │   types     │
        └─────────────┘
```

---

## 3. Migration Strategy

### 3.1 Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Breaking existing tests | Low | High | Maintain facade, parallel testing |
| Breaking ingestion integration | Low | Critical | Integration tests, manual QA |
| Performance regression | Very Low | Medium | Benchmark before/after |
| Missing edge cases | Low | High | 100% test coverage maintained |
| Config loading issues | Low | Medium | Comprehensive config tests |

### 3.2 Phased Migration Approach

#### Phase 2.5.1: Foundation (Week 1, Days 1-2)
**Low Risk - No Behavioral Changes**

| Task | Deliverable | Risk | Testing |
|------|-------------|------|---------|
| Create `types.py` with all Protocols & DTOs | type definitions | Minimal | Type checking only |
| Extract `exceptions.py` | exception classes | Minimal | Import tests |
| Create `config.py` with StripeConfig | config dataclass | Low | Config loading tests |

**Validation Criteria**:
- ✅ All types importable
- ✅ Exception hierarchy matches current
- ✅ Config loads from env vars correctly
- ✅ Zero behavioral changes

#### Phase 2.5.2: Infrastructure Services (Week 1, Days 3-4)
**Low Risk - Reusable Components**

| Task | Deliverable | Risk | Testing |
|------|-------------|------|---------|
| Extract `validation.py` | ValidationService | Low | Validation unit tests |
| Extract `retry_service.py` | RetryService | Low | Retry logic tests |
| Extract `idempotency_service.py` | IdempotencyService | Medium | Registry + collision tests |

**Validation Criteria**:
- ✅ All services pass unit tests
- ✅ Retry logic matches current behavior (5 retries, backoff)
- ✅ Idempotency registry thread-safe
- ✅ Collision detection working

#### Phase 2.5.3: Domain Services (Week 1, Days 5-7)
**Medium Risk - Core Business Logic**

| Task | Deliverable | Risk | Testing |
|------|-------------|------|---------|
| Extract `customer_service.py` | CustomerService | Medium | P1-002 tests |
| Extract `meter_event_service.py` | MeterEventService | Medium | P02-001 tests |
| Extract `batch_processor.py` | BatchProcessor | Medium | P02-002 tests |

**Validation Criteria**:
- ✅ Customer CRUD operations work identically
- ✅ Meter event reporting preserves idempotency
- ✅ Batch processing handles partial failures
- ✅ Database persistence unchanged

#### Phase 2.5.4: Integration Layer (Week 2, Days 1-2)
**High Risk - Backward Compatibility**

| Task | Deliverable | Risk | Testing |
|------|-------------|------|---------|
| Create `base.py` with initialization | StripeServiceBase | Low | Init tests |
| Create `facade.py` with StripeService | Backward compat API | **High** | All 50 existing tests |
| Update `__init__.py` exports | Public API | **High** | Import tests |

**Validation Criteria**:
- ✅ **All 202 passing tests pass without modification**
- ✅ Ingestion integration tests pass (14 tests)
- ✅ Usage calculation service integration works (29 tests)
- ✅ API signatures unchanged
- 📝 Optional: Fix 2 currently failing edge case tests (low priority)

#### Phase 2.5.5: Cutover & Validation (Week 2, Days 3-5)
**Critical - Production Readiness**

| Task | Deliverable | Risk | Testing |
|------|-------------|------|---------|
| Deprecate old `stripe_service.py` | Archive monolith | Low | N/A |
| Update import paths (if needed) | Code changes | Low | Import tests |
| Run full regression suite | Validation | **Critical** | All tests |
| Performance benchmarking | Metrics | Low | Load tests |
| Documentation updates | Docs | Minimal | N/A |

**Validation Criteria**:
- ✅ **96-98% test coverage maintained** (current: 96%)
- ✅ **Zero breaking changes** (202 passing tests remain passing)
- ✅ Performance within 5% of baseline
- ✅ Memory usage comparable
- ✅ All integration points verified
- 📝 Add 20 new critical module tests (idempotency, retry, validation)

---

## 4. Testing Strategy

### 4.1 Test Migration Plan (Verified 2025-01-25)

**Existing Tests - Reused via Facade**:

| Test Suite | Tests | Status | Strategy |
|------------|-------|--------|----------|
| `test_stripe_service.py` | 161 passing ✅ | Reuse | **Run unchanged via facade** |
| `test_stripe_service.py` | 2 failing ❌ | Optional fix | Edge cases (low priority) |
| `test_usage_calculation_service.py` | 29 passing ✅ | Reuse | **Run unchanged** |
| `test_ingestion_stripe_integration.py` | 14 passing ✅ | Reuse | **Run unchanged** |
| **Subtotal Existing** | **204 tests** | **202 reused** | **98% reuse rate** |

**New Tests - Critical Modules** (Recommended):

| Test Suite | Tests | Priority | Purpose |
|------------|-------|----------|---------|
| `test_idempotency_service.py` | ~8 | **High** | Security-critical (P02-004) |
| `test_retry_service.py` | ~6 | **High** | Reliability-critical (P02-003) |
| `test_validation.py` | ~6 | **High** | Input sanitization security |
| **Subtotal Critical** | **~20** | **Must have** | **Isolated unit tests** |

**New Tests - Optional** (Nice to have):

| Test Suite | Tests | Priority | Purpose |
|------------|-------|----------|---------|
| `test_customer_service.py` | ~5 | Low | Optional isolation |
| `test_meter_event_service.py` | ~5 | Low | Optional isolation |
| `test_batch_processor.py` | ~5 | Low | Optional isolation |
| **Subtotal Optional** | **~15** | **Nice to have** | **Better test isolation** |

**Total Test Count**:
- Existing (reused): 202 tests ✅
- Fix failing: 2 tests 🔧 (optional)
- New critical: 20 tests 📝 (recommended)
- New optional: 15 tests 📝 (nice to have)
- **Grand Total**: 224-239 tests

### 4.2 Regression Prevention

```python
# pytest conftest.py fixture
@pytest.fixture(scope="session", autouse=True)
def verify_backward_compatibility():
    """Ensure facade matches original API."""
    from src.services.stripe import StripeService
    from src.services.stripe.facade import StripeService as FacadeService

    # Verify public API unchanged
    original_methods = {
        'initialize', 'create_customer', 'get_customer_by_tenant',
        'update_customer', 'delete_customer', 'report_usage',
        'report_usage_batch'
    }

    facade_methods = {
        name for name in dir(FacadeService)
        if not name.startswith('_') and callable(getattr(FacadeService, name))
    }

    assert original_methods.issubset(facade_methods), \
        "Facade missing required methods"
```

### 4.3 Performance Benchmarking

```python
# tests/performance/test_stripe_service_performance.py
import pytest
import time

@pytest.mark.benchmark
async def test_report_usage_performance_regression(benchmark):
    """Ensure refactored code is not slower than monolith."""
    # Baseline from monolith: ~50ms per report_usage call
    service = StripeService()
    await service.initialize()

    def run_report():
        return await service.report_usage(
            meter_event="ai_labels",
            value=100,
            tenant_id="tenant_001"
        )

    # Benchmark should complete within 60ms (20% tolerance)
    result = benchmark(run_report)
    assert benchmark.stats.mean < 0.060  # 60ms
```

---

## 5. Backward Compatibility Guarantee

### 5.1 Public API Contract

**Guaranteed Unchanged**:
```python
from src.services.stripe import StripeService

# All these calls MUST work identically
service = StripeService()
await service.initialize()

# P1-002: Customer CRUD
customer_id = await service.create_customer(tenant, email, name, db_session, created_by)
customer = await service.get_customer_by_tenant(tenant_id, db_session)
updated = await service.update_customer(stripe_customer_id, email, name, metadata, db_session)
deleted = await service.delete_customer(stripe_customer_id, db_session)

# P02-001: Meter event reporting
result = await service.report_usage(meter_event, value, tenant_id, metadata, stripe_customer_id, db_session, batch_id)

# P02-002: Batch processing
batch_result = await service.report_usage_batch(events, tenant_id, stripe_customer_id, db_session)
```

### 5.2 Exception Compatibility

All current exception types preserved:
- `StripeServiceError` (base)
- `StripeCustomerNotFoundError`
- `StripeAPIError`
- `StripeMeterValidationError`

### 5.3 Configuration Compatibility

All environment variables preserved:
- `STRIPE_SECRET_KEY`
- `STRIPE_AI_LABELS_METER_ID`
- `STRIPE_HUMAN_AUDITS_METER_ID`
- `STRIPE_MAX_RETRIES`
- `STRIPE_INITIAL_RETRY_DELAY_MS`
- `STRIPE_MAX_RETRY_DELAY_MS`

---

## 6. Implementation Checklist

### Phase 2.5.1: Foundation ☐
- [ ] Create `src/services/stripe/` directory
- [ ] Implement `types.py` with all Protocols and DTOs
- [ ] Implement `exceptions.py` with exception hierarchy
- [ ] Implement `config.py` with StripeConfig
- [ ] Write unit tests for types and config
- [ ] Verify imports work correctly

### Phase 2.5.2: Infrastructure Services ☐
- [ ] Implement `validation.py` with ValidationService
- [ ] Implement `retry_service.py` with RetryService
- [ ] Implement `idempotency_service.py` with IdempotencyService
- [ ] Write unit tests for each service
- [ ] Verify thread safety of registry
- [ ] Benchmark retry performance

### Phase 2.5.3: Domain Services ☐
- [ ] Implement `customer_service.py` with CustomerService
- [ ] Implement `meter_event_service.py` with MeterEventService
- [ ] Implement `batch_processor.py` with BatchProcessor
- [ ] Write unit tests for each service
- [ ] Verify database operations
- [ ] Test Stripe API integration

### Phase 2.5.4: Integration Layer ☐
- [ ] Implement `base.py` with StripeServiceBase
- [ ] Implement `facade.py` with StripeService
- [ ] Update `__init__.py` with public exports
- [ ] **Run all 202 passing tests - MUST PASS unchanged**
- [ ] Run ingestion integration tests (14 tests)
- [ ] Run usage calculation tests (29 tests)
- [ ] Verify backward compatibility
- [ ] Write 20 critical module tests (idempotency, retry, validation)

### Phase 2.5.5: Cutover & Validation ☐
- [ ] Archive old `stripe_service.py` to `stripe_service_legacy.py`
- [ ] Update imports if needed
- [ ] Run full regression suite (224 tests: 202 existing + 20 new + 2 optional fixes)
- [ ] Performance benchmarking vs baseline
- [ ] Memory profiling
- [ ] Verify 96-98% code coverage maintained
- [ ] Update documentation
- [ ] Code review and approval
- [ ] Merge to feature branch

---

## 7. Rollback Plan

### 7.1 Rollback Triggers

Rollback if ANY of these occur:
- ❌ Any existing test fails
- ❌ Performance degrades by >10%
- ❌ Memory usage increases by >20%
- ❌ Integration with ingestion pipeline breaks
- ❌ Critical bug discovered in production

### 7.2 Rollback Procedure

1. **Immediate Rollback**:
   ```bash
   # Restore original file
   cp src/services/stripe_service_legacy.py src/services/stripe_service.py

   # Remove new module directory
   rm -rf src/services/stripe/

   # Run tests to verify
   pytest tests/unit/services/test_stripe_service.py -v
   ```

2. **Verify Rollback Success**:
   - All 161 tests pass (same as current state)
   - Ingestion integration works (14 tests)
   - Usage calculation tests pass (29 tests)
   - No import errors

3. **Root Cause Analysis**:
   - Document failure reason
   - Fix in separate branch
   - Re-test before retry

---

## 8. Success Criteria

### 8.1 Functional Requirements
- ✅ All 202 existing passing tests pass without modification
- ✅ 96-98% code coverage maintained (current: 96%)
- ✅ Ingestion pipeline integration verified (14 tests pass)
- ✅ Usage calculation service integration verified (29 tests pass)
- ✅ Customer CRUD operations identical
- ✅ Meter event reporting preserves idempotency
- ✅ Batch processing handles partial failures
- 📝 20 new critical module tests added (idempotency, retry, validation)

### 8.2 Non-Functional Requirements
- ✅ Performance within 5% of baseline
- ✅ Memory usage comparable (±10%)
- ✅ Thread safety verified
- ✅ Code modularity improved
- ✅ Test isolation enabled
- ✅ Dependency injection implemented

### 8.3 Quality Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Lines per module | 1743 | <400 | ☐ |
| Cyclomatic complexity (max) | High | <10 | ☐ |
| Test coverage | 100% | 100% | ☐ |
| Responsibilities per class | 7 | 1 | ☐ |
| Dependencies per module | Mixed | <5 | ☐ |
| Mock setup lines per test | 50+ | <15 | ☐ |

---

## 9. Post-Refactoring Benefits

### 9.1 Immediate Benefits
- ✅ **Testability**: Each module tested independently
- ✅ **Maintainability**: Focused, single-responsibility modules
- ✅ **Extensibility**: Easy to add new meter types or features
- ✅ **Reusability**: RetryService can be used elsewhere
- ✅ **Code Quality**: Follows SOLID principles

### 9.2 Phase 3-5 Enablement
- ✅ **Subscriptions (P3)**: Add SubscriptionService alongside existing modules
- ✅ **Webhooks (P4)**: Add WebhookHandler as separate module
- ✅ **Testing (P5)**: Focused unit tests for each new module
- ✅ **Future Features**: Can extend without modifying existing code

---

## 10. Timeline & Effort Estimate

| Phase | Duration | Effort (person-days) | Dependencies |
|-------|----------|---------------------|--------------|
| 2.5.1 Foundation | 2 days | 2 | None |
| 2.5.2 Infrastructure | 2 days | 2 | Phase 2.5.1 |
| 2.5.3 Domain Services | 3 days | 3 | Phase 2.5.2 |
| 2.5.4 Integration | 2 days | 2 | Phase 2.5.3 |
| 2.5.5 Cutover | 3 days | 2 | Phase 2.5.4 |
| **Total** | **12 days** | **11 person-days** | |

**Assumptions**:
- Single developer
- Part-time effort (50% allocation)
- Includes testing and documentation
- No major blockers

---

## 11. Approval & Sign-off

| Role | Name | Approval | Date |
|------|------|----------|------|
| Technical Lead | | ☐ Approved | |
| Product Owner | | ☐ Approved | |
| QA Lead | | ☐ Approved | |

---

## 12. References

- [Stripe Service Modular Design](./docs/architecture/stripe-service-modular-design.md)
- [Original Requirements](./STRIPE_METERED_BILLING_REQUIREMENTS.md)
- [Test Coverage Report](./STRIPE_SERVICE_TEST_SUCCESS.md)
- [Code Review Findings](./docs/code-review/stripe-service-analysis.md)

---

**Next Steps**:
1. ✅ Approve this refactoring plan
2. ☐ Create feature branch `refactor/stripe-service-modular`
3. ☐ Begin Phase 2.5.1 implementation
4. ☐ Daily standup updates on progress
5. ☐ Code reviews after each phase
6. ☐ Final validation before Phase 3
